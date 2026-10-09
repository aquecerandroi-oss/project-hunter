"""On-chain :class:`LeaderSource` (H-037): ``logsSubscribe`` per followed wallet + ``getTransaction``.

The mandatory fallback of decision 2026-10-06 and also the **confirmation** of a NATS event by
signature (:meth:`ChainLeaderSource.confirm` -> :class:`LeaderConfirmation`, the five states of the
design: ``confirmed`` only after the chain transaction was read and wallet, mint, side, amount and slot
match).

* ``logsSubscribe`` ``mentions=[wallet]`` at ``confirmed`` (``getTransaction`` does not serve
  ``processed``), one subscription per wallet (the RPC accepts a single address). Every notification of a
  successful transaction is fetched (:mod:`leader_source_chain_fetch`: one call per signature, a 30 s
  deadline, a pause after a refusal) and read by :func:`leader_events_from_transaction` (a swap event
  attributed to the wallet, or nothing). ``first_seen_at`` of a chain event is the notification's receive
  stamp, not the end of the fetch.
* **Reconnects are visible and recovered** (:mod:`leader_source_chain_run`): a gap from the last healthy
  poll, then a paginated REST backfill from the frozen anchor; a recovery that cannot finish leaves a
  ``chain_recovery_failed`` gap on record.
* **What cannot be verified is not "divergent":** a node that did not answer, a transaction whose logs are
  unreadable or whose mint could not be resolved are ``rpc_error`` with the reason; ``divergent`` is
  reserved for a transaction that was read and disagrees.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Collection, Sequence
from datetime import datetime
from typing import Any

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.leader_events import (
    ConfirmationStatus,
    LeaderConfirmation,
    LeaderEvent,
    LeaderItem,
)
from hunter_exchanges.pumpfun.leader_source_chain_derive import (
    ChainRead,
    leader_events_from_transaction,
)
from hunter_exchanges.pumpfun.leader_source_chain_fetch import (
    DEADLINE_S,
    MAX_INFLIGHT,
    RETRY_DELAYS_S,
    FetchTx,
    TxFetcher,
)
from hunter_exchanges.pumpfun.leader_source_chain_run import ChainRun, ListSignatures, LogsFeed
from hunter_exchanges.pumpfun.leader_source_stats import LeaderSourceStats

logger = get_logger(__name__)

MONITOR_INTERVAL_S = 0.5
SETTLE_S = 1.0

__all__ = ["ChainLeaderSource", "LogsFeed"]

_CANNOT_VERIFY = frozenset({"logs_unreadable", "mint_unresolved"})
"""The transaction was reached but could not be read into a verdict: not a divergence."""


def _status_of(reason: str) -> ConfirmationStatus:
    if reason == "not_found":
        return "not_found"
    if reason == "tx_failed":
        return "failed_tx"
    if (
        reason in _CANNOT_VERIFY
        or reason in ("rate_limited", "unavailable")
        or reason.startswith("refused_")
    ):
        return "rpc_error"
    return "divergent"


class ChainLeaderSource:
    def __init__(
        self,
        *,
        feed: LogsFeed,
        fetch_tx: FetchTx,
        list_signatures: ListSignatures | None = None,
        stats: LeaderSourceStats | None = None,
        wall: Callable[[], datetime] = utcnow,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        retry_delays_s: Sequence[float] = RETRY_DELAYS_S,
        deadline_s: float = DEADLINE_S,
        max_inflight: int = MAX_INFLIGHT,
        monitor_interval_s: float = MONITOR_INTERVAL_S,
        settle_s: float = SETTLE_S,
    ) -> None:
        self._feed, self._list = feed, list_signatures
        self.stats = stats or LeaderSourceStats()
        self._wall, self._sleep = wall, sleep
        self._interval, self._settle = monitor_interval_s, settle_s
        self._tx = TxFetcher(
            fetch_tx,
            stats=self.stats,
            wall=wall,
            sleep=sleep,
            retry_delays_s=retry_delays_s,
            deadline_s=deadline_s,
            max_inflight=max_inflight,
        )

    async def read(
        self,
        wallet: str,
        signature: str,
        *,
        first_seen_at: datetime,
        fields_complete_at: datetime | None = None,
    ) -> ChainRead:
        """The chain's reading of ``signature`` for ``wallet`` (``reason`` names why no events)."""
        tx, why = await self._tx.get(signature)
        if tx is None:
            return ChainRead((), why)
        return leader_events_from_transaction(
            tx,
            wallet=wallet,
            signature=signature,
            first_seen_at=first_seen_at,
            fields_complete_at=fields_complete_at or self._wall(),
        )

    async def confirm(self, event: LeaderEvent) -> LeaderConfirmation:
        """Cross-check an earlier event against the chain by signature (idempotent: asking twice is the
        same answer). The five states of the design; ``confirmed_at`` is local reception of the result."""
        read = await self.read(event.wallet, event.signature, first_seen_at=event.first_seen_at)
        base: dict[str, Any] = {
            "wallet": event.wallet,
            "mint": event.mint,
            "signature": event.signature,
            "slot": event.slot,
            "confirmed_at": self._wall(),
        }
        if not read.events:
            reason = read.reason or "not_a_trade"
            return LeaderConfirmation(
                status=_status_of(reason), reason=reason, block_time=None, **base
            )
        chain = next((e for e in read.events if e.mint == event.mint), None)
        if chain is None and read.partial:  # the trade may sit in the part that could not be read
            return LeaderConfirmation(
                status="rpc_error", reason="logs_partial", block_time=None, **base
            )
        if chain is None:
            return LeaderConfirmation(
                status="divergent",
                reason="mint_not_in_tx",
                block_time=read.events[0].block_time,
                **base,
            )
        mismatch = (
            "side"
            if chain.side != event.side
            else "token_delta"
            if chain.token_delta_atoms != event.token_delta_atoms
            else "slot"
            if chain.slot != event.slot
            else None
        )
        return LeaderConfirmation(
            status="divergent" if mismatch else "confirmed",
            reason=mismatch,
            block_time=chain.block_time,
            post_reserves=read.reserves.get(event.mint),
            chain_token_delta_atoms=chain.token_delta_atoms,
            chain_position_after_atoms=chain.position_after_atoms,
            **base,
        )

    # ------------------------------------------------------------------ the stream
    async def stream(self, wallets: Collection[str]) -> AsyncIterator[LeaderItem]:
        followed = frozenset(wallets)
        if not followed:
            raise ValueError("a leader source needs at least one wallet")
        run = ChainRun(
            followed=followed,
            feed=self._feed,
            read=self.read,
            lister=self._list,
            stats=self.stats,
            wall=self._wall,
            sleep=self._sleep,
            interval_s=self._interval,
            settle_s=self._settle,
        )
        tasks = [
            asyncio.create_task(run.listen()),
            asyncio.create_task(run.setup()),
            asyncio.create_task(run.monitor()),
        ]
        try:
            while True:
                yield await run.queue.get()
        finally:
            everything: list[asyncio.Future[Any]] = [*tasks, *run.inflight]
            for task in everything:
                task.cancel()
            # gather, not a suppressed await: a cancel aimed at THIS task must not be swallowed
            await asyncio.gather(*everything, return_exceptions=True)
            await self._tx.aclose()
            try:
                await self._feed.aclose()
            except Exception as exc:
                logger.warning("leader_chain_feed_close_failed", error=type(exc).__name__)
