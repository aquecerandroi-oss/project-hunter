"""The two pure entry points of ``docs/RISK_ENGINE_MEME.md`` §2.

``evaluate_meme_entry`` runs the 25 checks of §4 in order, **records every one**
(even after the first refusal), sizes only when the admissibility checks passed
and publishes the binding ceiling. ``evaluate_meme_exit`` runs no entry check
and always approves: it decides the quantity (never more than the position) and
the route (curve or PumpSwap), not the permission.

No network, no database, no clock: the instant is ``wallet.as_of``.
"""

from __future__ import annotations

from decimal import Decimal

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_meme.checks import coin_checks
from hunter_risk_meme.checks_wallet import wallet_checks
from hunter_risk_meme.decision import MemeCheck, MemeDecision, MemeExitPlan, check
from hunter_risk_meme.inputs import (
    CurveState,
    MemeContext,
    MemeEntryProposal,
    MemeExitProposal,
    MemeKillSwitchInputs,
    MemeWalletState,
    OpenMemePosition,
)
from hunter_risk_meme.kill_switch import assess, most_restrictive
from hunter_risk_meme.limits import MemeLimits
from hunter_risk_meme.sizing import size_entry

__all__ = ["evaluate_meme_entry", "evaluate_meme_exit"]

_ZERO = Decimal(0)


def evaluate_meme_entry(
    proposal: MemeEntryProposal,
    wallet: MemeWalletState,
    limits: MemeLimits,
    curve: CurveState,
    context: MemeContext,
    kill_switch: MemeKillSwitchInputs,
    *,
    live_enabled: bool,
    curve_fee_pct: Decimal,
    creates_ata: bool = True,
) -> MemeDecision:
    """§4 checks 1–25 and §5 sizing. ``curve_fee_pct`` is the curve's fee tier as the
    caller last read it (a ``TradeEvent`` or ``Global``), never a constant of this module."""
    ks = assess(wallet, limits, kill_switch)
    checks: list[MemeCheck] = coin_checks(
        proposal,
        wallet,
        limits,
        curve,
        context,
        effective=ks.effective,
        latched=kill_switch.daily_loss_latched,
        live_enabled=live_enabled,
    )
    checks.extend(wallet_checks(proposal, wallet, limits, context))
    sizing, sizing_checks = size_entry(
        proposal,
        wallet,
        limits,
        curve,
        context,
        kill_switch_multiplier=ks.entry_size_multiplier,
        curve_fee_pct=curve_fee_pct,
        creates_ata=creates_ata,
    )
    checks.extend(sizing_checks)
    approved = all(c.passed for c in checks) and sizing is not None
    return MemeDecision(
        approved=approved,
        kind="entry",
        proposal_id=proposal.proposal_id,
        wallet_id=proposal.wallet_id,
        mint=proposal.mint,
        limits_profile=limits.profile,
        effective_kill_switch=ks.effective,
        cancel_pending=ks.cancel_pending,
        checks=tuple(checks),
        # The sizing is published whether or not the entry was approved: the desk
        # shows the size the refusal was measured against (§4, "every check recorded").
        sizing=sizing,
    )


def evaluate_meme_exit(
    proposal: MemeExitProposal,
    position: OpenMemePosition,
    limits: MemeLimits,
    kill_switch: MemeKillSwitchInputs,
    *,
    wallet: MemeWalletState | None = None,
) -> MemeDecision:
    """Always approved (§6). Quantity = min(requested, position, wallet's view of the
    position); route = PumpSwap after the migration."""
    if wallet is not None:
        effective = assess(wallet, limits, kill_switch).effective
        ks_message = "with wallet state"
        held = next(
            (p.token_amount for p in wallet.positions if p.position_id == position.position_id),
            position.token_amount,
        )
    else:
        effective = most_restrictive(
            kill_switch.system, kill_switch.organization, kill_switch.wallet
        )
        ks_message = "without wallet state: persisted latches only"
        held = position.token_amount
    approved_tokens = min(proposal.token_amount, position.token_amount, held)
    plan = MemeExitPlan(
        position_id=position.position_id,
        requested_tokens=proposal.token_amount,
        approved_tokens=approved_tokens,
        reason=proposal.reason,
        route="pumpswap" if position.migrated else "curve",
        clamped=approved_tokens < proposal.token_amount,
    )
    return MemeDecision(
        approved=True,
        kind="exit",
        proposal_id=proposal.proposal_id,
        wallet_id=proposal.wallet_id,
        mint=proposal.mint,
        limits_profile=limits.profile,
        effective_kill_switch=effective,
        cancel_pending=effective is KillSwitchState.TRADING_DISABLED,
        checks=(check("exit_always_allowed", True, "never", message=ks_message),),
        exit_plan=plan,
    )
