"""Median/MAD of one bucket, its counts, its gate and its fingerprint.

Every expected number here was computed by hand from a series small enough to
check on paper: a baseline that "looks right" is exactly the kind of number the
brief forbids.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import BaselineSampling, BaselineSource
from hunter_indicators.baselines import (
    ALGO_VERSION,
    BaselineGate,
    BaselineKey,
    BaselineRevision,
    BaselineUnavailable,
    Observation,
    compute_revision,
    input_fingerprint,
    median,
    median_absolute_deviation,
)

MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")
HOUR = 14
WINDOW_END = datetime(2026, 9, 8, HOUR, 0, tzinfo=UTC)
WINDOW_START = WINDOW_END - timedelta(days=7)
AVAILABLE_AT = WINDOW_END + timedelta(minutes=1)
KEY = BaselineKey(market_id=MARKET, feature="relative_volume_1h", hour_of_day=HOUR)
GATE = BaselineGate(min_distinct_days=3, min_valid_observations=120, expected_size=420)


def observations(values: list[str], *, days: int = 7) -> tuple[Observation, ...]:
    """``values`` spread over ``days`` distinct days inside the 14:00 bucket."""
    out: list[Observation] = []
    for index, raw in enumerate(values):
        day = index % days
        minute = index // days
        ts = WINDOW_START + timedelta(days=day, minutes=minute)
        out.append(Observation(ts=ts, value=Decimal(raw)))
    return tuple(sorted(out, key=lambda o: o.ts))


def revision_of(values: list[str], *, days: int = 7) -> BaselineRevision | BaselineUnavailable:
    return compute_revision(
        key=KEY,
        feature_version=1,
        source=BaselineSource.LIVE,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        available_at=AVAILABLE_AT,
        observations=observations(values, days=days),
        expected_size=420,
    )


class TestMedianAndMad:
    def test_median_of_an_odd_sample_is_the_middle_value(self) -> None:
        assert median([Decimal(v) for v in ("13", "10", "12", "11", "100")]) == Decimal("12")

    def test_median_of_an_even_sample_is_the_midpoint(self) -> None:
        assert median([Decimal("10"), Decimal("12")]) == Decimal("11")

    def test_mad_is_the_median_of_the_absolute_deviations(self) -> None:
        values = [Decimal(v) for v in ("10", "11", "12", "13", "100")]
        # |x - 12| = 2, 1, 0, 1, 88 -> sorted 0, 1, 1, 2, 88 -> median 1
        assert median_absolute_deviation(values, Decimal("12")) == Decimal("1")

    def test_a_constant_sample_has_zero_mad(self) -> None:
        values = [Decimal("7")] * 9
        assert median_absolute_deviation(values, median(values)) == Decimal("0")


class TestRevision:
    def test_counts_coverage_and_statistics_of_a_full_bucket(self) -> None:
        revision = revision_of(["10"] * 210 + ["20"] * 210)
        assert isinstance(revision, BaselineRevision)
        assert revision.sample_size == 420
        assert revision.expected_size == 420
        assert revision.distinct_days == 7
        assert revision.coverage == Decimal("1.000000")
        assert revision.median == Decimal("15.0000000000")
        # |x - 15| = 5 for every observation
        assert revision.mad == Decimal("5.0000000000")
        assert revision.algo_version == ALGO_VERSION
        assert revision.sampling is BaselineSampling.PER_MINUTE

    def test_statistics_are_quantized_to_the_persisted_resolution(self) -> None:
        # The in-memory number must already be the one NUMERIC(28,10) can hold,
        # or a replay from the database would disagree with a replay from memory
        # (Astra, T2.3 design review, must-fix "replay numerico"). Here the exact
        # median is 1e-10 and the exact MAD is 5e-11 — half of the last digit the
        # column keeps, so it stores as 0 and the detector must take the
        # ``mad_zero`` branch in **both** replays, not only in the one that came
        # back from Postgres.
        revision = revision_of(["0.00000000005"] * 200 + ["0.00000000015"] * 200)
        assert isinstance(revision, BaselineRevision)
        assert revision.median == Decimal("0.0000000001")
        assert revision.mad == Decimal("0")
        assert revision.median.as_tuple().exponent == -10
        assert revision.mad.as_tuple().exponent == -10

    def test_an_empty_bucket_has_no_revision_and_says_why(self) -> None:
        revision = revision_of([])
        assert isinstance(revision, BaselineUnavailable)
        assert revision.reason == "no_observations"
        assert revision.sample_size == 0
        assert revision.coverage == Decimal("0.000000")

    def test_a_thin_bucket_is_computed_and_the_gate_refuses_it(self) -> None:
        revision = revision_of(["10"] * 119, days=7)
        assert isinstance(revision, BaselineRevision)
        assert revision.sample_size == 119
        assert revision.usable_under(GATE) is False
        assert revision.gate_reason(GATE) == "insufficient_history"

    def test_a_bucket_over_both_thresholds_is_usable(self) -> None:
        revision = revision_of(["10"] * 120, days=3)
        assert isinstance(revision, BaselineRevision)
        assert revision.distinct_days == 3
        assert revision.usable_under(GATE) is True
        assert revision.gate_reason(GATE) is None

    def test_enough_observations_over_too_few_days_is_still_refused(self) -> None:
        revision = revision_of(["10"] * 120, days=2)
        assert isinstance(revision, BaselineRevision)
        assert revision.distinct_days == 2
        assert revision.usable_under(GATE) is False

    def test_an_observation_outside_the_window_is_a_caller_bug(self) -> None:
        with pytest.raises(ValueError, match="outside the window"):
            compute_revision(
                key=KEY,
                feature_version=1,
                source=BaselineSource.LIVE,
                window_start=WINDOW_START,
                window_end=WINDOW_END,
                available_at=AVAILABLE_AT,
                observations=(Observation(ts=WINDOW_END + timedelta(minutes=1), value=Decimal(1)),),
                expected_size=420,
            )

    def test_an_observation_of_another_hour_is_a_caller_bug(self) -> None:
        with pytest.raises(ValueError, match="hour"):
            compute_revision(
                key=KEY,
                feature_version=1,
                source=BaselineSource.LIVE,
                window_start=WINDOW_START,
                window_end=WINDOW_END,
                available_at=AVAILABLE_AT,
                observations=(Observation(ts=WINDOW_START + timedelta(hours=1), value=Decimal(1)),),
                expected_size=420,
            )

    def test_two_observations_of_the_same_minute_are_a_caller_bug(self) -> None:
        ts = WINDOW_START + timedelta(minutes=3)
        with pytest.raises(ValueError, match="twice"):
            compute_revision(
                key=KEY,
                feature_version=1,
                source=BaselineSource.LIVE,
                window_start=WINDOW_START,
                window_end=WINDOW_END,
                available_at=AVAILABLE_AT,
                observations=(
                    Observation(ts=ts, value=Decimal(1)),
                    Observation(ts=ts, value=Decimal(2)),
                ),
                expected_size=420,
            )

    def test_available_at_before_window_end_is_refused(self) -> None:
        with pytest.raises(ValueError, match="available_at"):
            compute_revision(
                key=KEY,
                feature_version=1,
                source=BaselineSource.LIVE,
                window_start=WINDOW_START,
                window_end=WINDOW_END,
                available_at=WINDOW_END - timedelta(minutes=1),
                observations=observations(["10"] * 10),
                expected_size=420,
            )


class TestFingerprint:
    def test_the_same_input_set_fingerprints_the_same(self) -> None:
        sample = observations(["10", "11", "12"])
        first = input_fingerprint(
            key=KEY,
            feature_version=1,
            algo_version=ALGO_VERSION,
            sampling=BaselineSampling.PER_MINUTE,
            source=BaselineSource.LIVE,
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            expected_size=420,
            observations=sample,
        )
        second = input_fingerprint(
            key=KEY,
            feature_version=1,
            algo_version=ALGO_VERSION,
            sampling=BaselineSampling.PER_MINUTE,
            source=BaselineSource.LIVE,
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            expected_size=420,
            observations=tuple(reversed(sample)),
        )
        assert first == second

    def test_a_different_observation_set_fingerprints_differently(self) -> None:
        first = revision_of(["10", "11", "12"])
        second = revision_of(["10", "11", "13"])
        assert isinstance(first, BaselineRevision)
        assert isinstance(second, BaselineRevision)
        assert first.input_fingerprint != second.input_fingerprint

    def test_publishing_time_is_not_part_of_the_identity(self) -> None:
        # A retry of the same refresh must collide on
        # ``uq_feature_baselines_revision`` instead of writing a second revision.
        base = revision_of(["10", "11", "12"])
        later = compute_revision(
            key=KEY,
            feature_version=1,
            source=BaselineSource.LIVE,
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            available_at=AVAILABLE_AT + timedelta(hours=3),
            observations=observations(["10", "11", "12"]),
            expected_size=420,
        )
        assert isinstance(base, BaselineRevision)
        assert isinstance(later, BaselineRevision)
        assert base.input_fingerprint == later.input_fingerprint


class TestGateFromWeights:
    def test_the_gate_comes_from_the_weight_vector(self) -> None:
        gate = BaselineGate.from_weights(
            {
                "baseline_gate": {
                    "min_distinct_days": 3,
                    "min_valid_observations": 120,
                    "expected_size": 420,
                }
            }
        )
        assert gate == GATE

    def test_a_weight_vector_without_the_block_is_refused(self) -> None:
        with pytest.raises(KeyError):
            BaselineGate.from_weights({"components": {}})


class TestAstraDiffReviewMinuteIdentity:
    """Regression for finding 4: ``per_minute`` means one per minute."""

    def test_two_readings_of_the_same_minute_are_refused(self) -> None:
        # The vector's ``ts`` is ``ctx.as_of``, the instant of *processing*, so a
        # scanner recomputing 14:03 twice a second apart would otherwise push 60
        # "observations" of one minute into the population and clear the gate
        # without ever having seen 120 minutes.
        base = WINDOW_START + timedelta(minutes=3)
        with pytest.raises(ValueError, match="twice"):
            compute_revision(
                key=KEY,
                feature_version=1,
                source=BaselineSource.LIVE,
                window_start=WINDOW_START,
                window_end=WINDOW_END,
                available_at=AVAILABLE_AT,
                observations=(
                    Observation(ts=base, value=Decimal(1)),
                    Observation(ts=base + timedelta(seconds=1), value=Decimal(2)),
                ),
                expected_size=420,
            )

    def test_two_readings_of_different_minutes_are_fine(self) -> None:
        base = WINDOW_START + timedelta(minutes=3)
        revision = compute_revision(
            key=KEY,
            feature_version=1,
            source=BaselineSource.LIVE,
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            available_at=AVAILABLE_AT,
            observations=(
                Observation(ts=base, value=Decimal(1)),
                Observation(ts=base + timedelta(minutes=1, seconds=1), value=Decimal(2)),
            ),
            expected_size=420,
        )
        assert isinstance(revision, BaselineRevision)
        assert revision.sample_size == 2


class TestCrossReviewHalfOpenWindow:
    """The window is ``[window_start, window_end)`` and the row fits the CHECKs.

    A closed window counts the bucket whose hour *is* ``window_end``'s twice at
    the edges: 421 observations in seven days against ``expected_size = 420``,
    ``coverage = 1.002381``. Postgres refuses both (``CHECK sample_size <=
    expected_size``, ``coverage BETWEEN 0 AND 1``) and, because the adapter
    inserts in one batch, the whole market's bootstrap aborts. Half-open also
    lines up with the projection cut ``window_end < observation_ts``: the
    revision of hour H is exactly the minutes of hour H, and never the first
    minute of the next window.
    """

    def natural_window(self) -> tuple[datetime, datetime]:
        """Seven days ending on an hour boundary — what the hourly refresh uses."""
        end = datetime(2026, 9, 8, 0, 0, tzinfo=UTC)
        return end - timedelta(days=7), end

    def per_minute(self) -> dict[int, list[Observation]]:
        """One observation every minute of the window, bucketed by UTC hour."""
        start, end = self.natural_window()
        buckets: dict[int, list[Observation]] = {}
        minute = start
        while minute < end:
            buckets.setdefault(minute.hour, []).append(
                Observation(ts=minute, value=Decimal(minute.minute))
            )
            minute += timedelta(minutes=1)
        return buckets

    def test_every_hour_bucket_holds_exactly_the_expected_size(self) -> None:
        start, end = self.natural_window()
        buckets = self.per_minute()
        assert sorted(buckets) == list(range(24))
        for hour, sample in buckets.items():
            revision = compute_revision(
                key=BaselineKey(market_id=MARKET, feature="relative_volume_1h", hour_of_day=hour),
                feature_version=1,
                source=BaselineSource.LIVE,
                window_start=start,
                window_end=end,
                available_at=end + timedelta(minutes=1),
                observations=tuple(sample),
                expected_size=420,
            )
            assert isinstance(revision, BaselineRevision)
            # the two CHECK constraints of ``feature_baselines``
            assert revision.sample_size == 420
            assert revision.sample_size <= revision.expected_size
            assert revision.coverage == Decimal("1.000000")
            assert Decimal(0) <= revision.coverage <= Decimal(1)
            assert revision.distinct_days == 7

    def test_an_observation_at_window_end_is_outside_the_window(self) -> None:
        start, end = self.natural_window()
        with pytest.raises(ValueError, match=r"outside the window"):
            compute_revision(
                key=BaselineKey(market_id=MARKET, feature="relative_volume_1h", hour_of_day=0),
                feature_version=1,
                source=BaselineSource.LIVE,
                window_start=start,
                window_end=end,
                available_at=end,
                observations=(Observation(ts=end, value=Decimal(1)),),
                expected_size=420,
            )

    def test_the_window_is_spelled_as_half_open_in_the_message(self) -> None:
        start, end = self.natural_window()
        with pytest.raises(ValueError, match=r"\[.*, .*\)"):
            compute_revision(
                key=BaselineKey(market_id=MARKET, feature="relative_volume_1h", hour_of_day=0),
                feature_version=1,
                source=BaselineSource.LIVE,
                window_start=start,
                window_end=end,
                available_at=end,
                observations=(Observation(ts=end, value=Decimal(1)),),
                expected_size=420,
            )

    def test_more_observations_than_expected_is_a_caller_bug(self) -> None:
        # ``sample_size <= expected_size`` is a CHECK: a row that breaks it takes
        # the whole batch down, so it has to fail here, on the caller's side.
        sample = observations(["10"] * 421)
        with pytest.raises(ValueError, match="expected_size"):
            compute_revision(
                key=KEY,
                feature_version=1,
                source=BaselineSource.LIVE,
                window_start=WINDOW_START,
                window_end=WINDOW_END,
                available_at=AVAILABLE_AT,
                observations=sample,
                expected_size=420,
            )

    def test_exactly_the_expected_size_is_allowed(self) -> None:
        revision = revision_of(["10"] * 420)
        assert isinstance(revision, BaselineRevision)
        assert revision.sample_size == 420


class TestAstraFixesReviewRowInvariants:
    """The row itself refuses what the CHECK constraints refuse.

    ``compute_revision`` guards the computed path, but ``BaselineRevision`` is a
    plain dataclass and ``insert_revisions`` serialises whatever it is handed:
    Astra built one with ``sample_size = 421`` and ``coverage = 1.002381`` by
    hand and the INSERT compiled. Postgres would still refuse it — and take the
    batch with it — so the invariant belongs to the object, not only to the
    function that usually builds it.
    """

    def row(self, **overrides: object) -> BaselineRevision:
        base: dict[str, object] = {
            "key": KEY,
            "feature_version": 1,
            "algo_version": ALGO_VERSION,
            "sampling": BaselineSampling.PER_MINUTE,
            "source": BaselineSource.LIVE,
            "window_start": WINDOW_START,
            "window_end": WINDOW_END,
            "available_at": AVAILABLE_AT,
            "median": Decimal("1.0000000000"),
            "mad": Decimal("0.5000000000"),
            "sample_size": 420,
            "expected_size": 420,
            "distinct_days": 7,
            "coverage": Decimal("1.000000"),
            "input_fingerprint": "fp",
        }
        base.update(overrides)
        return BaselineRevision(**base)  # type: ignore[arg-type]

    def test_a_full_bucket_is_a_valid_row(self) -> None:
        assert self.row().sample_size == 420

    def test_a_sample_over_the_expected_size_is_refused(self) -> None:
        with pytest.raises(ValueError, match="expected_size"):
            self.row(sample_size=421, coverage=Decimal("1.002381"))

    def test_a_coverage_over_one_is_refused(self) -> None:
        with pytest.raises(ValueError, match="coverage"):
            self.row(coverage=Decimal("1.002381"))

    def test_a_negative_coverage_is_refused(self) -> None:
        with pytest.raises(ValueError, match="coverage"):
            self.row(coverage=Decimal("-0.000001"))

    def test_more_distinct_days_than_observations_is_refused(self) -> None:
        with pytest.raises(ValueError, match="distinct_days"):
            self.row(sample_size=3, coverage=Decimal("0.007143"), distinct_days=7)

    def test_an_expected_size_of_zero_is_a_caller_bug(self) -> None:
        with pytest.raises(ValueError, match="expected_size"):
            compute_revision(
                key=KEY,
                feature_version=1,
                source=BaselineSource.LIVE,
                window_start=WINDOW_START,
                window_end=WINDOW_END,
                available_at=AVAILABLE_AT,
                observations=(),
                expected_size=0,
            )
