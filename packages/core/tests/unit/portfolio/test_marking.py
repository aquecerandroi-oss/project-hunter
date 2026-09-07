"""Marking positions — the arithmetic, without a database.

The rule this file exists for: **a missing price is never zero.** A position
marked at zero would shrink the exposure, the drawdown and the daily loss at
exactly the moment the data is worst, which is when the limits matter most.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from hunter_core.db.repositories.ledger import PositionRow
from hunter_core.portfolio.ledger import NonLongPosition, mark_positions

pytestmark = pytest.mark.unit

_MARKET = uuid.uuid4()
_NO_COST = Decimal(0)
"""Most cases below are about the mark, not the cost, so they declare zero — an
explicit hypothesis, which is the whole point of the parameter having no default."""


def _row(
    *,
    qty: Decimal = Decimal(2),
    entry: Decimal = Decimal(100),
    stop: Decimal | None = Decimal(90),
    durable_mark: Decimal | None = Decimal(110),
    direction: str = "long",
) -> PositionRow:
    return PositionRow(
        position_id=uuid.uuid4(),
        market_id=_MARKET,
        exchange="binance",
        symbol="HTRUSDT",
        market_type="spot",
        base_asset="HTR",
        quote_asset="USDT",
        direction=direction,
        status="open",
        is_residual=False,
        qty=qty,
        avg_entry_price=entry,
        stop_price=stop,
        durable_mark_price=durable_mark,
    )


class TestTheLivePriceIsUsedWhenItIsValid:
    def test_notional_and_unrealised_come_from_the_live_price(self) -> None:
        (marked,) = mark_positions((_row(),), {_MARKET: Decimal(120)}, exit_cost_rate=_NO_COST)
        assert marked.is_stale is False
        assert marked.mark_price == Decimal(120)
        assert marked.notional == Decimal(240)
        assert marked.unrealized_pnl == Decimal(40)

    def test_planned_risk_is_the_distance_to_the_stop_at_the_live_price(self) -> None:
        (marked,) = mark_positions((_row(),), {_MARKET: Decimal(120)}, exit_cost_rate=_NO_COST)
        assert marked.planned_risk_quote == Decimal(60)

    def test_a_stop_already_above_the_price_commits_no_further_loss(self) -> None:
        (marked,) = mark_positions(
            (_row(stop=Decimal(130)),), {_MARKET: Decimal(120)}, exit_cost_rate=_NO_COST
        )
        assert marked.planned_risk_quote == Decimal(0)


class TestAMissingPriceIsNeverZero:
    def test_an_absent_price_falls_back_to_the_last_durable_mark(self) -> None:
        (marked,) = mark_positions((_row(),), {}, exit_cost_rate=_NO_COST)
        assert marked.is_stale is True
        assert marked.mark_price == Decimal(110)
        assert marked.notional == Decimal(220)

    def test_a_zero_price_is_not_a_price(self) -> None:
        (marked,) = mark_positions((_row(),), {_MARKET: Decimal(0)}, exit_cost_rate=_NO_COST)
        assert marked.is_stale is True
        assert marked.mark_price == Decimal(110)

    def test_a_negative_price_is_not_a_price(self) -> None:
        (marked,) = mark_positions((_row(),), {_MARKET: Decimal(-5)}, exit_cost_rate=_NO_COST)
        assert marked.is_stale is True
        assert marked.notional == Decimal(220)

    def test_without_any_mark_the_entry_price_carries_the_position(self) -> None:
        (marked,) = mark_positions((_row(durable_mark=None),), {}, exit_cost_rate=_NO_COST)
        assert marked.is_stale is True
        assert marked.mark_price == Decimal(100)
        assert marked.notional == Decimal(200)
        assert marked.unrealized_pnl == Decimal(0)


class TestTheExitCostIsPartOfThePlannedLoss:
    """Astra, review of the T3.3 diff, must-fix B: 190 of stop distance plus 2 of
    exit cost must not fit under a ceiling of 200 because the 2 was dropped."""

    def test_the_declared_exit_cost_is_added_to_the_stop_distance(self) -> None:
        (marked,) = mark_positions(
            (_row(),), {_MARKET: Decimal(120)}, exit_cost_rate=Decimal("0.001")
        )
        # 2 x (120 - 90) = 60 at the stop, plus 0,1 % of the 240 notional
        assert marked.planned_risk_quote == Decimal(60) + Decimal("0.240")

    def test_a_position_whose_stop_is_above_the_price_still_costs_its_exit(self) -> None:
        (marked,) = mark_positions(
            (_row(stop=Decimal(130)),), {_MARKET: Decimal(120)}, exit_cost_rate=Decimal("0.001")
        )
        assert marked.planned_risk_quote == Decimal("0.240")

    def test_a_position_without_a_stop_loses_the_notional_and_pays_to_get_out(self) -> None:
        (marked,) = mark_positions(
            (_row(stop=None),), {_MARKET: Decimal(120)}, exit_cost_rate=Decimal("0.001")
        )
        assert marked.planned_risk_quote == Decimal(240) + Decimal("0.240")


class TestAnUnknownPlannedLossIsNotZero:
    def test_a_position_without_a_stop_commits_its_whole_notional(self) -> None:
        (marked,) = mark_positions(
            (_row(stop=None),), {_MARKET: Decimal(120)}, exit_cost_rate=_NO_COST
        )
        assert marked.planned_risk_quote == Decimal(240)


class TestTheLedgerIsLongOnly:
    """Adversarial review of ``8a6a69f``, suggestion 13: D1 is SPOT-only, so a
    stored "short" position is data corruption, not a state to value."""

    def test_a_short_position_raises(self) -> None:
        with pytest.raises(NonLongPosition, match="direction 'short'"):
            mark_positions(
                (_row(direction="short"),), {_MARKET: Decimal(120)}, exit_cost_rate=_NO_COST
            )
