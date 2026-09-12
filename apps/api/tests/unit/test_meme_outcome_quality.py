# pyright: reportPrivateUsage=false
"""T4.16 on the API, without a database: the day's totals leave the
indeterminate closes out and count them apart, the row carries the brief's
label, the desk's ``BetOut`` shows ``decision_to_fill_s`` and the quality,
``/meme/sources`` carries the fast-lane and measured-latency fields, and the
scoreboard row carries ``indeterminate``."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_api.repositories.meme_desk_quality import IndeterminateTotals
from hunter_api.repositories.meme_desk_rows import DeskRow
from hunter_api.repositories.meme_lab import DayScoreRow
from hunter_api.repositories.meme_tests import BetRecord, DayTotalsRow
from hunter_api.schemas.meme_tests import OUTCOME_QUALITY_PT
from hunter_api.services.meme_desk_out import build_desk_row_out
from hunter_api.services.meme_lab import day_score_out
from hunter_api.services.meme_sources import build_meme_sources
from hunter_api.services.meme_tests import build_test_row, build_totals, outcome_quality_label

from .test_meme_desk_service import _bet as _desk_bet  # pyright: ignore[reportPrivateUsage]
from .test_meme_desk_service import _proposal as _desk_proposal
from .test_meme_desk_service import _rule_set as _desk_rule_set
from .test_meme_tests_service import _bet, _proposal, _rule_set

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)


def test_the_totals_leave_the_indeterminate_closes_out_and_count_them_apart() -> None:
    day = DayTotalsRow(
        bets=21,
        closed=21,
        open=0,
        wins=1,
        losses=20,
        pnl_sol=Decimal("-0.3835"),
        provisional_pnl_sol=Decimal(0),
        pnl_usd=Decimal("-38.35"),
        unpriced_usd=5,
        r_sum=Decimal("-7.67"),
    )
    indeterminate = IndeterminateTotals(
        bets=5,
        wins=0,
        losses=5,
        pnl_sol=Decimal("-0.25"),
        r_sum=Decimal("-5"),
        pnl_usd=None,
        unpriced_usd=5,
    )
    out = build_totals(day, real_rows=0, indeterminate=indeterminate)
    assert (out.bets, out.closed, out.indeterminate) == (21, 21, 5)
    assert (out.wins, out.losses) == (1, 15), "the 12/09 study: 16 measured, 1 win"
    assert out.pnl_sol == Decimal("-0.1335") and out.r_sum == Decimal("-2.67")
    assert out.unpriced_usd == 0 and out.pnl_usd == Decimal("-38.35"), (
        "the artefacts had no exit quote: the US$ sum did not include them"
    )
    below_0030 = build_totals(day, real_rows=0, indeterminate=None)
    assert below_0030.indeterminate == 0 and below_0030.r_sum == Decimal("-7.67")


def test_the_row_carries_the_quality_and_its_label() -> None:
    assert OUTCOME_QUALITY_PT["indeterminate"] == "indeterminado (sem fotografia)"
    assert outcome_quality_label(None) is None and outcome_quality_label("measured") == "medido"
    assert outcome_quality_label("guess") == "qualidade não registrada"
    bet = _bet(
        status="closed",
        exit={"reason": "rug_no_snapshot", "pending_reason": "target", "sol_received": "0"},
        outcome_quality="indeterminate",
        outcome_quality_reason="no_snapshot_in_window",
    )
    row = build_test_row(
        BetRecord(bet=bet, proposal=_proposal(), token=None, rule_set=_rule_set()), None
    )
    assert row.outcome_quality == "indeterminate"
    assert row.outcome_quality_label == "indeterminado (sem fotografia)"
    assert row.outcome_quality_reason == "no_snapshot_in_window"
    older = build_test_row(
        BetRecord(bet=_bet(), proposal=_proposal(), token=None, rule_set=_rule_set()), None
    )
    assert older.outcome_quality is None and older.outcome_quality_label is None


def test_the_desk_shows_the_measured_fill_delay_and_the_quality() -> None:
    rule_set = _desk_rule_set()
    proposal = _desk_proposal(rule_set)
    entry = {"sol_spent": "0.05", "fee_sol": "0.0009", "tokens": "1000", "decision_to_fill_s": 4}
    filled = _desk_bet(rule_set, proposal.id, entry=entry, outcome_quality="measured")
    out = build_desk_row_out(
        DeskRow(proposal=proposal, token=None, bet=filled, rule_set=rule_set, rank=0)
    )
    assert out.bet is not None
    assert out.bet.decision_to_fill_s == 4 and out.bet.outcome_quality == "measured"
    assert out.bet.outcome_quality_reason is None
    older = _desk_bet(rule_set, proposal.id)
    out = build_desk_row_out(
        DeskRow(proposal=proposal, token=None, bet=older, rule_set=rule_set, rank=0)
    )
    assert out.bet is not None and out.bet.decision_to_fill_s is None
    assert out.bet.outcome_quality is None, "a row mapped without the 0030 columns"


def test_the_sources_payload_carries_the_fast_lane_and_the_measured_latency() -> None:
    heartbeat = {
        "ts": AS_OF.isoformat(),
        "sources_at": (AS_OF - timedelta(seconds=5)).isoformat(),
        "sources": json.dumps({}),
        "fast_lane_mints": "7",
        "fast_lane_reads_60s": "26",
        "fast_lane_calls_60s": "8",
        "fast_lane_cycle_s": "0.412",
        "lab_decision_to_fill_s_p50": "4",
        "lab_decision_to_fill_s_p95": "19",
        "lab_decision_to_fill_n": "12",
        "lab_bets_indeterminate_total": "5",
    }
    out = build_meme_sources(heartbeat, {}, as_of=AS_OF, heartbeat_key="hb:meme:radar")
    assert (out.fast_lane_mints, out.fast_lane_reads_60s, out.fast_lane_calls_60s) == (7, 26, 8)
    assert out.fast_lane_cycle_s == 0.412
    assert (out.lab_decision_to_fill_s_p50, out.lab_decision_to_fill_s_p95) == (4, 19)
    assert out.lab_decision_to_fill_n == 12 and out.lab_bets_indeterminate_total == 5
    older = build_meme_sources(
        {"ts": AS_OF.isoformat(), "sources_at": AS_OF.isoformat(), "sources": "{}"},
        {},
        as_of=AS_OF,
        heartbeat_key="hb:meme:radar",
    )
    assert older.fast_lane_mints is None and older.lab_decision_to_fill_s_p50 is None


def test_the_scoreboard_row_counts_the_indeterminate_apart() -> None:
    row = DayScoreRow(
        rule_set_id="01994d00-6c1a-7000-8000-000000000001",
        day=AS_OF.date(),
        bets=21,
        closed=21,
        wins=1,
        pnl_sol=Decimal("-0.1335"),
        pnl_usd=None,
        unpriced_usd=0,
        r_sum=Decimal("-2.67"),
        max_drawdown_sol=Decimal("0.2"),
        rugs=5,
        indeterminate=5,
    )
    out = day_score_out(row)
    assert out.indeterminate == 5 and out.rugs == 5 and out.r_sum.value == Decimal("-2.67")
    below_0030 = DayScoreRow(
        rule_set_id=row.rule_set_id,
        day=row.day,
        bets=1,
        closed=1,
        wins=0,
        pnl_sol=None,
        pnl_usd=None,
        unpriced_usd=0,
        r_sum=None,
        max_drawdown_sol=None,
        rugs=0,
    )
    assert day_score_out(below_0030).indeterminate == 0, "an older board: none counted, not unknown"
