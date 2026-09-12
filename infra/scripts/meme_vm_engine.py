"""VM1, VM2, VM3 and VM7 over the pure engine (``hunter_risk_meme``, T4.14).

Imported by ``meme_vm.py``; kept apart so that file stays under the 350-line
budget. Every scenario is the doctrine's own sentence turned into arithmetic:
the minimum of the ceilings with the binding one published (VM1); five buys of
0.05 under a daily cap of 0.20 (VM2); the latched daily block that stops entries
and never an exit, the resume refused while the day still blocks (VM3); a rug
during the hold that forces the exit and bans the mint (VM7).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_meme import (
    MEME_PAPER_V0,
    CurveState,
    MemeContext,
    MemeEntryProposal,
    MemeExitProposal,
    MemeKillSwitchInputs,
    MemeResumeAuthorization,
    MemeResumeRefused,
    MemeWalletState,
    OpenMemePosition,
    PendingMemeIntent,
    PositionForExit,
    assess,
    decide_exit,
    evaluate_meme_entry,
    evaluate_meme_exit,
    resume,
)
from hunter_risk_meme.exits import ExitParams

AS_OF = datetime(2026, 9, 12, 15, 30, tzinfo=UTC)
DAY_START = datetime(2026, 9, 12, 3, 0, tzinfo=UTC)
MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
OTHER = "So11111111111111111111111111111111111111112"
CREATOR = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
INITIAL_REAL = 793_100_000_000_000


def _proposal(**over: Any) -> MemeEntryProposal:
    base: dict[str, Any] = {
        "proposal_id": "vm",
        "wallet_id": "w",
        "mint": MINT,
        "requested_sol": Decimal("0.05"),
        "max_slippage_pct": Decimal("0.01"),
        "priority_fee_sol": Decimal("0.0001"),
    }
    base.update(over)
    return MemeEntryProposal(**base)


def _wallet(**over: Any) -> MemeWalletState:
    base: dict[str, Any] = {
        "wallet_id": "w",
        "as_of": AS_OF,
        "sol_balance": Decimal("1"),
        "day_start_sol_equity": Decimal("1"),
        "peak_sol_equity": Decimal("1"),
        "day_start_utc": DAY_START,
    }
    base.update(over)
    return MemeWalletState(**base)


def _curve() -> CurveState:
    return CurveState(
        mint=MINT,
        virtual_sol_reserves=36_400_000_000,
        virtual_token_reserves=900_000_000_000_000,
        real_sol_reserves=6_400_000_000,
        real_token_reserves=INITIAL_REAL * 8 // 10,
        total_supply=1_000_000_000_000_000,
        complete=False,
        creator=CREATOR,
        is_mayhem_mode=False,
        slot=1,
        commitment="confirmed",
        observed_at=AS_OF - timedelta(seconds=1),
        source="solana_rpc",
    )


def _context(**over: Any) -> MemeContext:
    base: dict[str, Any] = {
        "mint": MINT,
        "token_created_at": AS_OF - timedelta(seconds=120),
        "token_age_source": "meme_tokens.created_at",
        "initial_real_token_reserves": INITIAL_REAL,
        "organic_volume_1m_sol": Decimal("20"),
        "volume_ts": AS_OF - timedelta(seconds=30),
        "volume_window_complete": True,
        "bundled_share_pct": Decimal("0.05"),
        "top10_share_pct": Decimal("0.15"),
        "holder_denominator_valid": True,
        "creator_net_sol": Decimal("1"),
    }
    base.update(over)
    return MemeContext(**base)


def _decide(p: MemeEntryProposal, w: MemeWalletState, ctx: MemeContext, ks: MemeKillSwitchInputs):
    return evaluate_meme_entry(
        p, w, MEME_PAPER_V0, _curve(), ctx, ks, live_enabled=False, curve_fee_pct=Decimal("0.0125")
    )


def vm1_sizing() -> tuple[bool, str]:
    d = _decide(_proposal(), _wallet(), _context(), MemeKillSwitchInputs())
    assert d.sizing is not None
    tied = _decide(
        _proposal(requested_sol=Decimal("0.05")), _wallet(), _context(), MemeKillSwitchInputs()
    )
    bitten = _decide(
        _proposal(), _wallet(), _context(organic_volume_1m_sol=Decimal("2")), MemeKillSwitchInputs()
    )
    assert bitten.sizing is not None and tied.sizing is not None
    checks = [
        d.approved and d.sizing.sol_final == Decimal("0.05"),
        tied.sizing.binding_constraint == "requested" and "trade_cap" in tied.sizing.tied_limits,
        bitten.sizing.binding_constraint == "participation",
        bitten.sizing.size_without_participation.sol == Decimal("0.05"),
        bitten.sizing.size_without_multipliers.sol == Decimal("0.02"),
        len(d.checks) == 25,
    ]
    return all(checks), (
        f"sol_final=min(caps)={d.sizing.sol_final} binding={d.sizing.binding_constraint}; "
        f"tie -> {tied.sizing.binding_constraint} tied={list(tied.sizing.tied_limits)}; "
        f"participation bites: {bitten.sizing.sol_final} vs without={bitten.sizing.size_without_participation.sol}; "
        f"{len(d.checks)} checks recorded"
    )


def vm2_caps() -> tuple[bool, str]:
    over = _decide(
        _proposal(), _wallet(sol_balance=Decimal("2.5")), _context(), MemeKillSwitchInputs()
    )
    open_positions = tuple(
        OpenMemePosition(
            position_id=f"o{i}",
            mint=OTHER,
            sol_spent=Decimal("0.05"),
            token_amount=1,
            mark_sol=Decimal("0.05"),
        )
        for i in range(3)
    )
    pending = (PendingMemeIntent(proposal_id="q", mint=OTHER, reserved_sol=Decimal("0.05")),)
    limits = MEME_PAPER_V0.model_validate({**MEME_PAPER_V0.model_dump(), "max_open_positions": 10})
    fifth = evaluate_meme_entry(
        _proposal(),
        _wallet(positions=open_positions, pending_intents=pending, sol_balance=Decimal("0.8")),
        limits,
        _curve(),
        _context(),
        MemeKillSwitchInputs(),
        live_enabled=False,
        curve_fee_pct=Decimal("0.0125"),
    )
    per_trade = _decide(
        _proposal(requested_sol=Decimal("1")), _wallet(), _context(), MemeKillSwitchInputs()
    )
    assert fifth.sizing is not None and per_trade.sizing is not None
    checks = [
        "wallet_over_max_sol" in over.refusals,
        fifth.sizing.binding_constraint == "daily_cap" and fifth.sizing.sol_final == 0,
        "below_min_sol" in fifth.refusals,
        per_trade.sizing.binding_constraint == "trade_cap"
        and per_trade.sizing.sol_final == Decimal("0.05"),
    ]
    return all(checks), (
        f"balance 2.5 > wallet_max 2.0 -> {over.first_refusal}; 4×0.05 committed + 5th under daily cap 0.20 -> "
        f"{fifth.sizing.binding_constraint}={fifth.sizing.sol_final} ({fifth.first_refusal}); request 1 SOL -> "
        f"trade_cap {per_trade.sizing.sol_final}"
    )


def vm3_kill_switch() -> tuple[bool, str]:
    lost = _wallet(sol_balance=Decimal("0.79"))
    a = assess(lost, MEME_PAPER_V0, MemeKillSwitchInputs())
    entry = _decide(_proposal(), lost, _context(), MemeKillSwitchInputs(daily_loss_latched=True))
    position = OpenMemePosition(
        position_id="p",
        mint=MINT,
        sol_spent=Decimal("0.05"),
        token_amount=10,
        mark_sol=Decimal("0.01"),
    )
    exit_decision = evaluate_meme_exit(
        MemeExitProposal(
            proposal_id="x",
            wallet_id="w",
            position_id="p",
            mint=MINT,
            token_amount=10,
            reason="target",
        ),
        position,
        MEME_PAPER_V0,
        MemeKillSwitchInputs(system=KillSwitchState.EMERGENCY, daily_loss_latched=True),
    )
    refused = ""
    try:
        resume(
            lost,
            MEME_PAPER_V0,
            MemeKillSwitchInputs(daily_loss_latched=True),
            MemeResumeAuthorization(
                wallet_id="w", actor_role="OWNER", actor_id="everton", reason="r"
            ),
        )
    except MemeResumeRefused as exc:
        refused = exc.reason
    not_owner = ""
    try:
        resume(
            _wallet(),
            MEME_PAPER_V0,
            MemeKillSwitchInputs(daily_loss_latched=True),
            MemeResumeAuthorization(wallet_id="w", actor_role="ADMIN", actor_id="x", reason="r"),
        )
    except MemeResumeRefused as exc:
        not_owner = exc.reason
    released = resume(
        _wallet(sol_balance=Decimal("0.95")),
        MEME_PAPER_V0,
        MemeKillSwitchInputs(daily_loss_latched=True),
        MemeResumeAuthorization(wallet_id="w", actor_role="OWNER", actor_id="everton", reason="r"),
    )
    checks = [
        a.automatic is KillSwitchState.TRADING_DISABLED and a.latched,
        "daily_loss_cap_latched" in entry.refusals and not entry.approved,
        exit_decision.approved
        and exit_decision.exit_plan is not None
        and exit_decision.exit_plan.approved_tokens == 10,
        refused == "still_blocked_by_daily_loss",
        not_owner == "resume_requires_owner",
        released.daily_loss_latched is False,
    ]
    return all(checks), (
        f"loss 0.21 >= cap 0.20 -> {a.automatic} latched={a.latched}; entry -> {entry.first_refusal}; "
        f"exit under EMERGENCY+latch -> approved={exit_decision.approved}; resume while blocked -> {refused}; "
        f"resume by ADMIN -> {not_owner}; resume by OWNER after recovery -> latched={released.daily_loss_latched}; "
        "10 s re-read: executor loop (kill_switch_once)"
    )


def vm7_rug_during_hold() -> tuple[bool, str]:
    held = PositionForExit(
        position_id="p",
        mint=MINT,
        entry_at=AS_OF - timedelta(seconds=60),
        sol_spent=Decimal("0.05"),
        token_amount=10,
        peak_mark_sol=Decimal("0.06"),
    )
    params = ExitParams(
        target_multiple=Decimal("2"), trailing_from_peak_pct=Decimal("0.30"), time_stop_s=900
    )
    forced = decide_exit(held, Decimal("0.055"), AS_OF, params, rug_signal=True)
    banned = _decide(_proposal(), _wallet(), _context(mint_rugged=True), MemeKillSwitchInputs())
    cooling = _decide(
        _proposal(),
        _wallet(),
        _context(rug_cooldown_until=AS_OF + timedelta(seconds=3600)),
        MemeKillSwitchInputs(),
    )
    degraded = decide_exit(held, None, AS_OF, params, rug_signal=True)
    checks = [
        forced == "rug_signal",
        "token_rugged_no_reentry" in banned.refusals,
        "rug_cooldown_active" in cooling.refusals,
        degraded == "rug_signal",
    ]
    return all(checks), (
        f"rug signal during hold -> exit {forced} (also without a mark: {degraded}, the sale waits degraded, "
        f"never a fabricated fill); reentry -> {banned.first_refusal}; wallet cooldown -> {cooling.first_refusal}"
    )
