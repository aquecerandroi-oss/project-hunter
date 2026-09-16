"""T4.28 — stage 1 "liga sozinho": the executor opens the desk's ``operator``
proposal as a live one without the click, inside the written small-test scope.

Pure pieces, tabled: the planner (which ``proposed`` rows become live this tick,
which are skipped and why), the scope arithmetic (trades and SOL used against the
written scope; the requested size clamped to what is left) and the boot rules
(the flag is read only with the live flag on and a small test in the gates; a
flag without scope refuses by name). Nothing here touches a database or a key.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hunter_core.domain.enums import KillSwitchState
from hunter_core.execution.meme.approval import AUTO_STAGE1_DECIDED_BY
from hunter_core.execution.meme.base58 import b58encode
from hunter_core.execution.meme.gates import MemeLiveTradingRefused, SmallTestAuthorization
from hunter_core.execution.meme.signer import ENV_SECRET_KEY
from hunter_meme_executor.auto_approve import (
    AUTO_APPROVE_MAX_AGE_S,
    OperatorProposal,
    auto_decision,
    plan_auto_approvals,
)
from hunter_meme_executor.config import boot
from hunter_meme_executor.scope import scope_use

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 16, 4, 30, tzinfo=UTC)
TODAY = date(2026, 9, 16)
SUGGESTED: dict[str, Any] = {
    "size_sol": "0.05",
    "target_x": "3",
    "trailing_pct": "35",
    "max_hold_s": 1800,
    "manual_plan": "Comprar 0,05 SOL de X ...",
}
SMALL_TEST = SmallTestAuthorization(
    authorized_by="everton",
    max_sol_per_trade=Decimal("0.05"),
    max_total_sol=Decimal("0.25"),
    max_trades=5,
    expires_at=date(2026, 9, 18),
    decision_note="obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md",
)


def _proposal(
    *,
    mint: str = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump",
    age_s: float = 5,
    ttl_s: float = 180,
    suggested: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    id: str = "01994d00-6c1a-7000-8000-000000000101",
) -> OperatorProposal:
    proposed_at = NOW - timedelta(seconds=age_s)
    return OperatorProposal(
        id=id,
        mint=mint,
        suggested=dict(SUGGESTED if suggested is None else suggested),
        proposed_at=proposed_at,
        expires_at=proposed_at + timedelta(seconds=ttl_s),
        rule_set_params={"max_sol_per_bet": "0.05"} if params is None else params,
    )


def _plan(candidates: list[OperatorProposal], **overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "now": NOW,
        "approved_last_hour": 0,
        "max_per_hour": 5,
        "max_per_tick": 1,
    }
    kwargs.update(overrides)
    return plan_auto_approvals(candidates, **kwargs)


class TestPlanner:
    def test_a_fresh_operator_proposal_is_opened_as_live_by_the_executor(self) -> None:
        plan = _plan([_proposal()])
        assert [p.id for p in plan.picks] == ["01994d00-6c1a-7000-8000-000000000101"]
        assert plan.skipped == {}
        decided = auto_decision(plan.picks[0], now=NOW)
        assert decided.status == "approved" and decided.mode == "live"
        assert decided.decided_by == AUTO_STAGE1_DECIDED_BY == "executor:auto_stage1"
        assert decided.decided_at == NOW
        assert decided.decision is not None
        # decision = suggested (the set's own numbers), plus who decided and why.
        for key, value in SUGGESTED.items():
            assert decided.decision[key] == value
        assert decided.decision["note"] == "auto_stage1: aberta pelo executor sem clique"

    def test_a_proposal_older_than_sixty_seconds_is_left_to_the_human(self) -> None:
        assert AUTO_APPROVE_MAX_AGE_S == 60
        plan = _plan([_proposal(age_s=60.5)])
        assert plan.picks == ()
        assert plan.skipped == {"too_old": 1}
        assert _plan([_proposal(age_s=59.9)]).picks != ()

    def test_the_hourly_cap_stops_the_robot_not_the_human(self) -> None:
        plan = _plan([_proposal()], approved_last_hour=5, max_per_hour=5)
        assert plan.picks == () and plan.skipped == {"hourly_cap": 1}
        assert _plan([_proposal()], approved_last_hour=4, max_per_hour=5).picks != ()

    def test_at_most_one_buy_per_tick(self) -> None:
        first = _proposal(id="01994d00-6c1a-7000-8000-000000000101")
        second = _proposal(
            id="01994d00-6c1a-7000-8000-000000000102",
            mint="2nG3hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump",
        )
        plan = _plan([first, second])
        assert [p.id for p in plan.picks] == [first.id]
        assert plan.skipped == {"tick_cap": 1}

    def test_never_two_for_the_same_mint_in_one_tick(self) -> None:
        first = _proposal(id="01994d00-6c1a-7000-8000-000000000101")
        twin = _proposal(id="01994d00-6c1a-7000-8000-000000000102")
        plan = _plan([first, twin], max_per_tick=2)
        assert [p.id for p in plan.picks] == [first.id]
        assert plan.skipped == {"mint_repeated": 1}

    def test_a_mint_with_a_live_position_or_a_buy_in_flight_is_left_alone(self) -> None:
        """Opening it would only be refused ``duplicate_position`` — and an
        auto-rejected proposal is gone for the human's click too."""
        busy = frozenset({"5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"})
        plan = _plan([_proposal()], busy_mints=busy)
        assert plan.picks == () and plan.skipped == {"mint_busy": 1}
        other = _proposal(mint="2nG3hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump")
        assert _plan([other], busy_mints=busy).picks == (other,)

    def test_a_proposal_past_its_deadline_is_never_opened(self) -> None:
        plan = _plan([_proposal(age_s=30, ttl_s=30)])
        assert plan.picks == () and plan.skipped == {"expired": 1}

    def test_the_set_ceiling_is_the_click_rule_too(self) -> None:
        plan = _plan([_proposal(suggested={**SUGGESTED, "size_sol": "0.06"})])
        assert plan.picks == () and plan.skipped == {"exceeds_max_sol_per_bet": 1}

    def test_a_suggestion_without_a_size_is_not_a_decision(self) -> None:
        plan = _plan([_proposal(suggested={"target_x": "3"})])
        assert plan.picks == () and plan.skipped == {"suggested_incomplete": 1}
        plan = _plan([_proposal(suggested={**SUGGESTED, "size_sol": "abc"})])
        assert plan.picks == () and plan.skipped == {"suggested_incomplete": 1}

    def test_the_hourly_cap_counts_this_ticks_picks_too(self) -> None:
        first = _proposal(id="01994d00-6c1a-7000-8000-000000000101")
        second = _proposal(
            id="01994d00-6c1a-7000-8000-000000000102",
            mint="2nG3hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump",
        )
        plan = _plan([first, second], approved_last_hour=4, max_per_hour=5, max_per_tick=2)
        assert [p.id for p in plan.picks] == [first.id]
        assert plan.skipped == {"hourly_cap": 1}


class TestScope:
    def test_inside_the_scope_the_request_passes_whole(self) -> None:
        use = scope_use(
            SMALL_TEST, trades_done=2, used_sol=Decimal("0.104"), requested_sol=Decimal("0.05")
        )
        assert use.exhausted is None
        assert use.remaining_sol == Decimal("0.146")
        assert use.requested_cap_sol == Decimal("0.05")
        assert use.as_json()["max_trades"] == 5 and use.as_json()["used_sol"] == "0.104"

    def test_the_trade_counter_closes_the_tap(self) -> None:
        use = scope_use(
            SMALL_TEST, trades_done=5, used_sol=Decimal("0.2"), requested_sol=Decimal("0.05")
        )
        assert use.exhausted == "max_trades"

    def test_the_sol_ceiling_closes_the_tap_too(self) -> None:
        use = scope_use(
            SMALL_TEST, trades_done=3, used_sol=Decimal("0.25"), requested_sol=Decimal("0.05")
        )
        assert use.exhausted == "max_total_sol"
        assert use.remaining_sol == Decimal("0")
        over = scope_use(
            SMALL_TEST, trades_done=3, used_sol=Decimal("0.26"), requested_sol=Decimal("0.05")
        )
        assert over.exhausted == "max_total_sol" and over.remaining_sol == Decimal("0")

    def test_the_last_buy_is_clamped_to_what_is_left(self) -> None:
        use = scope_use(
            SMALL_TEST, trades_done=4, used_sol=Decimal("0.209"), requested_sol=Decimal("0.05")
        )
        assert use.exhausted is None
        assert use.requested_cap_sol == Decimal("0.041")
        assert use.as_json()["requested_clamped"] is True


def _gates(tmp_path: Path, *, small_test: bool) -> str:
    doc: dict[str, object] = {
        "schema": "hunter.meme_gates/v1",
        "gate_a_engineering": {
            "passed": not small_test,
            "date": "2026-09-12",
            "evidence": "notes-T4.14",
        },
        "gate_b_evidence": {"passed": not small_test, "date": "2026-09-12", "evidence": "EXP-M1"},
        "gate_c_owner": {"enabled": True, "date": "2026-09-12"},
        "signed_by": "everton",
        "signed_at": "2026-09-12",
        "valid_until": "2026-10-12",
    }
    if small_test:
        doc["small_test_authorization"] = {
            "authorized_by": "everton",
            "scope": {"max_sol_per_trade": "0.05", "max_total_sol": "0.25", "max_trades": 5},
            "expires_at": "2026-09-18",
            "decision_note": "obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md",
        }
    path = tmp_path / "meme_gates.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return str(path)


def _test_key() -> str:
    seed = random.Random(20260916).randbytes(32)
    pub = (
        Ed25519PrivateKey.from_private_bytes(seed)
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    )
    return b58encode(seed + pub)


def _live_env(tmp_path: Path, *, small_test: bool, **extra: str) -> dict[str, str]:
    return {
        "ENABLE_MEME_LIVE_TRADING": "true",
        "MEME_GATES_FILE": _gates(tmp_path, small_test=small_test),
        "MEME_WALLET_MAX_SOL": "0.30",
        "MEME_MAX_SOL_PER_TRADE": "0.05",
        "MEME_DAILY_LOSS_CAP_SOL": "0.15",
        "MEME_MAX_OPEN_POSITIONS": "2",
        "MEME_COOLDOWN_S": "60",
        "SOLANA_RPC_URL": "https://rpc.example",
        ENV_SECRET_KEY: _test_key(),
        **extra,
    }


class TestBoot:
    def test_the_flag_is_off_by_default(self, tmp_path: Path) -> None:
        config, _, _ = boot(
            _live_env(tmp_path, small_test=True),
            today=TODAY,
            system_kill_switch=KillSwitchState.ACTIVE,
        )
        assert config.auto_approve is False
        assert config.auto_approve_max_per_hour == 5
        assert config.small_test_max_total_sol == Decimal("0.25")
        assert config.small_test_max_trades == 5

    def test_the_flag_with_a_written_scope_arms_the_robot(self, tmp_path: Path) -> None:
        env = _live_env(
            tmp_path,
            small_test=True,
            MEME_LIVE_AUTO_APPROVE="1",
            MEME_LIVE_AUTO_APPROVE_MAX_PER_HOUR="2",
        )
        config, _, _ = boot(env, today=TODAY, system_kill_switch=KillSwitchState.ACTIVE)
        assert config.auto_approve is True
        assert config.auto_approve_max_per_hour == 2

    def test_the_flag_without_a_written_scope_refuses_to_boot(self, tmp_path: Path) -> None:
        env = _live_env(tmp_path, small_test=False, MEME_LIVE_AUTO_APPROVE="1")
        with pytest.raises(MemeLiveTradingRefused) as info:
            boot(env, today=TODAY, system_kill_switch=KillSwitchState.ACTIVE)
        assert info.value.reason == "auto_approve_needs_small_test"
        assert ENV_SECRET_KEY in env, "refused before the key is read"

    def test_the_flag_without_the_live_flag_is_inert(self) -> None:
        config, _, signer = boot(
            {"MEME_LIVE_AUTO_APPROVE": "true"},
            today=TODAY,
            system_kill_switch=KillSwitchState.ACTIVE,
        )
        assert config.auto_approve is False and config.live is False and signer is None
