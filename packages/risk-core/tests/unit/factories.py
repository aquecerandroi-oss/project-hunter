"""Builders for the pure inputs, so a test states only what it is about."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import MarketType, TradeDirection
from hunter_core.strategies.envelope import AssumedCosts
from hunter_risk.exposure import OpenPosition, PendingEntry, PortfolioState, sao_paulo_day_start_utc
from hunter_risk.inputs import (
    BetaEstimate,
    BookLevel,
    EntryProposal,
    ExitProposal,
    MarketIdentity,
    MarketLiquidity,
    MarketSpec,
)
from hunter_risk.sizing import entry_cash_multiplier

NOW = datetime(2026, 9, 6, 18, 30, tzinfo=UTC)
"""One fixed instant for every table case: the engine never reads a clock."""

COSTS = AssumedCosts(
    spread_bps=Decimal("2"), slippage_bps=Decimal("5"), fee_bps=Decimal("4"), max_entry_delay_s=120
)
"""The frozen hypothesis of both v0 strategies (momentum_v1, volume_anomaly_v1)."""

CASH_MULTIPLIER = entry_cash_multiplier(COSTS)
"""What one unit of reference notional holds in cash under COSTS: 1,00100024."""

SOL = MarketIdentity(
    exchange="binance",
    symbol="SOLUSDT",
    market_type=MarketType.SPOT,
    base_asset="SOL",
    quote_asset="USDT",
)


def market(symbol: str = "SOLUSDT", base: str = "SOL") -> MarketIdentity:
    return SOL.model_copy(update={"symbol": symbol, "base_asset": base})


def spec(**over: Any) -> MarketSpec:
    return MarketSpec.model_validate(
        {
            "market": SOL,
            "step_size": Decimal("0.001"),
            "min_notional": Decimal("5"),
            "tick_size": Decimal("0.01"),
            **over,
        }
    )


def deep_book(price: Decimal = Decimal("100"), levels: int = 40) -> tuple[BookLevel, ...]:
    """A book so deep that book_depth never binds: 1000 quote per level, 1 bp apart."""
    return tuple(
        BookLevel(price=price * (Decimal(1) + Decimal(i) / Decimal("100000")), qty=Decimal("10"))
        for i in range(levels)
    )


def liquidity(**over: Any) -> MarketLiquidity:
    price = Decimal("100")
    return MarketLiquidity.model_validate(
        {
            "market": SOL,
            "last_price": price,
            "mid_price": price,
            "best_bid": Decimal("99.999"),
            "best_ask": Decimal("100.001"),
            "price_ts": NOW,
            "asks": deep_book(price),
            "book_ts": NOW,
            "quote_volume_24h": Decimal("260000000"),
            "last_minute_quote_volume": Decimal("500000"),
            "median_30m_quote_volume": Decimal("500000"),
            "volume_window_complete": True,
            "gap_state": "ok",
            "in_universe": True,
            "participation_used_quote": Decimal("0"),
            "volume_ts": NOW,
            "data_quality": "ok",
            **over,
        }
    )


def beta(value: str | Decimal = "1.0", **over: Any) -> BetaEstimate:
    return BetaEstimate.model_validate(
        {"value": Decimal(value), "as_of": NOW, "validated": True, "bars": 720, **over}
    )


def position(**over: Any) -> OpenPosition:
    return OpenPosition.model_validate(
        {
            "position_id": uuid.UUID("00000000-0000-7000-8000-0000000000cc"),
            "market": SOL,
            "qty": Decimal("10"),
            "notional": Decimal("1000"),
            "planned_risk_quote": Decimal("25"),
            "beta_btc": Decimal("1.0"),
            **over,
        }
    )


def pending(**over: Any) -> PendingEntry:
    """A reservation that holds its own cash, fees included, like the real one."""
    notional: Decimal = over.pop("reserved_notional", Decimal("1000"))
    return PendingEntry.model_validate(
        {
            "market": SOL,
            "reserved_notional": notional,
            "reserved_cash": notional * CASH_MULTIPLIER,
            "planned_risk_quote": Decimal("25"),
            "beta_btc": Decimal("1.0"),
            **over,
        }
    )


def portfolio(**over: Any) -> PortfolioState:
    equity = over.pop("equity", Decimal("20000"))
    return PortfolioState.model_validate(
        {
            "portfolio_id": uuid.UUID("00000000-0000-7000-8000-0000000000aa"),
            "as_of": NOW,
            "equity": equity,
            "cash": equity,
            "peak_equity": equity,
            "day_start_equity": equity,
            "day_start_utc": sao_paulo_day_start_utc(NOW),
            "open_positions": (),
            "pending_entries": (),
            "marks_complete": True,
            **over,
        }
    )


def proposal(**over: Any) -> EntryProposal:
    return EntryProposal.model_validate(
        {
            "proposal_id": uuid.UUID("00000000-0000-7000-8000-000000000001"),
            "portfolio_id": uuid.UUID("00000000-0000-7000-8000-0000000000aa"),
            "agent_id": uuid.UUID("00000000-0000-7000-8000-0000000000bb"),
            "market": SOL,
            "direction": TradeDirection.LONG,
            "entry_ref": Decimal("100"),
            "stop": Decimal("97.5"),
            "requested_notional": None,
            "assumed_costs": COSTS,
            **over,
        }
    )


def exit_proposal(**over: Any) -> ExitProposal:
    return ExitProposal.model_validate(
        {
            "proposal_id": uuid.UUID("00000000-0000-7000-8000-000000000002"),
            "portfolio_id": uuid.UUID("00000000-0000-7000-8000-0000000000aa"),
            "position_id": uuid.UUID("00000000-0000-7000-8000-0000000000cc"),
            "market": SOL,
            "qty": Decimal("10"),
            "reason": "stop",
            **over,
        }
    )
