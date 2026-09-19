"""T4.67b — the launch profile's inputs, pure (no DB, no RPC): the age comes
from the proposal's own create stamp (then the token row, then ``proposed_at``
labelled as a lower bound); the denominator from the token row, else the
stock curve's ``Global`` (never for a Mayhem coin); the volume is the curve's
real SOL; the request is the set's size capped by the ticket; the position's
params carry the launch exits with EXP-M18's defaults; every skipped check and
read is written by name; the fast admission approves the healthy launch and
records ``profile = launch``."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import BondingCurveAccount
from hunter_exchanges.pumpfun.global_state import decode_global_account
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID
from hunter_meme_executor.admission import AdmissionInputs, admit_launch, curve_from, wallet_from
from hunter_meme_executor.chain import CurveRead, WalletRead
from hunter_meme_executor.kill_switch import DayAnchor
from hunter_meme_executor.launch_admission import (
    LAUNCH_READS_SKIPPED,
    launch_context,
    launch_position_params,
    launch_proposal,
)
from hunter_meme_executor.launch_config import LAUNCH_SERIES, LaunchConfig
from hunter_meme_executor.launch_repo import LaunchCandidate, created_at_of
from hunter_meme_executor.repo import Candidate, OpenPosition, TokenContext
from hunter_risk_meme import LAUNCH_SKIPPED_CHECKS, MemeKillSwitchInputs, limits_from_env

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
CREATOR = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
WALLET = "3moUmVs7CHAtxggNQwQxEDN2A85JFrJ2SN3k2oggDRBD"
NOW = datetime(2026, 9, 19, 15, 0, 1, tzinfo=UTC)
CREATED = NOW - timedelta(seconds=1)
DAY_START = datetime(2026, 9, 19, 3, 0, tzinfo=UTC)
PROPOSAL_ID = "01994d00-6c1a-7000-8000-0000000000aa"
POLICY = {
    "MEME_WALLET_MAX_SOL": "0.5",
    "MEME_MAX_SOL_PER_TRADE": "0.05",
    "MEME_DAILY_LOSS_CAP_SOL": "0.1",
    "MEME_MAX_OPEN_POSITIONS": "3",
    "MEME_COOLDOWN_S": "3600",
}
LIMITS = limits_from_env(POLICY)
LAUNCH = LaunchConfig(mode="on")
GLOBAL = decode_global_account(
    json.loads((FIXTURES / "rpc_global_account_raw.json").read_text())["result"]["value"]["data"][
        0
    ],
    owner=json.loads((FIXTURES / "rpc_global_account_raw.json").read_text())["result"]["value"][
        "owner"
    ],
)


def _curve(
    *, real_sol: int = 500_000_000, mayhem: bool = False, supply: int | None = None
) -> CurveRead:
    """A curve one second old with ``real_sol`` lamports bought (dev buy + first bots)."""
    sold = 13_000_000_000_000 * real_sol // 500_000_000
    account = BondingCurveAccount(
        virtual_token_reserves=GLOBAL.initial_virtual_token_reserves - sold,
        virtual_sol_reserves=GLOBAL.initial_virtual_sol_reserves + real_sol,
        real_token_reserves=GLOBAL.initial_real_token_reserves - sold,
        real_sol_reserves=real_sol,
        token_total_supply=GLOBAL.token_total_supply if supply is None else supply,
        complete=False,
        creator=CREATOR,
        is_mayhem_mode=mayhem,
        is_cashback_coin=False,
        quote_mint="11111111111111111111111111111111",
    )
    return CurveRead(
        MINT, account, TOKEN_PROGRAM_ID, 1, NOW - timedelta(milliseconds=200), "processed"
    )


def _candidate(
    *,
    reasons: list[dict[str, Any]] | None = None,
    decision: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    quote: dict[str, Any] | None = None,
) -> LaunchCandidate:
    return LaunchCandidate(
        candidate=Candidate(
            id=PROPOSAL_ID,
            mint=MINT,
            decision={"size_sol": "0.01"} if decision is None else decision,
            decided_at=NOW - timedelta(milliseconds=500),
            decided_by="rules",
            status="approved",
            proposed_at=NOW - timedelta(milliseconds=500),
        ),
        suggested={"size_sol": "0.01"},
        quote=quote or {},
        reasons=[{"series": LAUNCH_SERIES, "created_at": CREATED.isoformat()}]
        if reasons is None
        else reasons,
        rule_set_params={"clock": "event", "time_stop_s": 6, "max_drawdown_from_peak_pct": "20"}
        if params is None
        else params,
        rule_set_version="1",
    )


def _token(**over: Any) -> TokenContext:
    base: dict[str, Any] = {
        "created_at": CREATED - timedelta(milliseconds=100),
        "creator": CREATOR,
        "initial_real_token_reserves": 793_100_000,
        "completed_at": None,
        "migrated_at": None,
        "curve_volume_1m_sol": None,
        "features_end_time": None,
        "creator_sold": None,
        "top10_share": None,
        "bundled_share": None,
    }
    base.update(over)
    return TokenContext(**base)


# ---- provenance ---------------------------------------------------------------------


def test_the_age_comes_from_the_proposals_create_stamp_first() -> None:
    stamp, source = created_at_of(_candidate())
    assert stamp == CREATED and source == "meme_proposals.reasons[0].created_at"
    from_quote = _candidate(
        reasons=[{"series": LAUNCH_SERIES}], quote={"created_at": CREATED.isoformat()}
    )
    assert created_at_of(from_quote) == (CREATED, "meme_proposals.quote.created_at")
    naive = _candidate(reasons=[{"series": LAUNCH_SERIES, "created_at": "2026-09-19T15:00:00"}])
    assert created_at_of(naive) == (None, None), "a naive stamp is no stamp"
    from dataclasses import replace

    lane = replace(_candidate(reasons=[{"series": LAUNCH_SERIES}]), features_end_time=CREATED)
    assert created_at_of(lane) == (CREATED, "meme_proposals.features_end_time"), (
        "T4.67a stamps the create instant in features_end_time"
    )
    context, extras = launch_context(
        from_quote, None, _curve(), GLOBAL, participation_used_sol=Decimal(0), now=NOW
    )
    assert context.token_created_at == CREATED
    bare = _candidate(reasons=[{"series": LAUNCH_SERIES}])
    context, extras = launch_context(
        bare, _token(), _curve(), GLOBAL, participation_used_sol=Decimal(0), now=NOW
    )
    assert context.token_age_source == "meme_tokens.created_at"
    context, extras = launch_context(
        bare, None, _curve(), GLOBAL, participation_used_sol=Decimal(0), now=NOW
    )
    assert context.token_created_at == bare.candidate.proposed_at
    assert extras["token_age_source"] == "meme_proposals.proposed_at(lower_bound_on_age)"


def test_the_denominator_is_the_token_rows_else_the_stock_curves_global_never_mayhems() -> None:
    from_row, extras = launch_context(
        _candidate(), _token(), _curve(), GLOBAL, participation_used_sol=Decimal(0), now=NOW
    )
    assert from_row.initial_real_token_reserves == 793_100_000 * 10**6
    assert extras["denominator_source"] == "meme_tokens.initial_real_token_reserves"
    from_lane, extras = launch_context(
        _candidate(reasons=[{"series": LAUNCH_SERIES, "initial_real_token_reserves": "793100000"}]),
        None,
        _curve(),
        GLOBAL,
        participation_used_sol=Decimal(0),
        now=NOW,
    )
    assert from_lane.initial_real_token_reserves == 793_100_000 * 10**6
    assert extras["denominator_source"] == "meme_proposals.reasons[0].initial_real_token_reserves"
    from_global, extras = launch_context(
        _candidate(), None, _curve(), GLOBAL, participation_used_sol=Decimal(0), now=NOW
    )
    assert from_global.initial_real_token_reserves == GLOBAL.initial_real_token_reserves
    assert extras["denominator_source"] == "pump_global.initial_real_token_reserves(stock_curve)"
    mayhem, extras = launch_context(
        _candidate(), None, _curve(mayhem=True), GLOBAL, participation_used_sol=Decimal(0), now=NOW
    )
    assert mayhem.initial_real_token_reserves is None and extras["denominator_source"] == "none"
    odd_supply, _ = launch_context(
        _candidate(),
        None,
        _curve(supply=2 * 10**15),
        GLOBAL,
        participation_used_sol=Decimal(0),
        now=NOW,
    )
    assert odd_supply.initial_real_token_reserves is None


def test_the_volume_is_the_curves_real_sol_and_the_skips_are_written_by_name() -> None:
    context, extras = launch_context(
        _candidate(),
        None,
        _curve(real_sol=750_000_000),
        GLOBAL,
        participation_used_sol=Decimal("0.002"),
        now=NOW,
    )
    assert (
        context.organic_volume_1m_sol == Decimal("0.75") and context.volume_window_complete is True
    )
    assert context.volume_ts is not None and context.participation_used_sol == Decimal("0.002")
    assert context.bundled_share_pct is None and context.top10_share_pct is None
    assert context.creator_net_sol is None
    assert extras["profile"] == "launch" and extras["quote_commitment"] == "processed"
    assert extras["skipped_checks"] == LAUNCH_SKIPPED_CHECKS
    assert extras["skipped_reads"] == LAUNCH_READS_SKIPPED
    assert set(LAUNCH_READS_SKIPPED) == {
        "risk_snapshot_on_demand",
        "creator_ata",
        "buyer_ata",
        "conviction_read",
        "token_context",
    }


# ---- the request and the position ----------------------------------------------------


def test_the_request_is_the_sets_size_or_the_ticket_and_always_live() -> None:
    proposal = launch_proposal(
        _candidate(),
        wallet_id=WALLET,
        limits=LIMITS,
        launch=LAUNCH,
        priority_fee_sol=Decimal("0.0004"),
    )
    assert proposal.requested_sol == Decimal("0.01") and proposal.mode == "live"
    assert (
        proposal.agent_id == "launch:rules" and proposal.max_slippage_pct == LIMITS.max_slippage_pct
    )
    silent = launch_proposal(
        _candidate(decision={}),
        wallet_id=WALLET,
        limits=LIMITS,
        launch=LAUNCH,
        priority_fee_sol=Decimal(0),
    )
    assert silent.requested_sol == Decimal("0.01")
    absurd = launch_proposal(
        _candidate(decision={"size_sol": "-3"}),
        wallet_id=WALLET,
        limits=LIMITS,
        launch=LAUNCH,
        priority_fee_sol=Decimal(0),
    )
    assert absurd.requested_sol == Decimal("0.01")


def test_the_position_params_carry_the_launch_exits_with_the_sets_numbers_or_the_defaults() -> None:
    params = launch_position_params(_candidate(), _curve())
    assert params["lane"] == "launch" and params["series"] == LAUNCH_SERIES
    assert params["time_stop_s"] == 6 and params["max_hold_s"] == 6
    assert params["max_drawdown_from_peak_pct"] == "20" and params["trailing_pct"] == "20"
    assert params["exit_on_first_third_party_sell"] is True
    assert (
        params["creator"] == CREATOR
        and params["creation_slot"] is None
        and params["known_buyers"] == []
    )
    assert "target_x" not in params, "the launch set has no target; the profile's default applies"
    from hunter_meme_executor.exit_common import exit_params

    exits = exit_params(params, LIMITS)
    assert exits.time_stop_s == 6 and exits.trailing_from_peak_pct == Decimal("0.20")
    assert exits.target_multiple == LIMITS.target_multiple
    custom = launch_position_params(
        _candidate(
            decision={"size_sol": "0.01", "time_stop_s": "15", "target_x": "1.5"},
            params={"max_drawdown_from_peak_pct": "35", "exit_on_first_third_party_sell": False},
            reasons=[
                {
                    "series": LAUNCH_SERIES,
                    "creation_slot": 448_000_000,
                    "known_buyers": ["A", "B", 3],
                }
            ],
        ),
        _curve(),
    )
    assert custom["time_stop_s"] == 15 and custom["max_drawdown_from_peak_pct"] == "35"
    assert custom["exit_on_first_third_party_sell"] is False and custom["target_x"] == "1.5"
    assert custom["creation_slot"] == 448_000_000 and custom["known_buyers"] == ["A", "B"]
    silent = launch_position_params(_candidate(decision={}, params={}), _curve())
    assert silent["time_stop_s"] == 6 and silent["max_drawdown_from_peak_pct"] == "20"


# ---- the fast admission end to end (pure) ----------------------------------------------


def _inputs(
    *, positions: list[OpenPosition] | None = None, priority_fee_sol: Decimal = Decimal("0.0004")
) -> AdmissionInputs:
    candidate, curve = _candidate(), _curve()
    context, _ = launch_context(
        candidate, None, curve, GLOBAL, participation_used_sol=Decimal(0), now=NOW
    )
    return AdmissionInputs(
        proposal=launch_proposal(
            candidate,
            wallet_id=WALLET,
            limits=LIMITS,
            launch=LAUNCH,
            priority_fee_sol=priority_fee_sol,
        ),
        wallet=wallet_from(
            wallet_id=WALLET,
            now=NOW,
            balance=WalletRead(WALLET, 300_000_000, 1, NOW),
            positions=positions or [],
            pending=[],
            anchor=DayAnchor(DAY_START, Decimal("0.3"), Decimal("0.3"), NOW),
            limits=LIMITS,
        ),
        curve=curve_from(curve),
        context=context,
        kill_switch=MemeKillSwitchInputs(),
        creates_ata=True,
        curve_fee_pct=Decimal("0.0125"),
    )


def _launch_position(i: int) -> OpenPosition:
    return OpenPosition(
        id=f"l{i}",
        proposal_id=f"01994d00-6c1a-7000-8000-0000000000{i:02d}",
        mint="So11111111111111111111111111111111111111112",
        entry_at=NOW - timedelta(seconds=3),
        tokens=1000,
        sol_spent_lamports=10_000_000,
        initial_risk_sol=Decimal("0.01"),
        params={"lane": "launch"},
        mark_sol=Decimal("0.01"),
        high_water_sol=Decimal("0.01"),
        exit_intent=None,
        sell_requested_at=None,
        sell_requested_by=None,
        migrated=False,
    )


def test_the_fast_admission_approves_a_healthy_launch_under_the_processed_quote() -> None:
    decision = admit_launch(_inputs(), LIMITS, LAUNCH.profile(LIMITS), live_enabled=True)
    assert decision.approved, decision.refusals
    assert decision.profile == "launch"
    assert decision.sizing is not None and decision.sizing.sol_final == Decimal("0.01")
    states = {c.name: c.state.value for c in decision.checks}
    assert states["state_freshness"] == "passed" and states["creator_behaviour"] == "skipped"
    assert states["bundled_share"] == "skipped" and states["conviction"] == "skipped"
    assert states["launch_open_cap"] == "passed"
    # 0,01 SOL under a 0,02 live floor: the floor followed the ticket (check 23 passed).
    assert LIMITS.min_trade_sol == Decimal("0.02") and states["sizing"] == "passed"


def test_the_launch_cap_refuses_the_third_launch_and_the_fee_cap_binds_at_five_pct() -> None:
    two = admit_launch(
        _inputs(positions=[_launch_position(1), _launch_position(2)]),
        LIMITS,
        LAUNCH.profile(LIMITS),
        live_enabled=True,
    )
    assert "launch_max_open_reached" in two.refusals
    # 1 000 000 µL/CU × 400 000 CU = 0,0004 SOL ≤ 5 % of 0,01; 2 000 000 is 0,0008 > 0,0005.
    pricey = admit_launch(
        _inputs(priority_fee_sol=Decimal("0.0008")),
        LIMITS,
        LAUNCH.profile(LIMITS),
        live_enabled=True,
    )
    assert "priority_fee_above_cap" in pricey.refusals


def test_the_full_profile_would_refuse_the_same_launch_by_name() -> None:
    from hunter_meme_executor.admission import admit

    full = admit(_inputs(), LIMITS, live_enabled=True)
    assert not full.approved
    assert {
        "commitment_too_weak",
        "token_too_young",
        "creator_flow_unknown",
        "bundled_share_unmeasurable",
    } <= set(full.refusals)
