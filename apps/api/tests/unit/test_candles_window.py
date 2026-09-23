"""T4.82: ``since``/``until`` on ``GET /markets/{exchange}/{symbol}/candles``.

The statement is compiled to Postgres SQL and read — no database. What matters
and is asserted here:

- the pre-T4.82 contract is untouched: no bound given still means "the
  ``limit`` most recent final candles", still ordered oldest-first;
- ``since`` and ``until`` are a **half-open** ``[since, until)`` window, so two
  adjacent windows never show the same bar twice;
- ``before`` and ``until`` are both upper bounds and are simply ANDed — the
  effective cut is the earlier of the two, with no precedence rule to
  remember;
- the server-side cap is ``MAX_CANDLES_LIMIT`` bars *of the requested
  timeframe*, so it scales with the unit the caller asked for instead of being
  a number of days that means something different at 1m and at 1d.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects import postgresql

from hunter_api.repositories.markets import build_candles_statement
from hunter_api.routers.markets import MAX_CANDLES_LIMIT, candle_window_max_span
from hunter_api.time_window import TimeWindowTooWideError, TimeWindowUnorderedError, check_window
from hunter_core.domain.enums import Timeframe

pytestmark = pytest.mark.unit

MARKET_ID = uuid.uuid4()
NOW = datetime(2026, 9, 23, 14, 45, tzinfo=UTC)


def _sql(**kwargs: object) -> str:
    statement = build_candles_statement(
        MARKET_ID,
        Timeframe.M15,
        limit=500,
        before=kwargs.get("before"),  # type: ignore[arg-type]
        since=kwargs.get("since"),  # type: ignore[arg-type]
        until=kwargs.get("until"),  # type: ignore[arg-type]
    )
    return str(statement.compile(dialect=postgresql.dialect()))


class TestStatement:
    def test_without_bounds_it_is_the_query_that_shipped_before_t4_82(self) -> None:
        sql = _sql()
        assert "candles.is_final IS true" in sql
        assert "candles.open_time <" not in sql
        assert "candles.open_time >=" not in sql
        assert "ORDER BY candles.open_time DESC" in sql

    def test_since_is_inclusive_and_until_is_exclusive(self) -> None:
        sql = _sql(since=NOW - timedelta(hours=1), until=NOW)
        assert "candles.open_time >= " in sql, "since is inclusive"
        assert "candles.open_time < " in sql, "until is exclusive — a half-open window"

    def test_before_and_until_are_both_applied(self) -> None:
        """Two upper bounds, ANDed: the effective cut is the earlier one. No
        precedence rule means no way to get it wrong."""
        sql = _sql(before=NOW, until=NOW - timedelta(hours=2))
        assert sql.count("candles.open_time < ") == 2

    def test_only_final_candles_are_ever_returned(self) -> None:
        assert "candles.is_final IS true" in _sql(since=NOW - timedelta(hours=1), until=NOW)


class TestCap:
    def test_the_cap_is_max_limit_bars_of_the_requested_timeframe(self) -> None:
        assert candle_window_max_span(Timeframe.M1) == timedelta(minutes=MAX_CANDLES_LIMIT)
        assert candle_window_max_span(Timeframe.M15) == timedelta(minutes=15 * MAX_CANDLES_LIMIT)
        assert candle_window_max_span(Timeframe.H1) == timedelta(hours=MAX_CANDLES_LIMIT)

    def test_a_window_of_exactly_the_cap_is_accepted(self) -> None:
        span = candle_window_max_span(Timeframe.M15)
        check_window(since=NOW - span, until=NOW, now=NOW, max_span=span)

    def test_one_bar_past_the_cap_is_refused_rather_than_truncated(self) -> None:
        span = candle_window_max_span(Timeframe.M15)
        with pytest.raises(TimeWindowTooWideError):
            check_window(
                since=NOW - span - timedelta(minutes=15),
                until=NOW,
                now=NOW,
                max_span=span,
            )

    def test_an_inverted_window_is_refused(self) -> None:
        span = candle_window_max_span(Timeframe.M15)
        with pytest.raises(TimeWindowUnorderedError):
            check_window(since=NOW, until=NOW - timedelta(minutes=15), now=NOW, max_span=span)
