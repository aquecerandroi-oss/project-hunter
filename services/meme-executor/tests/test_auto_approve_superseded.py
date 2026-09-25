"""T4.94 — stage 1 never opens a proposal on a tape the market already moved past.

R78 (``.claude/state/notes-R78.md`` §3.4 and "Achado fora do veredito";
``obsidian/11-KNOWLEDGE/KB-0158-recompra-sem-amostra-e-bundle-sem-filtro.md``,
"O que se aprendeu" 1): while op5 held a mint, op6's proposal for the same
mint was skipped ``mint_busy`` but left ``proposed`` for up to 60 s, and the
first pass after op5's target exit opened it **without re-reading the tape** —
007 (11.5 s old), BAGI (52.7 s) and ANT (53.8 s), all three lost. The quote,
flow and holders behind it predated the very move that made op5 exit.

Two rules, both pure and tabled here:

- a proposal whose mint was busy at a pass is **superseded**: the planner hands
  it back for a durable rejection (``mint_busy_superseded``), it is never a pick
  then or later, and the gate is free to propose the coin again on fresh data;
- no proposal older than ``MEME_LIVE_AUTO_APPROVE_MAX_AGE_S`` (default 10 s) is
  opened by the robot (``too_old``, left to the human as before). The real desk
  opened the 125 non-queued event-lane proposals (of 130) within 2.67 s of
  their tape (``.claude/state/r78/cache/pop.csv``); the five queued ones were
  11.5–53.8 s old.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_core.execution.meme.approval import AUTO_STAGE1_DECIDED_BY
from hunter_meme_executor.auto_approve import (
    AUTO_APPROVE_MAX_AGE_S,
    MINT_BUSY_SUPERSEDED,
    OperatorProposal,
    plan_auto_approvals,
    superseded_decision,
)
from hunter_meme_executor.config import boot

from .test_auto_approve import _live_env  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 25, 6, 18, 36, 730000, tzinfo=UTC)
TODAY = date(2026, 9, 16)
MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
OTHER = "2nG3hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump"
SUGGESTED: dict[str, Any] = {"size_sol": "0.05", "target_x": "3", "trailing_pct": "35"}


def _proposal(
    *, mint: str = MINT, age_s: float = 1.0, id: str = "01994d00-6c1a-7000-8000-000000000601"
) -> OperatorProposal:
    proposed_at = NOW - timedelta(seconds=age_s)
    return OperatorProposal(
        id=id,
        mint=mint,
        suggested=dict(SUGGESTED),
        proposed_at=proposed_at,
        expires_at=proposed_at + timedelta(seconds=180),
        rule_set_params={"max_sol_per_bet": "0.05"},
    )


def _plan(candidates: list[OperatorProposal], **overrides: Any) -> Any:
    kwargs: dict[str, Any] = {"now": NOW, "approved_last_hour": 0, "max_per_hour": 5}
    kwargs.update(overrides)
    return plan_auto_approvals(candidates, **kwargs)


class TestSuperseded:
    def test_a_proposal_seen_with_its_mint_busy_is_superseded_not_kept_waiting(self) -> None:
        """007 on 25/09/2026: op6's proposal born with op5's, op5 holding the mint."""
        op6 = _proposal()
        plan = _plan([op6], busy_mints=frozenset({MINT}))
        assert plan.picks == ()
        assert plan.superseded == (op6,)
        assert plan.skipped == {MINT_BUSY_SUPERSEDED: 1}
        assert MINT_BUSY_SUPERSEDED == "mint_busy_superseded"

    def test_the_superseded_rejection_is_the_robots_named_and_never_live(self) -> None:
        decided = superseded_decision(_proposal(), now=NOW)
        assert decided.status == "rejected"
        assert decided.mode == "paper", "it never became a live proposal"
        assert decided.decided_by == AUTO_STAGE1_DECIDED_BY
        assert decided.decided_at == NOW
        assert decided.decision is not None
        assert decided.decision["auto_refusal"] == MINT_BUSY_SUPERSEDED
        assert MINT_BUSY_SUPERSEDED in decided.decision["note"]

    def test_a_busy_mint_does_not_hide_a_fresh_one(self) -> None:
        busy, free = _proposal(), _proposal(mint=OTHER, id="01994d00-6c1a-7000-8000-000000000602")
        plan = _plan([busy, free], busy_mints=frozenset({MINT}))
        assert plan.picks == (free,) and plan.superseded == (busy,)

    def test_expired_and_too_old_keep_their_own_names(self) -> None:
        """Neither can ever be opened again anyway; the names stay what they were."""
        old = _plan([_proposal(age_s=AUTO_APPROVE_MAX_AGE_S + 1)], busy_mints=frozenset({MINT}))
        assert old.superseded == () and old.skipped == {"too_old": 1}

    def test_a_superseded_proposal_spends_no_slot_of_the_tick_or_the_hour(self) -> None:
        busy, free = _proposal(), _proposal(mint=OTHER, id="01994d00-6c1a-7000-8000-000000000602")
        plan = _plan([busy, free], busy_mints=frozenset({MINT}), approved_last_hour=4)
        assert plan.picks == (free,)


class TestFreshness:
    def test_the_default_bound_is_ten_seconds(self) -> None:
        assert AUTO_APPROVE_MAX_AGE_S == 10.0

    def test_a_fresh_proposal_is_opened(self) -> None:
        fresh = _proposal(age_s=2.67)  # the slowest non-queued real approval measured
        assert _plan([fresh]).picks == (fresh,)
        assert _plan([_proposal(age_s=10.0)]).picks != (), "the bound itself still passes"

    def test_an_older_proposal_is_refused_by_name(self) -> None:
        for age in (10.01, 11.52, 52.74, 53.84):  # 007, BAGI, ANT
            plan = _plan([_proposal(age_s=age)])
            assert plan.picks == () and plan.skipped == {"too_old": 1}, age

    def test_the_caller_sets_the_bound(self) -> None:
        assert _plan([_proposal(age_s=4)], max_age_s=3.0).skipped == {"too_old": 1}
        assert _plan([_proposal(age_s=4)], max_age_s=5.0).picks != ()


class TestMaxAgeConfig:
    def _boot(self, tmp_path: Path, **extra: str) -> float:
        env = _live_env(tmp_path, small_test=True, MEME_LIVE_AUTO_APPROVE="1", **extra)
        config, _, _ = boot(env, today=TODAY, system_kill_switch=KillSwitchState.ACTIVE)
        return config.auto_approve_max_age_s

    def test_default_and_override(self, tmp_path: Path) -> None:
        assert self._boot(tmp_path) == 10.0
        assert self._boot(tmp_path, MEME_LIVE_AUTO_APPROVE_MAX_AGE_S="5") == 5.0
        assert self._boot(tmp_path, MEME_LIVE_AUTO_APPROVE_MAX_AGE_S="60") == 60.0

    def test_an_unusable_value_falls_back_to_the_safe_default(self, tmp_path: Path) -> None:
        """``nan`` would compare false and switch the bound off; above 60 s it would
        reopen the old window; ``0``/negative would refuse every proposal silently."""
        for raw in ("nan", "inf", "-inf", "61", "0", "-3", "abc"):
            assert self._boot(tmp_path, MEME_LIVE_AUTO_APPROVE_MAX_AGE_S=raw) == 10.0, raw


class TestTemporalBusy:
    """Guardian review of T4.94, finding 1: "busy" is temporal, not observed.
    A pass that never *saw* the mint busy must still refuse a proposal the
    mint's activity has overtaken."""

    def test_scenario_a_a_sibling_of_this_passes_pick_is_superseded_not_tick_capped(
        self,
    ) -> None:
        """op5/op6 born on the same tape instant: op5 is picked, op6 must not wait
        as ``tick_cap`` for a tick 2 that may come after op5's target exit."""
        op5 = _proposal(id="01994d00-6c1a-7000-8000-000000000605")
        op6 = _proposal(id="01994d00-6c1a-7000-8000-000000000606")
        plan = _plan([op5, op6])
        assert plan.picks == (op5,)
        assert plan.siblings == (op6,)
        assert "tick_cap" not in plan.skipped and "mint_repeated" not in plan.skipped
        wide = _plan([op5, op6], max_per_tick=2)
        assert wide.picks == (op5,) and wide.siblings == (op6,)

    def test_scenario_b_a_proposal_the_mint_activity_overtook_is_superseded(self) -> None:
        """op6 born while op5 was open, op5 exited before any pass saw op6: the
        mint reads free now, but the rows say it was busy after op6 was born."""
        op6 = _proposal(age_s=3.5)
        plan = _plan([op6], superseded_ids=frozenset({op6.id}))
        assert plan.picks == () and plan.superseded == (op6,)
        assert plan.skipped == {MINT_BUSY_SUPERSEDED: 1}

    def test_a_mint_whose_activity_predates_the_proposal_is_opened(self) -> None:
        p = _proposal()
        assert _plan([p], superseded_ids=frozenset()).picks == (p,)


class TestTooOldPerLane:
    def test_too_old_is_also_counted_per_series(self) -> None:
        old = _proposal_with_series(12, "meme_features_15s_v1")
        plan = _plan([old, _proposal_with_series(11, None, id_suffix="2")])
        assert plan.skipped == {"too_old": 2, "too_old:meme_features_15s_v1": 1}


def _proposal_with_series(
    age_s: float, series: str | None, *, id_suffix: str = "1"
) -> OperatorProposal:
    proposed_at = NOW - timedelta(seconds=age_s)
    return OperatorProposal(
        id=f"01994d00-6c1a-7000-8000-00000000070{id_suffix}",
        mint=MINT,
        suggested=dict(SUGGESTED),
        proposed_at=proposed_at,
        expires_at=proposed_at + timedelta(seconds=180),
        rule_set_params={"max_sol_per_bet": "0.05"},
        series=series,
    )
