"""Labelled synthetic books, trades, filters and fees for the execution tests.

Nothing here is random and nothing is recorded from an exchange: every book has
a name that says what it is *for*, so a failing test names the market condition
it was about ("the gapped book", "the thin book") instead of a number soup.

The filter and fee stubs are structural stand-ins for
``hunter_exchanges.binance_spot.filters.SpotMarketFilters`` and
``...fees.SpotFeeSchedule``. ``hunter_core`` may not import ``hunter_exchanges``
(the distribution dependency runs the other way), so the adapter talks to a
``Protocol``; that the real classes satisfy it is proved separately in
``test_spot_filters_compat.py``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState, MarketType, OrderSide
from hunter_core.domain.market import BookLevel, NormalizedOrderBook, NormalizedTrade
from hunter_risk.decision import Counterfactual, LimitCap, RiskDecision, Sizing, check
from hunter_risk.inputs import MarketIdentity

NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
"""The instant every test measures ages against. Passed in, never read from a clock."""

EXCHANGE = "binance"
SYMBOL = "BTCUSDT"


def book(
    *,
    asks: list[tuple[str, str]] | None = None,
    bids: list[tuple[str, str]] | None = None,
    received_at: datetime = NOW,
    sequence: int | None = 1_000,
) -> NormalizedOrderBook:
    """A spot book stamped the way the spot adapter stamps one: ``ts == received_at``.

    The spot ``depth`` payload carries no exchange clock at all (T3.0a, §4 of
    ``.claude/state/notes-T3.0a.md``), so the only honest timestamp is when *we*
    received it — which is exactly what the latency and staleness rules measure.
    """
    return NormalizedOrderBook(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        bids=[BookLevel(price=Decimal(p), qty=Decimal(q)) for p, q in (bids or [])],
        asks=[BookLevel(price=Decimal(p), qty=Decimal(q)) for p, q in (asks or [])],
        sequence=sequence,
        is_snapshot=True,
        ts=received_at,
        received_at=received_at,
    )


def trade(
    price: str,
    *,
    trade_id: str = "100",
    ts: datetime = NOW,
    qty: str = "0.5",
    side: OrderSide = OrderSide.SELL,
) -> NormalizedTrade:
    """One aggregated trade — the only price the SPOT marking policy trusts."""
    return NormalizedTrade(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        trade_id=trade_id,
        price=Decimal(price),
        qty=Decimal(qty),
        side=side,
        ts=ts,
        received_at=ts,
    )


#: Enough resting size that a small order never reaches the second level.
DEEP_BOOK = book(
    asks=[("100.00", "10"), ("100.10", "10"), ("100.20", "50")],
    bids=[("99.90", "10"), ("99.80", "10"), ("99.70", "50")],
)

#: Two units on each side and nothing behind them: partial fills live here.
THIN_BOOK = book(asks=[("100.00", "2")], bids=[("99.90", "2")])

#: The stop is 95 and the best bid is 90: the fill is *worse than planned*, and
#: no line of code is allowed to pretend otherwise.
GAPPED_BOOK = book(asks=[("110.00", "5")], bids=[("90.00", "5"), ("89.50", "20")])

#: Observed, and empty. Not "unknown" — a market whose book we saw with nothing
#: on it. An exit here stays pending and degraded; it never invents a fill.
EMPTY_BOOK = book(asks=[], bids=[])


@dataclass(frozen=True)
class StubVerdict:
    """Structural twin of ``binance_spot.filters.MarketOrderCheck``."""

    ok: bool
    qty: Decimal
    notional: Decimal | None = None
    reason: str | None = None


@dataclass(frozen=True)
class StubFilters:
    """Structural twin of ``SpotMarketFilters``, with the same rounding policy."""

    step_size: Decimal = Decimal("0.001")
    min_qty: Decimal = Decimal("0.001")
    min_notional: Decimal | None = Decimal("5")
    apply_min_to_market: bool = True
    max_qty: Decimal = Decimal("1000")
    avg_price_mins: int | None = 5
    bid_multiplier_down: Decimal | None = Decimal("0.5")
    bid_multiplier_up: Decimal | None = Decimal("1.2")
    ask_multiplier_down: Decimal | None = Decimal("0.8")
    ask_multiplier_up: Decimal | None = Decimal("2")
    """The real BTCUSDT ``PERCENT_PRICE_BY_SIDE`` multipliers (T3.0a §5)."""

    @property
    def effective_step_size(self) -> Decimal:
        return self.step_size

    @property
    def effective_min_qty(self) -> Decimal:
        return self.min_qty

    @property
    def effective_max_qty(self) -> Decimal:
        return self.max_qty

    def price_band(self, side: OrderSide, *, avg_price: Decimal) -> tuple[Decimal, Decimal]:
        """Same shape as ``SpotMarketFilters.price_band``: no multiplier on a side
        collapses that edge onto the average, which is not a band."""
        if side is OrderSide.BUY:
            down, up = self.bid_multiplier_down, self.bid_multiplier_up
        else:
            down, up = self.ask_multiplier_down, self.ask_multiplier_up
        low = avg_price * down if down is not None else avg_price
        high = avg_price * up if up is not None else avg_price
        return low, high

    def round_qty_down(self, qty: Decimal) -> Decimal:
        if self.step_size <= 0:
            return qty
        return (qty / self.step_size).to_integral_value(rounding=ROUND_FLOOR) * self.step_size

    def check_market_order(
        self,
        qty: Decimal,
        *,
        avg_price: Decimal | None = None,
        last_price: Decimal | None = None,
    ) -> StubVerdict:
        rounded = self.round_qty_down(qty)
        if rounded < self.effective_min_qty:
            return StubVerdict(ok=False, qty=rounded, reason="min_qty")
        if rounded > self.effective_max_qty:
            return StubVerdict(ok=False, qty=rounded, reason="max_qty")
        if self.min_notional is None or not self.apply_min_to_market:
            return StubVerdict(ok=True, qty=rounded)
        reference = last_price if self.avg_price_mins == 0 else avg_price
        if reference is None:
            return StubVerdict(ok=False, qty=rounded, reason="avg_price_unavailable")
        notional = rounded * reference
        if notional < self.min_notional:
            return StubVerdict(ok=False, qty=rounded, notional=notional, reason="min_notional")
        return StubVerdict(ok=True, qty=rounded, notional=notional)


@dataclass(frozen=True)
class StubFees:
    """Structural twin of ``binance_spot.fees.SpotFeeSchedule`` — spot VIP 0."""

    taker_rate: Decimal = Decimal("0.001")
    maker_rate: Decimal = Decimal("0.001")
    bnb_deduction: bool = False
    source: str = "test double of the spot VIP 0 schedule"


@pytest.fixture
def filters() -> StubFilters:
    return StubFilters()


@pytest.fixture
def fees() -> StubFees:
    return StubFees()


def seconds(value: float) -> timedelta:
    """A duration written as seconds, without a float ever reaching a price."""
    return timedelta(milliseconds=int(value * 1000))


def coarse_filters(**changes: object) -> StubFilters:
    """``StubFilters`` with one field changed, for the minimum-size cases."""
    return replace(StubFilters(), **changes)  # type: ignore[arg-type]


def approved_decision(
    *,
    proposal_id: uuid.UUID | None = None,
    qty: str = "3",
    entry_ref: str = "100",
    stop: str = "95",
    approved: bool = True,
) -> RiskDecision:
    """A real ``RiskDecision``, because an entry order accepts nothing else.

    RISK_ENGINE.md §8: "nenhum caminho de código cria ordens de entrada sem
    ``risk_decision.approved = true``". A boolean the caller sets would make that
    a convention; the decision object makes it a fact — and ``RiskDecision``
    itself refuses to be ``approved`` while any check did not pass.
    """
    cap = LimitCap(name="risk_per_trade", notional=Decimal("200"))
    sizing = Sizing(
        entry_ref=Decimal(entry_ref),
        sizing_price=Decimal(entry_ref),
        stop=Decimal(stop),
        stop_distance_pct=Decimal("0.05"),
        cost_pct=Decimal("0.002"),
        caps=(cap,),
        binding_limit=cap,
        binding_constraint="risk_per_trade",
        size_without_multipliers=Counterfactual(name="size_without_multipliers", qty=Decimal(qty)),
        size_without_participation=Counterfactual(
            name="size_without_participation", qty=Decimal(qty)
        ),
        notional_before_multiplier=Decimal("200"),
        kill_switch_multiplier=Decimal(1),
        notional_after_multiplier=Decimal("200"),
        qty=Decimal(qty),
        notional=Decimal("200"),
        planned_risk_quote=Decimal("10"),
        planned_risk_pct=Decimal("0.0025"),
    )
    return RiskDecision(
        approved=approved,
        kind="entry",
        proposal_id=proposal_id or uuid.UUID(int=5),
        portfolio_id=uuid.UUID(int=6),
        market=MarketIdentity(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            market_type=MarketType.SPOT,
            base_asset="BTC",
            quote_asset="USDT",
        ),
        limits_profile="paper_v1",
        effective_kill_switch=KillSwitchState.ACTIVE,
        cancel_pending=False,
        shadow_only=False,
        checks=(check("cash", approved),),
        sizing=sizing if approved else None,
    )
