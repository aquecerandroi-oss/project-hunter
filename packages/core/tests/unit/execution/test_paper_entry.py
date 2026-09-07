"""The paper entry: one attempt, one walk, the remainder cancelled for good.

Every case below is a market condition with a name (the deep book, the thin
book, the stale book), because "why did this fill 2 instead of 10" has to be
answerable by reading the test name.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from hunter_core.domain.enums import ExecutionMode, OrderSide
from hunter_core.execution import (
    EXECUTION_POLICY_VERSION,
    ExecutionPolicy,
    InMemoryExecutionJournal,
    PaperExecutionAdapter,
    ReplayMismatch,
)
from hunter_core.execution.entries import MarketEntryOrder

from .conftest import (
    DEEP_BOOK,
    NOW,
    THIN_BOOK,
    StubFees,
    StubFilters,
    approved_decision,
    book,
    coarse_filters,
    seconds,
    trade,
)

AVG = Decimal("100")


def _order(
    qty: str = "3", *, entry_ref: str = "100", decided_s_ago: float = 0.5
) -> MarketEntryOrder:
    return MarketEntryOrder(
        decision=approved_decision(
            proposal_id=uuid.UUID(int=5),
            qty=str(Decimal(qty)),
            entry_ref=str(Decimal(entry_ref)),
            stop=str(Decimal("95")),
        ),
        qty=Decimal(qty),
        decision_at=NOW - seconds(decided_s_ago),
    )


def _adapter(**policy: object) -> PaperExecutionAdapter:
    return PaperExecutionAdapter(policy=ExecutionPolicy(**policy))  # type: ignore[arg-type]


def test_a_deep_book_fills_the_whole_order_at_the_best_ask(
    filters: StubFilters, fees: StubFees
) -> None:
    report = _adapter().submit_market_entry(
        _order("3"), DEEP_BOOK, trade("100"), filters, fees, NOW, avg_price=AVG
    )
    assert report.status == "filled"
    assert report.mode is ExecutionMode.PAPER
    assert report.side is OrderSide.BUY
    assert report.filled_qty == Decimal("3")
    assert report.gross_quote == Decimal("300.00")
    assert report.execution_key == f"entry:{uuid.UUID(int=5)}"
    assert report.execution_policy_version == EXECUTION_POLICY_VERSION
    assert report.book_policy_version == "spot_book_walk_v1"


def test_the_taker_fee_is_charged_in_the_base_asset_and_shrinks_what_we_own(
    filters: StubFilters, fees: StubFees
) -> None:
    """Binance spot charges the fee on the asset received: a buy pays in BTC.

    So the position is smaller than the quantity that traded, and the sellable
    quantity later is smaller than what the sizing approved. Booking the fee in
    USDT as well would charge the same 0,1 % twice.
    """
    report = _adapter().submit_market_entry(
        _order("3"), DEEP_BOOK, trade("100"), filters, fees, NOW, avg_price=AVG
    )
    assert report.fee is not None
    assert report.fee.asset == "base"
    assert report.fee.qty == Decimal("0.00300000")
    assert report.net_base_delta == Decimal("3") - Decimal("0.003")
    assert report.net_quote_delta == -Decimal("300.00")
    assert report.fee.quote_equivalent == Decimal("0.30000000")


def test_a_thin_book_fills_what_is_there_and_cancels_the_rest_terminally(
    filters: StubFilters, fees: StubFees
) -> None:
    """No automatic parcelling: what did not fill is gone, not queued."""
    report = _adapter().submit_market_entry(
        _order("10"), THIN_BOOK, trade("100"), filters, fees, NOW, avg_price=AVG
    )
    assert report.status == "partially_filled"
    assert report.filled_qty == Decimal("2")
    assert report.unfilled_qty == Decimal("8")
    assert report.remaining_cancelled is True
    assert report.depth_exhausted is True


def test_a_quantity_below_the_minimum_is_refused_with_the_filter_reason(fees: StubFees) -> None:
    """Round down, then refuse — never round up into a size nobody approved."""
    report = _adapter().submit_market_entry(
        _order("0.0004"),
        DEEP_BOOK,
        trade("100"),
        coarse_filters(min_qty=Decimal("0.001")),
        fees,
        NOW,
        avg_price=AVG,
    )
    assert report.status == "rejected"
    assert report.reason == "min_qty"
    assert report.filled_qty == 0
    assert report.levels == ()


def test_a_notional_below_the_exchange_floor_is_refused(fees: StubFees) -> None:
    """Measured live on BTCUSDT (T3.0a §10): the LOT_SIZE minimum of 0,00001 BTC
    is itself refused by the 5 USDT NOTIONAL floor. That is a decision reason,
    not an error."""
    report = _adapter().submit_market_entry(
        _order("0.001"),
        DEEP_BOOK,
        trade("100"),
        coarse_filters(min_notional=Decimal("5")),
        fees,
        NOW,
        avg_price=AVG,
    )
    assert (report.status, report.reason) == ("rejected", "min_notional")


def test_without_the_average_price_the_notional_filter_refuses_instead_of_guessing(
    filters: StubFilters, fees: StubFees
) -> None:
    """``avgPriceMins`` names a price the exchange computes; substituting the
    last trade would be answering a filter with a number it never asked for."""
    report = _adapter().submit_market_entry(
        _order("3"), DEEP_BOOK, trade("100"), filters, fees, NOW, avg_price=None
    )
    assert (report.status, report.reason) == ("rejected", "avg_price_unavailable")


def test_a_book_older_than_the_budget_rejects_the_entry_without_a_fill(
    filters: StubFilters, fees: StubFees
) -> None:
    stale = book(asks=[("100.00", "10")], received_at=NOW - seconds(30))
    report = _adapter().submit_market_entry(
        _order("3", decided_s_ago=60), stale, trade("100"), filters, fees, NOW, avg_price=AVG
    )
    assert (report.status, report.reason) == ("rejected", "book_stale")
    assert report.filled_qty == 0


def test_the_walk_uses_a_book_observed_after_the_declared_latency(
    filters: StubFilters, fees: StubFees
) -> None:
    """The snapshot the decision itself looked at is not the book the order met."""
    order = _order("3")
    same_instant = book(asks=[("100.00", "10")], received_at=order.decision_at)
    adapter = _adapter(latency_ms=150)
    report = adapter.submit_market_entry(
        order, same_instant, trade("100"), filters, fees, NOW, avg_price=AVG
    )
    assert (report.status, report.reason) == ("rejected", "book_before_latency")
    later = book(asks=[("100.00", "10")], received_at=order.decision_at + seconds(0.2))
    assert (
        adapter.submit_market_entry(
            order, later, trade("100"), filters, fees, NOW, avg_price=AVG
        ).status
        == "filled"
    )


def test_paying_above_the_reference_is_published_as_adverse_slippage(
    filters: StubFilters, fees: StubFees
) -> None:
    """Positive is adverse, and nothing "corrects" it back to the reference."""
    expensive = book(asks=[("101.00", "10")])
    report = _adapter().submit_market_entry(
        _order("3", entry_ref="100"), expensive, trade("101"), filters, fees, NOW, avg_price=AVG
    )
    assert report.slippage_vs_plan_quote == Decimal("3.00")
    assert report.slippage_vs_plan_bps == Decimal("100.00000000")
    assert report.planned_price == Decimal("100")


def test_the_declared_slippage_model_is_published_apart_from_what_the_book_did(
    filters: StubFilters, fees: StubFees
) -> None:
    report = _adapter(extra_slippage_bps=Decimal("10")).submit_market_entry(
        _order("3"), DEEP_BOOK, trade("100"), filters, fees, NOW, avg_price=AVG
    )
    assert report.vwap_before_adjustment == Decimal("100.00")
    assert report.vwap == Decimal("100.10000000")
    assert report.model_adjustment_bps == Decimal("10")
    assert report.gross_quote == Decimal("300.30000000")


def test_a_replayed_entry_returns_the_recorded_report_and_never_walks_again(
    filters: StubFilters, fees: StubFees
) -> None:
    """Idempotency of the execution: one decision, one order, one fill.

    The replay is handed a *different* book on purpose — a second walk would
    show up as a different price, and it does not happen.
    """
    journal = InMemoryExecutionJournal()
    adapter = PaperExecutionAdapter(journal=journal)
    order = _order("3")
    first = adapter.submit_market_entry(
        order, DEEP_BOOK, trade("100"), filters, fees, NOW, avg_price=AVG
    )
    richer = book(asks=[("90.00", "10")])
    second = adapter.submit_market_entry(
        order, richer, trade("90"), filters, fees, NOW, avg_price=AVG
    )
    assert second == first
    assert second.gross_quote == Decimal("300.00")
    assert len(journal.reports) == 1


def test_an_empty_book_produces_no_entry_fill_at_all(filters: StubFilters, fees: StubFees) -> None:
    report = _adapter().submit_market_entry(
        _order("3"), book(asks=[]), trade("100"), filters, fees, NOW, avg_price=AVG
    )
    assert (report.status, report.reason, report.filled_qty) == ("rejected", "empty_side", 0)


def test_a_book_of_another_symbol_never_fills_this_entry(
    filters: StubFilters, fees: StubFees
) -> None:
    """The decision priced BTCUSDT; this book is ETHUSDT (Astra, round 2)."""
    other = book(asks=[("100.00", "10")]).model_copy(update={"symbol": "ETHUSDT"})
    report = _adapter().submit_market_entry(
        _order("3"), other, trade("100"), filters, fees, NOW, avg_price=AVG
    )
    assert (report.status, report.reason) == ("rejected", "market_mismatch")
    assert report.filled_qty == 0


def test_a_trade_we_have_not_received_cannot_serve_as_the_filter_reference(fees: StubFees) -> None:
    """``avgPriceMins == 0`` means "use the last price" — a *valid* last price.

    Astra, round 2: with the average unavailable and the last print not yet
    received locally, the entry filled anyway. Temporal validity was enforced on
    triggers only; now the same rule guards every use of a trade.
    """
    not_yet = trade("100").model_copy(update={"received_at": NOW + seconds(5)})
    report = _adapter().submit_market_entry(
        _order("3"),
        DEEP_BOOK,
        not_yet,
        coarse_filters(avg_price_mins=0),
        fees,
        NOW,
        avg_price=None,
    )
    assert (report.status, report.reason) == ("rejected", "avg_price_unavailable")
    assert report.observed_trade_id == "100"


def test_a_replay_of_the_same_key_with_another_quantity_fails_loudly(
    filters: StubFilters, fees: StubFees
) -> None:
    """Review of 2026-09-07, item 9: the old fill answered a *different* order.

    ``entry:{proposal_id}`` is the identity of one decision, and the recorded
    report was handed back for any order carrying that key. A worker that
    re-decided the proposal for 2 units received the report of the 3 units that
    executed — a position 50 % larger than the caller believes it holds, with
    nothing in the log saying so.
    """
    journal = InMemoryExecutionJournal()
    adapter = PaperExecutionAdapter(journal=journal)
    first = adapter.submit_market_entry(
        _order("3"), DEEP_BOOK, trade("100"), filters, fees, NOW, avg_price=AVG
    )
    assert first.filled_qty == Decimal("3")

    with pytest.raises(ReplayMismatch) as raised:
        adapter.submit_market_entry(
            _order("2"), DEEP_BOOK, trade("100"), filters, fees, NOW, avg_price=AVG
        )
    assert raised.value.recorded_qty == Decimal("3")
    assert raised.value.requested_qty == Decimal("2")
    assert raised.value.execution_key == f"entry:{uuid.UUID(int=5)}"
    assert len(journal.reports) == 1


def test_a_replay_of_the_same_key_behind_another_decision_fails_loudly(
    filters: StubFilters, fees: StubFees
) -> None:
    """Same proposal, same size, a decision that sized against another price.

    The proposal id is in the key, so it can never diverge; the decision behind
    it can — a re-evaluation with a different ``sizing_price`` and stop is not
    the order that executed, and answering "already done" hides the difference.
    """
    journal = InMemoryExecutionJournal()
    adapter = PaperExecutionAdapter(journal=journal)
    recorded = adapter.submit_market_entry(
        _order("3"), DEEP_BOOK, trade("100"), filters, fees, NOW, avg_price=AVG
    )
    assert recorded.decision_fingerprint

    with pytest.raises(ReplayMismatch) as raised:
        adapter.submit_market_entry(
            _order("3", entry_ref="101"), DEEP_BOOK, trade("100"), filters, fees, NOW, avg_price=AVG
        )
    assert raised.value.recorded_decision == recorded.decision_fingerprint
    assert raised.value.requested_decision != recorded.decision_fingerprint
    assert raised.value.recorded_qty == raised.value.requested_qty == Decimal("3")


def test_a_fill_outside_the_percent_price_band_never_opens_a_position(
    filters: StubFilters, fees: StubFees
) -> None:
    """Review of 2026-09-07, item 15: ``PERCENT_PRICE_BY_SIDE``, finally used.

    The band is **ours**, not the exchange's — Binance applies that filter to a
    limit price and never rejects a MARKET order for it (T3.0a §5). It is here
    as a sanity guard on a *simulated* fill: this book says the best ask is 500
    while the reference price is 100, which is a corrupted snapshot, not a
    market. Filling it would credit the paper wallet with a position bought at
    five times the price, and paper equity is the whole output of the lab.
    """
    corrupted = book(asks=[("500.00", "10")])
    report = _adapter().submit_market_entry(
        _order("3"), corrupted, trade("100"), filters, fees, NOW, avg_price=AVG
    )
    assert (report.status, report.reason) == ("rejected", "price_band")
    assert report.filled_qty == 0
    assert report.remaining_cancelled is True


def test_a_symbol_without_published_multipliers_has_no_band_to_breach(fees: StubFees) -> None:
    """``price_band`` answers ``(avg, avg)`` when the symbol publishes none.

    Treating that as a band would refuse every fill whose vwap is not exactly
    the reference — which is every fill.
    """
    bandless = coarse_filters(
        bid_multiplier_down=None,
        bid_multiplier_up=None,
        ask_multiplier_down=None,
        ask_multiplier_up=None,
    )
    report = _adapter().submit_market_entry(
        _order("3"), DEEP_BOOK, trade("100"), bandless, fees, NOW, avg_price=AVG
    )
    assert report.status == "filled"


def test_a_recorded_report_without_its_identity_is_never_taken_for_the_same_order(
    filters: StubFilters, fees: StubFees
) -> None:
    """Astra, T3.4b review, MUST-FIX 3: absent identity is not "identical".

    A report rebuilt from Postgres carries whatever columns exist. If
    ``submitted_qty`` is not among them, treating the missing value as a match
    hands the recorded fill of 3 to an order for 2 — the very case the guard was
    added for, defeated by the round trip. Unknown identity fails closed.
    """
    journal = InMemoryExecutionJournal()
    adapter = PaperExecutionAdapter(journal=journal)
    first = adapter.submit_market_entry(
        _order("3"), DEEP_BOOK, trade("100"), filters, fees, NOW, avg_price=AVG
    )
    journal.reports[first.execution_key] = first.model_copy(
        update={"submitted_qty": None, "decision_fingerprint": ""}
    )
    with pytest.raises(ReplayMismatch) as raised:
        adapter.submit_market_entry(
            _order("2"), DEEP_BOOK, trade("100"), filters, fees, NOW, avg_price=AVG
        )
    assert raised.value.recorded_qty is None
    assert raised.value.requested_qty == Decimal("2")
