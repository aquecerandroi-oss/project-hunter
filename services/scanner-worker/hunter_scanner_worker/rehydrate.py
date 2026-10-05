"""Putting a market's memory back in line with what the database holds.

Two callers, one rule. A market that **joins** the universe starts empty and
loads its open anomalies and episode. A market whose evaluation was **invalidated**
at flush time (its baseline vanished before the write) had its rows dropped *after*
the collectors already moved its memory on: an ``EXPIRE`` of episode X forgot X, the
row never reached the table, and the next episode would open as Y beside an X the
database still holds open -- the veto behind the 30/09 and 02/10 stops (Astra,
05/10: "retaining the batch only in the ``except`` is not enough"). Reloading the
market from the table is what restores X.

For the resync the table is the truth, so a market with **no** open episode there ends
with none in memory: leaving a speculative id behind is exactly the divergence this
repairs. The join path does not do that (see ``authoritative``)
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_scanner_worker.persist import DB_ROLE
from hunter_scanner_worker.registry import MarketRef

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_scanner_worker.flush_lane import FlushLane
    from hunter_scanner_worker.scanner import Scanner

logger = get_logger(__name__)

__all__ = ["rehydrate_markets", "resync_invalidated"]


async def rehydrate_markets(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    refs: list[object],
    *,
    authoritative: bool = False,
) -> None:
    """Load the durable state of ``refs`` into their in-memory market states.

    ``authoritative=True`` is for a caller that holds ``lane.lock`` (the resync): the
    table wins, and a market with no open episode there ends with none in memory. A
    market that **joins** the universe is loaded outside the lock, while the cycle may
    already have collected its first ``OPEN`` -- wiping that id would let a second
    episode open beside it (Astra, 05/10) -- so there an absent episode is left alone."""
    from hunter_scanner_worker.checkpoint import history_mark_from_wire
    from hunter_scanner_worker.repo import load_open_anomalies, load_open_episodes

    typed = [ref for ref in refs if isinstance(ref, MarketRef)]
    if not typed:
        return
    ids = [ref.market_id for ref in typed]
    since = utcnow() - timedelta(hours=6)
    async with role_session(factory, db_role=DB_ROLE) as session:
        anomalies = await load_open_anomalies(session, ids, since=since)
        episodes = await load_open_episodes(session, ids)
    for ref in typed:
        state = scanner.state.get(ref.symbol)
        if state is None:
            continue
        loaded = anomalies.get(ref.market_id, {})
        state.anomalies = {kind: entry[1] for kind, entry in loaded.items()}
        state.anomaly_ids = {kind: entry[0] for kind, entry in loaded.items() if entry[1].is_open}
        state.closed_anomaly_at = {
            kind: entry[1].observation_ts for kind, entry in loaded.items() if not entry[1].is_open
        }
        episode = episodes.get(ref.market_id)
        if episode is None:
            if authoritative:
                state.episode = None
                state.opportunity_id = None
            continue
        state.episode = episode.episode
        state.opportunity_id = episode.opportunity_id
        if episode.history_wire:
            try:
                state.checkpoint = state.checkpoint.__class__(
                    features=state.checkpoint.features,
                    stage=state.checkpoint.stage,
                    history=history_mark_from_wire(episode.history_wire),
                    recovered=True,
                )
            except Exception:
                logger.warning("scanner_history_mark_unreadable", symbol=ref.symbol)


async def resync_invalidated(
    scanner: Scanner, factory: async_sessionmaker[AsyncSession], lane: FlushLane
) -> None:
    """Reload the markets whose rows ``flush_batch`` dropped, then re-evaluate them.

    The ids stay in ``lane.invalidated`` until the reload succeeded, so a database
    error here is retried on the next cycle instead of leaving the memory ahead.
    """
    refs = [scanner.registry.ref_by_id(market_id) for market_id in lane.invalidated]
    found = [ref for ref in refs if ref is not None]
    await rehydrate_markets(scanner, factory, list(found), authoritative=True)
    for ref in found:
        state = scanner.state.get(ref.symbol)
        if state is not None:
            state.touch("baseline_vanished")
    lane.invalidated.clear()
