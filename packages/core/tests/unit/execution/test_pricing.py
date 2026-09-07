"""One definition of a usable trade, used everywhere a price is trusted.

``usable_trade`` is the marking policy's only definition (age, receipt,
sequence). Anything that re-implements part of it drifts from it, and the part
that drifts is always the part nobody wrote a test for.
"""

from __future__ import annotations

from decimal import Decimal

from hunter_core.execution.pricing import ExecutionPolicy, mark_price

from .conftest import NOW, seconds, trade

POLICY = ExecutionPolicy()


def test_a_fresh_spot_trade_values_a_residual_and_names_itself() -> None:
    price, source = mark_price(trade("100", trade_id="101"), None, now=NOW, policy=POLICY)
    assert price == Decimal("100")
    assert source == "last_spot_trade:101"


def test_a_trade_we_have_not_received_yet_never_values_anything() -> None:
    """Review of 2026-09-07, item 10: ``mark_price`` had its own age rule.

    It checked ``0 <= now - trade.ts <= max_trade_age_s`` and not
    ``received_at <= now``, so a print stamped by the exchange that our socket
    had not seen priced a residual — the exact input ``usable_trade`` exists to
    refuse (Astra, round 2), accepted through the other door.
    """
    not_yet = trade("100", trade_id="101").model_copy(update={"received_at": NOW + seconds(5)})
    assert mark_price(not_yet, None, now=NOW, policy=POLICY) == (
        None,
        "unavailable: no valid spot trade and no average price",
    )


def test_the_exchange_average_is_the_fallback_never_the_unusable_print() -> None:
    not_yet = trade("100", trade_id="101").model_copy(update={"received_at": NOW + seconds(5)})
    assert mark_price(not_yet, Decimal("99"), now=NOW, policy=POLICY) == (
        Decimal("99"),
        "exchange_avg_price",
    )


def test_a_stale_print_still_falls_back_instead_of_pricing_with_it() -> None:
    stale = trade("100", trade_id="101", ts=NOW - seconds(45))
    assert mark_price(stale, Decimal("99"), now=NOW, policy=POLICY)[1] == "exchange_avg_price"
