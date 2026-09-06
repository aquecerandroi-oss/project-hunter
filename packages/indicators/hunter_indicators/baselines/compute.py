"""The pure computation of one baseline revision: median, MAD, counts, identity.

No IO, no clock: ``window_start``, ``window_end`` and ``available_at`` are given
by the caller, which is what makes "recompute tomorrow and reproduce today's
score" checkable. ``available_at`` is never back-dated, including for a bootstrap
over old candles — a baseline computed today may inform decisions from today, and
a decision taken last week could not have known it.

Robust statistics, exactly as ``docs/PIPELINE.md`` §3 asks: the median and the
median of the absolute deviations, both exact in ``Decimal`` and both quantised
to the resolution of the column that stores them.

The sampled window is **half-open**, ``[window_start, window_end)``. Closed at
both ends it counts one minute twice — the bucket whose hour is ``window_end``'s
gets 421 observations in seven days against ``expected_size = 420`` and a
``coverage`` of 1.002381, which ``feature_baselines`` refuses by CHECK and,
since the adapter inserts a market in one batch, takes the whole bootstrap down
with it. Half-open is also what the projection cut ``window_end <
observation_ts`` already assumes: the revision of an hour contains that hour's
minutes and never the first minute of the next window.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal, localcontext

from hunter_core.domain.enums import BaselineSampling, BaselineSource
from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.baselines.revision import (
    ALGO_VERSION,
    REASON_NO_OBSERVATIONS,
    BaselineKey,
    BaselineRevision,
    BaselineUnavailable,
    Observation,
    quantize_coverage,
    quantize_stat,
)

_TWO = Decimal(2)


def median(values: Sequence[Decimal]) -> Decimal:
    """The exact median of ``values`` (midpoint of the two centres if even)."""
    if not values:
        raise ValueError("the median of an empty sample is undefined")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    with localcontext(CONTEXT):
        return (ordered[middle - 1] + ordered[middle]) / _TWO


def median_absolute_deviation(values: Sequence[Decimal], centre: Decimal) -> Decimal:
    """``median(|x - centre|)`` — the scale the deviation is measured in.

    Raw MAD, deliberately **not** multiplied by 1.4826: the joint decision writes
    "desvio em MADs, sem alegar probabilidade" (``docs/plans/M2.md`` §Score), and
    the consistency factor would only be meaningful under a normality assumption
    nobody made about a crypto volume distribution.
    """
    with localcontext(CONTEXT):
        return median([abs(value - centre) for value in values])


def input_fingerprint(
    *,
    key: BaselineKey,
    feature_version: int,
    algo_version: str,
    sampling: BaselineSampling,
    source: BaselineSource,
    window_start: datetime,
    window_end: datetime,
    expected_size: int,
    observations: Sequence[Observation],
) -> str:
    """Canonical digest of the observation set and the cut that produced a row.

    What separates a **retry** from a **recomputation** (``docs/DATABASE.md``
    §17.2): replaying the same refresh job produces the same digest and collides
    with ``uq_feature_baselines_revision``; a backfill that changed the sample
    produces a different one and lands as a new revision. ``available_at`` is
    excluded on purpose — it is when we published, not what we saw, and a retry
    an hour later must still be a retry.
    """
    payload = {
        "algo_version": algo_version,
        "expected_size": expected_size,
        "feature": key.feature,
        "feature_version": feature_version,
        "hour_of_day": key.hour_of_day,
        "market_id": key.market_id,
        "observations": [
            [observation.ts, observation.value]
            for observation in sorted(observations, key=lambda o: o.ts)
        ],
        "sampling": sampling.value,
        "source": source.value,
        "window_end": window_end,
        "window_start": window_start,
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _check_inputs(
    key: BaselineKey,
    observations: Sequence[Observation],
    window_start: datetime,
    window_end: datetime,
    available_at: datetime,
    expected_size: int,
) -> None:
    """A caller bug raises here instead of producing a biased population."""
    if window_start >= window_end:
        raise ValueError(f"window_start {window_start} is not before window_end {window_end}")
    if available_at < window_end:
        raise ValueError(
            f"available_at {available_at} precedes window_end {window_end}: a revision cannot "
            "be usable before the last observation it contains"
        )
    if expected_size <= 0:
        raise ValueError(f"expected_size {expected_size} is not a population size for {key}")
    if len(observations) > expected_size:
        # ``feature_baselines`` declares ``CHECK sample_size <= expected_size``
        # and ``CHECK coverage BETWEEN 0 AND 1``. The adapter inserts a whole
        # market in one batch, so a single row over the line aborts the
        # transaction and the bootstrap of every other bucket with it: the
        # caller has to hear about it here, not from Postgres.
        raise ValueError(
            f"{len(observations)} observations exceed expected_size {expected_size} for {key}: "
            "sample_size <= expected_size is a database CHECK, not a preference"
        )
    seen: set[datetime] = set()
    for observation in observations:
        if not window_start <= observation.ts < window_end:
            raise ValueError(
                f"observation at {observation.ts} is outside the window "
                f"[{window_start}, {window_end})"
            )
        if observation.ts.hour != key.hour_of_day:
            raise ValueError(
                f"observation at {observation.ts} does not belong to the hour "
                f"{key.hour_of_day} bucket"
            )
        # ``per_minute`` sampling counts **minutes**, not events. The timestamp a
        # collector carries is the instant of processing (``ctx.as_of``), so a
        # scanner that recomputed 14:03 twice a second apart would otherwise push
        # sixty "observations" of one minute into the population and clear the
        # gate without ever having seen 120 minutes (Astra, T2.3 diff review,
        # must-fix 4).
        minute = observation.ts.replace(second=0, microsecond=0)
        if minute in seen:
            raise ValueError(f"minute {minute} appears twice in a per-minute sample")
        seen.add(minute)


def compute_revision(
    *,
    key: BaselineKey,
    feature_version: int,
    source: BaselineSource,
    window_start: datetime,
    window_end: datetime,
    available_at: datetime,
    observations: Sequence[Observation],
    expected_size: int,
    algo_version: str = ALGO_VERSION,
    sampling: BaselineSampling = BaselineSampling.PER_MINUTE,
) -> BaselineRevision | BaselineUnavailable:
    """One revision of one bucket, or the reason there is none.

    A bucket **below the gate is still computed**: the row carries its counts and
    the reader refuses it with its own versioned thresholds
    (``BaselineRevision.gate_reason``). Only an empty population has no revision
    at all — there is no median of nothing, and inventing one is precisely what
    the brief forbids.
    """
    window_start = ensure_utc(window_start)
    window_end = ensure_utc(window_end)
    available_at = ensure_utc(available_at)
    _check_inputs(key, observations, window_start, window_end, available_at, expected_size)
    sample_size = len(observations)
    distinct_days = len({observation.ts.date() for observation in observations})
    with localcontext(CONTEXT):
        coverage = quantize_coverage(Decimal(sample_size) / Decimal(expected_size))
    if sample_size == 0:
        return BaselineUnavailable(
            key=key,
            reason=REASON_NO_OBSERVATIONS,
            sample_size=0,
            expected_size=expected_size,
            distinct_days=0,
            coverage=coverage,
        )
    values = [observation.value for observation in observations]
    centre = median(values)
    return BaselineRevision(
        key=key,
        feature_version=feature_version,
        algo_version=algo_version,
        sampling=sampling,
        source=source,
        window_start=window_start,
        window_end=window_end,
        available_at=available_at,
        median=quantize_stat(centre),
        mad=quantize_stat(median_absolute_deviation(values, centre)),
        sample_size=sample_size,
        expected_size=expected_size,
        distinct_days=distinct_days,
        coverage=coverage,
        input_fingerprint=input_fingerprint(
            key=key,
            feature_version=feature_version,
            algo_version=algo_version,
            sampling=sampling,
            source=source,
            window_start=window_start,
            window_end=window_end,
            expected_size=expected_size,
            observations=observations,
        ),
    )


__all__ = [
    "compute_revision",
    "input_fingerprint",
    "median",
    "median_absolute_deviation",
]
