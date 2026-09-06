"""The baseline projection the detectors read, and how it is kept current.

Three jobs, deliberately apart:

1. **the cache** -- one selected revision per ``(market, feature, UTC hour)``,
   refreshed on the hour, so no evaluation ever queries history. The joint M2
   decision's cost rule: "baselines em cache, sem consulta de historico no
   scorer". The per-evaluation :class:`BaselineProjection` is rebuilt from the
   cache under *that evaluation's* cut, which is what keeps the causal test
   (``available_at <= as_of`` **and** ``window_end < observation_ts``) applied
   per observation rather than once per hour;
2. **the hourly refresh** -- recompute only the bucket of the hour that just
   closed, from the per-minute ``feature_snapshots`` of the last seven days
   (notes-T2.3 section 9). Recomputing all 24 buckets every hour would be 2.3M
   rows a day and would put the partitioning of an append-only archive back on
   the table;
3. **the bootstrap** -- at startup, the same calculators replayed over persisted
   candles, so a fresh install is not a week away from its first anomaly. What
   candles cannot reproduce (book, tape, ``_live``, ``trade_velocity_1m``) is
   excluded with a structured reason and reported as "under construction",
   never filled with a number.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import text

from hunter_core.domain.enums import BaselineSource
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_indicators.baselines import (
    ALGO_VERSION,
    BaselineCut,
    BaselineProjection,
    BaselineRequest,
    BaselineRevision,
    ObservationCollector,
    SqlBaselineStore,
    StoredBaseline,
)
from hunter_indicators.baselines.bootstrap import bootstrap_feature_keys
from hunter_indicators.features import (
    DEFAULT_REGISTRY,
    FeatureValue,
    FeatureVector,
    Quality,
    Reason,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncConnection

    from hunter_indicators.baselines import BaselineGate

from hunter_scanner_worker.registry import MarketRef

logger = get_logger(__name__)

WINDOW_DAYS = 7
EXPECTED_PER_BUCKET = WINDOW_DAYS * 60
"""420: one observation per minute, seven days, one UTC hour bucket."""

__all__ = [
    "EXPECTED_PER_BUCKET",
    "WINDOW_DAYS",
    "BaselineCache",
    "BaselineMaturity",
    "baseline_features",
    "bootstrap_roster",
    "hour_window",
    "read_hour_observations",
    "revisions_for",
    "vector_from_snapshot",
]


def baseline_features() -> tuple[tuple[str, int], ...]:
    """``(feature, feature_version)`` for every feature a baseline is kept for.

    The roster is the registry's, minus what a *bootstrap* cannot reproduce --
    but only the bootstrap is limited that way: a live refresh reads the same
    ``feature_snapshots`` the scanner wrote, so it can and does keep baselines
    for the book and tape features too. Keeping the two rosters equal here would
    hide a live baseline behind a historical limitation.
    """
    definitions = {
        definition.key: definition.version for definition in DEFAULT_REGISTRY.definitions()
    }
    return tuple(sorted((key, version) for key, version in definitions.items()))


def hour_window(closed_hour: datetime, *, days: int = WINDOW_DAYS) -> tuple[datetime, datetime]:
    """``[window_start, window_end)`` for the bucket of ``closed_hour``.

    Half-open at the end (T2.3 MF-1): closed at both ends, the minute that opens
    the next window counts twice and ``sample_size`` exceeds ``expected_size``,
    which the table's CHECK rejects -- aborting the whole batch, not just the
    offending bucket.
    """
    end = closed_hour.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return (end - timedelta(days=days), end)


@dataclass(frozen=True, slots=True)
class BaselineMaturity:
    """How much of the archive is actually usable, for ``/ready`` and the proof."""

    usable: int = 0
    under_construction: int = 0
    reasons: dict[str, int] = field(default_factory=dict[str, int])

    @property
    def total(self) -> int:
        return self.usable + self.under_construction


@dataclass
class BaselineCache:
    """Selected revisions per market, refreshed on the hour."""

    gate: BaselineGate
    entries: dict[UUID, tuple[StoredBaseline, ...]] = field(
        default_factory=dict[UUID, tuple[StoredBaseline, ...]]
    )
    refreshed_at: datetime | None = None

    def projection(self, market_id: UUID, cut: BaselineCut) -> BaselineProjection:
        """The revisions this market may be judged against at ``cut``.

        Filtering here rather than at load time is what makes the cut per
        *observation*: a revision published at 10:01 that already contains the
        10:00 minute is admissible for 10:05 and not for 10:00, and the cache
        holds one entry either way.
        """
        admitted = [
            entry for entry in self.entries.get(market_id, ()) if cut.admits(entry.revision)
        ]
        return BaselineProjection(admitted, cut=cut, gate=self.gate, algo_version=ALGO_VERSION)

    def maturity(self, market_ids: Sequence[UUID]) -> BaselineMaturity:
        usable = 0
        under = 0
        reasons: dict[str, int] = defaultdict(int)
        for market_id in market_ids:
            for entry in self.entries.get(market_id, ()):
                revision = entry.revision
                if (
                    revision.distinct_days >= self.gate.min_distinct_days
                    and revision.sample_size >= self.gate.min_valid_observations
                ):
                    usable += 1
                else:
                    under += 1
                    reasons["insufficient_history"] += 1
        return BaselineMaturity(usable=usable, under_construction=under, reasons=dict(reasons))

    def median_of(self, market_id: UUID, feature: str, hour_of_day: int) -> Decimal | None:
        """The usable median of one bucket, for the stage confirmations."""
        for entry in self.entries.get(market_id, ()):
            key = entry.revision.key
            if key.feature == feature and key.hour_of_day == hour_of_day:
                if (
                    entry.revision.distinct_days < self.gate.min_distinct_days
                    or entry.revision.sample_size < self.gate.min_valid_observations
                ):
                    return None
                return entry.revision.median
        return None

    async def refresh(
        self,
        connection: AsyncConnection,
        refs: Sequence[MarketRef],
        *,
        now: datetime | None = None,
    ) -> int:
        """Reload the selected revision of every bucket of every market."""
        moment = now or utcnow()
        store = SqlBaselineStore(connection)
        cut = BaselineCut(as_of=moment, observation_ts=moment)
        features = baseline_features()
        loaded = 0
        for ref in refs:
            requests = [
                BaselineRequest(
                    market_id=ref.market_id,
                    feature=feature,
                    feature_version=version,
                    hour_of_day=hour,
                )
                for feature, version in features
                for hour in range(24)
            ]
            entries = await store.load(requests, cut=cut)
            self.entries[ref.market_id] = entries
            loaded += len(entries)
        self.refreshed_at = moment
        return loaded


_SNAPSHOT_SQL = text(
    """
    SELECT market_id, ts, features
      FROM feature_snapshots
     WHERE ts >= :window_start
       AND ts <  :window_end
       AND EXTRACT(HOUR FROM ts AT TIME ZONE 'UTC') = :hour
       AND market_id = ANY(:market_ids)
     ORDER BY market_id, ts
    """
)


def vector_from_snapshot(
    row_features: dict[str, Any], *, exchange: str, symbol: str, ts: datetime
) -> FeatureVector:
    """Rebuild the stored vector so the collector applies its own admission rule.

    Reading ``quality == "ok"`` out of the JSONB by hand would work today and
    drift the day ``observations_from_vector`` changes what a valid observation
    is. Rebuilding the vector instead means the refresh and the live collector
    share one definition, and the test that proves it is a round trip
    (``as_wire`` -> here -> the same observations).
    """
    stored: dict[str, Any] = dict(row_features.get("values") or {})
    values: dict[str, FeatureValue] = {}
    for key, raw_entry in stored.items():
        if not isinstance(raw_entry, dict):
            continue
        entry: dict[str, Any] = dict(cast("dict[str, Any]", raw_entry))
        quality = Quality(str(entry.get("quality")))
        reason_text: Any = entry.get("reason")
        reason = Reason(str(reason_text)) if reason_text else None
        raw: Any = entry.get("value")
        if quality is Quality.UNAVAILABLE or raw is None:
            values[key] = FeatureValue.unavailable(key, reason or Reason.MISSING_INPUT)
            continue
        values[key] = FeatureValue(key=key, value=Decimal(str(raw)), quality=quality, reason=reason)
    return FeatureVector(
        exchange=exchange,
        symbol=symbol,
        ts=ensure_utc(ts),
        feature_set_version=str(row_features.get("feature_set_version") or ""),
        values=values,
        quality_policy_version=str(row_features.get("quality_policy_version") or ""),
    )


async def read_hour_observations(
    connection: AsyncConnection,
    refs: Sequence[MarketRef],
    *,
    hour: int,
    window_start: datetime,
    window_end: datetime,
    features: Sequence[str],
) -> dict[UUID, ObservationCollector]:
    """Per-minute observations of one UTC hour bucket, from ``feature_snapshots``.

    The snapshots are the only seven-day source of the *live* features (the tape
    and the book leave no other trace), and they are already one row per closed
    minute -- which is exactly the sampling ``baseline_sampling = per_minute``
    names.
    """
    if not refs:
        return {}
    result = await connection.execute(
        _SNAPSHOT_SQL,
        {
            "window_start": window_start,
            "window_end": window_end,
            "hour": hour,
            "market_ids": [str(ref.market_id) for ref in refs],
        },
    )
    by_id = {ref.market_id: ref for ref in refs}
    collectors: dict[UUID, ObservationCollector] = {}
    counts: dict[UUID, int] = defaultdict(int)
    for row in result:
        market_id = UUID(str(row.market_id))
        ref = by_id.get(market_id)
        if ref is None:
            continue
        collector = collectors.get(market_id)
        if collector is None:
            collector = ObservationCollector(market_id, features)
            collectors[market_id] = collector
        collector.add(
            vector_from_snapshot(
                dict(row.features or {}),
                exchange=ref.exchange,
                symbol=ref.symbol,
                ts=row.ts,
            )
        )
        counts[market_id] += 1
    logger.info(
        "scanner_baseline_hour_read",
        hour=hour,
        markets=len(collectors),
        minutes=sum(counts.values()),
    )
    return collectors


def revisions_for(
    collector: ObservationCollector,
    *,
    window_start: datetime,
    window_end: datetime,
    available_at: datetime,
    feature_versions: dict[str, int],
) -> list[BaselineRevision]:
    """The revisions of one market's closed hour, dropping the empty buckets."""
    produced = collector.revisions(
        window_start=window_start,
        window_end=window_end,
        available_at=available_at,
        source=BaselineSource.LIVE,
        expected_size=EXPECTED_PER_BUCKET,
        feature_versions=feature_versions,
    )
    return [item for item in produced if isinstance(item, BaselineRevision)]


def bootstrap_roster() -> tuple[str, ...]:
    """Features a candle replay can legitimately produce a baseline for."""
    return bootstrap_feature_keys()
