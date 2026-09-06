"""``evaluate`` and ``evaluate_exit`` - the two entry points of the risk core.

    evaluate(proposal, portfolio, limits, liquidity, kill_switch, beta, spec=...)

Pure and deterministic: no network, no database, no clock. The instant of the
evaluation is ``portfolio.as_of``, which is why every age is computed against
the state rather than against ``datetime.now()``. Two calls with the same
arguments produce byte-identical JSON, which is what makes the whole thing
testable by a table of cases and reusable in a backtest.

The shape of the answer never depends on the outcome: **every** check of
:data:`ENTRY_CHECKS` is present in every decision, in the same order, whether it
passed, failed or could not be evaluated. The engine does not stop at the first
refusal - the Explanation Panel needs the whole picture, and "rejected by the
kill switch" hides the fact that the market was also below the liquidity floor.

Exits go through :func:`evaluate_exit`, which shares nothing with the entry
gate. Directive §3 and §5: an entry lock must never prevent a protective exit,
and BLOQUEADO cancels pending entries without closing a position or disarming a
stop. The only thing that function refuses to do is sell more than the wallet
holds - on spot that order cannot exist, so the quantity is reduced to the
position and the clamp is recorded.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Final

from hunter_risk.checks import gate_checks
from hunter_risk.confirmations import (
    POST_SIZING_CHECKS,
    post_sizing_checks,
    unavailable_post_sizing,
)
from hunter_risk.decision import CheckState, ExitPlan, RiskCheck, RiskDecision
from hunter_risk.exposure import PortfolioState
from hunter_risk.inputs import (
    BetaEstimate,
    EntryProposal,
    ExitProposal,
    MarketLiquidity,
    MarketSpec,
)
from hunter_risk.kill_switch import KillSwitchInputs, assess
from hunter_risk.limits import RiskLimits
from hunter_risk.sizing import size_entry

GATE_CHECKS: Final = (
    "market_identity",
    "kill_switch",
    "portfolio_status",
    "modality",
    "data_quality",
    "market_gap",
    "market_in_universe",
    "signal_validity",
    "stop_distance",
    "liquidity_24h",
    "spread",
    "book_depth",
    "beta_validity",
    "concurrent_positions",
    "duplicate_position",
    "aggregate_risk_budget",
    "daily_loss",
    "drawdown",
)
"""``docs/RISK_ENGINE.md`` v2 §3.1, in its order. ``market_identity`` is the one
addition: v2 §1 requires every input to carry its market, and comparing them is
what stops a proposal decided on the perpetual from being sized against a spot
book (or the reverse)."""

ENTRY_CHECKS: Final = GATE_CHECKS + POST_SIZING_CHECKS
"""Every check of an entry decision, in evaluation order. A decision always
carries all of them."""


def _missing_sizing_inputs(
    proposal: EntryProposal,
    portfolio: PortfolioState,
    limits: RiskLimits,
    liquidity: MarketLiquidity,
    spec: MarketSpec,
    beta: BetaEstimate,
) -> list[str]:
    """The inputs the sizing arithmetic cannot do without.

    A *limit* that fails still produces a size - the panel then shows what would
    have been allowed. A missing *input* does not: inventing a number there would
    be worse than admitting the number does not exist.
    """
    missing: list[str] = []
    if proposal.market != liquidity.market or proposal.market != spec.market:
        missing.append("market_identity")
    if not Decimal(0) < proposal.stop < proposal.entry_ref:
        missing.append("stop_geometry")
    if not liquidity.asks or liquidity.reference_mid is None:
        missing.append("book")
    if liquidity.participation_reference is None:
        missing.append("participation_reference")
    if not beta.validated or portfolio.age_s(beta.as_of) > Decimal(limits.max_beta_age_s):
        missing.append("beta")
    if not portfolio.marks_complete or portfolio.beta_exposure() is None:
        missing.append("portfolio_marks")
    return missing


def _same_portfolio(proposal_portfolio_id: uuid.UUID, portfolio: PortfolioState) -> None:
    """The state has to be the state of the wallet the proposal is about.

    A wiring bug, not a risk decision, so it raises instead of producing a
    rejection: every other check would otherwise report numbers measured on a
    different wallet, and the decision would carry the proposal own portfolio id
    over them (Astra, diff review of T3.1).
    """
    if proposal_portfolio_id != portfolio.portfolio_id:
        raise ValueError(
            f"proposal belongs to portfolio {proposal_portfolio_id} but the state is of "
            f"{portfolio.portfolio_id}"
        )


def evaluate(
    proposal: EntryProposal,
    portfolio: PortfolioState,
    limits: RiskLimits,
    liquidity: MarketLiquidity,
    kill_switch: KillSwitchInputs,
    beta: BetaEstimate,
    *,
    spec: MarketSpec,
) -> RiskDecision:
    """Decide one entry. Nothing is created without ``approved is True``."""
    _same_portfolio(proposal.portfolio_id, portfolio)
    assessment = assess(portfolio, limits, kill_switch)
    gates = gate_checks(
        proposal=proposal,
        portfolio=portfolio,
        limits=limits,
        liquidity=liquidity,
        spec=spec,
        beta=beta,
        assessment=assessment,
    )
    by_name = {check.name: check for check in gates}
    missing = _missing_sizing_inputs(proposal, portfolio, limits, liquidity, spec, beta)

    if missing:
        sizing = None
        post: tuple[RiskCheck, ...] = unavailable_post_sizing(
            "sem tamanho, insumo ausente: " + ", ".join(missing)
        )
    else:
        sizing = size_entry(
            proposal=proposal,
            portfolio=portfolio,
            limits=limits,
            liquidity=liquidity,
            spec=spec,
            beta=beta,
            size_multiplier=assessment.entry_size_multiplier,
        )
        post = post_sizing_checks(
            sizing=sizing,
            proposal=proposal,
            portfolio=portfolio,
            limits=limits,
            liquidity=liquidity,
            spec=spec,
            beta=beta,
        )

    checks = gates + post
    return RiskDecision(
        approved=all(check.passed for check in checks),
        kind="entry",
        proposal_id=proposal.proposal_id,
        portfolio_id=proposal.portfolio_id,
        market=proposal.market,
        limits_profile=limits.profile,
        effective_kill_switch=assessment.effective,
        cancel_pending=assessment.cancel_pending,
        shadow_only=by_name["beta_validity"].state is not CheckState.PASSED,
        checks=checks,
        sizing=sizing,
    )


def evaluate_exit(
    proposal: ExitProposal,
    portfolio: PortfolioState,
    limits: RiskLimits,
    kill_switch: KillSwitchInputs,
) -> RiskDecision:
    """Approve a protective exit. Always approved - that is the whole contract.

    No entry check runs here, by construction rather than by a flag: a lock that
    could ever reach an exit is a lock that can trap the wallet in a losing
    position. The kill switch is still recorded, because the operator needs to
    know the state the exit happened in.

    Raises ``ValueError`` when the position is not in the state. That is a caller
    bug (the wallet was rebuilt without it, or the position already closed), not
    a risk refusal, and approving a sale of something the wallet does not hold
    would be the one way this function could lose money.
    """
    _same_portfolio(proposal.portfolio_id, portfolio)
    position = portfolio.position_by_id(proposal.position_id)
    if position is None:
        raise ValueError(
            f"position {proposal.position_id} is not open in this portfolio; an exit is bound "
            "to the position it reduces"
        )
    assessment = assess(portfolio, limits, kill_switch)
    approved_qty: Decimal = min(proposal.qty, position.qty)
    plan = ExitPlan(
        position_id=proposal.position_id,
        requested_qty=proposal.qty,
        approved_qty=approved_qty,
        reason=proposal.reason,
        clamped=approved_qty < proposal.qty,
    )
    checks = (
        RiskCheck(
            name="exit_allowed",
            state=CheckState.PASSED,
            message=(
                f"saida de protecao sempre permitida; kill switch {assessment.effective}, "
                f"motivo {proposal.reason}"
            ),
        ),
        RiskCheck(
            name="reduce_only",
            state=CheckState.PASSED,
            value=approved_qty,
            limit=position.qty,
            message="quantidade limitada ao que a posicao detem (spot)",
        ),
    )
    return RiskDecision(
        approved=True,
        kind="exit",
        proposal_id=proposal.proposal_id,
        portfolio_id=proposal.portfolio_id,
        market=proposal.market,
        limits_profile=limits.profile,
        effective_kill_switch=assessment.effective,
        cancel_pending=assessment.cancel_pending,
        shadow_only=False,
        checks=checks,
        exit_plan=plan,
    )
