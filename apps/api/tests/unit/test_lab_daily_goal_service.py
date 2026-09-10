"""Unit tests: the USDT-before-FX split of ``value_of_1r``/``progress`` and
the ``fx`` block — brief T3.78b (Everton, 2026-09-10).

Pure, no database: ``_value_of_1r``/``_progress``/``_fx_out`` never touch the
repository. ``FxObservation`` is built unattached (same pattern
``packages/core/tests/unit/portfolio/test_opening_policy.py`` uses) — its
attributes are read, never persisted.

Covers the branch ``notes-T3.78.md`` CONCERN 5 flagged as untested by the
integration suite: bets priceable in USDT with no FX observation available.
Since USDT pricing (Everton's rule) never needs a rate, that branch now
populates ``real_usdt_*``/``progress.real_usdt`` while leaving ``real_brl_*``
``None`` — explained by the top-level ``fx``/``fx_reason``, not by
``value_of_1r.reason``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_api.services.lab_daily_goal import (
    _fx_out,  # pyright: ignore[reportPrivateUsage]
    _progress,  # pyright: ignore[reportPrivateUsage]
    _value_of_1r,  # pyright: ignore[reportPrivateUsage]
)
from hunter_core.db.models.fx import FxObservation

pytestmark = pytest.mark.unit

_OBSERVED_AT = datetime(2026, 9, 6, 14, 32, tzinfo=UTC)
_AVAILABLE_AT = datetime(2026, 9, 6, 14, 32, 5, tzinfo=UTC)


def _fx(rate: Decimal = Decimal("5.00")) -> FxObservation:
    return FxObservation(
        id=uuid.uuid4(),
        pair="USDTBRL",
        source="binance.spot.ticker",
        rate=rate,
        observed_at=_OBSERVED_AT,
        available_at=_AVAILABLE_AT,
    )


class TestValueOf1rUsdtBeforeFx:
    def test_no_priceable_bets_nulls_both_currencies(self) -> None:
        result = _value_of_1r([], _fx())
        assert result.sample_size == 0
        assert result.reason == "no_priceable_bets"
        assert result.real_usdt_p10 is None
        assert result.real_usdt_p50 is None
        assert result.real_usdt_p90 is None
        assert result.real_brl_p10 is None
        assert result.real_brl_p50 is None
        assert result.real_brl_p90 is None

    def test_priceable_bets_with_fx_populate_both_currencies(self) -> None:
        result = _value_of_1r([Decimal("28")], _fx(Decimal("5.00")))
        assert result.sample_size == 1
        assert result.reason is None
        assert result.real_usdt_p50 == Decimal("28")
        assert result.real_brl_p50 == Decimal("28") * Decimal("5.00")

    def test_priceable_bets_without_fx_populate_usdt_only_and_reason_stays_none(self) -> None:
        """The branch the integration suite cannot construct with real data
        (concern 5): equity/candles priced the bet, but no ``fx_observations``
        row was available. USDT is real regardless -- only BRL is unknown,
        and that is the ``fx``/``fx_reason`` block's job to say, not this
        field's ``reason``."""
        result = _value_of_1r([Decimal("28")], None)
        assert result.sample_size == 1
        assert result.reason is None
        assert result.real_usdt_p50 == Decimal("28")
        assert result.real_brl_p10 is None
        assert result.real_brl_p50 is None
        assert result.real_brl_p90 is None

    def test_percentiles_of_a_five_bet_day_convert_pointwise(self) -> None:
        priced = [Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")]
        result = _value_of_1r(priced, _fx(Decimal("2")))
        assert result.real_usdt_p50 == Decimal("30")
        assert result.real_brl_p50 == Decimal("30") * Decimal("2")


class TestProgressRealUsdt:
    def test_real_usdt_is_unique_r_times_p50_independent_of_brl(self) -> None:
        value_of_1r = _value_of_1r([Decimal("28")], None)
        progress = _progress(
            unique_r=Decimal("2"), value_of_1r=value_of_1r, goal_brl=Decimal("9000")
        )
        assert progress.real_usdt == Decimal("2") * Decimal("28")
        assert progress.real_brl is None

    def test_real_usdt_is_none_only_when_no_bet_was_priceable_at_all(self) -> None:
        value_of_1r = _value_of_1r([], _fx())
        progress = _progress(
            unique_r=Decimal("0"), value_of_1r=value_of_1r, goal_brl=Decimal("9000")
        )
        assert progress.real_usdt is None
        assert progress.real_brl is None


class TestFxOut:
    def test_none_when_no_observation(self) -> None:
        assert _fx_out(None) is None

    def test_mirrors_the_observation_used(self) -> None:
        observation = _fx(Decimal("5.4321"))
        out = _fx_out(observation)
        assert out is not None
        assert out.rate == Decimal("5.4321")
        assert out.source == "binance.spot.ticker"
        assert out.observed_at == _OBSERVED_AT
        assert out.available_at == _AVAILABLE_AT
