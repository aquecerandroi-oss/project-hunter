"""Unit tests: dedupe and the two R sums behind the daily goal — brief T3.78.

No IO, no Postgres: every ``DailyOutcomeRow`` is built by hand.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_api.repositories.lab_daily_goal import DailyOutcomeRow
from hunter_api.services.lab_daily_goal_bets import dedupe_bets, sum_axis

pytestmark = pytest.mark.unit

MARKET = uuid.uuid4()
BAR = datetime(2026, 9, 10, 15, 0, tzinfo=UTC)
V1, V2, V3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
ACTIVATED_1 = datetime(2026, 8, 1, tzinfo=UTC)
ACTIVATED_2 = datetime(2026, 8, 5, tzinfo=UTC)
ACTIVATED_3 = datetime(2026, 8, 10, tzinfo=UTC)


def _row(
    *,
    version_id: uuid.UUID,
    activated_at: datetime | None,
    market_id: uuid.UUID = MARKET,
    bar: datetime = BAR,
    r: Decimal | None,
) -> DailyOutcomeRow:
    return DailyOutcomeRow(
        strategy_version_id=version_id,
        version_activated_at=activated_at,
        signal_id=uuid.uuid4(),
        market_id=market_id,
        source_bar_close=bar,
        exit_ts=bar,
        r_multiple=r,
        entry_ts=bar,
        virtual_entry=Decimal("100"),
        virtual_stop=Decimal("99"),
        meta={},
    )


class TestDedupeBets:
    def test_three_versions_on_the_same_bet_dedupe_to_one(self) -> None:
        rows = [
            _row(version_id=V1, activated_at=ACTIVATED_1, r=Decimal("1")),
            _row(version_id=V2, activated_at=ACTIVATED_2, r=Decimal("2")),
            _row(version_id=V3, activated_at=ACTIVATED_3, r=Decimal("3")),
        ]
        deduped = dedupe_bets(rows)
        assert len(deduped) == 1
        assert deduped[0].member_count == 3
        # The earliest-activated version wins, regardless of input order.
        assert deduped[0].winner.strategy_version_id == V1

    def test_dedupe_order_is_activation_not_query_order(self) -> None:
        rows = [
            _row(version_id=V3, activated_at=ACTIVATED_3, r=Decimal("9")),
            _row(version_id=V1, activated_at=ACTIVATED_1, r=Decimal("1")),
        ]
        assert dedupe_bets(rows)[0].winner.strategy_version_id == V1

    def test_a_version_with_no_activated_at_never_wins_over_one_that_has_it(self) -> None:
        rows = [
            _row(version_id=V2, activated_at=None, r=Decimal("5")),
            _row(version_id=V1, activated_at=ACTIVATED_1, r=Decimal("1")),
        ]
        assert dedupe_bets(rows)[0].winner.strategy_version_id == V1

    def test_ties_break_by_strategy_version_id_then_signal_id(self) -> None:
        low_id, high_id = sorted((uuid.uuid4(), uuid.uuid4()))
        rows = [
            _row(version_id=high_id, activated_at=ACTIVATED_1, r=Decimal("1")),
            _row(version_id=low_id, activated_at=ACTIVATED_1, r=Decimal("2")),
        ]
        assert dedupe_bets(rows)[0].winner.strategy_version_id == low_id

    def test_different_bars_are_different_bets(self) -> None:
        rows = [
            _row(version_id=V1, activated_at=ACTIVATED_1, bar=BAR, r=Decimal("1")),
            _row(
                version_id=V1, activated_at=ACTIVATED_1, bar=BAR.replace(minute=1), r=Decimal("1")
            ),
        ]
        assert len(dedupe_bets(rows)) == 2


class TestSumAxis:
    def test_pooled_counts_every_row_unique_counts_the_winner_once(self) -> None:
        rows = [
            _row(version_id=V1, activated_at=ACTIVATED_1, r=Decimal("1")),
            _row(version_id=V2, activated_at=ACTIVATED_2, r=Decimal("2")),
            _row(version_id=V3, activated_at=ACTIVATED_3, r=Decimal("3")),
        ]
        deduped = dedupe_bets(rows)
        sums = sum_axis(rows, deduped)
        assert sums.axis == "r_net"
        assert sums.pooled_r == Decimal("6")
        assert sums.pooled_priced == 3
        assert sums.unique_r == Decimal("1")  # V1's row, the winner
        assert sums.unique_bets == 1

    def test_funding_null_is_excluded_and_counted_not_zeroed(self) -> None:
        rows = [
            _row(version_id=V1, activated_at=ACTIVATED_1, r=None),
            _row(
                version_id=V1,
                activated_at=ACTIVATED_1,
                bar=BAR.replace(minute=2),
                market_id=MARKET,
                r=Decimal("2"),
            ),
        ]
        deduped = dedupe_bets(rows)
        sums = sum_axis(rows, deduped)
        assert sums.pooled_r == Decimal("2")
        assert sums.pooled_funding_null == 1
        assert sums.unique_funding_null == 1
        assert sums.unique_bets == 1

    def test_hit_rate_numerator_only_counts_positive_priced_bets(self) -> None:
        rows = [
            _row(version_id=V1, activated_at=ACTIVATED_1, bar=BAR, r=Decimal("1")),
            _row(
                version_id=V1, activated_at=ACTIVATED_1, bar=BAR.replace(minute=3), r=Decimal("-1")
            ),
            _row(
                version_id=V1, activated_at=ACTIVATED_1, bar=BAR.replace(minute=4), r=Decimal("0")
            ),
        ]
        sums = sum_axis(rows, dedupe_bets(rows))
        assert sums.unique_bets == 3
        assert sums.unique_wins == 1

    def test_empty_population_is_all_zero(self) -> None:
        sums = sum_axis([], [])
        assert sums.pooled_r == Decimal(0)
        assert sums.unique_r == Decimal(0)
        assert sums.unique_bets == 0
