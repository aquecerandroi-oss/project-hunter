"""The rug-risk reader: ``GET /in-memory-coin/{mint}`` for the mints that matter,
at most once per mint per ``min_interval_s`` (5 min by the brief).

Who matters: mints with an **open paper bet** (the Lab is marking them), mints on
the site's ``graduating`` board (the ones about to leave the curve) and — since
T4.28b/T4.28g — the mints a **real** buy decision is pending on
(``repo_tape.pending_operator_mints``: an operator proposal still ``proposed`` or
already ``approved`` by stage 1, or a live buy before its fill). Nothing else —
the read is undocumented and this project spends it where a wrong number would
cost the most.

**A mint's first read is never deferred** (T4.28g): :meth:`RiskReader.due` defers
only a mint it has already read, so the ceiling above throttles refreshes, never
the first look at a coin the executor is about to judge. That ordering is the
whole fix — measured 16/09/2026, the ``meme_risk_snapshots`` row of a mint landed
a median 103 s *after* the admission that needed it.

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
from hunter_meme_worker.graduation import CompletionSignals, earliest_completion
from hunter_meme_worker.repo import TokenRow, upsert_token
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
        """Who is read this tick. ``mint not in self.last_read`` comes **first**: a
        mint seen for the first time is due now, whatever the interval says, and no
        per-tick cap can push it behind a coin read 30 s ago (T4.28g)."""
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
                # T4.26: every read teaches the reuse count, not only a graduation.
                if snapshot.graduated_at is not None or snapshot.twitter_reuse_count is not None:
                    await upsert_token(session, _pool_row(snapshot))
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


def _pool_row(snapshot: NormalizedRiskSnapshot) -> TokenRow:
    """The risk read's ``graduationDate`` is the indexer's ``gd`` too (T4.2d):
    the pool signal, with this read as its source, once. T4.26: the same read
    also carries ``twitterReuseCount`` — mutable, like ``mayhem_state``; this
    row is now built whenever *either* signal is present, so
    ``pool_created_source`` must not be set without ``pool_created_at`` (the
    CHECK ``a_pool_names_its_source`` — ``ddl/meme_graduation.py``)."""
    signals = CompletionSignals(
        pool_created_at=snapshot.graduated_at,
        pool_created_source=snapshot.source if snapshot.graduated_at is not None else None,
    )
    return TokenRow(
        mint=snapshot.mint,
        first_seen_source=snapshot.source,
        first_seen_at=snapshot.received_at,
        last_seen_at=snapshot.received_at,
        pool_created_at=signals.pool_created_at,
        pool_created_source=signals.pool_created_source,
        completed_at=earliest_completion(signals),
        twitter_reuse_count=snapshot.twitter_reuse_count,
        twitter_reuse_observed_at=(
            snapshot.received_at if snapshot.twitter_reuse_count is not None else None
        ),
    )
