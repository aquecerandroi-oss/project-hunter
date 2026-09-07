"""The protection exit: the attempt ends, the intention does not — and no fill is invented.

The three sentences from the joint decision (item 3) that these cases hold to:

- "sem livro utilizável **não se fabrica fill**: a saída fica pendente,
  degradada, com alerta, e vela nunca fornece fill retroativo";
- "resíduo abaixo do mínimo fica contabilizado e visível", without fictitious
  settlement;
- and the directive's own "execuções piores que o stop planejado, **sem
  fabricar proteção perfeita**".
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from hunter_core.domain.enums import ExitReason, MarketType, OrderSide
from hunter_core.execution import (
    ExecutionPolicy,
    InMemoryExecutionJournal,
    PaperExecutionAdapter,
)
from hunter_core.execution.intents import ExitAttempt, ExitIntent, apply_attempt, void_intent
from hunter_core.execution.triggers import ProtectedPosition, check_triggers
from hunter_risk.inputs import MarketIdentity

from .conftest import (
    DEEP_BOOK,
    EMPTY_BOOK,
    GAPPED_BOOK,
    NOW,
    StubFees,
    StubFilters,
    book,
    coarse_filters,
    seconds,
    trade,
)

AVG = Decimal("100")


def _intent(intended: str = "10", filled: str = "0", *, trigger: str = "95") -> ExitIntent:
    return ExitIntent(
        intent_id=uuid.UUID(int=21),
        portfolio_id=uuid.UUID(int=6),
        position_id=uuid.UUID(int=8),
        protection_key="stop",
        reason=ExitReason.STOP,
        intended_qty=Decimal(intended),
        filled_qty=Decimal(filled),
        trigger_price=Decimal(trigger),
    )


def _attempt(
    intent: ExitIntent, qty: str, *, position_qty: str | None = None, decided_s_ago: float = 0.5
) -> ExitAttempt:
    return ExitAttempt.for_intent(
        intent,
        qty=Decimal(qty),
        decision_at=NOW - seconds(decided_s_ago),
        position_qty=None if position_qty is None else Decimal(position_qty),
    )


def _adapter(**policy: object) -> PaperExecutionAdapter:
    return PaperExecutionAdapter(policy=ExecutionPolicy(**policy))  # type: ignore[arg-type]


def test_a_protection_sells_into_the_bids_and_pays_the_fee_in_quote(
    filters: StubFilters, fees: StubFees
) -> None:
    intent = _intent("10")
    report = _adapter().submit_protection_exit(
        _attempt(intent, "10"),
        Decimal("10"),
        DEEP_BOOK,
        trade("95"),
        filters,
        fees,
        NOW,
        avg_price=AVG,
    )
    assert report.status == "filled"
    assert report.side is OrderSide.SELL
    assert report.filled_qty == Decimal("10")
    assert report.gross_quote == Decimal("999.00")
    assert report.fee is not None and report.fee.asset == "quote"
    assert report.fee.qty == Decimal("0.99900000")
    assert report.net_quote_delta == Decimal("999.00") - Decimal("0.999")
    assert report.net_base_delta == -Decimal("10")


def test_a_partial_protection_fill_never_cancels_the_remainder(
    filters: StubFilters, fees: StubFees
) -> None:
    """The §10 scenario, end to end: 10 wanted, 4 sellable, 6 still protected."""
    intent = _intent("10")
    thin = book(bids=[("95.00", "4")])
    report = _adapter().submit_protection_exit(
        _attempt(intent, "10"), Decimal("10"), thin, trade("95"), filters, fees, NOW, avg_price=AVG
    )
    assert report.status == "partially_filled"
    assert report.filled_qty == Decimal("4")
    assert report.unfilled_qty == Decimal("6")
    assert report.remaining_cancelled is False
    after = apply_attempt(intent, report, now=NOW, min_qty=Decimal("0.001"))
    assert after.remaining_qty == Decimal("6")
    assert after.live


def test_without_a_usable_book_the_exit_is_pending_degraded_with_an_alert(
    filters: StubFilters, fees: StubFees
) -> None:
    """And the last trade printing *below the stop* still buys no fill.

    This is the case that would tempt a simulator into "the candle low was 90,
    so the stop filled at 90". It did not: nobody was bidding.
    """
    intent = _intent("10")
    report = _adapter().submit_protection_exit(
        _attempt(intent, "10"),
        Decimal("10"),
        EMPTY_BOOK,
        trade("90"),
        filters,
        fees,
        NOW,
        avg_price=AVG,
    )
    assert report.status == "pending_degraded"
    assert report.filled_qty == 0
    assert report.levels == ()
    assert report.degraded and report.alert
    assert report.reason == "empty_side"
    after = apply_attempt(intent, report, now=NOW, min_qty=Decimal("0.001"))
    assert after.degraded_since == NOW
    assert after.remaining_qty == Decimal("10")


def test_a_stale_book_degrades_the_exit_instead_of_rejecting_the_protection(
    filters: StubFilters, fees: StubFees
) -> None:
    """A protection is never *refused*: it waits with an alert until there is data."""
    intent = _intent("10")
    old = book(bids=[("95.00", "10")], received_at=NOW - seconds(30))
    report = _adapter().submit_protection_exit(
        _attempt(intent, "10", decided_s_ago=60),
        Decimal("10"),
        old,
        trade("95"),
        filters,
        fees,
        NOW,
        avg_price=AVG,
    )
    assert (report.status, report.reason) == ("pending_degraded", "book_stale")


def test_a_gap_fills_worse_than_the_planned_stop_and_says_so(
    filters: StubFilters, fees: StubFees
) -> None:
    """Directive: execuções piores que o stop planejado, sem fabricar proteção.

    Planned 95, the best bid is 90: the fill is at 90 and ``slippage_vs_plan``
    publishes the 5 per unit. Nothing anywhere moves the price back to 95.
    """
    intent = _intent("5", trigger="95")
    report = _adapter().submit_protection_exit(
        _attempt(intent, "5"),
        Decimal("5"),
        GAPPED_BOOK,
        trade("90"),
        filters,
        fees,
        NOW,
        avg_price=AVG,
    )
    assert report.filled_qty == Decimal("5")
    assert report.vwap == Decimal("90.00")
    assert report.planned_price == Decimal("95")
    assert report.slippage_vs_plan_quote == Decimal("25.00")
    assert report.slippage_vs_plan_bps == Decimal("526.31578947")


def test_a_remainder_below_the_minimum_comes_back_as_a_visible_residual(fees: StubFees) -> None:
    """0,4 left under a 1,0 minimum: quantity kept, value published, nothing settled."""
    intent = _intent("10")
    filters = coarse_filters(min_qty=Decimal("1"), step_size=Decimal("0.1"), min_notional=None)
    partial = book(bids=[("95.00", "9.6")])
    report = _adapter().submit_protection_exit(
        _attempt(intent, "10"),
        Decimal("10"),
        partial,
        trade("95"),
        filters,
        fees,
        NOW,
        avg_price=AVG,
    )
    assert report.filled_qty == Decimal("9.6")
    assert report.residual is not None
    assert report.residual.qty == Decimal("0.4")
    assert report.residual.reason == "below_min_qty"
    assert report.residual.value_quote == Decimal("38.00")
    assert report.residual.valuation_price == Decimal("95.00")


def test_an_attempt_entirely_below_the_minimum_is_refused_with_the_residual_named(
    fees: StubFees,
) -> None:
    intent = _intent("0.5")
    filters = coarse_filters(min_qty=Decimal("1"), step_size=Decimal("0.1"), min_notional=None)
    report = _adapter().submit_protection_exit(
        _attempt(intent, "0.5"),
        Decimal("0.5"),
        DEEP_BOOK,
        trade("95"),
        filters,
        fees,
        NOW,
        avg_price=AVG,
    )
    assert (report.status, report.reason) == ("rejected", "min_qty")
    assert report.residual is not None and report.residual.qty == Decimal("0.5")
    assert report.filled_qty == 0


def test_a_residual_without_a_valid_price_is_null_with_a_reason_never_zero(fees: StubFees) -> None:
    intent = _intent("0.5")
    filters = coarse_filters(min_qty=Decimal("1"), step_size=Decimal("0.1"), min_notional=None)
    report = _adapter().submit_protection_exit(
        _attempt(intent, "0.5"),
        Decimal("0.5"),
        DEEP_BOOK,
        None,
        filters,
        fees,
        NOW,
        avg_price=None,
    )
    assert report.residual is not None
    assert report.residual.value_quote is None
    assert report.residual.valuation_source.startswith("unavailable")


def test_the_attempt_never_sells_more_than_the_position_holds(
    filters: StubFilters, fees: StubFees
) -> None:
    """Spot cannot sell what it does not have; the clamp is in the attempt."""
    intent = _intent("10")
    attempt = _attempt(intent, "10", position_qty="6")
    assert attempt.qty == Decimal("6")
    report = _adapter().submit_protection_exit(
        attempt, Decimal("6"), DEEP_BOOK, trade("95"), filters, fees, NOW, avg_price=AVG
    )
    assert report.filled_qty == Decimal("6")


def test_a_shrinking_position_clamps_the_attempt_at_submission_too(
    filters: StubFilters, fees: StubFees
) -> None:
    """The competing protection sold in between: this attempt re-reads the position.

    Directive, "ordens simultâneas": the stop took 7 of the 10 while this target
    attempt was in flight, so the target sells 3, not 10.
    """
    intent = _intent("10")
    report = _adapter().submit_protection_exit(
        _attempt(intent, "10"),
        Decimal("3"),
        DEEP_BOOK,
        trade("95"),
        filters,
        fees,
        NOW,
        avg_price=AVG,
    )
    assert report.filled_qty == Decimal("3")
    assert report.requested_qty == Decimal("3")


def test_a_position_with_nothing_left_produces_no_order_at_all(
    filters: StubFilters, fees: StubFees
) -> None:
    intent = _intent("10")
    report = _adapter().submit_protection_exit(
        _attempt(intent, "10"),
        Decimal("0"),
        DEEP_BOOK,
        trade("95"),
        filters,
        fees,
        NOW,
        avg_price=AVG,
    )
    assert (report.status, report.reason, report.filled_qty) == ("rejected", "no_position_qty", 0)


def test_a_replayed_attempt_returns_the_recorded_report_and_never_fills_twice(
    filters: StubFilters, fees: StubFees
) -> None:
    journal = InMemoryExecutionJournal()
    adapter = PaperExecutionAdapter(journal=journal)
    intent = _intent("10")
    attempt = _attempt(intent, "10")
    first = adapter.submit_protection_exit(
        attempt, Decimal("10"), DEEP_BOOK, trade("95"), filters, fees, NOW, avg_price=AVG
    )
    second = adapter.submit_protection_exit(
        attempt, Decimal("10"), DEEP_BOOK, trade("95"), filters, fees, NOW, avg_price=AVG
    )
    assert second == first
    assert len(journal.reports) == 1
    folded = apply_attempt(intent, first, now=NOW, min_qty=Decimal("0.001"))
    assert folded.filled_qty == Decimal("10")


def test_a_missing_filter_reference_degrades_the_exit_instead_of_calling_it_dust(
    filters: StubFilters, fees: StubFees
) -> None:
    """Astra, T3.4 diff review, finding 4, reproduced then closed.

    Ten units to sell, the ``NOTIONAL`` filter needs the exchange average price
    and it is not there. The first version answered ``rejected`` with a residual
    of ten — a whole protected position reclassified as dust because a reference
    was late. Not knowing is not the same as knowing it is too small.
    """
    intent = _intent("10")
    report = _adapter().submit_protection_exit(
        _attempt(intent, "10"),
        Decimal("10"),
        DEEP_BOOK,
        None,
        filters,
        fees,
        NOW,
        avg_price=None,
    )
    assert (report.status, report.reason) == ("pending_degraded", "avg_price_unavailable")
    assert report.residual is None
    assert report.degraded and report.alert
    after = apply_attempt(intent, report, now=NOW, min_qty=Decimal("0.001"))
    assert after.remaining_qty == Decimal("10")
    assert after.live


def test_the_report_names_the_trade_that_fired_the_protection_not_the_one_it_saw(
    filters: StubFilters, fees: StubFees
) -> None:
    """Astra, T3.4 diff review, finding 5.

    The stop fires on print 102 at 94. There is no book, so the attempt retries
    later while the tape prints 99 — and the first version attributed the firing
    to that later print. The causing observation now travels with the attempt.
    """
    intent = _intent("10")
    fired = check_triggers(
        ProtectedPosition(
            position_id=intent.position_id, qty=Decimal("10"), stop_price=Decimal("95")
        ),
        [trade("94", trade_id="102")],
        NOW,
    )
    attempt = ExitAttempt.for_intent(
        intent, qty=Decimal("10"), decision_at=NOW - seconds(0.5), trigger=fired
    )
    report = _adapter().submit_protection_exit(
        attempt,
        Decimal("10"),
        DEEP_BOOK,
        trade("99", trade_id="140"),
        filters,
        fees,
        NOW,
        avg_price=AVG,
    )
    assert report.trigger_trade_id == "102"
    assert report.trigger_trade_price == Decimal("94")
    assert report.triggered_at == NOW
    assert report.observed_trade_id == "140"


def test_a_terminal_intention_is_refused_by_the_adapter_too(
    filters: StubFilters, fees: StubFees
) -> None:
    """Astra, round 2: the helper guarded it, the constructor did not.

    A ``voided`` intention handed straight to ``ExitAttempt`` sold two more
    units — the protection had already been settled by a competing one, and the
    position paid twice.
    """
    voided = void_intent(_intent("10"), now=NOW, reason="taken by the stop")
    with pytest.raises(ValueError, match="terminal"):
        ExitAttempt(
            attempt_id=uuid.uuid4(),
            intent=voided,
            qty=Decimal("2"),
            decision_at=NOW - seconds(0.5),
        )


def test_a_leftover_the_exchange_refuses_for_a_maximum_is_not_called_dust(fees: StubFees) -> None:
    """Astra, round 2, finding 4b: only a *minimum* makes a residual.

    Nine units left under a per-order maximum of five are perfectly sellable —
    in two attempts. Marking them ``below_min_qty`` would retire the protection
    of a position that can still be closed.
    """
    intent = _intent("10")
    capped = coarse_filters(max_qty=Decimal("5"), min_qty=Decimal("0.1"), min_notional=None)
    report = _adapter().submit_protection_exit(
        _attempt(intent, "1"),
        Decimal("10"),
        DEEP_BOOK,
        trade("95"),
        capped,
        fees,
        NOW,
        avg_price=AVG,
    )
    assert report.filled_qty == Decimal("1")
    assert report.residual is None


def test_a_book_from_another_market_never_fills_this_protection(
    filters: StubFilters, fees: StubFees
) -> None:
    """Astra, round 2: a decision on BTC filled against an ETH book.

    The identity has to be compared, not assumed — the same reason
    ``hunter_risk`` carries a ``MarketIdentity`` on every input.
    """
    intent = _intent("10").model_copy(
        update={
            "market": MarketIdentity(
                exchange="binance",
                symbol="BTCUSDT",
                market_type=MarketType.SPOT,
                base_asset="BTC",
                quote_asset="USDT",
            )
        }
    )
    other = book(bids=[("95.00", "10")]).model_copy(update={"symbol": "ETHUSDT"})
    report = _adapter().submit_protection_exit(
        _attempt(intent, "10"),
        Decimal("10"),
        other,
        trade("95"),
        filters,
        fees,
        NOW,
        avg_price=AVG,
    )
    assert (report.status, report.reason) == ("pending_degraded", "market_mismatch")
    assert report.filled_qty == 0
