"""Properties, over random books: value is conserved and nothing is invented.

Table-driven cases prove the rules we thought of. These two properties are for
the ones we did not:

1. **the fee is the only leak.** For a buy, what left the wallet in quote equals
   what the book charged, and what arrived in base equals what traded minus the
   fee — counted **once**, in the asset it was charged in. This is the identity
   the ledger's ``equity = cash + Σ positions`` rests on: if the adapter created
   or destroyed value here, no amount of care downstream would recover it;
2. **no fill exceeds the observed depth**, ever, for any random book and any
   requested quantity.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from hunter_core.domain.enums import OrderSide
from hunter_core.execution.book_walk import walk_book
from hunter_core.execution.entries import MarketEntryOrder
from hunter_core.execution.paper import PaperExecutionAdapter

from .conftest import NOW, StubFees, StubFilters, approved_decision, book, seconds, trade

_ADAPTER = PaperExecutionAdapter()
_FILTERS = StubFilters(step_size=Decimal("0.001"), min_qty=Decimal("0.001"), min_notional=None)
_FEES = StubFees()

_levels = st.lists(
    st.tuples(
        st.integers(min_value=9_000, max_value=11_000),
        st.integers(min_value=1, max_value=5_000),
    ),
    min_size=1,
    max_size=8,
)
_qty = st.integers(min_value=1, max_value=20_000)


def _ascending(raw: list[tuple[int, int]]) -> list[tuple[str, str]]:
    """Prices ascending (an ask side), quantities in thousandths."""
    prices = sorted({price for price, _ in raw})
    return [
        (str(Decimal(price) / 100), str(Decimal(qty) / 1000))
        for price, (_, qty) in zip(prices, raw, strict=False)
    ]


@settings(max_examples=75, deadline=None)
@given(raw=_levels, requested=_qty)
def test_the_only_value_that_leaves_the_trade_is_the_fee(
    raw: list[tuple[int, int]], requested: int
) -> None:
    asks = _ascending(raw)
    order = MarketEntryOrder(
        decision=approved_decision(
            proposal_id=uuid.uuid4(),
            qty=str(Decimal(requested) / 1000),
            entry_ref=str(Decimal("100")),
            stop=str(Decimal("95")),
        ),
        qty=Decimal(requested) / 1000,
        decision_at=NOW - seconds(1),
    )
    report = _ADAPTER.submit_market_entry(
        order, book(asks=asks), trade("100"), _FILTERS, _FEES, NOW, avg_price=Decimal("100")
    )
    if not report.filled:
        assert report.gross_quote == 0
        assert report.net_base_delta == 0
        return
    assert report.fee is not None
    walked = sum(level.price * level.qty for level in report.levels)
    assert report.gross_quote == walked
    assert report.net_quote_delta == -walked
    assert report.net_base_delta == report.filled_qty - report.fee.qty
    assert report.net_base_delta < report.filled_qty  # the fee always costs something
    assert report.fee.asset == "base"


@settings(max_examples=75, deadline=None)
@given(raw=_levels, requested=_qty)
def test_a_walk_never_fills_more_than_the_levels_hold(
    raw: list[tuple[int, int]], requested: int
) -> None:
    asks = _ascending(raw)
    depth = sum(Decimal(qty) for _, qty in asks)
    walk = walk_book(book(asks=asks), Decimal(requested) / 1000, side=OrderSide.BUY)
    assert walk.filled_qty <= depth
    assert walk.filled_qty + walk.unfilled_qty == Decimal(requested) / 1000
    assert sum(level.qty for level in walk.levels) == walk.filled_qty
