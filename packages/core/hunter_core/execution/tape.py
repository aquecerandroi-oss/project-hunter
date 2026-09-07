"""Reading one batch of spot prints: what is usable, and what we cannot read.

Split out of :mod:`hunter_core.execution.triggers` so that module answers only
"what does a crossing mean" while this one answers "what did we actually
manage to read". The rules are the versioned marking policy
(``spot_last_trade_v1``) and they are the same everywhere a price is trusted:

- **age** — ``0 <= now - trade.ts <= max_trade_age_s``, measured against the
  exchange's own clock, which ``aggTrade`` really carries (unlike the spot
  book, which carries none). 10 s is a **declared** budget, not a measured
  guarantee, and it travels on every report;
- **receipt** — ``received_at <= now``: a print stamped by the exchange that our
  socket has not seen decides nothing;
- **sequence** — ids advance strictly, compared as integers. A print that goes
  backwards is a replay; a repeat does not refresh the age, but the last
  accepted trade stays usable until it expires.

Each print is judged **on its own**. One we cannot read is a :data:`Defect`,
recorded with its place in the sequence, and it never erases the prints around
it — validating the whole batch first is how a touched stop disappeared (review
of 2026-09-07, blocker 1).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal, localcontext

from pydantic import Field

from hunter_core.domain.market import NormalizedTrade
from hunter_core.execution.adapter import ExecutionModel
from hunter_core.strategies.numeric import CONTEXT

__all__ = [
    "MARKING_POLICY_VERSION",
    "Defect",
    "MarkingPolicy",
    "ReadBatch",
    "UsablePrint",
    "age_of",
    "earlier_defect",
    "read_batch",
    "usable_trade",
]

MARKING_POLICY_VERSION = "spot_last_trade_v1"
"""Versioned marking policy — ``docs/plans/M3.md`` T3.4, "política de marcação
SPOT versionada". Changing any rule here changes this string."""

_QUANTUM = Decimal("0.00000001")

UsablePrint = tuple[int, NormalizedTrade, Decimal]
"""``(trade_id, trade, age)`` of a print we are allowed to decide with."""

Defect = tuple[str, NormalizedTrade, Decimal, int | None]
"""``(reason, trade, age, trade_id)`` of a print we could not read. The id is
``None`` when it is not even a number, which means we cannot place it in the
sequence at all — and a print we cannot place may be *before* anything."""

ReadBatch = tuple[list[tuple[int, NormalizedTrade]], list[UsablePrint], "Defect | None"]
"""Everything ordered, everything usable, and the **earliest** thing we could not read."""


class MarkingPolicy(ExecutionModel):
    """The declared rules for calling a spot trade usable."""

    version: str = MARKING_POLICY_VERSION
    max_trade_age_s: Decimal = Field(default=Decimal(10), gt=0)
    require_monotonic_trade_id: bool = True


def age_of(now: datetime, trade: NormalizedTrade) -> Decimal:
    with localcontext(CONTEXT):
        return Decimal((now - trade.ts).total_seconds()).quantize(_QUANTUM)


def numeric_id(trade: NormalizedTrade) -> int | None:
    """The id as an integer, or ``None`` — and never an exception.

    ``"--101"`` satisfies ``raw.lstrip("-").isdigit()`` and blows up ``int()``,
    so the earlier shape crashed reading the batch and the stop printed next to
    it was never reported (Astra, T3.4b round 3). Unreadable is a **verdict**,
    not a traceback.
    """
    try:
        return int(trade.trade_id.strip())
    except ValueError:
        return None


def usable_trade(
    trade: NormalizedTrade | None, *, now: datetime, policy: MarkingPolicy
) -> tuple[NormalizedTrade | None, str]:
    """The single definition of a trade we are allowed to use, for anything.

    Triggers were not the only consumer: with ``avgPriceMins == 0`` the
    ``NOTIONAL`` filter is judged against "the last price", and a print we have
    not received is not a last price (Astra, round 2). Same rule, one place —
    :func:`hunter_core.execution.pricing.mark_price` calls it too, after a
    review found it re-implementing half of it.
    """
    if trade is None:
        return None, "no_trade"
    age = age_of(now, trade)
    if age < 0:
        return None, "trade_from_the_future"
    if trade.received_at > now:
        return None, "trade_not_yet_received"
    if age > policy.max_trade_age_s:
        return None, "stale_trade"
    return trade, ""


def earlier_defect(current: Defect | None, candidate: Defect) -> Defect:
    """Keep the defect that sits **earliest** in the tape, not the first seen.

    Prints do not arrive in id order. Keeping the first defect encountered let
    an out-of-order batch ``[103 broken, 100 broken, 101 target]`` publish the
    target — 103 sits after it — and move the watermark past the 100, which was
    a stop (Astra, T3.4b round 2). A print with no numeric id cannot be placed
    at all, so it counts as earliest.
    """
    if current is None or current[3] is None:
        return current or candidate
    if candidate[3] is None or candidate[3] < current[3]:
        return candidate
    return current


def read_batch(
    trades: Sequence[NormalizedTrade],
    *,
    now: datetime,
    rules: MarkingPolicy,
    watermark: int | None,
) -> ReadBatch:
    """Split one batch into what we can read, and the earliest thing we cannot.

    A stale print is merely too old to decide with; a malformed id, a future
    timestamp or a print our socket has not seen is a **defect**. A defect
    already past the age budget is not one: readable or not it could only ever
    be ``stale_trade``, so it may not hold a target hostage for as long as the
    caller keeps handing that window back.
    """
    ordered: list[tuple[int, NormalizedTrade]] = []
    usable: list[UsablePrint] = []
    defect: Defect | None = None
    for trade in trades:
        age = age_of(now, trade)
        identifier = numeric_id(trade)
        expired = age > rules.max_trade_age_s
        if identifier is None:
            if not expired:
                defect = earlier_defect(defect, ("trade_id_not_numeric", trade, age, None))
            continue
        ordered.append((identifier, trade))
        if rules.require_monotonic_trade_id and watermark is not None and identifier < watermark:
            continue
        candidate, reason = usable_trade(trade, now=now, policy=rules)
        if candidate is None:
            if reason != "stale_trade" and not expired:
                defect = earlier_defect(defect, (reason, trade, age, identifier))
            continue
        usable.append((identifier, trade, age))
    ordered.sort(key=lambda item: item[0])
    usable.sort(key=lambda item: item[0])
    return ordered, usable, defect
