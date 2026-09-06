"""The causal cut, the deterministic selection, the retry and the replay door."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import BaselineSampling, BaselineSource
from hunter_indicators.baselines import (
    REASON_INSUFFICIENT_HISTORY,
    REASON_NO_BASELINE,
    REASON_VERSION_MISMATCH,
    BaselineCut,
    BaselineGate,
    BaselineKey,
    BaselineProjection,
    BaselineRequest,
    BaselineRevision,
    BaselineStore,
    InMemoryBaselineStore,
    StoredBaseline,
)

MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")
OTHER_MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000002")
FEATURE = "relative_volume_1h"
HOUR = 10
GATE = BaselineGate(min_distinct_days=3, min_valid_observations=120, expected_size=420)
KEY = BaselineKey(market_id=MARKET, feature=FEATURE, hour_of_day=HOUR)


def revision(
    *,
    window_end: datetime,
    available_at: datetime,
    median: str = "2",
    mad: str = "0.5",
    sample_size: int = 400,
    distinct_days: int = 7,
    fingerprint: str = "fp-a",
    key: BaselineKey = KEY,
    feature_version: int = 1,
    source: BaselineSource = BaselineSource.LIVE,
) -> BaselineRevision:
    return BaselineRevision(
        key=key,
        feature_version=feature_version,
        algo_version="median_mad_v1",
        sampling=BaselineSampling.PER_MINUTE,
        source=source,
        window_start=window_end - timedelta(days=7),
        window_end=window_end,
        available_at=available_at,
        median=Decimal(median),
        mad=Decimal(mad),
        sample_size=sample_size,
        expected_size=420,
        distinct_days=distinct_days,
        coverage=Decimal(sample_size) / Decimal(420),
        input_fingerprint=fingerprint,
    )


class TestInMemoryStoreIsThePort:
    def test_the_in_memory_store_satisfies_the_protocol(self) -> None:
        store: BaselineStore = InMemoryBaselineStore()
        assert store is not None

    async def test_a_retry_returns_the_row_that_is_already_stored(self) -> None:
        store = InMemoryBaselineStore()
        row = revision(
            window_end=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
            available_at=datetime(2026, 9, 8, 10, 5, tzinfo=UTC),
        )
        first = await store.append([row])
        second = await store.append([row])
        assert first[0].baseline_id == second[0].baseline_id
        assert len(await store.load_ids([first[0].baseline_id])) == 1

    async def test_a_recomputation_lands_as_a_new_revision(self) -> None:
        store = InMemoryBaselineStore()
        window_end = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
        first = await store.append(
            [revision(window_end=window_end, available_at=window_end, fingerprint="fp-a")]
        )
        second = await store.append(
            [
                revision(
                    window_end=window_end,
                    available_at=window_end + timedelta(hours=1),
                    fingerprint="fp-b",
                )
            ]
        )
        assert first[0].baseline_id != second[0].baseline_id

    async def test_another_algorithm_is_refused_by_the_store_profile(self) -> None:
        store = InMemoryBaselineStore(algo_version="median_mad_v2")
        with pytest.raises(ValueError, match="another population"):
            await store.append(
                [
                    revision(
                        window_end=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
                        available_at=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
                    )
                ]
            )


class TestCausalCut:
    async def test_a_baseline_published_after_the_cut_is_not_returned(self) -> None:
        store = InMemoryBaselineStore()
        await store.append(
            [
                revision(
                    window_end=datetime(2026, 9, 8, 9, 0, tzinfo=UTC),
                    available_at=datetime(2026, 9, 8, 10, 3, tzinfo=UTC),
                )
            ]
        )
        cut = BaselineCut(
            as_of=datetime(2026, 9, 8, 10, 2, tzinfo=UTC),
            observation_ts=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
        )
        loaded = await store.load(
            [BaselineRequest(MARKET, FEATURE, 1, HOUR)],
            cut=cut,
        )
        assert loaded == ()

    async def test_a_baseline_containing_the_observation_is_not_returned(self) -> None:
        # The scenario that needs both conditions: a feature of 10:00 processed at
        # 10:02 against a revision published at 10:01 whose window already folds
        # 10:00 in (docs/DATABASE.md 17.2).
        store = InMemoryBaselineStore()
        await store.append(
            [
                revision(
                    window_end=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
                    available_at=datetime(2026, 9, 8, 10, 1, tzinfo=UTC),
                )
            ]
        )
        cut = BaselineCut(
            as_of=datetime(2026, 9, 8, 10, 2, tzinfo=UTC),
            observation_ts=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
        )
        loaded = await store.load([BaselineRequest(MARKET, FEATURE, 1, HOUR)], cut=cut)
        assert loaded == ()

    async def test_an_older_admissible_revision_is_still_found(self) -> None:
        # Selection must apply the cut *before* picking the newest, or a future
        # revision hides an eligible one (Astra, T2.3 design review, item 1).
        store = InMemoryBaselineStore()
        old = await store.append(
            [
                revision(
                    window_end=datetime(2026, 9, 8, 9, 0, tzinfo=UTC),
                    available_at=datetime(2026, 9, 8, 9, 1, tzinfo=UTC),
                    fingerprint="fp-old",
                )
            ]
        )
        await store.append(
            [
                revision(
                    window_end=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
                    available_at=datetime(2026, 9, 8, 10, 1, tzinfo=UTC),
                    fingerprint="fp-new",
                )
            ]
        )
        cut = BaselineCut(
            as_of=datetime(2026, 9, 8, 10, 2, tzinfo=UTC),
            observation_ts=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
        )
        loaded = await store.load([BaselineRequest(MARKET, FEATURE, 1, HOUR)], cut=cut)
        assert [entry.baseline_id for entry in loaded] == [old[0].baseline_id]

    async def test_an_incompatible_feature_version_is_another_population(self) -> None:
        store = InMemoryBaselineStore()
        await store.append(
            [
                revision(
                    window_end=datetime(2026, 9, 8, 9, 0, tzinfo=UTC),
                    available_at=datetime(2026, 9, 8, 9, 1, tzinfo=UTC),
                    feature_version=2,
                )
            ]
        )
        cut = BaselineCut(
            as_of=datetime(2026, 9, 8, 10, 2, tzinfo=UTC),
            observation_ts=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
        )
        assert await store.load([BaselineRequest(MARKET, FEATURE, 1, HOUR)], cut=cut) == ()

    async def test_selection_is_deterministic_when_two_revisions_tie(self) -> None:
        store = InMemoryBaselineStore()
        window_end = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)
        available_at = datetime(2026, 9, 8, 9, 1, tzinfo=UTC)
        stored = await store.append(
            [
                revision(window_end=window_end, available_at=available_at, fingerprint="fp-1"),
                revision(window_end=window_end, available_at=available_at, fingerprint="fp-2"),
            ]
        )
        cut = BaselineCut(
            as_of=datetime(2026, 9, 8, 10, 2, tzinfo=UTC),
            observation_ts=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
        )
        loaded = await store.load([BaselineRequest(MARKET, FEATURE, 1, HOUR)], cut=cut)
        expected = max(stored, key=lambda entry: entry.selection_key)
        assert loaded[0].baseline_id == expected.baseline_id

    def test_a_cut_cannot_judge_a_future_observation(self) -> None:
        with pytest.raises(ValueError, match="after as_of"):
            BaselineCut(
                as_of=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
                observation_ts=datetime(2026, 9, 8, 10, 1, tzinfo=UTC),
            )


class TestProjection:
    def cut(self) -> BaselineCut:
        return BaselineCut(
            as_of=datetime(2026, 9, 8, 10, 2, tzinfo=UTC),
            observation_ts=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
        )

    def stored(self, **kwargs: object) -> StoredBaseline:
        return StoredBaseline(
            baseline_id=uuid.UUID("0199a1d0-0000-7000-8000-00000000000a"),
            revision=revision(
                window_end=datetime(2026, 9, 8, 9, 0, tzinfo=UTC),
                available_at=datetime(2026, 9, 8, 9, 1, tzinfo=UTC),
                **kwargs,  # type: ignore[arg-type]
            ),
        )

    def test_a_usable_baseline_answers_with_its_id(self) -> None:
        projection = BaselineProjection([self.stored()], cut=self.cut(), gate=GATE)
        lookup = projection.resolve(MARKET, FEATURE, self.cut().observation_ts)
        assert lookup.usable is True
        assert lookup.median == Decimal("2")
        assert lookup.baseline_id is not None

    def test_a_bucket_with_no_revision_says_no_baseline(self) -> None:
        projection = BaselineProjection([], cut=self.cut(), gate=GATE)
        lookup = projection.resolve(MARKET, FEATURE, self.cut().observation_ts)
        assert lookup.usable is False
        assert lookup.reason == REASON_NO_BASELINE

    def test_a_thin_revision_is_visible_and_refused(self) -> None:
        projection = BaselineProjection(
            [self.stored(sample_size=100, distinct_days=7)], cut=self.cut(), gate=GATE
        )
        lookup = projection.resolve(MARKET, FEATURE, self.cut().observation_ts)
        assert lookup.usable is False
        assert lookup.reason == REASON_INSUFFICIENT_HISTORY
        assert lookup.revision is not None
        assert lookup.revision.sample_size == 100

    def test_an_entry_that_violates_the_cut_raises(self) -> None:
        late = StoredBaseline(
            baseline_id=uuid.UUID("0199a1d0-0000-7000-8000-00000000000b"),
            revision=revision(
                window_end=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
                available_at=datetime(2026, 9, 8, 10, 1, tzinfo=UTC),
            ),
        )
        with pytest.raises(ValueError, match="violates the cut"):
            BaselineProjection([late], cut=self.cut(), gate=GATE)

    def test_two_revisions_of_one_bucket_are_a_caller_bug(self) -> None:
        first = self.stored()
        second = StoredBaseline(
            baseline_id=uuid.UUID("0199a1d0-0000-7000-8000-00000000000c"),
            revision=first.revision,
        )
        with pytest.raises(ValueError, match="Selection belongs to the store"):
            BaselineProjection([first, second], cut=self.cut(), gate=GATE)

    def test_asking_about_another_observation_raises(self) -> None:
        projection = BaselineProjection([self.stored()], cut=self.cut(), gate=GATE)
        with pytest.raises(ValueError, match="built for observation_ts"):
            projection.resolve(MARKET, FEATURE, datetime(2026, 9, 8, 9, 59, tzinfo=UTC))

    def test_another_market_does_not_borrow_a_baseline(self) -> None:
        projection = BaselineProjection([self.stored()], cut=self.cut(), gate=GATE)
        lookup = projection.resolve(OTHER_MARKET, FEATURE, self.cut().observation_ts)
        assert lookup.reason == REASON_NO_BASELINE


class TestReplay:
    async def test_the_same_ids_reproduce_the_same_numbers_tomorrow(self) -> None:
        # "reproduzir hoje o d de ontem com os mesmos baseline_ids": a newer
        # revision exists, and the replay still reads the row the envelope names.
        store = InMemoryBaselineStore()
        yesterday = await store.append(
            [
                revision(
                    window_end=datetime(2026, 9, 7, 10, 0, tzinfo=UTC),
                    available_at=datetime(2026, 9, 7, 10, 1, tzinfo=UTC),
                    median="2",
                    mad="0.5",
                    fingerprint="fp-yesterday",
                )
            ]
        )
        await store.append(
            [
                revision(
                    window_end=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
                    available_at=datetime(2026, 9, 8, 10, 1, tzinfo=UTC),
                    median="9",
                    mad="3",
                    fingerprint="fp-today",
                )
            ]
        )
        replayed = await store.load_ids([yesterday[0].baseline_id])
        assert replayed[0].revision.median == Decimal("2")
        assert replayed[0].revision.mad == Decimal("0.5")


class TestAstraDiffReviewVersions:
    """Regression for finding 7: the projection is bound to a version profile."""

    def cut(self) -> BaselineCut:
        return BaselineCut(
            as_of=datetime(2026, 9, 8, 10, 2, tzinfo=UTC),
            observation_ts=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
        )

    def stored(self, **kwargs: object) -> StoredBaseline:
        return StoredBaseline(
            baseline_id=uuid.UUID("0199a1d0-0000-7000-8000-00000000000d"),
            revision=revision(
                window_end=datetime(2026, 9, 8, 9, 0, tzinfo=UTC),
                available_at=datetime(2026, 9, 8, 9, 1, tzinfo=UTC),
                **kwargs,  # type: ignore[arg-type]
            ),
        )

    def test_a_revision_of_another_algorithm_is_refused_on_construction(self) -> None:
        entry = StoredBaseline(
            baseline_id=uuid.UUID("0199a1d0-0000-7000-8000-00000000000e"),
            revision=BaselineRevision(
                key=KEY,
                feature_version=1,
                algo_version="median_mad_v2",
                sampling=BaselineSampling.PER_MINUTE,
                source=BaselineSource.LIVE,
                window_start=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
                window_end=datetime(2026, 9, 8, 9, 0, tzinfo=UTC),
                available_at=datetime(2026, 9, 8, 9, 1, tzinfo=UTC),
                median=Decimal("2"),
                mad=Decimal("0.5"),
                sample_size=400,
                expected_size=420,
                distinct_days=7,
                coverage=Decimal("0.952381"),
                input_fingerprint="fp-other-algo",
            ),
        )
        with pytest.raises(ValueError, match="another population"):
            BaselineProjection([entry], cut=self.cut(), gate=GATE)

    def test_a_revision_of_another_feature_version_is_not_usable(self) -> None:
        # The cache/``load_ids`` path bypasses the SELECT that pins the version,
        # so the reader has to refuse it: a median of feature v2 is another
        # population, not a newer value of v1.
        projection = BaselineProjection([self.stored(feature_version=2)], cut=self.cut(), gate=GATE)
        lookup = projection.resolve(MARKET, FEATURE, self.cut().observation_ts, feature_version=1)
        assert lookup.usable is False
        assert lookup.reason == REASON_VERSION_MISMATCH

    def test_the_matching_version_is_usable(self) -> None:
        projection = BaselineProjection([self.stored()], cut=self.cut(), gate=GATE)
        lookup = projection.resolve(MARKET, FEATURE, self.cut().observation_ts, feature_version=1)
        assert lookup.usable is True
