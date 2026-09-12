"""The rug-risk reader: ``GET /in-memory-coin/{mint}`` for the mints that matter,
at most once per mint per ``min_interval_s`` (5 min by the brief).

Who matters: mints with an **open paper bet** (the Lab is marking them) and
mints on the site's ``graduating`` board (the ones about to leave the curve).
Nothing else — the read is undocumented and this project spends it where a
wrong number would cost the most.

Every read lands raw in ``meme_risk_snapshots`` and, like a board entry, as a
:class:`HoldersObservation` the fold may use for the minute it was **received**
in (never an earlier one).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_exchanges.base import RateLimited
from hunter_meme_worker.features_tape import HoldersObservation
from hunter_meme_worker.repo_boards import insert_risk_snapshot
from hunter_meme_worker.sources import INDEXER_RISK, SourcesState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.board_models import NormalizedRiskSnapshot

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
HISTORY = 4


class RiskSource(Protocol):
    async def get_risk_snapshot(self, mint: str) -> NormalizedRiskSnapshot: ...


@dataclass(frozen=True, slots=True)
class RiskReport:
    read: int
    skipped_recent: int
    errors: int


class RiskReader:
    def __init__(
        self, client: RiskSource, *, min_interval_s: int, sources: SourcesState | None = None
    ) -> None:
        self._client = client
        self._interval = timedelta(seconds=min_interval_s)
        self._sources = sources
        self.last_read: dict[str, datetime] = {}
        self._readings: dict[str, deque[HoldersObservation]] = {}

    def readings(self, mint: str) -> list[HoldersObservation]:
        return list(self._readings.get(mint, ()))

    def due(self, candidates: set[str], now: datetime) -> list[str]:
        return sorted(
            mint
            for mint in candidates
            if mint not in self.last_read or now - self.last_read[mint] >= self._interval
        )

    async def read_once(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        candidates: set[str],
        *,
        now: datetime,
    ) -> RiskReport:
        due = self.due(candidates, now)
        read = errors = 0
        for mint in due:
            self.last_read[mint] = now
            try:
                snapshot = await self._client.get_risk_snapshot(mint)
            except RateLimited as exc:
                self._error(now, f"rate_limited:{exc.retry_after_s:.0f}s")
                errors += 1
                break  # the bucket is empty for everyone; try again next cycle
            except Exception as exc:  # one mint's failure is not the cycle's
                self._error(now, type(exc).__name__)
                logger.warning("meme_risk_read_failed", mint=mint, error=str(exc))
                errors += 1
                continue
            async with role_session(session_factory, db_role=WORKER_ROLE) as session:
                await insert_risk_snapshot(session, snapshot)
            self._readings.setdefault(mint, deque(maxlen=HISTORY)).append(
                HoldersObservation(
                    observed_at=snapshot.observed_at,
                    received_at=snapshot.received_at,
                    source=snapshot.source,
                    holders=snapshot.holders,
                    top10_share=snapshot.top10_share,
                    dev_share=snapshot.dev_share,
                    snipers=snapshot.snipers,
                )
            )
            if self._sources is not None:
                self._sources[INDEXER_RISK].record_ok(
                    observed_at=snapshot.observed_at, received_at=snapshot.received_at
                )
            read += 1
        return RiskReport(read=read, skipped_recent=len(candidates) - len(due), errors=errors)

    def _error(self, at: datetime, error: str) -> None:
        if self._sources is not None:
            self._sources[INDEXER_RISK].record_spent(at)
            self._sources[INDEXER_RISK].record_error(at, error)
