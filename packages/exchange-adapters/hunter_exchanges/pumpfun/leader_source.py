"""The production :class:`LeaderSource` of the copy-trade pilot (H-037): NATS first, the chain confirms.

Two children are merged — the NATS per-wallet channel and the on-chain source — into one stream of
:data:`LeaderItem` (event, confirmation, gap) with these rules:

* **The first trustworthy signal goes out at once.** A NATS event is emitted the instant the child
  yields it (``confirmed=False``, ``source="nats"``); nothing waits for the chain. In parallel the chain
  reads the same signature (``chain.confirm``) and the **LeaderConfirmation** — one of the five states
  ``confirmed`` / ``divergent`` / ``failed_tx`` / ``not_found`` / ``rpc_error`` — is emitted whatever the
  outcome (never silence: a check that could not run says ``rpc_error`` and why). The event is never
  rewritten. ``nats_to_confirm`` times the lag until a ``confirmed`` one.
* **One answer per key**, with a second chance: the on-chain logs path may prove a trade whose
  confirmation had failed (``not_found`` / ``rpc_error``); then the confirmation is asked again once
  (``late_confirmation``). Otherwise the logs path's event for a key already followed by the NATS path is
  a counted duplicate. A trade only the chain saw is emitted as a confirmed ``kind="swap"`` event
  (``chain_only``); a NATS copy arriving after it is dropped.
* **Gaps.** Every child gap is passed through with its own reason (the decision of 06/10: losing the
  NATS path is an explicit, named gap even while the chain still covers it), and, additionally, a
  ``no_coverage:<nats reason>+<chain reason>`` gap while **both** children have lost the wallet (or
  everything), from the moment the second one was lost until either recovers. A one-transaction loss (a
  closed gap that was never announced open) passes through as it is. A crashed child is its own open gap.
* **Nothing pending is forgotten:** a state is only evicted once its confirmation was emitted.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Collection
from datetime import datetime
from typing import Protocol

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.leader_events import (
    LeaderConfirmation,
    LeaderEvent,
    LeaderGap,
    LeaderItem,
    LeaderSource,
)
from hunter_exchanges.pumpfun.leader_source_stats import LeaderSourceStats

logger = get_logger(__name__)

STATES_MAX = 4096

__all__ = ["ChainSide", "CombinedLeaderSource"]

Key = tuple[str, str, str]


class ChainSide(LeaderSource, Protocol):
    async def confirm(self, event: LeaderEvent) -> LeaderConfirmation: ...


class _State:
    __slots__ = ("confirmation", "preview", "retried")

    def __init__(self, preview: LeaderEvent | None) -> None:
        self.preview = preview
        self.confirmation: LeaderConfirmation | None = None
        self.retried = False

    @property
    def settled(self) -> bool:
        return self.preview is None or self.confirmation is not None


class CombinedLeaderSource:
    def __init__(
        self,
        *,
        nats: LeaderSource,
        chain: ChainSide,
        stats: LeaderSourceStats | None = None,
        wall: Callable[[], datetime] = utcnow,
    ) -> None:
        """``stats`` should be the object the children were built with, so one snapshot has the
        receive->emit distribution (NATS child) and the confirmation ones (this class)."""
        self.nats, self.chain, self.wall = nats, chain, wall
        self.stats = stats or LeaderSourceStats()

    def stream(self, wallets: Collection[str]) -> AsyncIterator[LeaderItem]:
        return _Run(self, frozenset(wallets)).run()


class _Run:
    def __init__(self, owner: CombinedLeaderSource, followed: frozenset[str]) -> None:
        self.o, self.followed = owner, followed
        self.queue: asyncio.Queue[LeaderItem] = asyncio.Queue()
        self.states: OrderedDict[Key, _State] = OrderedDict()
        self.inflight: set[asyncio.Task[None]] = set()
        self.books: dict[str, dict[tuple[str | None, str], datetime]] = {"nats": {}, "chain": {}}
        self.announced: dict[str | None, LeaderGap] = {}

    async def run(self) -> AsyncIterator[LeaderItem]:
        if not self.followed:
            raise ValueError("a leader source needs at least one wallet")
        pumps = [
            asyncio.create_task(
                self._pump("nats", self.o.nats.stream(self.followed), self._on_nats)
            ),
            asyncio.create_task(
                self._pump("chain", self.o.chain.stream(self.followed), self._on_chain)
            ),
        ]
        try:
            while True:
                item = await self.queue.get()
                if isinstance(item, LeaderEvent) and item.source == "nats":
                    lag = (self.o.wall() - item.first_seen_at).total_seconds()
                    self.o.stats.first_seen_to_deliver.record(lag)
                yield item
        finally:
            tasks = (*pumps, *self.inflight)
            for task in tasks:
                task.cancel()
            # gather, not a suppressed await: a cancel aimed at THIS task must not be swallowed
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _pump(
        self, side: str, source: AsyncIterator[LeaderItem], handle: Callable[[LeaderEvent], None]
    ) -> None:
        """No await between a child's item and its emission: this loop is the millisecond path."""
        try:
            async for item in source:
                if isinstance(item, LeaderGap):
                    self._on_gap(side, item)
                elif isinstance(item, LeaderEvent):
                    handle(item)
                else:  # a child never emits confirmations of its own: only this class does
                    self.o.stats.count("unexpected_item")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.o.stats.count(f"{side}_crashed")
            logger.error("leader_source_child_crashed", side=side, error=type(exc).__name__)
            self._on_gap(side, LeaderGap(None, self.o.wall(), None, f"{side}_crashed"))
        finally:
            with contextlib.suppress(Exception):
                await source.aclose()  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ events
    def _on_nats(self, event: LeaderEvent) -> None:
        key = (event.wallet, event.signature, event.mint)
        known = self.states.get(key)
        if known is not None:
            self.o.stats.count("nats_after_chain" if known.preview is None else "duplicate_preview")
            return
        state = _State(event)
        self._remember(key, state)
        self.queue.put_nowait(event)  # the first trustworthy signal, before any chain check
        self._spawn_confirm(state)

    def _on_chain(self, event: LeaderEvent) -> None:
        key = (event.wallet, event.signature, event.mint)
        state = self.states.get(key)
        if state is None:
            self._remember(key, _State(None))
            self.o.stats.count("chain_only")
            self.queue.put_nowait(event)
            return
        c = state.confirmation
        if c is not None and c.status in ("not_found", "rpc_error") and not state.retried:
            state.retried = (
                True  # the other road proved the trade: ask the confirmation again, once
            )
            state.confirmation = None
            self.o.stats.count("late_confirmation")
            self._spawn_confirm(state)
        else:
            self.o.stats.count("chain_duplicate")

    def _remember(self, key: Key, state: _State) -> None:
        self.states[key] = state
        while len(self.states) > STATES_MAX:
            oldest = next((k for k, s in self.states.items() if s.settled), None)
            if oldest is None:
                break  # everything left is unresolved: never evict a pending confirmation
            del self.states[oldest]

    def _spawn_confirm(self, state: _State) -> None:
        task = asyncio.ensure_future(self._confirm(state))
        self.inflight.add(task)
        task.add_done_callback(self.inflight.discard)

    async def _confirm(self, state: _State) -> None:
        preview = state.preview
        assert preview is not None
        try:
            result = await self.o.chain.confirm(preview)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("leader_source_confirm_crashed", error=type(exc).__name__)
            result = LeaderConfirmation(
                wallet=preview.wallet,
                mint=preview.mint,
                signature=preview.signature,
                slot=preview.slot,
                status="rpc_error",
                reason="confirm_crashed",
                confirmed_at=self.o.wall(),
                block_time=None,
            )
        state.confirmation = result
        self.o.stats.count(f"confirmation_{result.status}")
        if result.status == "confirmed":
            lag = (result.confirmed_at - preview.first_seen_at).total_seconds()
            self.o.stats.nats_to_confirm.record(lag)
        self.queue.put_nowait(result)

    # ------------------------------------------------------------------ coverage gaps
    def _on_gap(self, side: str, gap: LeaderGap) -> None:
        book, key = self.books[side], (gap.wallet, gap.reason)
        if gap.end is None:
            book[key] = gap.start
        elif key in book:
            del book[key]
        self.queue.put_nowait(gap)  # every child gap is passed through with its own reason
        self._reconcile()

    def _since(self, side: str, wallet: str | None) -> tuple[datetime, str] | None:
        """When ``side`` lost ``wallet`` (or everything), and why — the earliest matching gap."""
        hits = [
            (start, reason)
            for (w, reason), start in self.books[side].items()
            if w is None or w == wallet
        ]
        return min(hits) if hits else None

    def _reconcile(self) -> None:
        both: dict[str | None, LeaderGap] = {}
        everything = self._both(None)
        if everything is not None:
            both[None] = everything
        else:
            for wallet in sorted(self.followed):
                lost = self._both(wallet)
                if lost is not None:
                    both[wallet] = lost
        for wallet in [w for w in self.announced if w not in both]:
            was = self.announced.pop(wallet)
            end = max(self.o.wall(), was.start)
            self.queue.put_nowait(LeaderGap(was.wallet, was.start, end, was.reason))
        for wallet, gap in both.items():
            if wallet not in self.announced:
                self.announced[wallet] = gap
                self.queue.put_nowait(gap)

    def _both(self, wallet: str | None) -> LeaderGap | None:
        n, c = self._since("nats", wallet), self._since("chain", wallet)
        if n is None or c is None:
            return None
        return LeaderGap(wallet, max(n[0], c[0]), None, f"no_coverage:{n[1]}+{c[1]}")
