"""T4.16 — the honest scoreboard and the measured latency, without a database:
a close without a photo is ``indeterminate`` with its reason (the row keeps
its numbers), a priced close is ``measured``, the wallet's SQL sums measured
closes only, the fill delay is sampled from what the fill wrote, and the
heartbeat's percentiles are nearest-rank over that sample — empty is empty,
never zero."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_meme_worker import lab_repo_bets
from hunter_meme_worker.lab import LabState
from hunter_meme_worker.lab_heartbeat import heartbeat_fields, percentile
from hunter_meme_worker.lab_values import INDETERMINATE, MEASURED, NO_SNAPSHOT_IN_WINDOW
from hunter_meme_worker.paper_engine import close_bet, close_without_snapshot

from .test_paper_engine import T0, _bet, _snapshot  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.unit


def test_a_close_without_a_photo_is_indeterminate_and_keeps_its_numbers() -> None:
    bet = _bet()
    exit_ = close_without_snapshot(bet, now=T0 + timedelta(minutes=5), pending_reason="target")
    assert exit_.exit["reason"] == "rug_no_snapshot" and exit_.exit["pending_reason"] == "target"
    assert exit_.outcome_quality == INDETERMINATE
    assert exit_.outcome_quality_reason == NO_SNAPSHOT_IN_WINDOW
    assert exit_.exit["outcome_quality"] == INDETERMINATE
    assert exit_.pnl_sol == -bet.sol_spent and exit_.r_multiple == Decimal(-1), (
        "the row keeps the doctrine's number; the sums are what change"
    )
    priced = close_bet(
        bet, _snapshot(120, "40", "804000000"), "target", None, intent_snapshot_at=None
    )
    assert priced.outcome_quality == MEASURED and priced.outcome_quality_reason is None
    assert "outcome_quality" not in priced.exit


def test_the_wallet_and_the_close_write_the_quality_in_sql() -> None:
    wallet = str(lab_repo_bets._WALLET)  # pyright: ignore[reportPrivateUsage]
    assert wallet.count("outcome_quality = 'measured'") == 2, "realized total and today, both"
    assert "sum(initial_risk_sol) FILTER (WHERE status = 'open')" in wallet, (
        "open exposure is every open bet — quality is a property of a close"
    )
    close = str(lab_repo_bets._CLOSE_BET)  # pyright: ignore[reportPrivateUsage]
    assert "outcome_quality = :outcome_quality" in close
    assert "outcome_quality_at = :outcome_quality_at" in close, (
        "bound on its own: a CASE sharing :exit_at makes asyncpg deduce text for it"
    )


def test_percentiles_are_nearest_rank_and_an_empty_sample_is_unknown() -> None:
    assert percentile([], 0.5) is None
    assert percentile([27], 0.5) == 27 and percentile([27], 0.95) == 27
    assert percentile([5, 148, 27, 30, 12], 0.5) == 27
    assert percentile([5, 148, 27, 30, 12], 0.95) == 148
    assert (
        percentile(list(range(1, 101)), 0.95) == 95 and percentile(list(range(1, 101)), 0.5) == 50
    )


def test_the_heartbeat_measures_the_fill_delay_and_counts_the_indeterminate() -> None:
    state = LabState()
    fields = heartbeat_fields(state)
    assert fields["lab_decision_to_fill_s_p50"] == "" and fields["lab_decision_to_fill_n"] == "0"
    assert fields["lab_bets_indeterminate_total"] == "" and fields["lab_fast_last_as_of"] == ""
    for seconds in (5, 148, 27, 30, 12):
        state.record_fill_delay(seconds)
    state.bets_indeterminate_total = 5
    state.fast_rows_evaluated = 40
    state.fast_proposals_total = 2
    fields = heartbeat_fields(state)
    assert (fields["lab_decision_to_fill_s_p50"], fields["lab_decision_to_fill_s_p95"]) == (
        "27",
        "148",
    ), "the study's own numbers: median 27 s, worst 148 s"
    assert fields["lab_decision_to_fill_n"] == "5" and fields["lab_bets_indeterminate_total"] == "5"
    assert (fields["lab_fast_rows_evaluated"], fields["lab_fast_proposals_total"]) == ("40", "2")
    for seconds in range(300):
        state.record_fill_delay(seconds)
    assert len(state.fill_delays) == 200, "a bounded sample of the most recent fills"
