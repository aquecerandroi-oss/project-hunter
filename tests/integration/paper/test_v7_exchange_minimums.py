"""V7 — exchange minimums and quantity increments, against the real BTCUSDT filters.

**Objetivo (spec V7):** the exchange's notional floor and quantity step are
respected on the execution side, not only in the pure sizing core — rounding
always down, never up, and an explicit refusal when the size never reaches the
minimum tradable amount.

Every filter here is ``recorded_filters("BTCUSDT")`` (§0): the real, measured
``spot_exchange_info.json`` fixture, never a hand-typed number. No database is
needed for most of this file — ``SpotMarketFilters``/``PaperExecutionAdapter``
are pure — so these run without the wallet fixture, against BTCUSDT only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import ExitReason, MarketType, OrderSide
from hunter_core.domain.market import BookLevel, NormalizedOrderBook, NormalizedTrade
from hunter_core.domain.types import uuid7
from hunter_core.execution.intents import ExitAttempt, ExitIntent
from hunter_core.execution.paper import PaperExecutionAdapter
from hunter_core.execution.pricing import untradable_reason
from hunter_exchanges.binance_spot.fees import SPOT_VIP0
from hunter_risk.inputs import MarketIdentity
from hunter_risk.sizing import floor_to_step

from .conftest import recorded_filters

pytestmark = [pytest.mark.integration]

PRICE = Decimal("80000.00")
"""§0's synthetic, labelled reference price for BTCUSDT filter scenarios —
deliberately not the live price of any measurement day."""

NOW = datetime(2026, 9, 6, 18, 30, tzinfo=UTC)
FILTERS = recorded_filters("BTCUSDT")
IDENTITY = MarketIdentity(
    exchange="binance",
    symbol="BTCUSDT",
    market_type=MarketType.SPOT,
    base_asset="BTC",
    quote_asset="USDT",
)


def _book(
    *, received_at: datetime, bid: Decimal, ask: Decimal, qty: Decimal
) -> NormalizedOrderBook:
    return NormalizedOrderBook(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        ts=received_at,
        received_at=received_at,
        bids=[BookLevel(price=bid, qty=qty)],
        asks=[BookLevel(price=ask, qty=qty)],
        sequence=None,
        is_snapshot=True,
    )


def _trade(*, price: Decimal, ts: datetime, trade_id: int) -> NormalizedTrade:
    return NormalizedTrade(
        exchange="binance",
        symbol="BTCUSDT",
        market_type=MarketType.SPOT,
        ts=ts,
        received_at=ts,
        trade_id=str(trade_id),
        price=price,
        qty=Decimal(1),
        side=OrderSide.BUY,
    )


class TestTheMinimumLotSizeIsBelowTheNotionalFloor:
    """Step 1: the smallest BTCUSDT ``LOT_SIZE`` quantity (0,00001 BTC) at
    80.000 USDT is 0,80 USDT of notional — below the 5 USDT floor.

    **O que refuta:** the check rounding the quantity **up** to reach the
    floor (the mutant that already reproves 20 tests in the pure core,
    ``review-T3.2-risk-core.md``); any ``ok=True`` verdict for this quantity.
    """

    def test_the_minimum_qty_is_rejected_never_rounded_up_to_reach_the_floor(self) -> None:
        qty = FILTERS.effective_min_qty
        assert qty == Decimal("0.00001")
        verdict = FILTERS.check_market_order(qty, avg_price=PRICE, last_price=PRICE)
        assert verdict.ok is False
        assert verdict.reason == "min_notional"
        assert verdict.qty == qty  # never rounded to anything else, up or down
        assert verdict.notional == qty * PRICE == Decimal("0.80000000")


class TestAQuantityBetweenTwoStepsRoundsDownNeverUp:
    """Step 2: 0,123456 BTC requested, ``stepSize = 0,00001`` → 0,12345, never
    0,12346.

    **O que refuta:** any rounding that lands on 0,12346 or leaves the
    quantity untouched at 0,123456 (a step violation the exchange would
    reject outright).
    """

    def test_a_quantity_between_two_multiples_of_the_step_floors_down(self) -> None:
        rounded = FILTERS.round_qty_down(Decimal("0.123456"))
        assert rounded == Decimal("0.12345")
        assert rounded != Decimal("0.12346")


class TestTheRiskEngineAndTheExecutionAdapterAgreeOnTheSameStep:
    """Step 3: ``hunter_risk.sizing.floor_to_step`` (the Risk Engine's own
    rounding) and ``SpotMarketFilters.round_qty_down`` (the execution side)
    must floor the **same** quantity to the **same** number for BTCUSDT's real
    step — proving the two layers share one step size instead of each
    happening to agree by coincidence.

    **O que refuta:** any quantity where the two roundings diverge by even one
    ``0,00001`` increment.
    """

    @pytest.mark.parametrize(
        "candidate",
        [Decimal("0.123456"), Decimal("1.000009"), Decimal("0.00001"), Decimal("0.000019")],
    )
    def test_the_two_roundings_agree(self, candidate: Decimal) -> None:
        step = FILTERS.effective_step_size
        assert floor_to_step(candidate, step) == FILTERS.round_qty_down(candidate)


class TestTheNotionalReferenceIsTheExchangeAverageNeverTheLastTrade:
    """Step 4: BTCUSDT's ``NOTIONAL`` filter carries ``avgPriceMins = 5``
    (measured, not zero) — Binance judges a MARKET order's notional against
    ``avgPrice``, never the last trade (``.claude/state/notes-T3.0a.md`` §5).
    Without an ``avgPrice`` the check refuses explicitly; it never substitutes
    ``last_price``, no matter how fresh.

    **O que refuta:** a verdict that passes (or that computes a notional at
    all) using ``last_price`` when ``avg_price`` is ``None`` and
    ``avgPriceMins`` is not zero; any ``reason`` other than
    ``avg_price_unavailable`` for this exact input.
    """

    def test_without_avg_price_the_check_refuses_and_never_uses_the_last_trade(self) -> None:
        assert FILTERS.avg_price_mins == 5
        verdict = FILTERS.check_market_order(
            Decimal(1),
            avg_price=None,
            last_price=PRICE,  # a perfectly fresh last trade
        )
        assert verdict.ok is False
        assert verdict.reason == "avg_price_unavailable"
        assert verdict.notional is None  # never computed from the substituted price


class TestAResidualBelowTheFloorIsAccountedAndVisibleNeverQuietlySettled:
    """Step 5: a stop's partial fill on BTCUSDT leaves 0,00001 BTC — worth
    0,80 USDT at 80.000, below the 5 USDT notional floor — as a
    :class:`~hunter_core.execution.adapter.Residual`, not a silent zero.

    **Divergência com a spec, registrada (não ajustada em silêncio):** o texto
    de V7 item 5 escreve ``reason='below_min_qty'`` para este cenário. O código
    mede o resíduo (0,00001 BTC) contra ``effective_min_qty`` primeiro — e
    0,00001 **não é menor** que o próprio ``effective_min_qty`` (são iguais) —
    então ``untradable_reason`` cai no piso de ``NOTIONAL`` (0,80 USDT < 5
    USDT) e devolve ``'below_min_notional'``. A quantidade, o preço e o "nunca
    quitado" da spec estão corretos; só o rótulo do motivo diverge. Detalhado
    em ``.claude/state/notes-T3.9b.md``.
    """

    def test_the_residual_is_below_min_notional_not_below_min_qty(self) -> None:
        leftover = Decimal("0.00001")
        reason = untradable_reason(leftover, FILTERS, PRICE)
        assert reason == "below_min_notional"
        assert leftover >= FILTERS.effective_min_qty  # exactly at the LOT_SIZE floor

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "spec V7 item 5 says reason='below_min_qty' for a 0,00001 BTC leftover; the code "
            "measures LOT_SIZE first (0,00001 is not below 0,00001) and only NOTIONAL fails "
            "(0,80 < 5), producing 'below_min_notional' — see notes-T3.9b.md"
        ),
    )
    def test_v7_step5_the_spec_reason_below_min_qty(self) -> None:
        leftover = Decimal("0.00001")
        assert untradable_reason(leftover, FILTERS, PRICE) == "below_min_qty"

    def test_the_residual_is_visible_on_the_report_never_silently_dropped(self) -> None:
        """The full path: a shallow book leaves exactly this dust on a real
        ``submit_protection_exit`` report — accounted, valued, never zeroed.

        The wanted quantity (1 BTC, 80.000 USDT notional) clears the
        ``NOTIONAL`` floor easily — the point is that the **book**, not the
        filter, is what leaves the tiny leftover; a wanted quantity whose
        notional is already below the floor would be rejected outright before
        any walk, which is a different scenario (item 1 above).
        """
        intent = ExitIntent(
            intent_id=uuid7(),
            portfolio_id=uuid7(),
            position_id=uuid7(),
            protection_key="stop",
            reason=ExitReason.STOP,
            intended_qty=Decimal("1"),
            market=IDENTITY,
        )
        book_at = NOW + timedelta(milliseconds=300)
        cycle_at = NOW + timedelta(seconds=1)
        attempt = ExitAttempt.for_intent(
            intent, qty=Decimal("1"), decision_at=NOW, position_qty=Decimal("1")
        )
        book = _book(received_at=book_at, bid=PRICE, ask=PRICE, qty=Decimal("0.99999"))
        trade = _trade(price=PRICE, ts=NOW, trade_id=1)
        report = PaperExecutionAdapter().submit_protection_exit(
            attempt, Decimal("1"), book, trade, FILTERS, SPOT_VIP0, cycle_at, avg_price=PRICE
        )
        assert report.status == "partially_filled"
        assert report.filled_qty == Decimal("0.99999")
        assert report.residual is not None
        assert report.residual.qty == Decimal("0.00001")
        assert report.residual.reason == "below_min_notional"
        assert report.residual.value_quote == Decimal("0.80000000")
