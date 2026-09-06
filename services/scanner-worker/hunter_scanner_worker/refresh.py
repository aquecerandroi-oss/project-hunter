"""The hourly refresh: one bucket, the hour that just closed, and nothing else.

Recomputing all 24 buckets every hour would be 2.3 M rows a day into an
append-only archive, so when an hour closes only *that* hour's bucket is
recomputed, from the per-minute ``feature_snapshots`` of the last seven days
(notes-T2.3 section 9). The rest of the projection stays exactly as it was.

**A thin live revision must not shadow a mature bootstrap.** The projection picks
the newest admissible revision (``ORDER BY available_at DESC``), with no
preference for maturity, so on a fresh install the first hourly refresh — 60
observations, one distinct day — would supersede a 420-observation bootstrap and
then fail the gate. The detector would lose the baseline it had just gained, and
the whole bootstrap would be pointless one hour later (Astra, T2.5b design
review, must-fix 2).

So the refresh **withholds** a revision that is less mature than the one in force:
if the bucket currently resolves to a usable baseline and the freshly computed one
would not pass the gate, it is not written, it is counted
(``hunter_scanner_baseline_revisions_total{outcome="withheld"}``) and it is
logged. This is an explicit, temporary policy and it is stated as such: the right
answer is one population built from historical and live observations together,
one per minute, and medians already computed cannot be merged to reconstruct it.
As the live population matures the withholding stops on its own — the first
revision that passes the gate is written and supersedes the bootstrap normally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_indicators.baselines import SqlBaselineStore
from hunter_scanner_worker.baselines import (
    baseline_features,
    hour_window,
    read_hour_observations,
    revisions_for,
)
from hunter_scanner_worker.metrics import scanner_baseline_revisions_total

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine

    from hunter_indicators.baselines import BaselineGate, BaselineRevision
    from hunter_scanner_worker.baselines import BaselineCache
    from hunter_scanner_worker.registry import MarketRef

logger = get_logger(__name__)

CHUNK = 25
"""Markets per read. One statement for 200 markets × 7 days of minutes is a
single very large result set; a chunk keeps the refresh interruptible and its
memory bounded."""

__all__ = [
    "RefreshOutcome",
    "admissible",
    "closed_hour_before",
    "refresh_hour",
    "reload_market",
]


@dataclass(frozen=True, slots=True)
class RefreshOutcome:
    """What one hourly refresh wrote, and what it deliberately did not."""

    closed_hour: datetime
    markets: int = 0
    written: int = 0
    withheld: int = 0
    withheld_features: dict[str, int] = field(default_factory=dict[str, int])


def closed_hour_before(now: datetime) -> datetime:
    """The last UTC hour that is fully over at ``now``."""
    top = ensure_utc(now).replace(minute=0, second=0, microsecond=0)
    return top - timedelta(hours=1)


def _usable(revision: BaselineRevision, gate: BaselineGate) -> bool:
    return (
        revision.distinct_days >= gate.min_distinct_days
        and revision.sample_size >= gate.min_valid_observations
    )


def admissible(
    revisions: Sequence[BaselineRevision], cache: BaselineCache, gate: BaselineGate
) -> tuple[list[BaselineRevision], list[BaselineRevision]]:
    """Split into what is written and what is withheld as less mature.

    Shared with the bootstrap: whichever source produces it, a revision that
    would replace a usable baseline with one that fails the gate is withheld.
    """
    keep: list[BaselineRevision] = []
    withheld: list[BaselineRevision] = []
    for revision in revisions:
        in_force = cache.median_of(
            revision.key.market_id, revision.key.feature, revision.key.hour_of_day
        )
        if in_force is not None and not _usable(revision, gate):
            withheld.append(revision)
        else:
            keep.append(revision)
    return keep, withheld


async def refresh_hour(
    engine: AsyncEngine,
    refs: Sequence[MarketRef],
    *,
    cache: BaselineCache,
    gate: BaselineGate,
    closed_hour: datetime,
    now: datetime,
    window_days: int = 7,
    chunk: int = CHUNK,
) -> RefreshOutcome:
    """Recompute and publish the bucket of ``closed_hour``, then reload the cache."""
    if not refs:
        return RefreshOutcome(closed_hour=closed_hour)
    hour = ensure_utc(closed_hour)
    window_start, window_end = hour_window(hour, days=window_days)
    features = baseline_features()
    keys = [key for key, _ in features]
    versions = dict(features)
    written = 0
    withheld_features: dict[str, int] = {}
    withheld_total = 0
    for index in range(0, len(refs), chunk):
        batch = list(refs[index : index + chunk])
        async with engine.begin() as connection:
            collectors = await read_hour_observations(
                connection,
                batch,
                hour=hour.hour,
                window_start=window_start,
                window_end=window_end,
                features=keys,
            )
            produced: list[BaselineRevision] = []
            # Stamped per chunk, after its own read: a snapshot persisted while an
            # earlier chunk was being processed is folded into *this* chunk, and a
            # single ``now`` taken before the loop would publish it as if it had
            # been known minutes earlier (Astra, T2.5b diff review, must-fix 1).
            available_at = max(now, utcnow())
            for collector in collectors.values():
                produced.extend(
                    revisions_for(
                        collector,
                        window_start=window_start,
                        window_end=window_end,
                        available_at=available_at,
                        feature_versions=versions,
                    )
                )
            keep, withheld = admissible(produced, cache, gate)
            for revision in withheld:
                key = revision.key.feature
                withheld_features[key] = withheld_features.get(key, 0) + 1
            withheld_total += len(withheld)
            if keep:
                await SqlBaselineStore(connection).append(keep)
                written += len(keep)
    scanner_baseline_revisions_total.labels(source="live", outcome="written").inc(written)
    scanner_baseline_revisions_total.labels(source="live", outcome="withheld").inc(withheld_total)
    async with engine.begin() as connection:
        loaded = await cache.refresh(connection, refs, now=now)
    logger.info(
        "scanner_baseline_hour_refreshed",
        hour=hour.isoformat(),
        markets=len(refs),
        written=written,
        withheld=withheld_total,
        cached=loaded,
    )
    return RefreshOutcome(
        closed_hour=hour,
        markets=len(refs),
        written=written,
        withheld=withheld_total,
        withheld_features=withheld_features,
    )


async def reload_market(
    engine: AsyncEngine, cache: BaselineCache, ref: MarketRef, *, now: datetime
) -> int:
    """Reload one market's projection, right after its bootstrap was written.

    Without this a bootstrap is invisible until the next hour closes: the
    revisions are in the archive, and the detectors read the *cache*. Waiting up
    to an hour to use a baseline that already exists would be a self-inflicted
    blind spot — and on a fresh install it is precisely the hour in which nothing
    can be scored.
    """
    async with engine.begin() as connection:
        loaded = await cache.refresh(connection, [ref], now=now)
    logger.info("scanner_baseline_market_reloaded", symbol=ref.symbol, revisions=loaded)
    return loaded
