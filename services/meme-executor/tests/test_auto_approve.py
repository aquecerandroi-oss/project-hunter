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
from hunter_meme_executor.refusal_cooldown import (
    DETERMINISTIC_REFUSALS,
    cooling_mints_of,
    refusal_window_start,
)
from hunter_meme_executor.repo import RISK_SNAPSHOT_MAX_AGE_S
from hunter_meme_executor.risk_snapshot import (
    SNAPSHOT_MAX_AGE_S,
    mints_with_snapshot,
    risk_snapshot_sql,
)
from hunter_meme_executor.scope import scope_use
from hunter_risk_meme.checks import REFUSAL_NAMES

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

    def test_a_proposal_older_than_ten_seconds_is_left_to_the_human(self) -> None:
        """T4.94: 10 s by default (60 s before; R78's queue opened 11.5–53.8 s-old rows)."""
        assert AUTO_APPROVE_MAX_AGE_S == 10
        plan = _plan([_proposal(age_s=10.5)])
        assert plan.picks == ()
        assert plan.skipped == {"too_old": 1}
        assert _plan([_proposal(age_s=9.9)]).picks != ()

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
        # T4.94 guardian finding 1: the twin is superseded once ``first`` opens.
        assert [p.id for p in plan.siblings] == [twin.id] and plan.skipped == {}

    def test_a_mint_with_a_live_position_or_a_buy_in_flight_is_never_opened(self) -> None:
        """Opening it now would only be refused ``duplicate_position``; opening it
        after the other position exits would buy on a stale tape (T4.94, R78) —
        so it is superseded (rejected by name), not kept waiting."""
        busy = frozenset({"5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"})
        plan = _plan([_proposal()], busy_mints=busy)
        assert plan.picks == () and plan.skipped == {"mint_busy_superseded": 1}
        assert [p.id for p in plan.superseded] == ["01994d00-6c1a-7000-8000-000000000101"]
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


class TestRefusalCooldown:
    """T4.28f — measured 16/09/2026 11:46–11:48 BRT: the desk re-proposed the same
    mint every ~20 s, the robot opened it five times and the admission refused it
    five times with the same ``progress_below_window``. A refusal that cannot
    change in the next couple of minutes buys nothing on a retry: one RPC curve
    read, one ``refused`` order row and one ``rejected`` proposal each time."""

    MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"

    def test_every_cooling_reason_is_a_real_admission_refusal(self) -> None:
        """The set is a subset of §4's names: a typo here would silently never
        cool anything (no refusal would ever match it)."""
        assert DETERMINISTIC_REFUSALS <= REFUSAL_NAMES
        assert (
            "progress_above_window" in DETERMINISTIC_REFUSALS
            and "progress_below_window" not in DETERMINISTIC_REFUSALS
        )
        # Reversible on the next tick — these must never block a retry. The last
        # one is the rule's own boundary: ``token_too_young`` is cleared by the
        # **clock** at ``token_age_min_s`` (30 s), well inside a 120 s cooldown,
        # so cooling it would sit on a coin that is already admissible.
        for reason in (
            "curve_state_stale",
            "volume_unavailable",
            "marks_incomplete",
            "wallet_over_max_sol",
            "token_too_young",
        ):
            assert reason in REFUSAL_NAMES
            assert reason not in DETERMINISTIC_REFUSALS
        # And the gate's own refusals are not admission refusals at all: a mint
        # the radar gate refused never reaches ``meme_live_orders``.
        for gate_only in ("creator_serial", "symbol_clone", "mayhem_curve", "mayhem_unknown"):
            assert gate_only not in REFUSAL_NAMES
            assert gate_only not in DETERMINISTIC_REFUSALS

    def test_a_mint_refused_thirty_seconds_ago_is_not_reopened(self) -> None:
        refused_at = NOW - timedelta(seconds=30)
        assert refusal_window_start(NOW, 120.0) == NOW - timedelta(seconds=120)
        assert refused_at >= (refusal_window_start(NOW, 120.0) or NOW), "inside the window"
        cooling = cooling_mints_of([(self.MINT, "progress_above_window")])
        assert cooling == frozenset({self.MINT})
        plan = _plan([_proposal()], cooling_mints=cooling)
        assert plan.picks == () and plan.skipped == {"recently_refused": 1}

    def test_the_same_mint_refused_two_hundred_seconds_ago_is_opened_again(self) -> None:
        """Past the cooldown the query no longer returns the row (``received_at >=
        :since``), so nothing cools and the next proposal is opened."""
        since = refusal_window_start(NOW, 120.0)
        assert since is not None and NOW - timedelta(seconds=200) < since
        plan = _plan([_proposal()], cooling_mints=frozenset())
        assert [p.id for p in plan.picks] == ["01994d00-6c1a-7000-8000-000000000101"]

    def test_a_refusal_that_can_clear_on_the_next_tick_never_cools(self) -> None:
        cooling = cooling_mints_of([(self.MINT, "curve_state_stale")])
        assert cooling == frozenset()
        assert _plan([_proposal()], cooling_mints=cooling).picks != ()
        # Mixed rows: only the deterministic one cools its mint.
        other = "2nG3hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump"
        mixed = cooling_mints_of([(self.MINT, "curve_state_stale"), (other, "token_too_old")])
        assert mixed == frozenset({other})

    def test_the_cooldown_at_zero_disables_the_skip(self) -> None:
        assert refusal_window_start(NOW, 0.0) is None, "no window, no query, no skip"
        assert refusal_window_start(NOW, -5.0) is None
        plan = _plan([_proposal()], cooling_mints=frozenset())
        assert plan.picks != () and plan.skipped == {}

    def test_a_cooling_mint_does_not_hide_a_fresh_one(self) -> None:
        other = _proposal(
            id="01994d00-6c1a-7000-8000-000000000102",
            mint="2nG3hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump",
        )
        plan = _plan([_proposal(), other], cooling_mints=frozenset({self.MINT}))
        assert [p.id for p in plan.picks] == [other.id]
        assert plan.skipped == {"recently_refused": 1}


class TestRiskSnapshotPending:
    """T4.28g — the robot waits for the rug read instead of burning the proposal.

    Measured 16/09/2026 (R5): 13 of the day's 16 real orders were refused
    ``bundled_share_unmeasurable``, and the mint's ``meme_risk_snapshots`` row
    landed a median **103 s after** the decision. Opening the proposal then is
    strictly worse than not opening it: the row is ``rejected`` by the robot (gone
    for the human's click too), one RPC curve read and one ``refused`` order are
    written, and the coin becomes unbuyable for a number that arrives seconds
    later. Nothing here loosens check 11 — an unmeasured ``bundled_share`` still
    refuses; the proposal simply is not opened until the input exists."""

    MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"

    def test_a_mint_without_a_fresh_risk_snapshot_is_not_opened_yet(self) -> None:
        plan = _plan([_proposal()], snapshot_mints=frozenset())
        assert plan.picks == ()
        assert plan.skipped == {"risk_snapshot_pending": 1}

    def test_the_same_mint_with_a_snapshot_is_opened(self) -> None:
        plan = _plan([_proposal()], snapshot_mints=frozenset({self.MINT}))
        assert [p.mint for p in plan.picks] == [self.MINT]
        assert plan.skipped == {}

    def test_a_pending_mint_does_not_hide_a_measured_one(self) -> None:
        """The skip costs the tick nothing: the next candidate is still opened."""
        other = _proposal(
            id="01994d00-6c1a-7000-8000-000000000102",
            mint="2nG3hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump",
        )
        plan = _plan([_proposal(), other], snapshot_mints=frozenset({other.mint}))
        assert [p.id for p in plan.picks] == [other.id]
        assert plan.skipped == {"risk_snapshot_pending": 1}

    def test_the_skip_is_off_when_the_caller_did_not_measure(self) -> None:
        """``None`` is "not measured", not "measured empty" — the planner then
        behaves exactly as it did before T4.28g (open, and let the admission
        refuse by name). ``auto_approve_once`` always measures."""
        assert _plan([_proposal()]).picks != ()
        assert _plan([_proposal()], snapshot_mints=None).picks != ()

    def test_a_proposal_too_old_is_the_humans_not_a_pending_snapshot(self) -> None:
        """``too_old`` wins the ordering, so the two names never collide: past
        ``AUTO_APPROVE_MAX_AGE_S`` the row is left to the click, snapshot or not.
        That is also why the skip needs no age condition of its own — anything
        reaching it is younger than ``AUTO_APPROVE_MAX_AGE_S``."""
        plan = _plan([_proposal(age_s=90)], snapshot_mints=frozenset())
        assert plan.picks == () and plan.skipped == {"too_old": 1}

    def test_a_busy_or_cooling_mint_still_wins_the_ordering(self) -> None:
        """Waiting on a read a mint does not need would hide the real reason."""
        busy = _plan([_proposal()], snapshot_mints=frozenset(), busy_mints=frozenset({self.MINT}))
        assert busy.skipped == {"mint_busy_superseded": 1}
        cooling = _plan(
            [_proposal()], snapshot_mints=frozenset(), cooling_mints=frozenset({self.MINT})
        )
        assert cooling.skipped == {"recently_refused": 1}

    def test_the_freshness_window_is_the_admissions_own(self) -> None:
        """One home for the 600 s: the planner waits for exactly the row
        ``repo.token_context`` would accept, never a different one."""
        assert SNAPSHOT_MAX_AGE_S == RISK_SNAPSHOT_MAX_AGE_S == 600

    def test_only_a_measured_bundled_share_counts_as_a_snapshot(self) -> None:
        """A ``/in-memory-coin`` read that answered without ``bundledSharePct`` is
        not the input check 11 needs; waiting for another one is right, and
        ``mints_with_snapshot`` must not report it as measured."""
        sql = risk_snapshot_sql()
        assert "bundled_share IS NOT NULL" in sql
        assert "observed_at >= :since" in sql
        assert "mint = ANY(:mints)" in sql

    @pytest.mark.asyncio
    async def test_no_candidates_means_no_query(self) -> None:
        """A tick with nothing to open must not touch a partitioned table."""

        class Forbidden:
            async def execute(self, *args: Any, **kwargs: Any) -> Any:
                raise AssertionError("no candidates must not query meme_risk_snapshots")

        measured = await mints_with_snapshot(Forbidden(), frozenset(), now=NOW)  # type: ignore[arg-type]
        assert measured == frozenset()


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
        assert config.auto_approve_refusal_cooldown_s == 120.0, "T4.28f default"

    def test_the_refusal_cooldown_comes_from_the_environment(self, tmp_path: Path) -> None:
        env = _live_env(
            tmp_path,
            small_test=True,
            MEME_LIVE_AUTO_APPROVE="1",
            MEME_LIVE_AUTO_APPROVE_REFUSAL_COOLDOWN_S="30",
        )
        config, _, _ = boot(env, today=TODAY, system_kill_switch=KillSwitchState.ACTIVE)
        assert config.auto_approve_refusal_cooldown_s == 30.0
        off = _live_env(
            tmp_path,
            small_test=True,
            MEME_LIVE_AUTO_APPROVE="1",
            MEME_LIVE_AUTO_APPROVE_REFUSAL_COOLDOWN_S="0",
        )
        config, _, _ = boot(off, today=TODAY, system_kill_switch=KillSwitchState.ACTIVE)
        assert config.auto_approve_refusal_cooldown_s == 0.0
        assert refusal_window_start(NOW, config.auto_approve_refusal_cooldown_s) is None
        junk = _live_env(
            tmp_path,
            small_test=True,
            MEME_LIVE_AUTO_APPROVE="1",
            MEME_LIVE_AUTO_APPROVE_REFUSAL_COOLDOWN_S="-9",
        )
        config, _, _ = boot(junk, today=TODAY, system_kill_switch=KillSwitchState.ACTIVE)
        assert config.auto_approve_refusal_cooldown_s == 0.0, "never negative"

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
