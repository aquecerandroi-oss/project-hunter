"""The durable exit intention, and the attempts that serve it.

``docs/RISK_ENGINE.md`` §10, second half (the first half — the entry, one
attempt, remainder cancelled — is :mod:`hunter_core.execution.entries`).

**Protection.** The attempt ends, the *intention* survives for the remaining
quantity, with new attempts of their own identity (``exit:{attempt_id}``). It
terminates only when the intended quantity is liquidated (``fulfilled``, which
the database defines as ``filled_qty = intended_qty``), when an audited
substitution replaces it (``superseded``), or when a competing protection took
the quantity (``voided`` — the terminal that exists so no intention ever needs a
fictitious fill). Below the exchange minimum the leftover is
``blocked_residual``: accounted, visible, and not terminal.

**One lock, one quantity.** :func:`allocate_sellable` hands the position's
quantity out in priority order, so stop, target and manual close can never sell
the same unit twice — which on spot would be a short.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, model_validator

from hunter_core.domain.enums import ExitIntentState, ExitReason, OrderSide
from hunter_core.domain.market import NormalizedTrade
from hunter_core.domain.types import uuid7
from hunter_core.execution.adapter import ExecutionModel, ExecutionReport
from hunter_core.execution.triggers import TriggerEvaluation
from hunter_risk.inputs import MarketIdentity

__all__ = [
    "ExitAttempt",
    "ExitIntent",
    "allocate_sellable",
    "apply_attempt",
    "client_order_id_for_exit",
    "execution_key_for_exit",
    "supersede",
    "void_intent",
]

_PRIORITY = {"stop": 0, "manual": 1}
"""Protection first, then the manual close, then the targets in key order."""


def client_order_id_for_exit(attempt_id: uuid.UUID) -> str:
    return f"exit:{attempt_id}"


def execution_key_for_exit(attempt_id: uuid.UUID) -> str:
    """One aggregated execution per attempt (Astra, point 3).

    Per-level keys would let a redelivery of level 2 arrive without level 1, and
    a single key per *intention* would swallow the legitimate second attempt.
    """
    return f"exit:{attempt_id}"


class ExitIntent(ExecutionModel):
    """A durable intention to exit, mirroring ``portfolio_exit_intents``."""

    intent_id: uuid.UUID
    portfolio_id: uuid.UUID
    position_id: uuid.UUID
    protection_key: str = Field(min_length=1)
    """``stop``, ``target:1``, ``manual`` — the protection's stable identity. The
    price is deliberately not part of it: moving a stop revises one protection."""
    reason: ExitReason
    intended_qty: Decimal = Field(gt=0)
    filled_qty: Decimal = Field(default=Decimal(0), ge=0)
    state: ExitIntentState = ExitIntentState.OPEN
    trigger_price: Decimal | None = Field(default=None, gt=0)
    market: MarketIdentity | None = None
    """The market the position lives in (``portfolio_exit_intents.market_id``).
    Compared with the book before any fill: a protection filled against another
    symbol's book sells liquidity that was never there."""
    degraded_since: datetime | None = None
    degraded_reason: str | None = None
    superseded_by_id: uuid.UUID | None = None
    closed_reason: str | None = None
    closed_at: datetime | None = None
    applied_attempts: tuple[uuid.UUID, ...] = ()
    """The attempts already folded into ``filled_qty`` — what makes
    :func:`apply_attempt` idempotent. ``portfolio_exit_intents`` has **no column
    for it yet** (debt registered for T3.1b/T3.10), so across a restart it is
    rebuilt from the fills that were really written
    (:func:`~hunter_core.execution.idempotency.applied_attempts_from_execution_keys`
    over ``fills.execution_key``)."""

    @model_validator(mode="after")
    def _same_checks_the_database_makes(self) -> ExitIntent:
        if self.filled_qty > self.intended_qty:
            raise ValueError("filled_qty may never exceed intended_qty")
        if (self.state is ExitIntentState.FULFILLED) != (self.filled_qty == self.intended_qty):
            raise ValueError(
                "fulfilled means the intended quantity was really liquidated, and nothing else"
            )
        if (self.state is ExitIntentState.SUPERSEDED) != (self.superseded_by_id is not None):
            raise ValueError("a superseded intention names its successor")
        if (self.degraded_since is None) != (self.degraded_reason is None):
            raise ValueError("degradation is all or nothing: since and reason travel together")
        if self.state is ExitIntentState.VOIDED and not self.closed_reason:
            raise ValueError("a voided intention states why")
        terminal = self.state in (
            ExitIntentState.FULFILLED,
            ExitIntentState.SUPERSEDED,
            ExitIntentState.VOIDED,
        )
        if terminal != (self.closed_at is not None):
            raise ValueError(
                "a terminal intention is closed and a live one is not "
                "(the `terminal_states_are_closed` CHECK, enforced before the INSERT)"
            )
        if self.superseded_by_id == self.intent_id:
            raise ValueError("an intention cannot supersede itself")
        return self

    @property
    def remaining_qty(self) -> Decimal:
        return self.intended_qty - self.filled_qty

    @property
    def live(self) -> bool:
        """Still holding sellable quantity — the two non-terminal states."""
        return self.state in (ExitIntentState.OPEN, ExitIntentState.BLOCKED_RESIDUAL)


class ExitAttempt(ExecutionModel):
    """One attempt at an intention, with an identity of its own."""

    attempt_id: uuid.UUID
    intent: ExitIntent
    qty: Decimal = Field(gt=0)
    decision_at: datetime
    planned_price: Decimal | None = Field(default=None, gt=0)
    """What the protection *planned* to get — the stop or target price. The
    comparison base for ``slippage_vs_plan``, never a floor under the fill."""
    trigger_trade_id: str | None = None
    trigger_trade_price: Decimal | None = Field(default=None, gt=0)
    triggered_at: datetime | None = None
    trigger_received_at: datetime | None = None
    trigger_evaluated_at: datetime | None = None
    """The observation that **fired** this protection, carried immutably from the
    trigger evaluation. Distinct from the trade observed at attempt time: a stop
    that fires at 95, finds no book, and retries while the tape prints 100 must
    not end up attributing its firing to the 100 (Astra, T3.4 diff review, 5)."""

    @model_validator(mode="after")
    def _never_attempts_a_terminal_intention(self) -> ExitAttempt:
        if not self.intent.live:
            raise ValueError(
                f"intention {self.intent.intent_id} is terminal ({self.intent.state}); "
                "a settled protection is replaced, never attempted again"
            )
        return self

    @property
    def client_order_id(self) -> str:
        return client_order_id_for_exit(self.attempt_id)

    @property
    def execution_key(self) -> str:
        return execution_key_for_exit(self.attempt_id)

    @classmethod
    def for_intent(
        cls,
        intent: ExitIntent,
        *,
        qty: Decimal,
        decision_at: datetime,
        position_qty: Decimal | None = None,
        attempt_id: uuid.UUID | None = None,
        trigger: TriggerEvaluation | None = None,
    ) -> ExitAttempt:
        """Clamp the attempt to what really exists, then mint its identity."""
        if not intent.live:
            raise ValueError(
                f"intention {intent.intent_id} is terminal ({intent.state}); "
                "a terminal protection is replaced, never attempted again"
            )
        allowed = min(qty, intent.remaining_qty)
        if position_qty is not None:
            allowed = min(allowed, position_qty)
        if allowed <= 0:
            raise ValueError(
                f"intention {intent.intent_id} has nothing left to sell "
                f"(remaining={intent.remaining_qty}, position={position_qty})"
            )
        fired = trigger if trigger is not None and trigger.state == "triggered" else None
        return cls(
            attempt_id=attempt_id or uuid7(),
            intent=intent,
            qty=allowed,
            decision_at=decision_at,
            planned_price=intent.trigger_price,
            trigger_trade_id=None if fired is None else fired.trade_id,
            trigger_trade_price=None if fired is None else fired.trade_price,
            triggered_at=None if fired is None else fired.trade_ts,
            trigger_received_at=None if fired is None else fired.trade_received_at,
            trigger_evaluated_at=None if fired is None else fired.evaluated_at,
        )

    def report_identity(self, observed_trade: NormalizedTrade | None) -> dict[str, Any]:
        """The identity every report of this attempt carries."""
        return {
            "kind": "exit",
            "execution_key": self.execution_key,
            "client_order_id": self.client_order_id,
            "attempt_id": self.attempt_id,
            "intent_id": self.intent.intent_id,
            "position_id": self.intent.position_id,
            "submitted_qty": self.qty,
            "side": OrderSide.SELL,
            "planned_price": self.planned_price,
            "decision_at": self.decision_at,
            "trigger_trade_id": self.trigger_trade_id,
            "trigger_trade_price": self.trigger_trade_price,
            "triggered_at": self.triggered_at,
            "trigger_received_at": self.trigger_received_at,
            "trigger_evaluated_at": self.trigger_evaluated_at,
            "observed_trade_id": None if observed_trade is None else observed_trade.trade_id,
        }


def allocate_sellable(
    intents: Sequence[ExitIntent], *, position_qty: Decimal
) -> tuple[tuple[ExitIntent, Decimal], ...]:
    """Share one position's quantity between competing protections, under one lock.

    Returns every intention with the quantity it may attempt, in priority order.
    The sum never exceeds ``position_qty``: the second protection sees what the
    first committed, which is what stops the same unit being sold twice.
    """
    remaining = max(position_qty, Decimal(0))
    ordered = sorted(
        (intent for intent in intents if intent.live),
        key=lambda intent: (_PRIORITY.get(intent.protection_key, 2), intent.protection_key),
    )
    allocations: list[tuple[ExitIntent, Decimal]] = []
    for intent in ordered:
        share = min(intent.remaining_qty, remaining)
        allocations.append((intent, share))
        remaining -= share
    return tuple(allocations)


def apply_attempt(
    intent: ExitIntent,
    report: ExecutionReport,
    *,
    now: datetime,
    min_qty: Decimal,
    min_notional: Decimal | None = None,
    valuation_price: Decimal | None = None,
) -> ExitIntent:
    """Fold one attempt's report into the intention, and only what it proves.

    **Once per attempt.** Applying the same report twice summed the fill (0,4 →
    0,8) and, against an intention of 0,8, marked it ``fulfilled`` while 0,4
    units were still in the position with no protection left (review of
    2026-09-07, blocker 2). A redelivery is the normal case of an at-least-once
    stream, so the second application is a **no-op**, not an exception — even
    when the first one closed the intention.
    """
    if report.intent_id not in (None, intent.intent_id):
        raise ValueError("this report belongs to another intention")
    attempt_id = report.attempt_id
    if attempt_id is None:
        raise ValueError("an exit report without an attempt_id cannot be applied idempotently")
    if attempt_id in intent.applied_attempts:
        return intent
    if not intent.live:
        raise ValueError(
            f"intention {intent.intent_id} is terminal ({intent.state}); applying an attempt "
            "would reopen it with `closed_at` still set, a row Postgres refuses"
        )
    filled = intent.filled_qty + report.filled_qty
    if filled > intent.intended_qty:
        raise ValueError("an attempt filled more than the intention ever intended")
    remaining = intent.intended_qty - filled
    changes: dict[str, object] = {
        "filled_qty": filled,
        "applied_attempts": (*intent.applied_attempts, attempt_id),
    }
    if report.degraded:
        changes["degraded_since"] = intent.degraded_since or now
        changes["degraded_reason"] = report.reason or "degraded"
    elif report.filled_qty > 0:
        changes["degraded_since"] = None
        changes["degraded_reason"] = None
    if remaining == 0:
        changes["state"] = ExitIntentState.FULFILLED
        changes["closed_at"] = now
    elif _below_minimum(remaining, min_qty, min_notional, valuation_price or report.vwap):
        changes["state"] = ExitIntentState.BLOCKED_RESIDUAL
    else:
        changes["state"] = ExitIntentState.OPEN
    return ExitIntent.model_validate(intent.model_dump() | changes)


def _below_minimum(
    remaining: Decimal,
    min_qty: Decimal,
    min_notional: Decimal | None,
    price: Decimal | None,
) -> bool:
    """Is the leftover untradable? A missing price never *proves* it is."""
    if remaining < min_qty:
        return True
    if min_notional is None or price is None:
        return False
    return remaining * price < min_notional


def void_intent(intent: ExitIntent, *, now: datetime, reason: str) -> ExitIntent:
    """Terminate an intention whose quantity a competing protection liquidated."""
    if not reason:
        raise ValueError("a voided intention states why")
    return ExitIntent.model_validate(
        intent.model_dump()
        | {"state": ExitIntentState.VOIDED, "closed_reason": reason, "closed_at": now}
    )


def supersede(intent: ExitIntent, *, successor_id: uuid.UUID, now: datetime) -> ExitIntent:
    """Retire an intention naming its replacement — the audited substitution.

    The successor's id is known first because UUIDs are generated by the
    application: that ordering is what the deferred foreign key in
    ``portfolio_exit_intents`` was made deferrable for (DATABASE.md §18.4).
    """
    if successor_id == intent.intent_id:
        raise ValueError("an intention cannot supersede itself")
    return ExitIntent.model_validate(
        intent.model_dump()
        | {
            "state": ExitIntentState.SUPERSEDED,
            "superseded_by_id": successor_id,
            "closed_at": now,
            "closed_reason": intent.closed_reason or "superseded by an audited replacement",
        }
    )
