"""``evaluate`` and ``evaluate_exit`` (docs/RISK_ENGINE_B3.md §8.1, §8.4, §8.6).

Pure and deterministic: no network, database or clock — the instant is ``broker.as_of``.
All 25 checks are evaluated and recorded even after the first refusal; ``unavailable``
rejects. The engine writes nothing: ``triggers`` is what the service persists as an
audited kill-switch transition. ``evaluate_exit`` always approves — the risk engine never
blocks an exit; who may *send* one is the mutation guard's question (§2.4), not this one.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Final

from hunter_risk_b3.base import B3Model
from hunter_risk_b3.checks_book import (
    check_contracts_caps,
    check_open_positions,
    check_order_in_flight,
    check_slippage_guard,
    check_spread,
    check_stop_geometry,
    check_trades_today,
)
from hunter_risk_b3.checks_gate import (
    check_account_mode,
    check_entry_window,
    check_flatten_margin,
    check_kill_switch,
    check_quote_fresh,
    check_symbol_whitelist,
    check_terminal_state,
    check_trading_day,
)
from hunter_risk_b3.checks_ops import (
    breaker_trips_now,
    check_audit_path,
    check_broker_reject_breaker,
    check_equity_floor,
    check_reconciliation_ok,
    check_signal_validity,
    check_spec_unchanged,
)
from hunter_risk_b3.context import (
    CalendarB3,
    KillSwitchB3,
    MarginInputs,
    SessionContext,
    SpecInputs,
)
from hunter_risk_b3.daily_loss import assess_loss
from hunter_risk_b3.decision import SIZING_ZERO, B3Check, RiskDecision
from hunter_risk_b3.enums import CheckState, DecisionKind, ExitReason, KillCause
from hunter_risk_b3.frame import Done, Frame
from hunter_risk_b3.inputs import (
    AccountSnapshot,
    B3EntryProposal,
    BrokerPosition,
    BrokerSnapshot,
    QuoteSnapshot,
)
from hunter_risk_b3.kill_switch import automatic_state, effective_state, most_restrictive
from hunter_risk_b3.limits import RiskLimitsB3
from hunter_risk_b3.ops import RobotOpsState
from hunter_risk_b3.sizing import (
    check_margin,
    check_trade_risk_cap,
    check_trade_risk_vs_allowance,
    compute_sizing,
)

__all__ = ["ExitRequest", "evaluate", "evaluate_exit"]

_Check = Callable[[Frame, Done], B3Check]
# Evaluation order: every check before the ones that read its state (6 and 7 read 5).
_BEFORE_SIZING: Final[tuple[tuple[int, _Check], ...]] = (
    (1, check_kill_switch), (2, check_account_mode), (3, check_terminal_state),
    (5, check_trading_day), (4, check_symbol_whitelist), (6, check_entry_window),
    (7, check_flatten_margin), (8, check_quote_fresh), (9, check_spread),
    (10, check_open_positions), (11, check_order_in_flight), (12, check_contracts_caps),
    (13, check_trades_today), (15, check_stop_geometry), (19, check_broker_reject_breaker),
    (20, check_reconciliation_ok), (21, check_audit_path), (22, check_signal_validity),
    (23, check_spec_unchanged), (24, check_slippage_guard), (25, check_equity_floor),
)  # fmt: skip


def evaluate(
    proposal: B3EntryProposal,
    broker: BrokerSnapshot,
    account: AccountSnapshot,
    limits: RiskLimitsB3,
    session: SessionContext,
    calendar: CalendarB3,
    quote: QuoteSnapshot,
    kill_switch: KillSwitchB3,
    *,
    spec: SpecInputs,
    margin: MarginInputs,
    ops: RobotOpsState,
) -> RiskDecision:
    f = Frame(proposal, broker, account, limits, session, calendar, quote, kill_switch, spec,
              margin, ops)  # fmt: skip
    done: Done = {}
    for cid, run in _BEFORE_SIZING:
        done[cid] = run(f, done)
    loss = assess_loss(f)
    done[14] = loss.check

    persisted = effective_state(kill_switch)
    effective = (
        persisted if loss.loss_brl is None
        else most_restrictive(persisted, automatic_state(loss.loss_brl, limits))
    )  # fmt: skip
    sized = compute_sizing(f, loss.loss_brl, effective)
    done[16] = check_trade_risk_vs_allowance(f, done, sized)
    done[17] = check_trade_risk_cap(f, sized)
    done[18] = check_margin(f, done, sized)

    checks = tuple(done[cid] for cid in range(1, 26))
    sizing = sized.sizing
    reasons = [c.reason for c in checks if c.reason is not None]
    if sizing.n_raw is not None and sizing.n_final < 1:
        reasons.append(SIZING_ZERO)
    approved = all(c.passed for c in checks) and sizing.n_final >= 1
    triggers: list[KillCause] = []
    if done[14].state is CheckState.FAILED:
        triggers.append(KillCause.DAILY_LOSS_LIMIT)
    if breaker_trips_now(f):
        triggers.append(KillCause.BROKER_REJECT_BREAKER)
    as_of = broker.as_of
    return RiskDecision(
        kind=DecisionKind.ENTRY,
        proposal_id=proposal.proposal_id,
        approved=approved,
        reasons=tuple(reasons),
        checks=checks,
        sizing=sizing,
        kill_switch_effective=effective,
        triggers=tuple(triggers),
        limits_version=limits.limits_version,
        grid_version=session.grid_version,
        spec_pin_id=spec.pin.spec_pin_id,
        as_of=as_of,
        approved_at=as_of,
        expires_at=as_of + timedelta(seconds=limits.approval_ttl_s),
    )


class ExitRequest(B3Model):
    position_ticket: int
    exit_reason: ExitReason


def evaluate_exit(
    exit_request: ExitRequest, position: BrokerPosition | None, kill_switch: KillSwitchB3
) -> RiskDecision:
    """Always ``approved = True``; the two checks are informative and cannot refuse."""
    eff = effective_state(kill_switch)
    seen = position is not None and position.position_ticket == exit_request.position_ticket
    checks = (
        B3Check(id=1, name="kill_switch", state=CheckState.PASSED, value=eff.value,
                message="informative: exits are never blocked by risk (§8.6)"),
        B3Check(id=2, name="position_seen", state=CheckState.PASSED, value=exit_request.position_ticket)
        if seen else
        B3Check(id=2, name="position_seen", state=CheckState.UNAVAILABLE, reason="position_not_seen",
                value=exit_request.position_ticket, message="informative: does not refuse the exit"),
    )  # fmt: skip
    return RiskDecision(
        kind=DecisionKind.EXIT,
        proposal_id=None,
        approved=True,
        reasons=(),
        checks=checks,
        sizing=None,
        kill_switch_effective=eff,
        triggers=(),
        limits_version=None,
        grid_version=None,
        spec_pin_id=None,
        as_of=None,
        approved_at=None,
        expires_at=None,
    )
