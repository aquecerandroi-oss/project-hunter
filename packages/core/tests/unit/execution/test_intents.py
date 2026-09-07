"""Intention is not attempt — and an entry only exists behind an approved decision.

``docs/RISK_ENGINE.md`` §10 in code: an **entry** is one attempt whose remainder
is cancelled for good; a **protection** attempt also ends, but the durable
intention survives for the remaining quantity, with new attempts of their own
identity, and only terminates when the intended quantity is liquidated or an
audited substitution replaces it. Below the minimum the leftover is
``blocked_residual`` — accounted and visible, never fictitiously settled.

The other half is §8's guarantee: no code path creates an entry order without a
proposal whose ``risk_decision.approved`` is true. Here that is a constructor
that refuses, not a convention.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_core.domain.enums import (
    ExecutionMode,
    ExitIntentState,
    ExitReason,
    KillSwitchState,
    MarketType,
    OrderSide,
)
from hunter_core.execution.adapter import (
    EntryWithoutApproval,
    ExecutionReport,
    LevelFill,
    Residual,
)
from hunter_core.execution.entries import (
    MarketEntryOrder,
    client_order_id_for_entry,
    execution_key_for_entry,
)
from hunter_core.execution.idempotency import applied_attempts_from_execution_keys
from hunter_core.execution.intents import (
    ExitAttempt,
    ExitIntent,
    allocate_sellable,
    apply_attempt,
    execution_key_for_exit,
    supersede,
    void_intent,
)
from hunter_risk.decision import (
    Counterfactual,
    LimitCap,
    RiskDecision,
    Sizing,
    check,
)
from hunter_risk.inputs import MarketIdentity

from .conftest import NOW

PORTFOLIO = uuid.UUID(int=7)
POSITION = uuid.UUID(int=8)
MARKET = MarketIdentity(
    exchange="binance",
    symbol="BTCUSDT",
    market_type=MarketType.SPOT,
    base_asset="BTC",
    quote_asset="USDT",
)


def _sizing(qty: str = "2") -> Sizing:
    cap = LimitCap(name="risk_per_trade", notional=Decimal("200"))
    return Sizing(
        entry_ref=Decimal("100"),
        sizing_price=Decimal("100"),
        stop=Decimal("95"),
        stop_distance_pct=Decimal("0.05"),
        cost_pct=Decimal("0.002"),
        caps=(cap,),
        binding_limit=cap,
        binding_constraint="risk_per_trade",
        size_without_multipliers=Counterfactual(name="size_without_multipliers", qty=Decimal(qty)),
        size_without_participation=Counterfactual(
            name="size_without_participation", qty=Decimal(qty)
        ),
        notional_before_multiplier=Decimal("200"),
        kill_switch_multiplier=Decimal(1),
        notional_after_multiplier=Decimal("200"),
        qty=Decimal(qty),
        notional=Decimal("200"),
        planned_risk_quote=Decimal("10"),
        planned_risk_pct=Decimal("0.0025"),
    )


def _decision(*, approved: bool, proposal_id: uuid.UUID | None = None) -> RiskDecision:
    return RiskDecision(
        approved=approved,
        kind="entry",
        proposal_id=proposal_id or uuid.UUID(int=9),
        portfolio_id=PORTFOLIO,
        market=MARKET,
        limits_profile="paper_v1",
        effective_kill_switch=KillSwitchState.ACTIVE,
        cancel_pending=False,
        shadow_only=False,
        checks=(check("cash", approved),),
        sizing=_sizing() if approved else None,
    )


def _intent(intended: str = "10", filled: str = "0") -> ExitIntent:
    return ExitIntent(
        intent_id=uuid.UUID(int=11),
        portfolio_id=PORTFOLIO,
        position_id=POSITION,
        protection_key="stop",
        reason=ExitReason.STOP,
        intended_qty=Decimal(intended),
        filled_qty=Decimal(filled),
        trigger_price=Decimal("95"),
    )


def _exit_report(
    attempt: ExitAttempt,
    *,
    filled: str,
    price: str = "95",
    status: str = "partially_filled",
    residual: Residual | None = None,
    degraded: bool = False,
) -> ExecutionReport:
    qty = Decimal(filled)
    levels = (LevelFill(price=Decimal(price), qty=qty),) if qty > 0 else ()
    return ExecutionReport(
        kind="exit",
        status=status,  # type: ignore[arg-type]
        mode=ExecutionMode.PAPER,
        execution_key=attempt.execution_key,
        client_order_id=attempt.client_order_id,
        attempt_id=attempt.attempt_id,
        intent_id=attempt.intent.intent_id,
        position_id=attempt.intent.position_id,
        side=OrderSide.SELL,
        requested_qty=attempt.qty,
        filled_qty=qty,
        unfilled_qty=attempt.qty - qty,
        levels=levels,
        gross_quote=qty * Decimal(price),
        residual=residual,
        degraded=degraded,
        alert=degraded,
        reason="no_book" if degraded else "",
    )


# --------------------------------------------------------------------- entries


def test_an_entry_order_can_only_be_built_from_an_approved_decision() -> None:
    """RISK_ENGINE.md §8, as a constructor rather than as a convention."""
    with pytest.raises(EntryWithoutApproval, match="approved"):
        MarketEntryOrder.from_decision(_decision(approved=False), decision_at=NOW)


def test_an_approved_decision_carries_its_size_and_stop_into_the_order() -> None:
    order = MarketEntryOrder.from_decision(_decision(approved=True), decision_at=NOW)
    assert order.proposal_id == uuid.UUID(int=9)
    assert order.portfolio_id == PORTFOLIO
    assert order.qty == Decimal("2")
    assert order.entry_ref == Decimal("100")
    assert order.stop == Decimal("95")
    assert order.side is OrderSide.BUY


def test_an_entry_order_cannot_be_hand_built_around_the_decision() -> None:
    """There is no boolean to set: the order carries the decision itself.

    Astra, T3.4 diff review, finding 1: with a ``risk_approved`` flag a caller
    could build the order of a *rejected* proposal, pass ``True``, and get a
    fill — reproduced without constructing any decision at all. Now the only
    constructor argument that authorises anything is a ``RiskDecision``, and
    ``RiskDecision`` refuses to be approved while a check did not pass.
    """
    with pytest.raises(EntryWithoutApproval, match="approved"):
        MarketEntryOrder(decision=_decision(approved=False), qty=Decimal("1"), decision_at=NOW)


def test_an_entry_order_may_not_ask_for_more_than_the_decision_sized() -> None:
    """The size is a ceiling the engine published, not a suggestion."""
    with pytest.raises(EntryWithoutApproval, match="more than"):
        MarketEntryOrder(decision=_decision(approved=True), qty=Decimal("99"), decision_at=NOW)


def test_the_client_order_id_derives_from_the_proposal_so_a_replay_collides() -> None:
    """``orders.client_order_id`` is unique per portfolio (DATABASE.md §18.3).

    Deriving it from the proposal is what makes a redelivered
    ``proposals.decided`` event hit that unique index instead of opening a second
    position for one decision.
    """
    proposal = uuid.UUID(int=42)
    order = MarketEntryOrder.from_decision(
        _decision(approved=True, proposal_id=proposal), decision_at=NOW
    )
    assert order.client_order_id == client_order_id_for_entry(proposal)
    assert order.client_order_id == f"entry:{proposal}"
    assert order.execution_key == execution_key_for_entry(proposal)


# ------------------------------------------------------------------ intentions


def test_a_partial_protection_fill_leaves_the_intention_open_for_the_remainder() -> None:
    """The §10 scenario: a stop for 10 finds 4 sellable and 6 stay protected."""
    intent = _intent("10")
    attempt = ExitAttempt.for_intent(intent, qty=Decimal("10"), decision_at=NOW)
    after = apply_attempt(intent, _exit_report(attempt, filled="4"), now=NOW, min_qty=Decimal("1"))
    assert after.state is ExitIntentState.OPEN
    assert after.filled_qty == Decimal("4")
    assert after.remaining_qty == Decimal("6")


def test_a_second_attempt_has_its_own_identity_and_never_reuses_the_first_key() -> None:
    intent = _intent("10", "4")
    first = ExitAttempt.for_intent(intent, qty=Decimal("6"), decision_at=NOW)
    second = ExitAttempt.for_intent(intent, qty=Decimal("6"), decision_at=NOW)
    assert first.attempt_id != second.attempt_id
    assert first.execution_key != second.execution_key
    assert second.execution_key == execution_key_for_exit(second.attempt_id)
    assert second.client_order_id == f"exit:{second.attempt_id}"


def test_the_intention_is_fulfilled_only_when_the_intended_quantity_is_liquidated() -> None:
    intent = _intent("10", "6")
    attempt = ExitAttempt.for_intent(intent, qty=Decimal("4"), decision_at=NOW)
    after = apply_attempt(
        intent, _exit_report(attempt, filled="4", status="filled"), now=NOW, min_qty=Decimal("1")
    )
    assert after.state is ExitIntentState.FULFILLED
    assert after.closed_at == NOW
    assert after.remaining_qty == 0


def test_a_remainder_below_the_minimum_is_blocked_residual_not_fulfilled() -> None:
    """No fictitious settlement: 0.4 left under a 1.0 minimum stays visible."""
    intent = _intent("10", "0")
    attempt = ExitAttempt.for_intent(intent, qty=Decimal("10"), decision_at=NOW)
    after = apply_attempt(
        intent, _exit_report(attempt, filled="9.6"), now=NOW, min_qty=Decimal("1")
    )
    assert after.state is ExitIntentState.BLOCKED_RESIDUAL
    assert after.remaining_qty == Decimal("0.4")
    assert after.state is not ExitIntentState.FULFILLED


def test_a_blocked_residual_returns_to_open_when_the_minimum_stops_binding() -> None:
    """``blocked_residual`` is a state, not a terminal (DATABASE.md §18.4)."""
    blocked = _intent("10", "9.6").model_copy(update={"state": ExitIntentState.BLOCKED_RESIDUAL})
    attempt = ExitAttempt.for_intent(blocked, qty=Decimal("0.4"), decision_at=NOW)
    after = apply_attempt(
        blocked, _exit_report(attempt, filled="0"), now=NOW, min_qty=Decimal("0.1")
    )
    assert after.state is ExitIntentState.OPEN


def test_a_degraded_attempt_marks_the_intention_without_filling_anything() -> None:
    intent = _intent("10")
    attempt = ExitAttempt.for_intent(intent, qty=Decimal("10"), decision_at=NOW)
    report = _exit_report(attempt, filled="0", status="pending_degraded", degraded=True)
    after = apply_attempt(intent, report, now=NOW, min_qty=Decimal("1"))
    assert after.state is ExitIntentState.OPEN
    assert after.filled_qty == 0
    assert after.degraded_since == NOW
    assert after.degraded_reason == "no_book"


def test_a_later_fill_clears_the_degradation_marks_together() -> None:
    degraded = _intent("10").model_copy(
        update={"degraded_since": NOW, "degraded_reason": "no_book"}
    )
    attempt = ExitAttempt.for_intent(degraded, qty=Decimal("10"), decision_at=NOW)
    later = datetime(2026, 9, 6, 12, 0, 30, tzinfo=UTC)
    after = apply_attempt(
        degraded,
        _exit_report(attempt, filled="10", status="filled"),
        now=later,
        min_qty=Decimal("1"),
    )
    assert (after.degraded_since, after.degraded_reason) == (None, None)
    assert after.state is ExitIntentState.FULFILLED


def test_an_intention_left_with_nothing_to_sell_is_voided_not_marked_filled() -> None:
    """A stop that took the whole position leaves the target with nothing.

    ``fulfilled = (filled_qty = intended_qty)`` is a database CHECK, so the only
    way to close the target would be a fictitious fill. ``voided`` is the honest
    terminal.
    """
    target = _intent("6").model_copy(update={"protection_key": "target:1"})
    after = void_intent(target, now=NOW, reason="quantity taken by a competing protection")
    assert after.state is ExitIntentState.VOIDED
    assert after.filled_qty == 0
    assert after.closed_reason
    assert after.closed_at == NOW


def test_a_substitution_names_its_successor_and_is_never_itself() -> None:
    intent = _intent("10")
    successor_id = uuid.UUID(int=12)
    retired = supersede(intent, successor_id=successor_id, now=NOW)
    assert retired.state is ExitIntentState.SUPERSEDED
    assert retired.superseded_by_id == successor_id
    with pytest.raises(ValueError, match="itself"):
        supersede(intent, successor_id=intent.intent_id, now=NOW)


def test_the_model_refuses_the_states_the_database_refuses() -> None:
    """Same three CHECKs as ``portfolio_exit_intents``, enforced before the INSERT."""
    with pytest.raises(ValueError, match="fulfilled"):
        ExitIntent.model_validate(
            _intent("10", "4").model_dump() | {"state": ExitIntentState.FULFILLED}
        )
    with pytest.raises(ValueError, match="degrad"):
        ExitIntent.model_validate(_intent().model_dump() | {"degraded_since": NOW})
    with pytest.raises(ValueError, match="intended"):
        ExitIntent.model_validate(_intent().model_dump() | {"filled_qty": Decimal("11")})


# ------------------------------------------------------- the shared sellable lock


def test_two_protections_never_share_the_same_unit() -> None:
    """Stop, target and manual close compete for one quantity under one lock.

    Position of 10 with a stop for 10 and a target for 6: the allocation hands
    out 10 in total, not 16 — spot cannot sell what it does not hold, and a
    short is exactly what "sell the same unit twice" would create.
    """
    stop = _intent("10")
    target = _intent("6").model_copy(update={"protection_key": "target:1"})
    allocations = allocate_sellable([stop, target], position_qty=Decimal("10"))
    assert [qty for _, qty in allocations] == [Decimal("10"), Decimal("0")]
    assert sum(qty for _, qty in allocations) == Decimal("10")


def test_the_loser_of_the_race_revalidates_against_what_the_winner_sold() -> None:
    """Two simultaneous attempts on one position: one wins, the other re-reads.

    Directive, "ordens simultâneas e fills duplicados": after the stop sells 10,
    the manual close does not get to sell a phantom 4.
    """
    manual = _intent("4").model_copy(update={"protection_key": "manual"})
    allocations = allocate_sellable([manual], position_qty=Decimal("0"))
    assert allocations[0][1] == 0
    with pytest.raises(ValueError, match="nothing left"):
        ExitAttempt.for_intent(manual, qty=Decimal("4"), decision_at=NOW, position_qty=Decimal("0"))


def test_an_attempt_is_never_larger_than_the_position_or_the_intention() -> None:
    intent = _intent("10", "6")
    attempt = ExitAttempt.for_intent(
        intent, qty=Decimal("10"), decision_at=NOW, position_qty=Decimal("3")
    )
    assert attempt.qty == Decimal("3")


def test_a_terminal_intention_accepts_neither_a_new_attempt_nor_a_new_report() -> None:
    """Astra, T3.4 diff review, finding 3: a voided intention was reopening.

    ``apply_attempt`` recomputed the state from the quantities alone, so a
    voided intention handed an empty attempt came back ``open`` while
    ``closed_at`` was still set — a row Postgres refuses
    (``terminal_states_are_closed``), discovered only at INSERT time by a worker
    holding a lock.
    """
    voided = void_intent(_intent("6"), now=NOW, reason="taken by the stop")
    attempt = ExitAttempt.for_intent(_intent("6"), qty=Decimal("6"), decision_at=NOW)
    with pytest.raises(ValueError, match="terminal"):
        apply_attempt(voided, _exit_report(attempt, filled="0"), now=NOW, min_qty=Decimal("1"))
    with pytest.raises(ValueError, match="terminal"):
        ExitAttempt.for_intent(voided, qty=Decimal("6"), decision_at=NOW)


def test_a_fulfilled_or_superseded_intention_is_closed_and_stays_closed() -> None:
    intent = ExitIntent.model_validate(
        _intent("10").model_dump()
        | {"filled_qty": Decimal("10"), "state": ExitIntentState.FULFILLED, "closed_at": NOW}
    )
    attempt = ExitAttempt.for_intent(_intent("10"), qty=Decimal("1"), decision_at=NOW)
    with pytest.raises(ValueError, match="terminal"):
        apply_attempt(intent, _exit_report(attempt, filled="0"), now=NOW, min_qty=Decimal("1"))
    with pytest.raises(ValueError, match="closed"):
        ExitIntent.model_validate(
            _intent("10").model_dump()
            | {"filled_qty": Decimal("10"), "state": ExitIntentState.FULFILLED, "closed_at": None}
        )


# ------------------------------------------------- one attempt, applied once


def test_replaying_one_attempt_report_never_counts_its_fill_twice() -> None:
    """Review of 2026-09-07, blocker 2: a redelivery closed the intention early.

    Intention of 0,8 with an attempt that filled 0,4. Folding the same
    ``ExecutionReport`` in twice summed 0,4 + 0,4, marked the intention
    ``fulfilled`` and left 0,4 units of the position with no protection at all —
    from a redelivered stream event, which is the normal case, not the exotic one.
    """
    intent = _intent("0.8")
    attempt = ExitAttempt.for_intent(intent, qty=Decimal("0.8"), decision_at=NOW)
    report = _exit_report(attempt, filled="0.4")

    once = apply_attempt(intent, report, now=NOW, min_qty=Decimal("0.1"))
    assert (once.filled_qty, once.state) == (Decimal("0.4"), ExitIntentState.OPEN)
    assert once.applied_attempts == (attempt.attempt_id,)

    twice = apply_attempt(once, report, now=NOW, min_qty=Decimal("0.1"))
    assert twice.filled_qty == Decimal("0.4")
    assert twice.state is ExitIntentState.OPEN
    assert twice.closed_at is None
    assert twice == once


def test_a_redelivery_after_the_intention_closed_is_a_no_op_not_an_exception() -> None:
    """The redelivery of the *last* attempt arrives at a terminal intention.

    Raising there would crash the worker on a legitimate at-least-once
    redelivery; recomputing would try to reopen a closed row. The attempt is
    already applied, so the answer is the intention exactly as it stands.
    """
    intent = _intent("0.4")
    attempt = ExitAttempt.for_intent(intent, qty=Decimal("0.4"), decision_at=NOW)
    report = _exit_report(attempt, filled="0.4", status="filled")
    closed = apply_attempt(intent, report, now=NOW, min_qty=Decimal("0.1"))
    assert closed.state is ExitIntentState.FULFILLED
    assert apply_attempt(closed, report, now=NOW, min_qty=Decimal("0.1")) == closed


def test_the_applied_attempts_are_rebuilt_from_the_execution_keys_of_the_fills() -> None:
    """``portfolio_exit_intents`` has no column for this yet — so it is derived.

    The durable authority for "this attempt was already applied" is
    ``fills.execution_key`` (``exit:{attempt_id}``, DATABASE.md §18.3). Until the
    column exists (debt registered for T3.1b/T3.10), the restart path rebuilds
    the set from the journal instead of trusting an empty in-memory tuple.
    """
    first, second = uuid.UUID(int=31), uuid.UUID(int=32)
    keys = [
        execution_key_for_exit(first),
        "entry:00000000-0000-0000-0000-000000000009",
        execution_key_for_exit(second),
    ]
    assert applied_attempts_from_execution_keys(keys) == (first, second)
    with pytest.raises(ValueError, match="exit:"):
        applied_attempts_from_execution_keys(["exit:not-a-uuid"])


def test_an_intention_rebuilt_from_postgres_is_made_idempotent_by_the_journal() -> None:
    """The restart the column debt would otherwise reopen.

    After a restart the intention comes back from Postgres without its applied
    attempts, so the same report would be folded in a second time. Rebuilding
    the set from the fills the journal wrote closes it with the data that *is*
    persisted.
    """
    intent = _intent("0.8")
    attempt = ExitAttempt.for_intent(intent, qty=Decimal("0.8"), decision_at=NOW)
    report = _exit_report(attempt, filled="0.4")
    applied = apply_attempt(intent, report, now=NOW, min_qty=Decimal("0.1"))

    rebuilt = ExitIntent.model_validate(applied.model_dump() | {"applied_attempts": ()})
    recovered = ExitIntent.model_validate(
        rebuilt.model_dump()
        | {"applied_attempts": applied_attempts_from_execution_keys([report.execution_key])}
    )
    assert apply_attempt(recovered, report, now=NOW, min_qty=Decimal("0.1")) == recovered


def test_an_attempt_that_filled_nothing_is_recovered_from_its_order_not_its_fill() -> None:
    """Astra, T3.4b review, MUST-FIX 2: no fill row means no key to derive from.

    A stop that found no usable book is applied to the intention (it marks the
    degradation) and writes **no fill** — only an ``orders`` row, whose
    ``client_order_id`` is the same ``exit:{attempt_id}``. Deriving the applied
    set from ``fills`` alone lost that attempt: after a restart the redelivery
    of the degraded report hit an intention meanwhile superseded and raised,
    turning a harmless redelivery into a crashed consumer.

    So the durable authority is both keys, and the parser takes either.
    """
    intent = _intent("10")
    attempt = ExitAttempt.for_intent(intent, qty=Decimal("10"), decision_at=NOW)
    degraded = _exit_report(attempt, filled="0", status="pending_degraded", degraded=True)
    applied = apply_attempt(intent, degraded, now=NOW, min_qty=Decimal("1"))
    assert applied.applied_attempts == (attempt.attempt_id,)

    retired = supersede(applied, successor_id=uuid.UUID(int=13), now=NOW)
    rebuilt = ExitIntent.model_validate(retired.model_dump() | {"applied_attempts": ()})
    with pytest.raises(ValueError, match="terminal"):
        apply_attempt(rebuilt, degraded, now=NOW, min_qty=Decimal("1"))

    recovered = ExitIntent.model_validate(
        rebuilt.model_dump()
        | {"applied_attempts": applied_attempts_from_execution_keys([attempt.client_order_id])}
    )
    assert apply_attempt(recovered, degraded, now=NOW, min_qty=Decimal("1")) == recovered
