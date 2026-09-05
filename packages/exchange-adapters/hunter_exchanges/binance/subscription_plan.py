"""Pure planning logic for Binance's combined-stream subscription diffs.

Split out of ``subscriptions.py`` (T1.2/T1.2b fix pass F6/F8/F12) so that
module stays under the 350-line budget: everything here is a pure
function/dataclass, no IO, no ``asyncio`` —
:class:`~hunter_exchanges.binance.subscriptions.SubscriptionController` owns
the IO (sending frames, ack bookkeeping, restart-on-failure) and is a thin
loop over :func:`plan_updates`'s output.

``docs/plans/M1.md`` T1.2b ("stable connection groups", joint decision "quem
fica não é reassinado"): when the monitored universe changes, symbols that
stay are never resubscribed — only the diff (added/removed symbols) travels
as a live ``SUBSCRIBE``/``UNSUBSCRIBE`` JSON-RPC frame over the existing
connection for their route; only overflow beyond every existing group's free
capacity (``MAX_SYMBOLS_PER_CONNECTION``) opens a brand-new one.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hunter_exchanges.base import StreamChannel
from hunter_exchanges.binance.streams import (
    MAX_STREAMS_PER_CONNECTION,
    MAX_SYMBOLS_PER_CONNECTION,
    stream_name,
)


@dataclass
class SymbolGroup:
    """One connection's live symbol set and the channels it carries."""

    key: str
    route: str
    channels: tuple[StreamChannel, ...]
    symbols: list[str] = field(default_factory=list[str])


def control_frame(method: str, rpc_id: int, names: Sequence[str]) -> str:
    """A Binance WebSocket API ``SUBSCRIBE``/``UNSUBSCRIBE`` JSON-RPC request."""
    return json.dumps({"method": method, "params": list(names), "id": rpc_id})


def is_control_ack(envelope: dict[str, Any]) -> bool:
    """A ``SUBSCRIBE``/``UNSUBSCRIBE`` response: has ``id``, never ``stream``.

    A data frame is always ``{"stream": ..., "data": ...}``; a control
    response is ``{"result": null, "id": N}`` — the two shapes never overlap.
    """
    return "id" in envelope and "stream" not in envelope


def names_for(symbols: Sequence[str], channels: Sequence[StreamChannel]) -> list[str]:
    return [stream_name(s, c) for s in symbols for c in channels]


def assert_stream_budget(group: SymbolGroup) -> None:
    """F12: ``MAX_SYMBOLS_PER_CONNECTION`` is only safe paired with today's
    channel counts (200 x 4 market channels = 800) — raise rather than
    silently build a connection over Binance's documented
    ``MAX_STREAMS_PER_CONNECTION`` if that ever stops being true (e.g. a
    5th/6th market channel)."""
    count = len(group.symbols) * len(group.channels)
    if count > MAX_STREAMS_PER_CONNECTION:
        raise ValueError(
            f"group {group.key!r} would carry {count} streams "
            f"({len(group.symbols)} symbols x {len(group.channels)} channels), "
            f"over Binance's {MAX_STREAMS_PER_CONNECTION}-stream connection limit (F12)"
        )


@dataclass
class SubscriptionPlan:
    """What :meth:`BinanceWsClient.update_subscriptions` must do for one route.

    ``unsubscribe``/``subscribe`` map an *existing* group's key to the exact
    stream names to send over its live connection; ``new_groups`` are the
    additional connections needed for symbols that fit no existing group's
    free capacity. Mutates the ``symbols`` list of every affected entry in
    ``groups`` in place, so the caller's own bookkeeping and the plan agree
    without a second pass.
    """

    unsubscribe: dict[str, list[str]]
    subscribe: dict[str, list[str]]
    new_groups: list[SymbolGroup]


def plan_updates(
    groups: dict[str, SymbolGroup],
    route: str,
    route_channels: Sequence[StreamChannel],
    added: Sequence[str],
    removed: Sequence[str],
    next_index: int,
) -> SubscriptionPlan:
    removed_set = set(removed)
    unsubscribe: dict[str, list[str]] = {}
    for key, group in groups.items():
        if group.route != route:
            continue
        hit = [s for s in group.symbols if s in removed_set]
        if not hit:
            continue
        unsubscribe[key] = names_for(hit, route_channels)
        group.symbols = [s for s in group.symbols if s not in removed_set]

    subscribe: dict[str, list[str]] = {}
    new_groups: list[SymbolGroup] = []
    pending = [s for s in added if s not in removed_set]
    route_keys = sorted(
        (k for k, g in groups.items() if g.route == route),
        key=lambda k: int(k.split(":")[1]),
    )
    for key in route_keys:
        if not pending:
            break
        group = groups[key]
        free = MAX_SYMBOLS_PER_CONNECTION - len(group.symbols)
        if free <= 0:
            continue
        take, pending = pending[:free], pending[free:]
        subscribe[key] = names_for(take, route_channels)
        group.symbols.extend(take)
        assert_stream_budget(group)

    index = next_index
    while pending:
        batch, pending = pending[:MAX_SYMBOLS_PER_CONNECTION], pending[MAX_SYMBOLS_PER_CONNECTION:]
        new_group = SymbolGroup(
            key=f"{route}:{index}", route=route, channels=tuple(route_channels), symbols=batch
        )
        assert_stream_budget(new_group)
        new_groups.append(new_group)
        index += 1
    return SubscriptionPlan(unsubscribe=unsubscribe, subscribe=subscribe, new_groups=new_groups)


__all__ = [
    "SubscriptionPlan",
    "SymbolGroup",
    "assert_stream_budget",
    "control_frame",
    "is_control_ack",
    "names_for",
    "plan_updates",
]
