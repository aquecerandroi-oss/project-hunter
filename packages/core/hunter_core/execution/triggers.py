"""What fires a stop or a target — and what refuses to say.

The M3 joint decision (item 3) fixes the source: **the last valid SPOT trade**.
``mark_price`` is a perpetual concept and is not transplanted, and a candle
never supplies a trigger after the fact. What "valid" means lives in
:mod:`hunter_core.execution.tape` (the versioned ``spot_last_trade_v1`` policy:
age, receipt, sequence) and travels on every report; this module decides what a
crossing *means* once the batch has been read.

Three verdicts, and the third is the one that matters most: ``unavailable`` is
not ``not_triggered``. A tape we cannot see does not prove the stop was not hit,
and saying "no trigger" there is exactly how a protection disappears without
anyone deciding to remove it.

Two asymmetries, both deliberate and both written down:

- **protection first** — a print through the stop and a target is a stop, and a
  stop crossing is published even when part of the batch is unreadable. The
  print that crossed it really did cross it;
- **a target waits for chronology** — an unread print that may have come
  *before* a target makes the order of events unknown, and the hidden print may
  have hit the stop. The target is held (``unavailable``, watermark unmoved)
  unless a later stop crossing settles the question, in which case the stop is
  what gets published (Astra, T3.4b review).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from hunter_core.domain.enums import TradeDirection
from hunter_core.domain.market import NormalizedTrade
from hunter_core.execution.adapter import ExecutionModel
from hunter_core.execution.tape import (
    MARKING_POLICY_VERSION,
    Defect,
    MarkingPolicy,
    UsablePrint,
    age_of,
    read_batch,
    usable_trade,
)

__all__ = [
    "MARKING_POLICY_VERSION",
    "usable_trade",
    "MarkingPolicy",
    "ProtectedPosition",
    "TriggerEvaluation",
    "check_triggers",
]

TriggerKind = Literal["stop", "target"]
TriggerState = Literal["triggered", "not_triggered", "unavailable"]

Crossing = tuple[int, NormalizedTrade, Decimal, TriggerKind, int | None]
"""``(trade_id, trade, age, kind, target_index)`` — a protection really touched."""


class ProtectedPosition(ExecutionModel):
    """A long spot position and the protections that watch it."""

    position_id: uuid.UUID
    qty: Decimal = Field(gt=0)
    direction: TradeDirection = TradeDirection.LONG
    stop_price: Decimal | None = Field(default=None, gt=0)
    target_prices: tuple[Decimal, ...] = ()

    @model_validator(mode="after")
    def _long_only_geometry(self) -> ProtectedPosition:
        if self.direction is not TradeDirection.LONG:
            raise ValueError("spot has no short side (directive §6): only LONG is protected here")
        if self.stop_price is not None and any(
            target <= self.stop_price for target in self.target_prices
        ):
            raise ValueError("every target must sit above the stop; the stop is below the entry")
        return self


class TriggerEvaluation(ExecutionModel):
    """Which protection fired, or why the question could not be answered."""

    state: TriggerState
    kind: TriggerKind | None = None
    target_index: int | None = None
    reason: str = ""
    trade_id: str | None = None
    trade_price: Decimal | None = None
    trade_ts: datetime | None = None
    trade_received_at: datetime | None = None
    """When *we* saw it. A late receipt and an instant trigger are different
    facts, and only both together reconstruct when the protection could act."""
    evaluated_at: datetime | None = None
    age_s: Decimal | None = None
    accepted_trade_id: int | None = None
    """The watermark to carry into the next evaluation. It never moves on an
    ``unavailable`` verdict: the prints behind it are read again next cycle."""
    pending_stop_trade_id: str | None = None
    pending_stop_price: Decimal | None = None
    pending_stop_ts: datetime | None = None
    """A stop crossing seen in the same batch, **behind** the crossing published.

    One evaluation publishes one crossing and the watermark stops at it, so the
    next call reports the next one — which only works while that print is still
    inside the age budget. A target and a stop stamped together and received
    nine seconds late published the target and, one second later, the stop was
    stale: a touch at 90 observed and never acted on (Astra, T3.4b round 4). It
    travels with the verdict instead, so both protections can be opened in one
    transaction. Only the **stop** is carried: protection first.
    """
    undecided_reason: str = ""
    """Why part of the batch could not be read, when the rest still answered.

    A crossing seen in what we could read is a fact; a print we could not read
    is a second fact, and squashing the two into one ``unavailable`` was how a
    touched stop disappeared (review of 2026-09-07, blocker 1)."""
    marking_policy_version: str = MARKING_POLICY_VERSION


def _unavailable(reason: str, **fields: object) -> TriggerEvaluation:
    return TriggerEvaluation(state="unavailable", reason=reason, **fields)  # type: ignore[arg-type]


def _undecided(defect: Defect, watermark: int | None) -> TriggerEvaluation:
    """The verdict for a batch we could not finish reading."""
    reason, broken, age, _ = defect
    return _unavailable(
        reason, trade_id=broken.trade_id, trade_ts=broken.ts, age_s=age, accepted_trade_id=watermark
    )


def _cross(position: ProtectedPosition, price: Decimal) -> tuple[TriggerKind, int | None] | None:
    """Protection first: a print through both the stop and a target is a stop."""
    if position.stop_price is not None and price <= position.stop_price:
        return "stop", None
    for index, target in enumerate(position.target_prices):
        if price >= target:
            return "target", index
    return None


def check_triggers(
    position: ProtectedPosition,
    trades: Sequence[NormalizedTrade],
    now: datetime,
    *,
    policy: MarkingPolicy | None = None,
    last_accepted_trade_id: int | None = None,
    tape_gap: bool = False,
) -> TriggerEvaluation:
    """Evaluate every usable trade **in order** and report the first crossing."""
    rules = policy or MarkingPolicy()
    watermark = last_accepted_trade_id
    if not trades:
        return _unavailable("tape_gap" if tape_gap else "no_trade", accepted_trade_id=watermark)

    ordered, usable, defect = read_batch(trades, now=now, rules=rules, watermark=watermark)
    if tape_gap:
        # A gap says "we may have missed prints", which is a reason to distrust
        # silence and a target — never a reason to unsee a print that really
        # went through the stop (Astra, T3.4b round 3).
        seen = _first_crossing(position, usable, watermark, rules, only="stop")
        if seen is None:
            return _unavailable("tape_gap", accepted_trade_id=watermark)
        return _triggered(seen, now, undecided="tape_gap")

    crossing = _first_crossing(position, usable, watermark, rules)
    if crossing is not None and defect is not None and _target_must_wait(crossing, defect):
        # Chronology unknown before a target: the unread print may have crossed
        # the stop first. A **later stop** settles it — publishing that is both
        # protective and true — and otherwise the target waits with the
        # watermark unmoved (Astra, T3.4b review, MUST-FIX 1 and round 2).
        crossing = _first_crossing(position, usable, watermark, rules, only="stop")
        if crossing is None:
            return _undecided(defect, watermark)
    if crossing is not None:
        return _triggered(
            crossing,
            now,
            undecided="" if defect is None else defect[0],
            pending_stop=_first_crossing(position, usable, watermark, rules, only="stop"),
        )
    if defect is not None:
        # Nothing crossed in what we could read, and part of the batch is
        # unreadable: the question stays open, and the watermark stays put.
        return _undecided(defect, watermark)
    if usable:
        return _read_but_uncrossed(position, usable, watermark)
    if not ordered:
        return _unavailable("no_trade", accepted_trade_id=watermark)
    return _stale_or_absent(ordered, now, watermark, rules)


def _triggered(
    crossing: Crossing,
    now: datetime,
    *,
    undecided: str,
    pending_stop: Crossing | None = None,
) -> TriggerEvaluation:
    """A protection really was touched, and what we saw alongside it."""
    identifier, trade, age, kind, target_index = crossing
    behind = None if pending_stop is None or pending_stop[0] == identifier else pending_stop[1]
    return TriggerEvaluation(
        state="triggered",
        kind=kind,
        target_index=target_index,
        trade_id=trade.trade_id,
        trade_price=trade.price,
        trade_ts=trade.ts,
        trade_received_at=trade.received_at,
        evaluated_at=now,
        age_s=age,
        accepted_trade_id=identifier,
        pending_stop_trade_id=None if behind is None else behind.trade_id,
        pending_stop_price=None if behind is None else behind.price,
        pending_stop_ts=None if behind is None else behind.ts,
        undecided_reason=undecided,
    )


def _target_must_wait(crossing: Crossing, defect: Defect) -> bool:
    """Is this a target with an unreadable print possibly before it?"""
    if crossing[3] != "target":
        return False
    return defect[3] is None or defect[3] < crossing[0]


def _first_crossing(
    position: ProtectedPosition,
    usable: Sequence[UsablePrint],
    watermark: int | None,
    rules: MarkingPolicy,
    *,
    only: TriggerKind | None = None,
) -> Crossing | None:
    """The earliest crossing among the prints we have not reported yet."""
    for identifier, trade, age in usable:
        if rules.require_monotonic_trade_id and watermark is not None and identifier <= watermark:
            # Already reported once. A trigger is an observation, not a
            # liquidation: re-reporting the same target would hide the stop the
            # remaining units met right after it (Astra, T3.4 diff review).
            continue
        crossing = _cross(position, trade.price)
        if crossing is not None and only in (None, crossing[0]):
            kind, target_index = crossing
            return identifier, trade, age, kind, target_index
    return None


def _read_but_uncrossed(
    position: ProtectedPosition, usable: Sequence[UsablePrint], watermark: int | None
) -> TriggerEvaluation:
    """The batch was readable and nothing new crossed — or it crossed before."""
    last_id, last_trade, last_age = usable[-1]
    if _cross(position, last_trade.price) is not None:
        # It crossed, and it is at or below the watermark: we already reported
        # it. Publishing ``not_triggered`` here printed a price *below the stop*
        # under a verdict that reads as "the stop was not hit" (review of
        # 2026-09-07, item 8).
        return _unavailable(
            "already_reported",
            trade_id=last_trade.trade_id,
            trade_price=last_trade.price,
            trade_ts=last_trade.ts,
            age_s=last_age,
            accepted_trade_id=watermark,
        )
    return TriggerEvaluation(
        state="not_triggered",
        trade_id=last_trade.trade_id,
        trade_price=last_trade.price,
        trade_ts=last_trade.ts,
        age_s=last_age,
        accepted_trade_id=max(watermark or last_id, last_id),
    )


def _stale_or_absent(
    ordered: Sequence[tuple[int, NormalizedTrade]],
    now: datetime,
    watermark: int | None,
    rules: MarkingPolicy,
) -> TriggerEvaluation:
    """Nothing usable: say whether it was too old or entirely superseded."""
    newest_id, newest = ordered[-1]
    age = age_of(now, newest)
    if watermark is not None and newest_id < watermark and age <= rules.max_trade_age_s:
        return _unavailable(
            "no_new_trade",
            trade_id=newest.trade_id,
            trade_ts=newest.ts,
            age_s=age,
            accepted_trade_id=watermark,
        )
    return _unavailable(
        "stale_trade",
        trade_id=newest.trade_id,
        trade_price=newest.price,
        trade_ts=newest.ts,
        age_s=age,
        accepted_trade_id=watermark,
    )
