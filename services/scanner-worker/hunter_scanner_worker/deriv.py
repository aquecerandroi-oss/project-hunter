"""Derivative history from the durable tables, and the roster it arms.

Two jobs that only look unrelated:

1. :class:`DerivHistory` keeps, per market, the open-interest readings of the
   last :data:`DEFAULT_WINDOW_HOURS` hours. They are not in the hot state — the
   ``deriv`` hash holds the *current* value only — so without this loader
   ``open_interest_change_1h/4h`` are ``missing_input`` forever and every
   evaluation of ``OPEN_INTEREST_SPIKE`` is silent (notes-T2.2 section 8;
   ``repo.load_deriv_history`` existed since T2.5 and nothing called it);
2. :func:`detector_roster` turns "this market has no derivative evidence" into a
   **disarmed detector with a reason** instead of an armed detector that never
   fires. The difference is not cosmetic: an armed-and-mute detector is
   indistinguishable from a calm market, while ``enabled=False`` +
   ``disabled_reason`` travels into the evaluation
   (``evaluate_detector`` -> ``detector_disabled`` + detail), into the heartbeat
   and into the metric.

**Capability is not warm-up** (Astra, T2.5b design review, must-fix 6). "There is
no history at all" is a capability the deployment lacks and this module declares;
"there is history but it does not reach an hour back" is the feature's own
``warmup``, and collapsing the two would hide the second behind the first. So the
roster only disarms on *absence*, and rearms on the very next evaluation once a
single reading exists — the roster is rebuilt per market, per cycle, from
current state, never once at startup.

The reload is incremental **with overlap**: a cursor placed strictly after the
newest reading held would silently lose a row inserted late behind it (the query
filters on the observation's own timestamp, not on insertion order). Re-reading
the last :data:`DEFAULT_OVERLAP_MINUTES` costs a handful of rows per market and
removes that class of loss; readings are merged by ``ts``, so an overlap never
duplicates one.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from hunter_core.db.session import role_session
from hunter_core.domain.enums import AnomalyType
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_indicators.anomalies import DEFAULT_DETECTORS, DetectorDefinition
from hunter_scanner_worker.context import history_entry
from hunter_scanner_worker.persist import DB_ROLE
from hunter_scanner_worker.repo import load_deriv_history

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_indicators.features import DerivObservation
    from hunter_scanner_worker.registry import MarketRef
    from hunter_scanner_worker.scanner import Scanner

logger = get_logger(__name__)

DEFAULT_WINDOW_HOURS = 9
"""Long enough for every lookback that reads this series: ``funding_change_8h``
asks for a reading 8 h back with 48 min of tolerance, and
``open_interest_change_4h`` for 4 h with 24 min. Nine hours covers both with
room; shorter and the longest feature is permanently in warm-up."""

DEFAULT_OVERLAP_MINUTES = 30
"""How far behind the newest held reading the incremental reload re-reads."""

REASON_NO_OI_HISTORY = "deriv_history_unavailable"
REASON_NO_FUNDING = "funding_unavailable"

__all__ = [
    "DEFAULT_OVERLAP_MINUTES",
    "DEFAULT_WINDOW_HOURS",
    "REASON_NO_FUNDING",
    "REASON_NO_OI_HISTORY",
    "DerivHistory",
    "deriv_loop",
    "detector_roster",
    "disarmed_reasons",
    "history_entry",
]


class DerivHistory:
    """Open-interest readings per market, reloaded incrementally with overlap."""

    __slots__ = ("_entries", "_loaded_at", "overlap", "window")

    def __init__(
        self,
        *,
        window_hours: int = DEFAULT_WINDOW_HOURS,
        overlap_minutes: int = DEFAULT_OVERLAP_MINUTES,
    ) -> None:
        self.window = timedelta(hours=window_hours)
        self.overlap = timedelta(minutes=overlap_minutes)
        self._entries: dict[UUID, list[DerivObservation]] = {}
        self._loaded_at: dict[UUID, datetime] = {}

    def for_market(self, market_id: UUID) -> list[DerivObservation]:
        return self._entries.get(market_id, [])

    def has_history(self, market_id: UUID) -> bool:
        return bool(self._entries.get(market_id))

    def drop(self, market_id: UUID) -> None:
        """A market left the universe; its readings leave with it."""
        self._entries.pop(market_id, None)
        self._loaded_at.pop(market_id, None)

    def _since(self, market_id: UUID, now: datetime) -> datetime:
        """Where this market's reload starts: the full window, or the overlap.

        A market whose last reload is older than the overlap gets the full
        window again — anything shorter would leave a hole between the two
        reads, which is the very failure the overlap exists to prevent.
        """
        loaded_at = self._loaded_at.get(market_id)
        if loaded_at is None or now - loaded_at >= self.overlap:
            return now - self.window
        return max(now - self.window, loaded_at - self.overlap)

    def _merge(self, market_id: UUID, fresh: Sequence[DerivObservation], now: datetime) -> int:
        """Fold ``fresh`` into what is held, keyed by ``ts``; trim to the window."""
        floor = now - self.window
        by_stamp = {item.ts: item for item in self._entries.get(market_id, ()) if item.ts >= floor}
        for item in fresh:
            if item.ts >= floor:
                by_stamp[item.ts] = item
        merged = [by_stamp[key] for key in sorted(by_stamp)]
        self._entries[market_id] = merged
        self._loaded_at[market_id] = now
        return len(merged)

    async def refresh(
        self,
        factory: async_sessionmaker[AsyncSession],
        refs: Sequence[MarketRef],
        *,
        now: datetime | None = None,
    ) -> int:
        """Reload every market's readings. Returns how many are held afterwards."""
        if not refs:
            return 0
        moment = now or utcnow()
        held = 0
        async with role_session(factory, db_role=DB_ROLE) as session:
            for ref in refs:
                observations = await load_deriv_history(
                    session, ref.market_id, since=self._since(ref.market_id, moment)
                )
                held += self._merge(ref.market_id, observations, moment)
        logger.debug("scanner_deriv_history_refreshed", markets=len(refs), observations=held)
        return held


_ROSTERS: dict[tuple[bool, bool], tuple[DetectorDefinition, ...]] = {}


def detector_roster(*, has_oi_history: bool, has_funding: bool) -> tuple[DetectorDefinition, ...]:
    """The shipped roster with the derivative detectors armed only if they can fire.

    Memoised on the two flags: the roster is rebuilt for every market on every
    cycle (that is what makes rearming automatic), and rebuilding four immutable
    tuples once is cheaper than rebuilding them 200 times a second.
    """
    key = (has_oi_history, has_funding)
    cached = _ROSTERS.get(key)
    if cached is not None:
        return cached
    disarm = {
        AnomalyType.OPEN_INTEREST_SPIKE: None if has_oi_history else REASON_NO_OI_HISTORY,
        AnomalyType.FUNDING_ANOMALY: None if has_funding else REASON_NO_FUNDING,
    }
    roster = tuple(
        definition
        if disarm.get(definition.type) is None or not definition.enabled
        else replace(definition, enabled=False, disabled_reason=disarm[definition.type])
        for definition in DEFAULT_DETECTORS
    )
    _ROSTERS[key] = roster
    return roster


def disarmed_reasons(roster: Sequence[DetectorDefinition]) -> tuple[tuple[str, str], ...]:
    """``(type, reason)`` for every detector this market cannot evaluate."""
    return tuple(
        (definition.type.value, definition.disabled_reason or "unknown")
        for definition in roster
        if not definition.enabled and definition.disabled_reason
    )


async def deriv_loop(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    runtime: WorkerRuntime,
) -> None:
    """Keep the open-interest history current for the whole universe.

    Its own loop, and not part of the evaluation cycle, because the readings are
    written every five minutes by somebody else: re-reading them per tick would
    be 200 queries a second for rows that change twelve times an hour.
    """
    while True:
        try:
            await scanner.deriv.refresh(factory, list(scanner.registry.by_symbol.values()))
            runtime.mark_success()
        except asyncio.CancelledError:
            raise
        except Exception:
            runtime.mark_error()
            logger.exception("scanner_deriv_refresh_failed")
        await asyncio.sleep(scanner.config.deriv_refresh_s)
