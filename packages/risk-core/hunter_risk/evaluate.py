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
stop. It takes the **position**, not the wallet: the daily anchor that
``PortfolioState`` demands is a limit on entries, and a stop must not wait for it
to be rebuilt after a restart. The only thing that function refuses to do is sell
more than the position holds - on spot that order cannot exist, so the quantity
is reduced to the position and the clamp is recorded.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Final

from hunter_core.domain.enums import KillSwitchState
from hunter_risk.checks import gate_checks
from hunter_risk.confirmations import (
    POST_SIZING_CHECKS,
    post_sizing_checks,
    unavailable_post_sizing,
)
from hunter_risk.decision import CheckState, ExitPlan, RiskCheck, RiskDecision
from hunter_risk.exposure import OpenPosition, PortfolioState
from hunter_risk.inputs import (
    BetaEstimate,
    EntryProposal,
    ExitProposal,
    MarketLiquidity,
    MarketSpec,
)
from hunter_risk.kill_switch import KillSwitchInputs, assess, blocks_entries, most_restrictive
from hunter_risk.limits import RiskLimits
from hunter_risk.observations import stale_volume_reason
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
    if stale_volume_reason(portfolio, limits, liquidity) is not None:
        missing.append("volume_age")
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
    position: OpenPosition,
    limits: RiskLimits,
    kill_switch: KillSwitchInputs,
    *,
    portfolio: PortfolioState | None = None,
) -> RiskDecision:
    """Approve a protective exit. Always approved - that is the whole contract.

    No entry check runs here, by construction rather than by a flag: a lock that
    could ever reach an exit is a lock that can trap the wallet in a losing
    position.

    **The position is the argument, and the wallet state is optional** (Astra,
    second review of this diff). ``PortfolioState`` cannot be built without the
    daily anchor of v2 §5, and that anchor is a *restart* problem: after a
    restart past Sao Paulo midnight the worker rebuilds the position from
    Postgres long before it rebuilds the day's reference. If the exit needed the
    whole state, the stop of a position that already exists would wait on a
    number that only limits **entries** - or the caller would invent one. The
    contract says the opposite in as many words: without the reference, "entradas
    novas bloqueadas, proteções preservadas". When the state *is* available it is
    passed in and the automatic kill-switch assessment is recorded with it;
    without it the effective state is the most restrictive of the persisted
    latches, and the decision says so.

    Raises ``ValueError`` when the position does not answer the proposal (another
    position, another market, another wallet). That is a caller bug, not a risk
    refusal, and approving a sale of something the wallet does not hold would be
    the one way this function could lose money.
    """
    if position.position_id != proposal.position_id:
        raise ValueError(
            f"exit names position {proposal.position_id} but was handed {position.position_id}; "
            "an exit is bound to the position it reduces"
        )
    if position.market != proposal.market:
        raise ValueError(
            f"exit is on {proposal.market.exchange}:{proposal.market.symbol} but the position "
            f"holds {position.market.exchange}:{position.market.symbol}"
        )
    effective, assessed = _exit_kill_switch(portfolio, limits, kill_switch)
    held = position.qty
    if portfolio is not None:
        _same_portfolio(proposal.portfolio_id, portfolio)
        in_state = portfolio.position_by_id(proposal.position_id)
        if in_state is None:
            raise ValueError(
                f"position {proposal.position_id} is not open in this portfolio; an exit is "
                "bound to the position it reduces"
            )
        # Two sources for the same holding: take the smaller (Astra, third review
        # of this diff). After a partial exit of 6 the wallet holds 4 while a
        # stale position object still says 10, and selling 10 on spot would sell
        # units that are not there. Disagreement never refuses the exit - it
        # only ever sells less.
        held = min(position.qty, in_state.qty)

    approved_qty: Decimal = min(proposal.qty, held)
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
                f"saida de protecao sempre permitida; kill switch {effective} "
                f"({'com' if assessed else 'sem'} estado da carteira), motivo {proposal.reason}"
            ),
        ),
        RiskCheck(
            name="reduce_only",
            state=CheckState.PASSED,
            value=approved_qty,
            limit=held,
            message=(
                "quantidade limitada ao menor entre a posicao entregue e a da carteira (spot)"
            ),
        ),
    )
    return RiskDecision(
        approved=True,
        kind="exit",
        proposal_id=proposal.proposal_id,
        portfolio_id=proposal.portfolio_id,
        market=proposal.market,
        limits_profile=limits.profile,
        effective_kill_switch=effective,
        cancel_pending=blocks_entries(effective),
        shadow_only=False,
        checks=checks,
        exit_plan=plan,
    )


def _exit_kill_switch(
    portfolio: PortfolioState | None, limits: RiskLimits, kill_switch: KillSwitchInputs
) -> tuple[KillSwitchState, bool]:
    """The state to record on an exit, and whether the wallet could be assessed.

    Without the wallet the automatic rungs (daily loss, drawdown) are not
    measurable - and they only ever *raise* the state, so the exit is recorded
    under the persisted latches instead of under a fabricated ACTIVE.
    """
    if portfolio is None:
        latches = most_restrictive(
            kill_switch.system, kill_switch.organization, kill_switch.portfolio
        )
        return latches, False
    return assess(portfolio, limits, kill_switch).effective, True
