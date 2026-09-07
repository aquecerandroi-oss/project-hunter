"""The book walk: one pass, only over depth we actually observed.

Two separate questions live here and the tests keep them apart:

- **is this book usable at all** (:func:`eligible_book`) — the declared latency
  has to have passed, the snapshot may not be older than the declared budget,
  may not come from the future, and may not be a sequence regression;
- **what does it fill** (:func:`walk_book`) — a single pass, never more than the
  levels hold, and the same snapshot handed back does not restore depth another
  attempt already ate.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from hunter_core.domain.enums import OrderSide
from hunter_core.domain.market import BookLevel
from hunter_core.execution.book_walk import (
    BOOK_POLICY_VERSION,
    eligible_book,
    walk_book,
)

from .conftest import DEEP_BOOK, EMPTY_BOOK, NOW, THIN_BOOK, book, seconds

LATENCY = seconds(0.15)


def test_a_book_received_after_the_declared_latency_is_eligible() -> None:
    fresh = book(asks=[("100", "1")], received_at=NOW - seconds(0.05))
    verdict = eligible_book(
        fresh, decision_at=NOW - seconds(0.30), latency=LATENCY, now=NOW, max_age=seconds(10)
    )
    assert verdict.eligible
    assert verdict.reason == ""
    assert verdict.sequence == 1_000


def test_a_book_observed_before_the_latency_elapsed_is_not_eligible() -> None:
    """The fill has to come from the book the order would really have met.

    Decision at 12:00:00.000 with 150 ms of declared latency: a snapshot from
    12:00:00.100 is the book *before* the order arrived, and using it is how a
    simulator quietly awards itself prices that were already gone.
    """
    early = book(asks=[("100", "1")], received_at=NOW - seconds(0.05))
    verdict = eligible_book(
        early, decision_at=NOW, latency=LATENCY, now=NOW + seconds(0.2), max_age=seconds(10)
    )
    assert not verdict.eligible
    assert verdict.reason == "book_before_latency"


def test_a_stale_book_is_not_eligible() -> None:
    old = book(asks=[("100", "1")], received_at=NOW - seconds(30))
    verdict = eligible_book(
        old, decision_at=NOW - seconds(60), latency=LATENCY, now=NOW, max_age=seconds(10)
    )
    assert not verdict.eligible
    assert verdict.reason == "book_stale"
    assert verdict.age_s == Decimal(30)


def test_a_book_from_the_future_is_not_eligible() -> None:
    """A negative age is a clock disagreement, never "very fresh"."""
    ahead = book(asks=[("100", "1")], received_at=NOW + seconds(5))
    verdict = eligible_book(
        ahead, decision_at=NOW - seconds(1), latency=LATENCY, now=NOW, max_age=seconds(10)
    )
    assert not verdict.eligible
    assert verdict.reason == "book_from_the_future"


def test_a_sequence_that_does_not_advance_is_a_regression() -> None:
    replayed = book(asks=[("100", "1")], received_at=NOW, sequence=900)
    verdict = eligible_book(
        replayed,
        decision_at=NOW - seconds(1),
        latency=LATENCY,
        now=NOW,
        max_age=seconds(10),
        previous_sequence=900,
    )
    assert not verdict.eligible
    assert verdict.reason == "book_sequence_regression"


def test_a_missing_or_empty_side_is_not_eligible() -> None:
    for candidate, reason in ((None, "no_book"), (EMPTY_BOOK, "empty_side")):
        verdict = eligible_book(
            candidate,
            decision_at=NOW - seconds(1),
            latency=LATENCY,
            now=NOW,
            max_age=seconds(10),
            side=OrderSide.SELL,
        )
        assert not verdict.eligible
        assert verdict.reason == reason


def test_a_small_buy_is_filled_at_the_best_ask_alone() -> None:
    walk = walk_book(DEEP_BOOK, Decimal("3"), side=OrderSide.BUY)
    assert walk.filled_qty == Decimal("3")
    assert walk.gross_quote == Decimal("300.00")
    assert walk.vwap == Decimal("100.00")
    assert [level.price for level in walk.levels] == [Decimal("100.00")]
    assert walk.unfilled_qty == 0
    assert not walk.depth_exhausted


def test_a_larger_buy_pays_every_level_it_eats() -> None:
    walk = walk_book(DEEP_BOOK, Decimal("15"), side=OrderSide.BUY)
    assert walk.filled_qty == Decimal("15")
    assert walk.gross_quote == Decimal("1000.00") + Decimal("500.50")
    assert walk.vwap == (Decimal("1500.50") / Decimal("15")).quantize(Decimal("0.00000001"))
    assert [(level.price, level.qty) for level in walk.levels] == [
        (Decimal("100.00"), Decimal("10")),
        (Decimal("100.10"), Decimal("5")),
    ]


def test_the_walk_never_invents_depth_beyond_the_levels_observed() -> None:
    """The thin book holds 2; asking for 10 fills 2 and says the depth ran out."""
    walk = walk_book(THIN_BOOK, Decimal("10"), side=OrderSide.BUY)
    assert walk.filled_qty == Decimal("2")
    assert walk.unfilled_qty == Decimal("8")
    assert walk.depth_exhausted


def test_a_sell_walks_the_bids_from_the_best_down() -> None:
    walk = walk_book(DEEP_BOOK, Decimal("12"), side=OrderSide.SELL)
    assert [(level.price, level.qty) for level in walk.levels] == [
        (Decimal("99.90"), Decimal("10")),
        (Decimal("99.80"), Decimal("2")),
    ]
    assert walk.gross_quote == Decimal("999.00") + Decimal("199.60")


def test_the_same_snapshot_handed_back_does_not_restore_consumed_depth() -> None:
    """Joint decision, item 3: "reentrega do mesmo snapshot não repõe profundidade".

    Without this, two attempts inside one 100 ms snapshot both buy the same 10
    units at the best ask and the simulated wallet reports liquidity that never
    existed.
    """
    first = walk_book(DEEP_BOOK, Decimal("10"), side=OrderSide.BUY)
    second = walk_book(DEEP_BOOK, Decimal("10"), side=OrderSide.BUY, already_consumed=first.levels)
    assert [(level.price, level.qty) for level in second.levels] == [
        (Decimal("100.10"), Decimal("10"))
    ]
    assert second.gross_quote == Decimal("1001.00")


def test_a_walk_of_an_empty_side_fills_nothing_and_raises_nothing() -> None:
    walk = walk_book(EMPTY_BOOK, Decimal("1"), side=OrderSide.SELL)
    assert walk.filled_qty == 0
    assert walk.levels == ()
    assert walk.vwap is None
    assert walk.depth_exhausted


def test_a_non_positive_quantity_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="positive"):
        walk_book(DEEP_BOOK, Decimal("0"), side=OrderSide.BUY)


def test_the_policy_version_is_published() -> None:
    """A simulated fill is only comparable over time if the rules are versioned."""
    assert BOOK_POLICY_VERSION == "spot_book_walk_v1"


def test_eligibility_uses_the_receive_stamp_because_spot_has_no_exchange_clock() -> None:
    """T3.0a §4: spot ``depth`` carries no timestamp; ``ts == received_at``.

    So "the book after the latency" is a statement about *our* receipt, and the
    test pins it: moving only ``received_at`` moves the verdict.
    """
    decided_at = NOW - timedelta(milliseconds=200)
    late_enough = book(asks=[("100", "1")], received_at=NOW)
    assert eligible_book(
        late_enough, decision_at=decided_at, latency=LATENCY, now=NOW, max_age=seconds(10)
    ).eligible
    too_early = book(asks=[("100", "1")], received_at=NOW - timedelta(milliseconds=100))
    assert not eligible_book(
        too_early, decision_at=decided_at, latency=LATENCY, now=NOW, max_age=seconds(10)
    ).eligible


def test_a_price_of_zero_is_not_a_book_level_at_all() -> None:
    """Review of 2026-09-07, item 11, half one: the model refuses it.

    ``BookLevel.qty`` was bounded and ``price`` was not, so a level priced at 0
    (or below) was a legal object all the way into the walk.
    """
    with pytest.raises(ValidationError):
        BookLevel(price=Decimal("0"), qty=Decimal("1"))


def test_a_non_positive_level_is_refused_as_a_verdict_not_as_an_exception() -> None:
    """Half two, which is the one that matters in production.

    The Binance stream parser builds levels with ``model_construct``
    (``binance/streams.py``: "``BookLevel.Field(ge=0)`` doesn't run under
    ``model_construct``"), so validation never ran on that path. A zero-priced
    level then reached ``walk_book``, where ``LevelFill(price=0)`` raised a
    ``ValidationError`` out of the middle of an attempt — an exception escaping
    the adapter instead of a report, which is the one thing the caller cannot
    write down, degrade or alert on.
    """
    corrupt = book(asks=[("100", "1")]).model_copy(
        update={"asks": [BookLevel.model_construct(price=Decimal("0"), qty=Decimal("1"))]}
    )
    verdict = eligible_book(
        corrupt, decision_at=NOW - seconds(1), latency=LATENCY, now=NOW, max_age=seconds(10)
    )
    assert not verdict.eligible
    assert verdict.reason == "non_positive_level"
