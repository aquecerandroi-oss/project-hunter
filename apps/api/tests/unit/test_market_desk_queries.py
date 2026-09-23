"""T4.82: the ``spot/1`` desk trail — the queries behind
``GET /api/v1/orgs/{org_id}/markets/{exchange}/{symbol}/desk``.

The one that matters is the **positions** query. A point query ("what was open
at 11:45") would miss a position opened at 10:00 and still open — which is
precisely the row block A of the design §4 exists to show. So it is an
**interval intersection**: the position's own interval ``[entry_at, exit_at]``
(or ``[entry_at, ∞)`` while it is open) against the requested window
``[since, until)``.

The scenarios below are the truth table of that predicate, asserted on a pure
Python twin (:func:`position_intersects_window`) that the SQL is compiled
against in the same file — so the two can never drift without a red test.

Compiled SQL and pure functions; no database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects import postgresql

from hunter_api.repositories.market_desk import (
    build_desk_market_statement,
    build_desk_orders_statement,
    build_desk_positions_statement,
    position_intersects_window,
)

pytestmark = pytest.mark.unit

SYMBOL = "ZECUSDT"
# The design's own example: a cursor at 11:45 with the default +/- 15 min.
SINCE = datetime(2026, 9, 23, 11, 30, tzinfo=UTC)
UNTIL = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
TEN = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


class TestIntervalIntersection:
    """Each case names the position, not the operator — the operators are the
    implementation, the cases are the contract."""

    def test_opened_at_ten_and_still_open_appears_in_an_1145_window(self) -> None:
        """The design's headline case (§4A, §7a item 3). A point query would
        lose this row and the screen would say the desk held nothing."""
        assert position_intersects_window(entry_at=TEN, exit_at=None, since=SINCE, until=UNTIL)

    def test_opened_and_closed_before_the_window_does_not_appear(self) -> None:
        assert not position_intersects_window(
            entry_at=TEN, exit_at=TEN + timedelta(minutes=30), since=SINCE, until=UNTIL
        )

    def test_opened_before_and_closed_inside_the_window_appears(self) -> None:
        assert position_intersects_window(
            entry_at=TEN, exit_at=SINCE + timedelta(minutes=5), since=SINCE, until=UNTIL
        )

    def test_opened_and_closed_entirely_inside_the_window_appears(self) -> None:
        assert position_intersects_window(
            entry_at=SINCE + timedelta(minutes=1),
            exit_at=SINCE + timedelta(minutes=2),
            since=SINCE,
            until=UNTIL,
        )

    def test_opened_inside_and_still_open_appears(self) -> None:
        assert position_intersects_window(
            entry_at=SINCE + timedelta(minutes=1), exit_at=None, since=SINCE, until=UNTIL
        )

    def test_opened_after_the_window_does_not_appear(self) -> None:
        assert not position_intersects_window(
            entry_at=UNTIL + timedelta(minutes=1), exit_at=None, since=SINCE, until=UNTIL
        )

    def test_a_position_closed_exactly_at_since_appears(self) -> None:
        """``exit_at == since`` is the instant the window opens: the position
        was still alive then, so it belongs to the window."""
        assert position_intersects_window(entry_at=TEN, exit_at=SINCE, since=SINCE, until=UNTIL)

    def test_a_position_opened_exactly_at_until_belongs_to_the_next_window(self) -> None:
        """The window is half-open ``[since, until)`` everywhere in T4.82. With
        ``entry_at <= until`` this row would show up in two adjacent windows
        and the screen would count the same entry twice."""
        assert not position_intersects_window(
            entry_at=UNTIL, exit_at=None, since=SINCE, until=UNTIL
        )

    def test_a_position_opened_exactly_at_since_appears(self) -> None:
        assert position_intersects_window(entry_at=SINCE, exit_at=None, since=SINCE, until=UNTIL)


class TestPositionsStatement:
    def _sql(self) -> str:
        statement = build_desk_positions_statement(SYMBOL, since=SINCE, until=UNTIL, limit=500)
        return str(statement.compile(dialect=postgresql.dialect()))

    def test_it_is_an_intersection_and_not_a_point_query(self) -> None:
        sql = self._sql()
        assert "spot_positions.entry_at <" in sql
        assert "spot_positions.exit_at IS NULL" in sql
        assert "spot_positions.exit_at >=" in sql

    def test_the_open_leg_is_reached_through_an_or_not_a_status_filter(self) -> None:
        """Keying on ``status = 'open'`` instead of ``exit_at IS NULL`` would
        tie the read to a column the executor updates separately from the exit
        itself."""
        sql = self._sql()
        assert " OR " in sql
        assert "spot_positions.status =" not in sql

    def test_it_is_scoped_to_one_symbol(self) -> None:
        assert "spot_positions.market_symbol =" in self._sql()

    def test_it_is_bounded(self) -> None:
        assert "LIMIT" in self._sql()


class TestOrdersStatement:
    def _sql(self) -> str:
        statement = build_desk_orders_statement(SYMBOL, since=SINCE, until=UNTIL, limit=500)
        return str(statement.compile(dialect=postgresql.dialect()))

    def test_orders_are_a_point_in_time_and_cut_on_received_at(self) -> None:
        """An order is an instant, not an interval — no intersection here."""
        sql = self._sql()
        assert "spot_orders.received_at >=" in sql
        assert "spot_orders.received_at <" in sql

    def test_it_is_scoped_to_one_symbol_and_bounded(self) -> None:
        sql = self._sql()
        assert "spot_orders.market_symbol =" in sql
        assert "LIMIT" in sql

    def test_refusals_are_not_filtered_out(self) -> None:
        """ "Olhamos e recusamos" (§4A) is the most valuable line of the screen:
        a ``refused`` row must reach the client, never be hidden as noise."""
        sql = self._sql()
        where = sql.split("WHERE", 1)[1]
        assert "status" not in where


def test_the_desk_market_lookup_is_by_binance_symbol() -> None:
    sql = str(build_desk_market_statement(SYMBOL).compile(dialect=postgresql.dialect()))
    assert "spot_desk_markets.binance_symbol =" in sql


class TestTruncationIsNeverSilent:
    """Astra, review of T4.82, must-fix 1: a ``LIMIT`` that drops rows without
    saying so lets the screen conclude "nada estava vigente" from a page that
    simply ran out of room.

    The scenario she gave: a window holding 501 eligible positions where the
    oldest one is the one that was open at the cursor and the other 500 opened
    after it. Ordered newest-first, the oldest is exactly the row the cap
    drops — and it is the only one that answers the screen's question.

    The fix is not a different ordering (that only changes *which* facts
    vanish) but a flag: the reads ask for one row more than they will return,
    and say whether that extra row existed.
    """

    def test_the_statements_fetch_one_row_more_than_they_return(self) -> None:
        for build in (build_desk_positions_statement, build_desk_orders_statement):
            sql = str(
                build(SYMBOL, since=SINCE, until=UNTIL, limit=10).compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            )
            assert "LIMIT 11" in sql, f"{build.__name__} must probe for the row past the cap"


class TestTheOperatorsAreExact:
    """Astra, review of T4.82: ``"entry_at <" in sql`` also passes for
    ``entry_at <=``, so it does not actually pin the half-open boundary the
    Python twin implements."""

    def test_the_upper_bound_on_entry_at_is_strict(self) -> None:
        sql = str(
            build_desk_positions_statement(SYMBOL, since=SINCE, until=UNTIL, limit=10).compile(
                dialect=postgresql.dialect()
            )
        )
        assert "spot_positions.entry_at <=" not in sql
        assert "spot_positions.exit_at >" in sql
        assert "spot_positions.exit_at > " not in sql, "the exit bound is inclusive: >="

    def test_the_order_window_is_half_open_on_both_ends(self) -> None:
        sql = str(
            build_desk_orders_statement(SYMBOL, since=SINCE, until=UNTIL, limit=10).compile(
                dialect=postgresql.dialect()
            )
        )
        assert "spot_orders.received_at <=" not in sql
        assert "spot_orders.received_at >=" in sql
