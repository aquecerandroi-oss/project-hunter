"""The thin SQL adapter: what it asks Postgres, and what it does with the answer.

No database here on purpose — these are unit tests of the *statements* and of the
retry path. The statements are compiled against the real PostgreSQL dialect, so a
clause that would not compile fails here rather than in the scanner.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql.expression import ClauseElement

from hunter_core.domain.enums import BaselineSampling, BaselineSource
from hunter_indicators.baselines import (
    BaselineCut,
    BaselineKey,
    BaselineRequest,
    BaselineRevision,
    SqlBaselineStore,
    insert_revisions,
    select_projection,
)

MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")
FEATURE = "relative_volume_1h"
WINDOW_END = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)
CUT = BaselineCut(
    as_of=datetime(2026, 9, 8, 10, 2, tzinfo=UTC),
    observation_ts=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
)


def revision(fingerprint: str = "fp-a") -> BaselineRevision:
    return BaselineRevision(
        key=BaselineKey(market_id=MARKET, feature=FEATURE, hour_of_day=10),
        feature_version=1,
        algo_version="median_mad_v1",
        sampling=BaselineSampling.PER_MINUTE,
        source=BaselineSource.LIVE,
        window_start=WINDOW_END - timedelta(days=7),
        window_end=WINDOW_END,
        available_at=WINDOW_END + timedelta(minutes=1),
        median=Decimal("2.0000000000"),
        mad=Decimal("0.5000000000"),
        sample_size=400,
        expected_size=420,
        distinct_days=7,
        coverage=Decimal("0.952381"),
        input_fingerprint=fingerprint,
    )


def compiled(statement: ClauseElement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


class FakeResult:
    def __init__(self, rows: Sequence[Mapping[str, Any]]) -> None:
        self._rows: list[Mapping[str, Any]] = list(rows)

    def mappings(self) -> Sequence[Mapping[str, Any]]:
        return self._rows


class FakeConnection:
    """Records the statements and answers with rows a test hands it."""

    def __init__(self, answers: Sequence[Sequence[Mapping[str, Any]]] = ()) -> None:
        self.executed: list[str] = []
        self._answers: list[Sequence[Mapping[str, Any]]] = list(answers)

    async def execute(
        self, statement: ClauseElement, *args: object, **kwargs: object
    ) -> FakeResult:
        del args, kwargs
        self.executed.append(compiled(statement))
        empty: Sequence[Mapping[str, Any]] = []
        rows = self._answers.pop(0) if self._answers else empty
        return FakeResult(rows)


def row_of(baseline_id: uuid.UUID, revision_: BaselineRevision) -> dict[str, Any]:
    row = dict(revision_.as_row())
    row["id"] = baseline_id
    row["source"] = revision_.source
    row["sampling"] = revision_.sampling
    return row


class TestSelectStatement:
    def test_the_select_applies_both_halves_of_the_causal_cut(self) -> None:
        sql = compiled(
            select_projection(
                [BaselineRequest(MARKET, FEATURE, 1, 10)],
                cut=CUT,
                algo_version="median_mad_v1",
                sampling=BaselineSampling.PER_MINUTE,
            )
        )
        assert "available_at <=" in sql
        assert "window_end <" in sql

    def test_the_select_picks_one_revision_per_bucket_deterministically(self) -> None:
        sql = compiled(
            select_projection(
                [BaselineRequest(MARKET, FEATURE, 1, 10)],
                cut=CUT,
                algo_version="median_mad_v1",
                sampling=BaselineSampling.PER_MINUTE,
            )
        )
        assert "DISTINCT ON" in sql
        # the same order the in-memory store's ``selection_key`` implements
        assert "available_at DESC" in sql
        assert "window_end DESC" in sql
        assert "feature_baselines.id DESC" in sql

    def test_the_projection_key_is_the_one_the_in_memory_store_uses(self) -> None:
        # ``DISTINCT ON`` has to name every column that identifies a bucket for
        # the reader. ``InMemoryBaselineStore._candidates`` matches on
        # ``feature_version`` and on the store's ``algo_version`` too, so a batch
        # asking for two versions of one feature would get two rows in memory and
        # one from Postgres — the same projection disagreeing with itself.
        sql = compiled(
            select_projection(
                [
                    BaselineRequest(MARKET, FEATURE, 1, 10),
                    BaselineRequest(MARKET, FEATURE, 2, 10),
                ],
                cut=CUT,
                algo_version="median_mad_v1",
                sampling=BaselineSampling.PER_MINUTE,
            )
        )
        assert (
            "DISTINCT ON (feature_baselines.market_id, feature_baselines.feature, "
            "feature_baselines.feature_version, feature_baselines.algo_version, "
            "feature_baselines.hour_of_day)" in sql
        )
        # the ORDER BY has to start with the DISTINCT ON key, or Postgres refuses
        assert (
            "ORDER BY feature_baselines.market_id, feature_baselines.feature, "
            "feature_baselines.feature_version, feature_baselines.algo_version, "
            "feature_baselines.hour_of_day, feature_baselines.available_at DESC" in sql
        )

    def test_the_select_pins_the_algorithm_and_the_sampling(self) -> None:
        sql = compiled(
            select_projection(
                [BaselineRequest(MARKET, FEATURE, 1, 10)],
                cut=CUT,
                algo_version="median_mad_v1",
                sampling=BaselineSampling.PER_MINUTE,
            )
        )
        assert "algo_version =" in sql
        assert "sampling =" in sql

    def test_the_feature_version_travels_with_the_feature(self) -> None:
        # Two features at different versions in one batch must not cross-select.
        sql = compiled(
            select_projection(
                [
                    BaselineRequest(MARKET, FEATURE, 1, 10),
                    BaselineRequest(MARKET, "atr_14_pct", 2, 10),
                ],
                cut=CUT,
                algo_version="median_mad_v1",
                sampling=BaselineSampling.PER_MINUTE,
            )
        )
        assert "feature_version" in sql
        assert "IN (" in sql


class TestInsertStatement:
    def test_the_insert_never_updates(self) -> None:
        sql = compiled(insert_revisions([revision()], ids=[uuid.uuid4()]))
        assert "ON CONFLICT" in sql
        assert "DO NOTHING" in sql
        assert "DO UPDATE" not in sql

    def test_the_insert_carries_every_column_of_the_revision(self) -> None:
        sql = compiled(insert_revisions([revision()], ids=[uuid.uuid4()]))
        for column in (
            "market_id",
            "feature",
            "feature_version",
            "algo_version",
            "hour_of_day",
            "window_start",
            "window_end",
            "available_at",
            "median",
            "mad",
            "sample_size",
            "expected_size",
            "distinct_days",
            "coverage",
            "source",
            "sampling",
            "input_fingerprint",
        ):
            assert column in sql


class TestAppendReturnsWhatIsStored:
    async def test_a_fresh_insert_returns_the_new_id(self) -> None:
        new_id = uuid.UUID("0199a1d0-0000-7000-8000-0000000000aa")
        connection = FakeConnection([[{"id": new_id, "input_fingerprint": "fp-a"}]])
        store = SqlBaselineStore(cast("AsyncConnection", connection))
        stored = await store.append([revision()])
        assert [entry.baseline_id for entry in stored] == [new_id]
        assert len(connection.executed) == 1

    async def test_a_collision_returns_the_id_already_in_the_archive(self) -> None:
        # The retry scenario: ON CONFLICT DO NOTHING returns nothing, and handing
        # the caller the uuid this process minted would put a dangling
        # baseline_id in an opportunity envelope.
        existing = uuid.UUID("0199a1d0-0000-7000-8000-0000000000bb")
        connection = FakeConnection([[], [row_of(existing, revision())]])
        store = SqlBaselineStore(cast("AsyncConnection", connection))
        stored = await store.append([revision()])
        assert [entry.baseline_id for entry in stored] == [existing]
        assert len(connection.executed) == 2

    async def test_a_revision_that_neither_inserted_nor_exists_is_refused(self) -> None:
        connection = FakeConnection([[], []])
        store = SqlBaselineStore(cast("AsyncConnection", connection))
        try:
            await store.append([revision()])
        except RuntimeError as error:
            assert "neither inserted nor found" in str(error)
        else:  # pragma: no cover - the assertion above is the contract
            raise AssertionError("a silent loss of a revision must not be possible")


class TestLoadMapsRowsBack:
    async def test_rows_become_stored_baselines(self) -> None:
        baseline_id = uuid.UUID("0199a1d0-0000-7000-8000-0000000000cc")
        connection = FakeConnection([[row_of(baseline_id, revision())]])
        store = SqlBaselineStore(cast("AsyncConnection", connection))
        loaded = await store.load([BaselineRequest(MARKET, FEATURE, 1, 10)], cut=CUT)
        assert loaded[0].baseline_id == baseline_id
        assert loaded[0].revision.median == Decimal("2.0000000000")
        assert loaded[0].revision.key.feature == FEATURE

    async def test_an_empty_request_asks_the_database_nothing(self) -> None:
        connection = FakeConnection()
        store = SqlBaselineStore(cast("AsyncConnection", connection))
        assert await store.load([], cut=CUT) == ()
        assert await store.load_ids([]) == ()
        assert await store.append([]) == ()
        assert connection.executed == []


class TestAstraDiffReview:
    """Regression for finding 3 of ``astra-review-T2.3-diff.md``."""

    async def test_a_collision_returns_the_revision_that_is_stored(self) -> None:
        # The retry carries the same fingerprint but a later ``available_at``.
        # Returning the attempted revision would announce a baseline as usable
        # from 10:01 when the archive says 09:01, and a projection built from
        # that answer would refuse a baseline that did exist.
        published = revision()
        retried = BaselineRevision(
            key=published.key,
            feature_version=published.feature_version,
            algo_version=published.algo_version,
            sampling=published.sampling,
            source=published.source,
            window_start=published.window_start,
            window_end=published.window_end,
            available_at=published.available_at + timedelta(hours=1),
            median=published.median,
            mad=published.mad,
            sample_size=published.sample_size,
            expected_size=published.expected_size,
            distinct_days=published.distinct_days,
            coverage=published.coverage,
            input_fingerprint=published.input_fingerprint,
        )
        existing = uuid.UUID("0199a1d0-0000-7000-8000-0000000000dd")
        connection = FakeConnection([[], [row_of(existing, published)]])
        store = SqlBaselineStore(cast("AsyncConnection", connection))
        stored = await store.append([retried])
        assert stored[0].baseline_id == existing
        assert stored[0].revision.available_at == published.available_at
