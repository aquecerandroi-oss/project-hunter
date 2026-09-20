"""Admission checks 14–20 of ``docs/RISK_ENGINE_MEME.md`` §4 — the wallet and the request —
and check 28 (T4.78), the wallet's memory of its last loss on the mint.

Checks 21–25 (participation, impact, sizing, available SOL, exposure after) are
part of the sizing and live in :mod:`hunter_risk_meme.sizing`.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from typing import Final

from hunter_risk_meme.decision import MemeCheck, check
from hunter_risk_meme.inputs import MemeContext, MemeEntryProposal, MemeWalletState
from hunter_risk_meme.limits import MemeLimits

__all__ = ["MINT_COOLDOWN_AFTER_LOSS", "mint_cooldown_after_loss_check", "wallet_checks"]

MINT_COOLDOWN_AFTER_LOSS: Final = "mint_cooldown_after_loss"
"""Prefix of check 28's refusal: ``mint_cooldown_after_loss:<seconds_left>``."""
_ONE = Decimal(1)


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


def mint_cooldown_after_loss_check(
    wallet: MemeWalletState, proposal: MemeEntryProposal, limits: MemeLimits
) -> MemeCheck:
    """Check 28 (T4.78) — no new buy on a mint whose last live close **lost**, for
    ``limits.mint_cooldown_after_loss_s`` seconds after that close.

    Everton's decision, 20/09/2026 00:3x BRT ("eu exijo que mexa pelo menos um
    pouco na estratégia"), applied as a limit on **repeated exposure**, not as a
    demonstrated edge. The evidence and the caveat, both on the record:

    - paper, 19/09/2026 (R64 §4): 19 re-entries after a trailing exit, **0**
      wins, −0,338 SOL;
    - real, 19/09/2026: Musepaid — ``operator/6`` exit at 17:28:15 UTC,
      ``operator/5`` re-entry at 17:28:40 (25 s later), a loss;
    - **counter-example:** NARKY#2 (+0,0142 SOL, real) re-entered 25 s after
      NARKY#1's trailing exit and would have been blocked — Astra's objection
      (``.claude/state/astra-review-estrategia-2026-09-20.md`` item 2: keep it
      in paper); the owner chose to apply it anyway;
    - every observed re-entry (paper and real) came in **under 5 min**, hence
      300 s and not 900: there is no evidence for a longer window.

    The refusal carries the seconds left, rounded **up** (a refusal never claims
    the window is shorter than it is). A close stamped in the future is two
    clocks disagreeing, not "no loss": it refuses for the whole window at most.
    ``0`` disables; the check is recorded ``passed`` with ``message = disabled``.
    Applies to every entry profile (desk sets and the launch lane); sells are
    never evaluated here (§6). Measurement in shadow: the executor runs this
    check **last**, so a refused order whose ``reason`` is this one had passed
    everything else — the count EXP-M21 needs.
    """
    name = MINT_COOLDOWN_AFTER_LOSS
    window = Decimal(limits.mint_cooldown_after_loss_s)
    if window <= 0:
        return check(name, True, name, limit=window, message="disabled")
    closed_at = wallet.recent_losses.get(proposal.mint)
    if closed_at is None:
        return check(name, True, name, limit=window)
    elapsed = wallet.age_s(closed_at)
    left = min(window, window - elapsed)
    stamp = closed_at.isoformat()
    if left <= 0:
        return check(name, True, name, value=elapsed, limit=window, input_ts=stamp)
    seconds_left = int(left.quantize(_ONE, rounding=ROUND_CEILING))
    return check(
        name,
        False,
        f"{name}:{seconds_left}",
        value=elapsed,
        limit=window,
        input_ts=stamp,
        message=f"closed with a loss {elapsed.quantize(_ONE)}s ago; window {window}s",
    )


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
