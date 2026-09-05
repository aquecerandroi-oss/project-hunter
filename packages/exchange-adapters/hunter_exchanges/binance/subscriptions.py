"""Incremental subscription diffs for Binance's combined-stream connections.

Planning (pure, no IO) lives in :mod:`~hunter_exchanges.binance.subscription_plan`
— :func:`~hunter_exchanges.binance.subscription_plan.plan_updates` computes
*what* to send; :class:`SubscriptionController` below owns the IO (sending
frames, ack bookkeeping, F6 restart-on-failure) and is a thin loop over its
output. ``docs/plans/M1.md`` T1.2b ("quem fica não é reassinado"): symbols
that stay are never resubscribed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

from hunter_core.logging import get_logger
from hunter_exchanges.base import ConnectionState, StreamChannel
from hunter_exchanges.binance.streams import split_channels_by_route
from hunter_exchanges.binance.subscription_plan import (
    SubscriptionPlan,
    SymbolGroup,
    assert_stream_budget,
    control_frame,
    is_control_ack,
    names_for,
    plan_updates,
)

logger = get_logger(__name__)


class _Sendable(Protocol):
    async def send(self, message: str) -> None: ...


class SubscriptionController:
    """Owns per-connection symbol groups, live sockets, and pending JSON-RPC
    acks for a :class:`~hunter_exchanges.binance.ws.BinanceWsClient` — kept
    separate so ``ws.py`` stays about connection lifecycle, not bookkeeping.

    ``start`` opens a new connection/task for a brand new
    :class:`SymbolGroup`; ``restart`` (F6/F8) restarts one *existing*
    connection's task in place (``BinanceWsClient.restart_connection``) —
    this class never touches ``asyncio.Task`` itself either way.
    """

    #: F6: how long a SUBSCRIBE may sit un-ACKed before it's an error ACK.
    DEFAULT_ACK_TIMEOUT_S = 5.0

    def __init__(
        self,
        start: Callable[[SymbolGroup], None],
        *,
        restart: Callable[[str], Awaitable[None]] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        ack_timeout_s: float = DEFAULT_ACK_TIMEOUT_S,
    ) -> None:
        self._start = start
        self._restart = restart
        self._sleep = sleep
        self._ack_timeout_s = ack_timeout_s
        self.groups: dict[str, SymbolGroup] = {}
        self.live_ws: dict[str, _Sendable] = {}
        # (key, method, names) — names feeds F6's drop-and-restart.
        self.pending_acks: dict[int, tuple[str, str, tuple[str, ...]]] = {}
        self._rpc_id = 0
        # F6: referenced so asyncio never GCs an in-flight ack-deadline task.
        self._ack_deadline_tasks: list[asyncio.Task[None]] = []
        # Serializes update() against catch_up() (and each other): both read
        # then mutate a group's symbols across an ``await``, so letting them
        # interleave can compute a diff against already-stale membership
        # (Astra review, T1.2b resume round 3, finding 1).
        self._lock = asyncio.Lock()

    def reset(self) -> None:
        for task in self._ack_deadline_tasks:
            task.cancel()
        self._ack_deadline_tasks.clear()
        self.groups.clear()
        self.live_ws.clear()
        self.pending_acks.clear()

    async def wait_for_pending_acks(self) -> None:
        """Test seam: block until every scheduled ack-deadline task has run."""
        tasks, self._ack_deadline_tasks = self._ack_deadline_tasks, []
        for task in tasks:
            await task

    def next_index(self, route: str) -> int:
        indices = [int(k.split(":")[1]) for k, g in self.groups.items() if g.route == route]
        return max(indices, default=-1) + 1

    def add_group(self, group: SymbolGroup) -> None:
        # F12: the one choke point every new connection (initial stream()
        # call and universe-diff overflow alike) goes through.
        assert_stream_budget(group)
        self.groups[group.key] = group
        self._start(group)

    async def update(
        self,
        added: Sequence[str],
        removed: Sequence[str],
        channels: Sequence[StreamChannel],
        states: dict[str, ConnectionState],
    ) -> None:
        """Apply an incremental universe diff without touching unaffected symbols."""
        async with self._lock:
            for route, route_channels in split_channels_by_route(channels).items():
                next_index = self.next_index(route)
                plan = plan_updates(self.groups, route, route_channels, added, removed, next_index)
                for key, names in plan.unsubscribe.items():
                    # Report the diff on `states[key].subscriptions` only
                    # once it actually reached the socket (Astra review,
                    # T1.2b resume finding 3) — the group's own bookkeeping
                    # has the new set regardless, so the next connect/
                    # reconnect self-heals `subscriptions`.
                    if await self._send_control_safe(key, "UNSUBSCRIBE", names, states):
                        states[key].subscriptions = tuple(
                            n for n in states[key].subscriptions if n not in names
                        )
                for key, names in plan.subscribe.items():
                    if await self._send_control_safe(key, "SUBSCRIBE", names, states):
                        states[key].subscriptions = (*states[key].subscriptions, *names)
                for group in plan.new_groups:
                    self.add_group(group)

    async def catch_up(
        self, key: str, opened_with: list[str], states: dict[str, ConnectionState]
    ) -> None:
        """Reconcile a newly-live connection against its group's *current*
        symbols, which may have moved (a diff arrived mid-handshake) since
        ``opened_with`` was computed for the URL that opened it (Astra
        review, T1.2b resume round 2, finding 3: otherwise the diff sits
        unsent until this connection's next rotation, up to 23.5h away).
        Locked the same as :meth:`update` — otherwise a concurrent universe
        diff can compute against already-stale membership (Astra review,
        T1.2b resume round 3, finding 1)."""
        async with self._lock:
            group = self.groups[key]
            current = names_for(group.symbols, group.channels)
            to_add = [n for n in current if n not in opened_with]
            to_remove = [n for n in opened_with if n not in current]
            # F5: UNSUBSCRIBE before SUBSCRIBE (update()'s order) — the
            # reverse order can transiently overshoot Binance's 1024-stream
            # limit on a mid-handshake diff (e.g. 800 -> 1200 -> 800).
            if await self.send_control(key, "UNSUBSCRIBE", to_remove, states=states):
                opened_with = [n for n in opened_with if n not in to_remove]
            if await self.send_control(key, "SUBSCRIBE", to_add, states=states):
                opened_with = [*opened_with, *to_add]
            states[key].subscriptions = tuple(opened_with)

    async def send_control(
        self,
        key: str,
        method: str,
        names: list[str],
        *,
        states: dict[str, ConnectionState] | None = None,
    ) -> bool:
        """Send one SUBSCRIBE/UNSUBSCRIBE frame; ``True`` only if it was
        actually written to a live socket (never just "attempted").

        A ``send()`` failure is **not** caught here — it propagates so
        :meth:`catch_up` (inside ``_run_connection``'s own try/except) uses
        the normal reconnect-attempt/backoff machinery; :meth:`update`
        (called directly by the market-worker) wraps this in
        :meth:`_send_control_safe` instead (F6). A successful SUBSCRIBE
        (``states`` given) is watched by a background ack-deadline (F6): an
        ack that never arrives is as dangerous as one that says "no".
        """
        if not names:
            return False
        connection = self.live_ws.get(key)
        if connection is None:
            logger.warning("binance_ws_control_no_connection", key=key, method=method)
            return False
        self._rpc_id += 1
        rpc_id = self._rpc_id
        self.pending_acks[rpc_id] = (key, method, tuple(names))
        try:
            await connection.send(control_frame(method, rpc_id, names))
        except Exception:
            self.pending_acks.pop(rpc_id, None)
            raise
        if method == "SUBSCRIBE" and states is not None:
            self._ack_deadline_tasks = [t for t in self._ack_deadline_tasks if not t.done()]
            self._ack_deadline_tasks.append(
                asyncio.ensure_future(self._ack_deadline(rpc_id, states))
            )
        return True

    async def _send_control_safe(
        self, key: str, method: str, names: list[str], states: dict[str, ConnectionState]
    ) -> bool:
        """:meth:`update`'s wrapper (F6): a ``send()`` failure here must
        never propagate to the market-worker caller — logged and restarted
        instead, the same path a rejected/timed-out ack uses."""
        try:
            return await self.send_control(key, method, names, states=states)
        except Exception as exc:
            logger.warning("binance_ws_control_send_failed", key=key, method=method, error=str(exc))
            await self._restart_connection(key)
            return False

    async def _ack_deadline(self, rpc_id: int, states: dict[str, ConnectionState]) -> None:
        await self._sleep(self._ack_timeout_s)
        pending = self.pending_acks.pop(rpc_id, None)
        if pending is None:
            return  # acked (or already handled) within the deadline
        key, method, names = pending
        logger.warning("binance_ws_control_ack_timeout", key=key, method=method, names=names)
        await self._drop_and_restart(key, names, states)

    async def resolve_ack(
        self, envelope: dict[str, Any], states: dict[str, ConnectionState]
    ) -> None:
        rpc_id = envelope.get("id")
        pending = self.pending_acks.pop(rpc_id, None) if isinstance(rpc_id, int) else None
        if pending is None:
            logger.warning("binance_ws_unexpected_ack", rpc_id=rpc_id)
            return
        error = envelope.get("error")
        key, method, names = pending
        if error is not None:
            logger.warning(
                "binance_ws_control_error_ack", key=key, method=method, error=error, names=names
            )
            if method == "SUBSCRIBE":
                # F6: never leave a rejected SUBSCRIBE reported as active —
                # drop it and restart this connection so it resubscribes
                # from the group's own desired set.
                await self._drop_and_restart(key, names, states)

    async def _drop_and_restart(
        self, key: str, names: tuple[str, ...], states: dict[str, ConnectionState]
    ) -> None:
        if key in states:
            name_set = set(names)
            states[key].subscriptions = tuple(
                n for n in states[key].subscriptions if n not in name_set
            )
        await self._restart_connection(key)

    async def _restart_connection(self, key: str) -> None:
        if self._restart is not None:
            await self._restart(key)


__all__ = [
    "SubscriptionController",
    "SubscriptionPlan",
    "SymbolGroup",
    "control_frame",
    "is_control_ack",
    "names_for",
    "plan_updates",
]
