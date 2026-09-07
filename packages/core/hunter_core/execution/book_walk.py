"""One walk, over the depth we really saw, on a book we are allowed to use.

Two decisions, kept apart on purpose:

**Is this book usable** (:func:`eligible_book`). The M3 joint decision says the
fill is "sempre determinado pelo livro elegível **após a latência declarada**".
On spot there is no exchange clock in the ``depth`` payload at all — the T3.0a
notes record that ``ts == received_at`` exactly — so "after the latency" is a
statement about *our* receipt, and this module measures it there and says so.
Seven ways a book is refused, each with its own reason: it is another market's,
its side is empty, it carries a level priced at zero or below (corrupt data the
stream parsers cannot catch, because they build levels with ``model_construct``),
it was observed before the latency elapsed, it is older than the declared budget,
it comes from the future (a clock disagreement is never "very fresh"), or its
sequence went backwards. Every one of them is a **verdict**, never an exception
raised from inside an attempt.

**What does it fill** (:func:`walk_book`). A single pass, best price first,
stopping when the levels run out — ``depth_exhausted`` instead of an extrapolated
level. ``already_consumed`` is what makes re-handing the same snapshot honest:
the same 100 ms photograph does not restore depth another attempt already ate.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from pydantic import Field

from hunter_core.domain.enums import OrderSide
from hunter_core.domain.market import BookLevel, NormalizedOrderBook
from hunter_core.execution.adapter import ExecutionModel, LevelFill
from hunter_core.strategies.numeric import CONTEXT

__all__ = [
    "BOOK_POLICY_VERSION",
    "BookVerdict",
    "BookWalk",
    "eligible_book",
    "walk_book",
]

BOOK_POLICY_VERSION = "spot_book_walk_v1"
"""Versioned because a simulated fill is only comparable over time if its rules are."""

_QUANTUM = Decimal("0.00000001")


class BookVerdict(ExecutionModel):
    """Whether the snapshot may be walked, and — when not — exactly why."""

    eligible: bool
    reason: str = ""
    received_at: datetime | None = None
    sequence: int | None = None
    age_s: Decimal | None = None


class BookWalk(ExecutionModel):
    """The result of one pass: what filled, at which levels, and what did not."""

    filled_qty: Decimal = Field(ge=0)
    unfilled_qty: Decimal = Field(ge=0)
    gross_quote: Decimal = Field(ge=0)
    levels: tuple[LevelFill, ...] = ()
    depth_exhausted: bool = False
    vwap: Decimal | None = None


def _seconds(delta: timedelta) -> Decimal:
    with localcontext(CONTEXT):
        return Decimal(delta.total_seconds()).quantize(_QUANTUM)


def _side_levels(book: NormalizedOrderBook, side: OrderSide) -> Sequence[BookLevel]:
    """A buy eats the asks, a sell hits the bids. Both are already best-first."""
    return book.asks if side is OrderSide.BUY else book.bids


def eligible_book(
    book: NormalizedOrderBook | None,
    *,
    decision_at: datetime,
    latency: timedelta,
    now: datetime,
    max_age: timedelta,
    previous_sequence: int | None = None,
    side: OrderSide = OrderSide.BUY,
    market: tuple[str, str] | None = None,
) -> BookVerdict:
    """Judge one snapshot against the market, latency, age and sequence rules."""
    if book is None:
        return BookVerdict(eligible=False, reason="no_book")
    if market is not None and (book.exchange, book.symbol) != market:
        # A decision priced on BTCUSDT filled against an ETH book is an entry
        # sized on liquidity that does not exist for the order being sent.
        return BookVerdict(eligible=False, reason="market_mismatch", received_at=book.received_at)
    received_at = book.received_at
    levels = _side_levels(book, side)
    if not levels:
        return BookVerdict(eligible=False, reason="empty_side", received_at=received_at)
    if any(level.price <= 0 or level.qty < 0 for level in levels):
        # ``BookLevel`` bounds both, but the stream parsers build levels with
        # ``model_construct`` and no validator runs there. Without this the walk
        # raised ``ValidationError`` from inside ``LevelFill`` - an exception
        # escaping the adapter instead of a verdict the caller can record,
        # degrade and alert on (review of 2026-09-07, item 11).
        return BookVerdict(
            eligible=False,
            reason="non_positive_level",
            received_at=received_at,
            sequence=book.sequence,
        )
    if received_at > now:
        return BookVerdict(
            eligible=False,
            reason="book_from_the_future",
            received_at=received_at,
            sequence=book.sequence,
        )
    age = _seconds(now - received_at)
    if received_at < decision_at + latency:
        return BookVerdict(
            eligible=False,
            reason="book_before_latency",
            received_at=received_at,
            sequence=book.sequence,
            age_s=age,
        )
    if now - received_at > max_age:
        return BookVerdict(
            eligible=False,
            reason="book_stale",
            received_at=received_at,
            sequence=book.sequence,
            age_s=age,
        )
    if (
        previous_sequence is not None
        and book.sequence is not None
        and book.sequence <= previous_sequence
    ):
        return BookVerdict(
            eligible=False,
            reason="book_sequence_regression",
            received_at=received_at,
            sequence=book.sequence,
            age_s=age,
        )
    return BookVerdict(eligible=True, received_at=received_at, sequence=book.sequence, age_s=age)


def _consumed_by_price(already_consumed: Iterable[LevelFill]) -> dict[Decimal, Decimal]:
    taken: dict[Decimal, Decimal] = {}
    for level in already_consumed:
        taken[level.price] = taken.get(level.price, Decimal(0)) + level.qty
    return taken


def walk_book(
    book: NormalizedOrderBook,
    qty: Decimal,
    *,
    side: OrderSide,
    already_consumed: Iterable[LevelFill] = (),
) -> BookWalk:
    """Consume ``qty`` from ``side`` of ``book``, level by level, exactly once."""
    if qty <= 0:
        raise ValueError(f"a walk needs a positive quantity, got {qty}")
    taken = _consumed_by_price(already_consumed)
    remaining = qty
    fills: list[LevelFill] = []
    gross = Decimal(0)
    with localcontext(CONTEXT):
        for level in _side_levels(book, side):
            if remaining <= 0:
                break
            available = level.qty - taken.get(level.price, Decimal(0))
            if available <= 0:
                continue
            hit = min(remaining, available)
            fills.append(LevelFill(price=level.price, qty=hit))
            gross += level.price * hit
            remaining -= hit
        filled = qty - remaining
        vwap = (gross / filled).quantize(_QUANTUM) if filled > 0 else None
    return BookWalk(
        filled_qty=filled,
        unfilled_qty=remaining,
        gross_quote=gross,
        levels=tuple(fills),
        depth_exhausted=remaining > 0,
        vwap=vwap,
    )
