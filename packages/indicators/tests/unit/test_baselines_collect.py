"""The collector's bucket key is ``(feature, minute)`` — one reading per minute.

``FeatureVector.ts`` is ``ctx.as_of``, the instant of *processing*, and it
carries seconds. Live, more than one vector per minute is the normal case (the
tick features are throttled at one second), so two readings of 14:03 would reach
``compute._check_inputs`` as two observations of the same minute, raise, and take
the whole market's baseline refresh down with them. The collector is where that
is resolved, because it is the only place that knows the arrival order.

**The first valid reading received for the minute wins** — first in arrival
order, not the earliest instant inside the minute. The reason is replay, not
causality: the collector consumes vectors in arrival order, so "first" is
decidable without looking at anything that came later and the same stream
selects the same value twice. Truncating a 14:03:40 reading to 14:03 would not
prove it was available at 14:03:10, and it is not claimed to (Astra, revisão do
fix-pass, item b); the causal guarantees are ``available_at`` and the projection
cut, which live elsewhere on purpose.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import BaselineSource
from hunter_indicators.baselines import (
    BaselineGate,
    BaselineKey,
    BaselineRevision,
    ObservationCollector,
    compute_revision,
    observations_from_vector,
)
from hunter_indicators.baselines.collect import (
    REASON_DEGRADED,
    REASON_DUPLICATE_MINUTE,
)
from hunter_indicators.features import (
    DEFAULT_REGISTRY,
    FeatureValue,
    FeatureVector,
    Quality,
    Reason,
)

MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")
FEATURE = "relative_volume_1h"
HOUR = 14
DAY_ONE = datetime(2026, 9, 1, HOUR, 0, tzinfo=UTC)
GATE = BaselineGate(min_distinct_days=3, min_valid_observations=120, expected_size=420)


def vector(ts: datetime, value: str, *, quality: Quality = Quality.OK) -> FeatureVector:
    entry = FeatureValue.ok(FEATURE, Decimal(value))
    if quality is not Quality.OK:
        entry = entry.degraded_to(quality, Reason.STALE_INPUT)
    return FeatureVector(
        exchange="binance",
        symbol="BTCUSDT",
        ts=ts,
        feature_set_version=DEFAULT_REGISTRY.feature_set_version,
        values={FEATURE: entry},
    )


def good_minutes(count: int) -> list[datetime]:
    """``count`` distinct minutes of the 14:00 bucket, filling day after day."""
    return [DAY_ONE + timedelta(days=index // 60, minutes=index % 60) for index in range(count)]


class TestOneReadingPerMinute:
    def test_two_readings_of_one_minute_are_one_observation_and_one_rejection(self) -> None:
        # The cross review's scenario: 14:03:10 and 14:03:40, then 126 good
        # minutes. 128 readings go in; 127 observations come out; the extra one
        # is *counted*, not swallowed, and nothing raises.
        collector = ObservationCollector(MARKET, [FEATURE])
        duplicated = datetime(2026, 9, 4, HOUR, 3, tzinfo=UTC)
        collector.add(vector(duplicated.replace(second=10), "5"))
        collector.add(vector(duplicated.replace(second=40), "9"))
        for minute in good_minutes(126):
            collector.add(vector(minute, "10"))

        bucket = collector.bucket(FEATURE, HOUR)
        assert len(bucket) == 127
        assert collector.rejections()[FEATURE] == {REASON_DUPLICATE_MINUTE: 1}
        kept = [item for item in bucket if item.ts == duplicated]
        assert len(kept) == 1
        assert kept[0].value == Decimal("5")  # the first reading of the minute

    def test_the_deduplicated_bucket_computes_a_revision(self) -> None:
        # This is the failure the cross review actually hit: the refresh of a
        # market died inside ``compute``, so no baseline was written at all.
        collector = ObservationCollector(MARKET, [FEATURE])
        duplicated = datetime(2026, 9, 4, HOUR, 3, tzinfo=UTC)
        collector.add(vector(duplicated.replace(second=10), "5"))
        collector.add(vector(duplicated.replace(second=40), "9"))
        for minute in good_minutes(126):
            collector.add(vector(minute, "10"))

        revision = compute_revision(
            key=BaselineKey(market_id=MARKET, feature=FEATURE, hour_of_day=HOUR),
            feature_version=1,
            source=BaselineSource.LIVE,
            window_start=DAY_ONE,
            window_end=DAY_ONE + timedelta(days=7),
            available_at=DAY_ONE + timedelta(days=7),
            observations=collector.bucket(FEATURE, HOUR),
            expected_size=420,
        )
        assert isinstance(revision, BaselineRevision)
        assert revision.sample_size == 127
        assert revision.distinct_days == 4
        assert revision.usable_under(GATE) is True

    def test_the_observation_timestamp_is_truncated_to_the_minute(self) -> None:
        ts = datetime(2026, 9, 4, HOUR, 3, 41, 123456, tzinfo=UTC)
        accepted, rejected = observations_from_vector(vector(ts, "5"), [FEATURE])
        assert not rejected
        assert accepted[0][1].ts == ts.replace(second=0, microsecond=0)

    def test_sixty_recomputations_of_one_minute_stay_one_observation(self) -> None:
        # The gate is 120 *minutes* seen. A scanner recomputing 14:03 once a
        # second must never clear it with one minute of data.
        collector = ObservationCollector(MARKET, [FEATURE])
        base = datetime(2026, 9, 4, HOUR, 3, tzinfo=UTC)
        for second in range(60):
            collector.add(vector(base.replace(second=second), "5"))
        assert len(collector.bucket(FEATURE, HOUR)) == 1
        assert collector.rejections()[FEATURE] == {REASON_DUPLICATE_MINUTE: 59}

    def test_distinct_minutes_are_all_kept(self) -> None:
        collector = ObservationCollector(MARKET, [FEATURE])
        for minute in good_minutes(5):
            collector.add(vector(minute.replace(second=7), "10"))
        assert len(collector.bucket(FEATURE, HOUR)) == 5
        assert collector.rejections() == {}

    def test_a_degraded_first_reading_leaves_the_minute_open(self) -> None:
        # A rejection is not an observation, so the ``ok`` reading that follows
        # inside the same minute is the first *valid* one and enters.
        collector = ObservationCollector(MARKET, [FEATURE])
        base = datetime(2026, 9, 4, HOUR, 3, tzinfo=UTC)
        collector.add(vector(base.replace(second=5), "99", quality=Quality.DEGRADED))
        collector.add(vector(base.replace(second=35), "5"))
        bucket = collector.bucket(FEATURE, HOUR)
        assert len(bucket) == 1
        assert bucket[0].value == Decimal("5")
        assert collector.rejections()[FEATURE] == {REASON_DEGRADED: 1}


class TestOutOfOrderArrival:
    """Arrival order decides the *selection*; it must not decide the *identity*.

    The collector's docstring justifies "first valid reading received" by replay
    (Astra, revisão do fix-pass, item b), and Astra asked for the test that
    actually exercises a stream whose arrival order differs from chronological
    order — the case where "first received" and "earliest instant" disagree.
    Two claims are separable and both are pinned here: which *value* is kept
    depends on arrival order and is allowed to, while the revision's statistics
    and ``input_fingerprint`` must not, or a retry that consumed the same
    readings in another order would land as a second revision instead of
    colliding on ``uq_feature_baselines_revision``.
    """

    def test_the_first_reading_received_wins_even_when_it_is_chronologically_later(self) -> None:
        # 14:03:40 arrives before 14:03:10. "First" is arrival order, not the
        # earliest instant inside the minute, and this is the case that tells
        # the two apart: the :40 value stays.
        collector = ObservationCollector(MARKET, [FEATURE])
        base = datetime(2026, 9, 4, HOUR, 3, tzinfo=UTC)
        collector.add(vector(base.replace(second=40), "9"))
        collector.add(vector(base.replace(second=10), "5"))

        bucket = collector.bucket(FEATURE, HOUR)
        assert len(bucket) == 1
        assert bucket[0].value == Decimal("9")
        assert bucket[0].ts == base
        assert collector.rejections()[FEATURE] == {REASON_DUPLICATE_MINUTE: 1}

    def test_a_minute_that_arrives_late_still_lands_in_its_bucket(self) -> None:
        # Nothing about a bucket depends on the stream being monotonic: an event
        # replayed out of order is a distinct minute and is kept as one.
        collector = ObservationCollector(MARKET, [FEATURE])
        base = datetime(2026, 9, 4, HOUR, 0, tzinfo=UTC)
        for minute in (5, 3, 9, 1):
            collector.add(vector(base + timedelta(minutes=minute), "10"))

        bucket = collector.bucket(FEATURE, HOUR)
        assert len(bucket) == 4
        assert {item.ts.minute for item in bucket} == {1, 3, 5, 9}
        assert collector.rejections() == {}

    def test_arrival_order_does_not_change_the_revision_it_computes(self) -> None:
        # Same readings, reversed stream: same population, same statistics and —
        # the one that matters for ``ON CONFLICT DO NOTHING`` — same digest.
        # ``input_fingerprint`` sorts the observations for exactly this reason.
        minutes = good_minutes(120)
        forward = ObservationCollector(MARKET, [FEATURE])
        backward = ObservationCollector(MARKET, [FEATURE])
        for index, minute in enumerate(minutes):
            forward.add(vector(minute, str(index)))
        for index, minute in reversed(list(enumerate(minutes))):
            backward.add(vector(minute, str(index)))

        def revision_of(collector: ObservationCollector) -> BaselineRevision:
            revision = compute_revision(
                key=BaselineKey(market_id=MARKET, feature=FEATURE, hour_of_day=HOUR),
                feature_version=1,
                source=BaselineSource.LIVE,
                window_start=DAY_ONE,
                window_end=DAY_ONE + timedelta(days=7),
                available_at=DAY_ONE + timedelta(days=7),
                observations=collector.bucket(FEATURE, HOUR),
                expected_size=420,
            )
            assert isinstance(revision, BaselineRevision)
            return revision

        first, second = revision_of(forward), revision_of(backward)
        assert first.sample_size == second.sample_size == 120
        assert first.median == second.median
        assert first.mad == second.mad
        assert first.input_fingerprint == second.input_fingerprint
