"""Admission checks 14–20 of ``docs/RISK_ENGINE_MEME.md`` §4 — the wallet and the request.

Checks 21–25 (participation, impact, sizing, available SOL, exposure after) are
part of the sizing and live in :mod:`hunter_risk_meme.sizing`.
"""

from __future__ import annotations

from decimal import Decimal

from hunter_risk_meme.decision import MemeCheck, check
from hunter_risk_meme.inputs import MemeContext, MemeEntryProposal, MemeWalletState
from hunter_risk_meme.limits import MemeLimits

__all__ = ["wallet_checks"]


def rug_history_check(wallet: MemeWalletState, context: MemeContext) -> MemeCheck:
    name = "rug_history"
    if context.mint_rugged:
        return check(name, False, "token_rugged_no_reentry")
    until = context.rug_cooldown_until
    if until is not None and until > wallet.as_of:
        return check(name, False, "rug_cooldown_active", input_ts=until.isoformat())
    return check(name, True, "rug_cooldown_active")


def duplicate_position_check(wallet: MemeWalletState, proposal: MemeEntryProposal) -> MemeCheck:
    held = any(p.mint == proposal.mint for p in wallet.positions)
    pending = any(i.mint == proposal.mint for i in wallet.pending_intents)
    return check("duplicate_position", not (held or pending), "duplicate_position")


def concurrent_positions_check(wallet: MemeWalletState, limits: MemeLimits) -> MemeCheck:
    used = wallet.slots_used
    return check(
        "concurrent_positions",
        used < limits.max_open_positions,
        "max_open_positions",
        value=Decimal(used),
        limit=Decimal(limits.max_open_positions),
    )


def wallet_cap_check(wallet: MemeWalletState, limits: MemeLimits) -> MemeCheck:
    name = "wallet_cap"
    if wallet.unrecognized_holdings:
        return check(
            name,
            False,
            "wallet_unrecognized_holdings",
            message=",".join(wallet.unrecognized_holdings[:5]),
        )
    return check(
        name,
        wallet.sol_balance <= limits.wallet_max_sol,
        "wallet_over_max_sol",
        value=wallet.sol_balance,
        limit=limits.wallet_max_sol,
    )


def daily_loss_check(wallet: MemeWalletState, limits: MemeLimits) -> MemeCheck:
    loss = wallet.daily_loss_sol
    return check(
        "daily_loss",
        loss < limits.daily_loss_cap_sol,
        "daily_loss_cap_reached",
        value=loss,
        limit=limits.daily_loss_cap_sol,
    )


def slippage_cap_check(proposal: MemeEntryProposal, limits: MemeLimits) -> MemeCheck:
    return check(
        "slippage_cap",
        proposal.max_slippage_pct <= limits.max_slippage_pct,
        "slippage_above_cap",
        value=proposal.max_slippage_pct,
        limit=limits.max_slippage_pct,
    )


def fee_caps_check(proposal: MemeEntryProposal, limits: MemeLimits) -> MemeCheck:
    name = "fee_caps"
    relative_cap = proposal.requested_sol * limits.max_priority_fee_pct_of_trade
    if proposal.priority_fee_sol > limits.max_priority_fee_sol:
        return check(
            name,
            False,
            "priority_fee_above_cap",
            value=proposal.priority_fee_sol,
            limit=limits.max_priority_fee_sol,
        )
    if proposal.priority_fee_sol > relative_cap:
        return check(
            name,
            False,
            "priority_fee_above_cap",
            value=proposal.priority_fee_sol,
            limit=relative_cap,
            message="above max_priority_fee_pct_of_trade",
        )
    if proposal.jito_tip_sol > limits.max_jito_tip_sol:
        return check(
            name,
            False,
            "jito_tip_above_cap",
            value=proposal.jito_tip_sol,
            limit=limits.max_jito_tip_sol,
        )
    return check(name, True, "priority_fee_above_cap", value=proposal.priority_fee_sol)


def wallet_checks(
    proposal: MemeEntryProposal,
    wallet: MemeWalletState,
    limits: MemeLimits,
    context: MemeContext,
) -> list[MemeCheck]:
    """Checks 14–20, in the order of §4."""
    return [
        rug_history_check(wallet, context),
        duplicate_position_check(wallet, proposal),
        concurrent_positions_check(wallet, limits),
        wallet_cap_check(wallet, limits),
        daily_loss_check(wallet, limits),
        slippage_cap_check(proposal, limits),
        fee_caps_check(proposal, limits),
    ]
