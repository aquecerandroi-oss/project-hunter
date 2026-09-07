"""The SPOT marking policy: what fires a stop or a target, and what refuses to say.

The M3 joint decision (item 3) fixes the source: **the last valid SPOT trade**.
``mark_price`` is a perpetual concept and is not transplanted, and a candle
never supplies a trigger after the fact. What "valid" means is the whole
contract, so it is written here, versioned as ``spot_last_trade_v1``, and it
travels on every report:

- **age** — ``0 <= now - trade.ts <= max_trade_age_s``, measured against the
  exchange's own clock, which ``aggTrade`` really carries (unlike the spot book,
  which carries none). 10 s is a **declared** initial budget, not a measured
  guarantee: Astra refused to defend another number without histograms of
  inter-trade time, and the honest move is to publish the budget with the
  verdict instead of hiding it;
- **sequence** — trade ids advance strictly, compared as integers. A print that
  goes backwards is a replay and is dropped; a repeat does **not** refresh the
  age, but the last accepted trade stays usable until it expires. Requiring a
  brand-new id every cycle would blind the stop in a quiet market.

And the third verdict: ``unavailable``. A tape we cannot see does not prove the
stop was not hit. Reporting "not triggered" there is exactly how a protection
disappears without anyone deciding to remove it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import Field, model_validator

from hunter_core.domain.enums import TradeDirection
from hunter_core.domain.market import NormalizedTrade
from hunter_core.execution.adapter import ExecutionModel
from hunter_core.strategies.numeric import CONTEXT

__all__ = [
    "MARKING_POLICY_VERSION",
    "usable_trade",
    "MarkingPolicy",
    "ProtectedPosition",
    "TriggerEvaluation",
    "check_triggers",
]

MARKING_POLICY_VERSION = "spot_last_trade_v1"
"""Versioned marking policy — ``docs/plans/M3.md`` T3.4, "política de marcação
SPOT versionada". Changing any rule below changes this string."""

TriggerKind = Literal["stop", "target"]
TriggerState = Literal["triggered", "not_triggered", "unavailable"]

_QUANTUM = Decimal("0.00000001")


class MarkingPolicy(ExecutionModel):
    """The declared rules for calling a spot trade usable."""

    version: str = MARKING_POLICY_VERSION
    max_trade_age_s: Decimal = Field(default=Decimal(10), gt=0)
    require_monotonic_trade_id: bool = True


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
    """The watermark to carry into the next evaluation."""
    marking_policy_version: str = MARKING_POLICY_VERSION


def _numeric_id(trade: NormalizedTrade) -> int | None:
    raw = trade.trade_id.strip()
    return int(raw) if raw.lstrip("-").isdigit() else None


def _age(now: datetime, trade: NormalizedTrade) -> Decimal:
    with localcontext(CONTEXT):
        return Decimal((now - trade.ts).total_seconds()).quantize(_QUANTUM)


def usable_trade(
    trade: NormalizedTrade | None, *, now: datetime, policy: MarkingPolicy
) -> tuple[NormalizedTrade | None, str]:
    """The single definition of a trade we are allowed to use, for anything.

    Triggers were not the only consumer: with ``avgPriceMins == 0`` the
    ``NOTIONAL`` filter is judged against "the last price", and a print we have
    not received is not a last price (Astra, round 2). Same rule, one place.
    """
    if trade is None:
        return None, "no_trade"
    age = _age(now, trade)
    if age < 0:
        return None, "trade_from_the_future"
    if trade.received_at > now:
        return None, "trade_not_yet_received"
    if age > policy.max_trade_age_s:
        return None, "stale_trade"
    return trade, ""


def _unavailable(reason: str, **fields: object) -> TriggerEvaluation:
    return TriggerEvaluation(state="unavailable", reason=reason, **fields)  # type: ignore[arg-type]


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
    if tape_gap:
        return _unavailable("tape_gap", accepted_trade_id=last_accepted_trade_id)
    if not trades:
        return _unavailable("no_trade", accepted_trade_id=last_accepted_trade_id)

    watermark = last_accepted_trade_id
    ordered: list[tuple[int, NormalizedTrade]] = []
    for trade in trades:
        identifier = _numeric_id(trade)
        if identifier is None:
            # The watermark survives a malformed print: dropping it would let the
            # next call accept id 99 after 100 was already processed.
            return _unavailable(
                "trade_id_not_numeric", trade_id=trade.trade_id, accepted_trade_id=watermark
            )
        ordered.append((identifier, trade))
    ordered.sort(key=lambda item: item[0])

    usable: list[tuple[int, NormalizedTrade, Decimal]] = []
    for identifier, trade in ordered:
        if rules.require_monotonic_trade_id and watermark is not None and identifier < watermark:
            continue
        candidate, reason = usable_trade(trade, now=now, policy=rules)
        age = _age(now, trade)
        if candidate is None:
            if reason == "stale_trade":
                continue  # too old to decide with, but not a broken clock
            # A print from the future, or one our socket has not seen, cannot
            # decide a stop: the same evaluation after a restart would differ.
            return _unavailable(
                reason,
                trade_id=trade.trade_id,
                trade_ts=trade.ts,
                age_s=age,
                accepted_trade_id=watermark,
            )
        usable.append((identifier, trade, age))

    if not usable:
        return _stale_or_absent(ordered, now, watermark, rules)

    for identifier, trade, age in usable:
        if rules.require_monotonic_trade_id and watermark is not None and identifier <= watermark:
            # Already reported once. A trigger is an observation, not a
            # liquidation: re-reporting the same target would hide the stop the
            # remaining units met right after it (Astra, T3.4 diff review).
            continue
        crossing = _cross(position, trade.price)
        if crossing is not None:
            kind, target_index = crossing
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
            )
    last_id, last_trade, last_age = usable[-1]
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
    age = _age(now, newest)
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
