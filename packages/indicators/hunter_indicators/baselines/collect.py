"""Turning feature vectors into the population a baseline is computed from.

One rule decides everything here: **only ``quality == ok`` observations enter the
sample**. A ``degraded`` reading means one of the feature's own inputs was late,
and folding those into the seven-day distribution would make the baseline
describe the health of our collection instead of the market. The cost is real and
declared: hours of instability are systematically thinner, so they show up as
lower ``coverage`` — visible, not silently repaired with a number that does not
describe anything (Astra, T2.3 design review, item 6).

Every rejection is counted by reason, per feature. "This bucket has 118
observations" is not an explanation; "118, and 22 minutes were dropped because
the book was stale" is.

Quality is read from :meth:`FeatureVector.quality_of`, never from
:meth:`FeatureVector.number` alone — that method also returns the value of a
degraded feature.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from hunter_core.domain.enums import BaselineSource
from hunter_indicators.baselines.compute import compute_revision
from hunter_indicators.baselines.revision import (
    ALGO_VERSION,
    BaselineKey,
    BaselineRevision,
    BaselineUnavailable,
    Observation,
)
from hunter_indicators.features.vector import FeatureVector, Quality

REASON_NOT_COMPUTED = "not_computed"
"""The vector does not carry this feature at all (another feature set version)."""

REASON_DEGRADED = "degraded_sample"
"""There is a number, but an input it declared was late — not a market fact."""

REASON_DUPLICATE_MINUTE = "duplicate_minute"
"""A second reading of a minute this feature already has — kept as a count.

``per_minute`` sampling counts **minutes**, not events, and live there is more
than one vector per minute (the tick features are throttled at one second). The
extra reading is not an error: it is dropped, counted, and the population stays
one observation per minute so ``compute`` never sees a duplicate."""


@dataclass(frozen=True, slots=True)
class ObservationRejection:
    """One minute of one feature that did not enter the population, and why."""

    feature: str
    ts: datetime
    reason: str


def observations_from_vector(
    vector: FeatureVector, features: Sequence[str]
) -> tuple[tuple[tuple[str, Observation], ...], tuple[ObservationRejection, ...]]:
    """The ``ok`` readings of ``features`` in ``vector``, and every rejection."""
    minute = vector.ts.replace(second=0, microsecond=0)
    accepted: list[tuple[str, Observation]] = []
    rejected: list[ObservationRejection] = []
    for feature in features:
        value = vector.values.get(feature)
        if value is None:
            rejected.append(
                ObservationRejection(feature=feature, ts=minute, reason=REASON_NOT_COMPUTED)
            )
            continue
        if value.quality is Quality.OK and value.value is not None:
            accepted.append((feature, Observation(ts=minute, value=value.value)))
            continue
        reason = (
            REASON_DEGRADED
            if value.quality is Quality.DEGRADED
            else (value.reason.value if value.reason is not None else REASON_NOT_COMPUTED)
        )
        rejected.append(ObservationRejection(feature=feature, ts=minute, reason=reason))
    return tuple(accepted), tuple(rejected)


class ObservationCollector:
    """Accumulates per-minute observations per ``(feature, UTC hour)`` bucket.

    Keyed by ``(feature, minute)``: **one reading per minute**, the first *valid*
    one received. ``FeatureVector.ts`` is ``ctx.as_of`` and carries seconds, and
    live there is normally more than one vector per minute, so without this the
    refresh of a market would raise inside ``compute._check_inputs`` and write no
    baseline at all.

    "First" means first in arrival order, not the earliest instant inside the
    minute, and a reading rejected for quality does not take the slot. Neither
    choice is neutral and this one is **not** justified by causality: truncating
    a 14:03:40 reading to 14:03 does not prove it was available at 14:03:10
    (Astra, revisão do fix-pass, item b). It is justified by *replay*: the
    collector consumes vectors in arrival order, so "first" is decidable without
    looking at anything that came later and the same stream selects the same
    value twice. Causality is enforced elsewhere and separately — the revision is
    published at ``available_at`` and read under ``window_end < observation_ts``.
    """

    __slots__ = ("_buckets", "_features", "_rejections", "_seen", "market_id")

    def __init__(self, market_id: uuid.UUID, features: Sequence[str]) -> None:
        self.market_id = market_id
        self._features = tuple(features)
        self._buckets: dict[tuple[str, int], list[Observation]] = {}
        self._seen: set[tuple[str, datetime]] = set()
        self._rejections: dict[str, dict[str, int]] = {}

    @property
    def features(self) -> tuple[str, ...]:
        return self._features

    def add(self, vector: FeatureVector) -> None:
        accepted, rejected = observations_from_vector(vector, self._features)
        for feature, observation in accepted:
            minute = (feature, observation.ts)
            if minute in self._seen:
                self._count(feature, REASON_DUPLICATE_MINUTE)
                continue
            self._seen.add(minute)
            self._buckets.setdefault((feature, observation.ts.hour), []).append(observation)
        for rejection in rejected:
            self._count(rejection.feature, rejection.reason)

    def _count(self, feature: str, reason: str) -> None:
        reasons = self._rejections.setdefault(feature, {})
        reasons[reason] = reasons.get(reason, 0) + 1

    def bucket(self, feature: str, hour_of_day: int) -> tuple[Observation, ...]:
        return tuple(self._buckets.get((feature, hour_of_day), ()))

    def buckets(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(self._buckets))

    def rejections(self) -> Mapping[str, Mapping[str, int]]:
        """``feature -> reason -> count``: why the population is as thin as it is."""
        return {feature: dict(reasons) for feature, reasons in sorted(self._rejections.items())}

    def revisions(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        available_at: datetime,
        source: BaselineSource,
        expected_size: int,
        feature_versions: Mapping[str, int],
        algo_version: str = ALGO_VERSION,
    ) -> tuple[BaselineRevision | BaselineUnavailable, ...]:
        """One revision per non-empty bucket, ordered by ``(feature, hour)``.

        ``available_at`` is the caller's: a bootstrap over last week's candles is
        published **today**, never back-dated to simulate knowledge nobody had
        (``docs/DATABASE.md`` §17.2).
        """
        out: list[BaselineRevision | BaselineUnavailable] = []
        for feature, hour in self.buckets():
            out.append(
                compute_revision(
                    key=BaselineKey(market_id=self.market_id, feature=feature, hour_of_day=hour),
                    feature_version=feature_versions[feature],
                    source=source,
                    window_start=window_start,
                    window_end=window_end,
                    available_at=available_at,
                    observations=self.bucket(feature, hour),
                    expected_size=expected_size,
                    algo_version=algo_version,
                )
            )
        return tuple(out)


__all__ = [
    "REASON_DEGRADED",
    "REASON_DUPLICATE_MINUTE",
    "REASON_NOT_COMPUTED",
    "ObservationCollector",
    "ObservationRejection",
    "observations_from_vector",
]
