"""Admission checks 1–12 of ``docs/RISK_ENGINE_MEME.md`` §4 — the coin and the curve.

Each function returns one :class:`MemeCheck` named exactly as the §4 table and,
when it does not pass, the refusal name of that row. ``unavailable`` rejects: an
input that is absent, undated, stale or reversible is not an input (§8).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_meme.decision import MemeCheck, check, unavailable
from hunter_risk_meme.inputs import CurveState, MemeContext, MemeEntryProposal, MemeWalletState
from hunter_risk_meme.limits import MemeLimits

__all__ = ["REFUSAL_NAMES", "coin_checks"]

_COMMITMENT_RANK: Final = {"processed": 0, "confirmed": 1, "finalized": 2}
_BPS = Decimal(10_000)

REFUSAL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "kill_switch_blocked",
        "daily_loss_cap_latched",
        "wallet_inactive",
        "agent_disabled",
        "marks_incomplete",
        "meme_live_disabled",
        "program_not_allowed",
        "unsupported_quote",
        "identity_mismatch",
        "curve_state_stale",
        "curve_state_undated",
        "curve_state_clock_skew",
        "commitment_too_weak",
        "token_too_young",
        "token_too_old",
        "token_age_unknown",
        "progress_below_window",
        "progress_above_window",
        "curve_complete",
        "progress_denominator_missing",
        "creator_net_seller",
        "creator_flow_unknown",
        "bundled_share_above_cap",
        "bundled_share_unmeasurable",
        "top10_share_above_cap",
        "top10_share_unknown",
        "holder_denominator_invalid",
        "mayhem_not_allowed",
        "mayhem_state_unknown",
        "token_rugged_no_reentry",
        "rug_cooldown_active",
        "duplicate_position",
        "max_open_positions",
        "wallet_over_max_sol",
        "wallet_unrecognized_holdings",
        "daily_loss_cap_reached",
        "slippage_above_cap",
        "priority_fee_above_cap",
        "jito_tip_above_cap",
        "participation_above_cap",
        "volume_window_incomplete",
        "volume_unavailable",
        "price_impact_above_cap",
        "below_min_sol",
        "insufficient_sol",
        "exposure_after_above_cap",
        # T4.61c — check 26 ``conviction`` (``hunter_risk_meme.conviction``).
        "entry_after_drop",
        "entry_after_drop_unknown",
        "conviction_too_low",
        "conviction_too_small",
    }
)
"""Every refusal name of §4, checks 1–26. ``test_checks_table.py`` proves each is
produced by at least one case of the table."""


def kill_switch_check(effective: KillSwitchState, latched: bool) -> MemeCheck:
    if latched:
        return check("kill_switch", False, "daily_loss_cap_latched", message="daily latch set")
    blocked = effective in (KillSwitchState.TRADING_DISABLED, KillSwitchState.EMERGENCY)
    return check(
        "kill_switch", not blocked, "kill_switch_blocked", message=f"effective={effective}"
    )


def wallet_status_check(wallet: MemeWalletState, proposal: MemeEntryProposal) -> MemeCheck:
    if not wallet.is_active:
        return check("wallet_status", False, "wallet_inactive")
    if not proposal.agent_enabled:
        return check("wallet_status", False, "agent_disabled")
    if not wallet.marks_complete:
        return check("wallet_status", False, "marks_incomplete")
    return check("wallet_status", True, "wallet_inactive")


def live_gate_check(proposal: MemeEntryProposal, *, live_enabled: bool) -> MemeCheck:
    ok = proposal.mode == "paper" or live_enabled
    return check("live_gate", ok, "meme_live_disabled", message=f"mode={proposal.mode}")


def program_allowed_check(proposal: MemeEntryProposal, context: MemeContext) -> MemeCheck:
    ok = proposal.program in context.program_allowlist
    return check("program_allowed", ok, "program_not_allowed", message=proposal.program)


def quote_supported_check(proposal: MemeEntryProposal) -> MemeCheck:
    return check("quote_supported", proposal.quote == "SOL", "unsupported_quote")


def identity_match_check(
    proposal: MemeEntryProposal, curve: CurveState, context: MemeContext
) -> MemeCheck:
    ok = proposal.mint == curve.mint == context.mint
    return check("identity_match", ok, "identity_mismatch")


def state_freshness_check(
    wallet: MemeWalletState, curve: CurveState, limits: MemeLimits
) -> MemeCheck:
    name = "state_freshness"
    limit = Decimal(limits.max_state_age_s)
    if curve.observed_at is None:
        return unavailable(name, "curve_state_undated", "curve state has no stamp", limit=limit)
    age = wallet.age_s(curve.observed_at)
    stamp = curve.observed_at.isoformat()
    if age < -Decimal(limits.clock_skew_tolerance_s):
        return check(name, False, "curve_state_clock_skew", value=age, limit=limit, input_ts=stamp)
    if age > limit:
        return unavailable(name, "curve_state_stale", f"age={age}s > {limit}s", limit=limit)
    if _COMMITMENT_RANK[curve.commitment] < _COMMITMENT_RANK[limits.min_commitment]:
        return check(name, False, "commitment_too_weak", value=age, limit=limit, input_ts=stamp)
    return check(name, True, "curve_state_stale", value=age, limit=limit, input_ts=stamp)


def token_age_check(wallet: MemeWalletState, context: MemeContext, limits: MemeLimits) -> MemeCheck:
    name = "token_age"
    if context.token_created_at is None or not context.token_age_source:
        return unavailable(name, "token_age_unknown", "created_at without provenance")
    age = wallet.age_s(context.token_created_at)
    stamp = context.token_created_at.isoformat()
    if age < limits.token_age_min_s:
        return check(
            name,
            False,
            "token_too_young",
            value=age,
            limit=Decimal(limits.token_age_min_s),
            input_ts=stamp,
        )
    if age > limits.token_age_max_s:
        return check(
            name,
            False,
            "token_too_old",
            value=age,
            limit=Decimal(limits.token_age_max_s),
            input_ts=stamp,
        )
    return check(
        name,
        True,
        "token_too_old",
        value=age,
        limit=Decimal(limits.token_age_max_s),
        input_ts=stamp,
    )


def curve_progress_check(curve: CurveState, context: MemeContext, limits: MemeLimits) -> MemeCheck:
    name = "curve_progress"
    if curve.complete:
        return check(name, False, "curve_complete")
    denominator = context.initial_real_token_reserves
    if denominator is None or denominator <= 0:
        return unavailable(name, "progress_denominator_missing", "initial_real_token_reserves")
    progress = Decimal(denominator - curve.real_token_reserves) / Decimal(denominator)
    if progress < limits.curve_progress_min_pct:
        return check(
            name,
            False,
            "progress_below_window",
            value=progress,
            limit=limits.curve_progress_min_pct,
        )
    if progress > limits.curve_progress_max_pct:
        return check(
            name,
            False,
            "progress_above_window",
            value=progress,
            limit=limits.curve_progress_max_pct,
        )
    return check(
        name, True, "progress_above_window", value=progress, limit=limits.curve_progress_max_pct
    )


def creator_behaviour_check(context: MemeContext, limits: MemeLimits) -> MemeCheck:
    name = "creator_behaviour"
    if context.creator_net_sol is None:
        return _unknown_creator(context, limits)
    seller = context.creator_net_sol < 0
    return check(name, not seller, "creator_net_seller", value=context.creator_net_sol)


def _unknown_creator(context: MemeContext, limits: MemeLimits) -> MemeCheck:
    """T4.28h — the owner's allowance, and the three ways it does **not** apply.

    ``creator_sold`` lands +123 to +441 s after a coin is created (R5, 16/09/2026)
    while the entry happens at 30–300 s, so 11 of 22 real orders that day were
    refused ``creator_flow_unknown``. With
    ``creator_unknown_allowed_if_dev_measured`` on, a **measured** dev share
    within the cap vouches for the unknown creator — the desk's own ``operator/5``
    rule (E1 arm 2), now sayable by the executor. Off (the default), unmeasured,
    or above the cap: the same refusal name as before, never a new one, with the
    cap published so the admission says *why*.
    """
    name, cap = "creator_behaviour", limits.creator_unknown_max_dev_share_pct
    if not limits.creator_unknown_allowed_if_dev_measured:
        return unavailable(name, "creator_flow_unknown", "creator net flow not measured")
    dev = context.dev_share_pct
    if dev is None:
        return unavailable(
            name,
            "creator_flow_unknown",
            "creator net flow and dev share both unmeasured",
            limit=cap,
        )
    stamp = None if context.dev_share_ts is None else context.dev_share_ts.isoformat()
    if dev > cap:
        return unavailable(
            name,
            "creator_flow_unknown",
            f"creator net flow unmeasured and dev share above {cap}",
            value=dev,
            limit=cap,
            input_ts=stamp,
        )
    return check(
        name,
        True,
        "creator_flow_unknown",
        value=dev,
        limit=cap,
        input_ts=stamp,
        message="creator_unknown_dev_share_measured",
    )


def bundled_share_check(context: MemeContext, limits: MemeLimits) -> MemeCheck:
    name = "bundled_share"
    if context.bundled_share_pct is None:
        return unavailable(name, "bundled_share_unmeasurable", "bundled share is null")
    return check(
        name,
        context.bundled_share_pct <= limits.max_bundled_share_pct,
        "bundled_share_above_cap",
        value=context.bundled_share_pct,
        limit=limits.max_bundled_share_pct,
    )


def top10_share_check(context: MemeContext, limits: MemeLimits) -> MemeCheck:
    name = "top10_share"
    if context.top10_share_pct is None:
        return unavailable(name, "top10_share_unknown", "top-10 share unknown")
    if context.holder_denominator_valid is not True:
        return check(name, False, "holder_denominator_invalid", value=context.top10_share_pct)
    return check(
        name,
        context.top10_share_pct <= limits.max_top10_share_pct,
        "top10_share_above_cap",
        value=context.top10_share_pct,
        limit=limits.max_top10_share_pct,
    )


def mayhem_policy_check(curve: CurveState, context: MemeContext) -> MemeCheck:
    name = "mayhem_policy"
    if not curve.is_mayhem_mode:
        return check(name, True, "mayhem_not_allowed")
    if not context.mayhem_agent_state_known:
        return unavailable(name, "mayhem_state_unknown", "Mayhem agent state unknown")
    return check(name, context.mayhem_policy_approved, "mayhem_not_allowed")


def coin_checks(
    proposal: MemeEntryProposal,
    wallet: MemeWalletState,
    limits: MemeLimits,
    curve: CurveState,
    context: MemeContext,
    *,
    effective: KillSwitchState,
    latched: bool,
    live_enabled: bool,
) -> list[MemeCheck]:
    """Checks 1–13, in the order of §4."""
    return [
        kill_switch_check(effective, latched),
        wallet_status_check(wallet, proposal),
        live_gate_check(proposal, live_enabled=live_enabled),
        program_allowed_check(proposal, context),
        quote_supported_check(proposal),
        identity_match_check(proposal, curve, context),
        state_freshness_check(wallet, curve, limits),
        token_age_check(wallet, context, limits),
        curve_progress_check(curve, context, limits),
        creator_behaviour_check(context, limits),
        bundled_share_check(context, limits),
        top10_share_check(context, limits),
        mayhem_policy_check(curve, context),
    ]
