"""Unit coverage for T3.68's manual order route: schema validation and the
named-reason mapping in ``hunter_api.services.orders`` — no database, no Redis.

The end-to-end filing/decision/replay/isolation/kill-switch behaviour is
``apps/api/tests/integration/test_manual_orders.py`` (testcontainers); this
file is only the pure boundary logic: what a malformed body looks like, and
which named reason each shape of "this market/ticker cannot be traded" maps to.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from hunter_api.schemas.orders import ManualOrderCreate
from hunter_api.services.orders_derive import (
    MANUAL_ORDER_SLIPPAGE_BPS,
    costs_from_ticker,
    spot_eligibility_reason,
)
from hunter_api.settings import ApiSettings
from hunter_core.domain.enums import MarketStatus, MarketType, TradeDirection
from hunter_core.strategies.base import assumed_costs as strategy_assumed_costs
from hunter_core.strategies.breakout_v1 import BreakoutV1
from hunter_risk.limits import PAPER_V1

pytestmark = pytest.mark.unit

MARKET_ID = uuid.uuid4()
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def _ticker(*, ts: datetime = NOW) -> dict[str, str]:
    return {"last": "100", "bid": "99.9", "ask": "100.1", "ts": ts.isoformat()}


class TestManualOrderCreate:
    def test_a_valid_long_body_parses(self) -> None:
        body = ManualOrderCreate.model_validate(
            {"market_id": str(MARKET_ID), "direction": "long", "stop": "97.5"}
        )
        assert body.direction is TradeDirection.LONG
        assert body.stop == Decimal("97.5")
        assert body.requested_notional is None

    def test_a_valid_short_body_parses_too(self) -> None:
        """Syntactically valid — the business refusal is
        ``hunter_api.services.orders.file_order``'s job, not the schema's
        (RISK_ENGINE.md §3.1 check 3, ``modality``)."""
        body = ManualOrderCreate.model_validate(
            {"market_id": str(MARKET_ID), "direction": "short", "stop": "97.5"}
        )
        assert body.direction is TradeDirection.SHORT

    def test_neutral_direction_is_refused_at_the_schema(self) -> None:
        with pytest.raises(ValidationError, match="long.*short"):
            ManualOrderCreate.model_validate(
                {"market_id": str(MARKET_ID), "direction": "neutral", "stop": "97.5"}
            )

    def test_a_float_stop_is_refused_never_silently_coerced(self) -> None:
        with pytest.raises(ValidationError, match="float"):
            ManualOrderCreate.model_validate(
                {"market_id": str(MARKET_ID), "direction": "long", "stop": 97.5}
            )

    def test_a_float_requested_notional_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="float"):
            ManualOrderCreate.model_validate(
                {
                    "market_id": str(MARKET_ID),
                    "direction": "long",
                    "stop": "97.5",
                    "requested_notional": 1500.25,
                }
            )

    def test_a_non_positive_stop_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ManualOrderCreate.model_validate(
                {"market_id": str(MARKET_ID), "direction": "long", "stop": "0"}
            )

    def test_an_unknown_field_is_refused(self) -> None:
        """``StrictModel``: a field the API does not know is a field the
        client thinks it is setting — the target price never existed here."""
        with pytest.raises(ValidationError):
            ManualOrderCreate.model_validate(
                {
                    "market_id": str(MARKET_ID),
                    "direction": "long",
                    "stop": "97.5",
                    "target": "110",
                }
            )


class TestSpotEligibilityReason:
    _BASE: dict[str, object] = {
        "market_type": MarketType.SPOT,
        "status": MarketStatus.ACTIVE,
        "is_monitored": True,
        "delisted_at": None,
        "base_asset": "SOL",
        "quote_asset": "USDT",
    }

    def test_an_eligible_spot_market_has_no_reason(self) -> None:
        assert spot_eligibility_reason(**self._BASE) is None  # type: ignore[arg-type]

    def test_a_perpetual_is_refused(self) -> None:
        kwargs = {**self._BASE, "market_type": MarketType.PERPETUAL}
        assert spot_eligibility_reason(**kwargs) == "market_not_executable_spot"  # type: ignore[arg-type]

    def test_a_suspended_market_is_refused(self) -> None:
        kwargs = {**self._BASE, "status": MarketStatus.SUSPENDED}
        assert spot_eligibility_reason(**kwargs) == "market_not_executable_spot"  # type: ignore[arg-type]

    def test_an_unmonitored_market_is_refused(self) -> None:
        kwargs = {**self._BASE, "is_monitored": False}
        assert spot_eligibility_reason(**kwargs) == "market_not_executable_spot"  # type: ignore[arg-type]

    def test_a_delisted_market_is_refused(self) -> None:
        kwargs = {**self._BASE, "delisted_at": NOW}
        assert spot_eligibility_reason(**kwargs) == "market_not_executable_spot"  # type: ignore[arg-type]

    def test_a_market_with_no_asset_on_record_is_refused(self) -> None:
        kwargs = {**self._BASE, "base_asset": None}
        assert spot_eligibility_reason(**kwargs) == "market_not_executable_spot"  # type: ignore[arg-type]


class TestCostsFromTicker:
    def test_a_healthy_ticker_derives_entry_ref_and_costs(self) -> None:
        result = costs_from_ticker(_ticker(), now=NOW)

        assert not isinstance(result, str)
        entry_ref, costs = result
        assert entry_ref == Decimal(100)
        # spread = (100.1 - 99.9) / 100 * 10_000 = 20 bps
        assert costs.spread_bps == Decimal(20)
        assert costs.fee_bps == Decimal(10)  # SPOT_VIP0: 0.10% taker
        assert costs.slippage_bps == Decimal(5)  # T3.68b finding 1: never 0
        assert costs.max_entry_delay_s == 60

    def test_no_last_price_is_spot_price_unavailable(self) -> None:
        assert costs_from_ticker({}, now=NOW) == "spot_price_unavailable"

    def test_a_zero_last_price_is_spot_price_unavailable(self) -> None:
        assert (
            costs_from_ticker({"last": "0", "bid": "1", "ask": "1"}, now=NOW)
            == "spot_price_unavailable"
        )

    def test_a_missing_bid_is_spot_spread_unavailable(self) -> None:
        assert (
            costs_from_ticker({"last": "100", "ask": "100.1"}, now=NOW) == "spot_spread_unavailable"
        )

    def test_a_missing_ask_is_spot_spread_unavailable(self) -> None:
        assert (
            costs_from_ticker({"last": "100", "bid": "99.9"}, now=NOW) == "spot_spread_unavailable"
        )

    def test_an_inverted_book_is_spot_spread_unavailable(self) -> None:
        """``ask < bid`` never happens on a real book; a corrupted or stale
        hash must not derive a negative spread."""
        assert (
            costs_from_ticker({"last": "100", "bid": "100.5", "ask": "99.5"}, now=NOW)
            == "spot_spread_unavailable"
        )

    def test_a_ticker_with_no_ts_is_spot_ticker_missing(self) -> None:
        """T3.68b finding 4: every existing fixture above that never sets
        ``ts`` still returns *its own* reason (checked first) — this is the
        one whose price and spread are fine and only ``ts`` is absent."""
        ticker = {"last": "100", "bid": "99.9", "ask": "100.1"}
        assert costs_from_ticker(ticker, now=NOW) == "spot_ticker_missing"

    def test_a_stale_ticker_is_spot_ticker_stale(self) -> None:
        stale_at = NOW - timedelta(seconds=PAPER_V1.max_price_age_s + 1)
        assert costs_from_ticker(_ticker(ts=stale_at), now=NOW) == "spot_ticker_stale"

    def test_a_ticker_exactly_at_the_age_limit_is_accepted(self) -> None:
        edge_at = NOW - timedelta(seconds=PAPER_V1.max_price_age_s)
        result = costs_from_ticker(_ticker(ts=edge_at), now=NOW)
        assert not isinstance(result, str)

    def test_a_ticker_slightly_ahead_of_now_is_tolerated_as_clock_skew(self) -> None:
        """Binance's ``closeTime`` may run up to 2 s ahead of this host (RISK_ENGINE §7.1)."""
        future = NOW + timedelta(seconds=1)
        assert not isinstance(costs_from_ticker(_ticker(ts=future), now=NOW), str)

    def test_a_ticker_far_in_the_future_is_named_clock_skew_not_stale(self) -> None:
        """A skewed producer is an NTP problem, never "very fresh" and never staleness."""
        future = NOW + timedelta(seconds=3)
        assert costs_from_ticker(_ticker(ts=future), now=NOW) == "spot_ticker_clock_skew"

    def test_manual_slippage_matches_the_strategy_path_for_the_same_geometry(self) -> None:
        """T3.68b finding 1: the manual route's assumed slippage is not a
        number invented for it — it is exactly what a strategy proposing the
        same geometry would assume, read through the same helper
        (``hunter_core.strategies.base.assumed_costs``) the strategies use."""
        result = costs_from_ticker(_ticker(), now=NOW)
        assert not isinstance(result, str)
        _, manual_costs = result
        strategy_costs = strategy_assumed_costs(BreakoutV1.default_parameters)
        assert manual_costs.slippage_bps == strategy_costs.slippage_bps == MANUAL_ORDER_SLIPPAGE_BPS


class TestManualOrderMaxPendingPerPortfolioSetting:
    """T3.68c — the setting a bare ``ApiSettings()`` falls back to, and the one
    an env var overrides, the same way every other integer field on this class
    already works (``rate_limit_per_minute`` et al.)."""

    def test_the_default_is_20(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MANUAL_ORDER_MAX_PENDING_PER_PORTFOLIO", raising=False)
        assert ApiSettings().manual_order_max_pending_per_portfolio == 20

    def test_an_env_var_overrides_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MANUAL_ORDER_MAX_PENDING_PER_PORTFOLIO", "5")
        assert ApiSettings().manual_order_max_pending_per_portfolio == 5
