"""Unit tests for ``infra/scripts/pumpfun_rt_probe_stats.py`` and ``pumpfun_rt_probe_logs.py`` (the pure half
of the pump.fun realtime latency probe, 2026-10-06). Offline: synthetic events and the committed
``hunter_exchanges`` ``getTransaction`` fixtures (their ``meta.logMessages`` are what ``logsSubscribe`` carries).

Run:
    uv run --no-sync pytest infra/scripts/tests/test_pumpfun_rt_probe_stats.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:  # the layout every script in this folder uses
    sys.path.insert(0, str(SCRIPTS_DIR))

from pumpfun_rt_probe_logs import logs_fact  # noqa: E402  (path surgery must come first)
from pumpfun_rt_probe_stats import (  # noqa: E402
    describe,
    drop_stalls,
    first_seen,
    pair_report,
    percentile,
    union_coverage,
)

FIX = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"


def _tx(name: str) -> tuple[str, int, list[str]]:
    raw: Any = json.loads((FIX / name).read_text())
    r = raw.get("result", raw)
    return r["transaction"]["signatures"][0], r["slot"], list(r["meta"]["logMessages"])


def ev(src: str, kind: str, id_: str, t: float, **extra: Any) -> dict[str, Any]:
    return {"s": src, "k": kind, "id": id_, "t": t, **extra}


# --- percentiles -----------------------------------------------------------------------------


def test_percentile_interpolates_linearly_and_handles_edges() -> None:
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(xs, 0.5) == 3.0
    assert percentile(xs, 0.0) == 1.0 and percentile(xs, 1.0) == 5.0
    assert percentile(xs, 0.25) == 2.0
    assert percentile([7.0], 0.9) == 7.0
    assert percentile([], 0.5) is None


def test_describe_reports_n_and_the_three_quantiles_unsorted_input() -> None:
    d = describe([5.0, 1.0, 3.0, 2.0, 4.0])
    assert d == {"n": 5, "p10": pytest.approx(1.4), "p50": 3.0, "p90": pytest.approx(4.6)}
    assert describe([]) == {"n": 0, "p10": None, "p50": None, "p90": None}


# --- first_seen / windows ---------------------------------------------------------------------


def test_first_seen_keeps_the_earliest_arrival_per_id_and_filters_by_window() -> None:
    events = [
        ev("a", "create", "s1", 10.5),
        ev("a", "create", "s1", 10.2),  # a duplicate frame: the first arrival wins
        ev("a", "create", "s2", 99.0),  # outside the window
        ev("a", "trade", "s1", 11.0),  # another kind
        ev("b", "create", "s1", 10.9),  # another source
    ]
    got = first_seen(events, "a", "create", t0=10.0, t1=20.0)
    assert got == {"s1": 10.2}


def test_drop_stalls_removes_events_that_landed_inside_a_loop_stall() -> None:
    events = [ev("a", "x", "1", 5.0), ev("a", "x", "2", 12.0), ev("a", "x", "3", 30.0)]
    kept = drop_stalls(events, [(10.0, 20.0)])
    assert [e["id"] for e in kept] == ["1", "3"]


# --- pair_report ------------------------------------------------------------------------------


def test_pair_report_positive_delta_means_the_first_source_is_later() -> None:
    a = {"s1": 10.5, "s2": 20.8, "s3": 31.0}  # e.g. logsSubscribe
    b = {"s1": 10.0, "s2": 21.0, "s4": 40.0}  # e.g. NATS
    rep = pair_report(a, b)
    assert rep["common"] == 2 and rep["only_a"] == 1 and rep["only_b"] == 1
    assert rep["delta_s"]["n"] == 2
    # deltas are +0.5 (a later) and -0.2 (a earlier)
    assert rep["delta_s"]["p50"] == pytest.approx(0.15)
    assert rep["a_first_share"] == pytest.approx(0.5)


def test_pair_report_with_no_overlap_says_so_instead_of_dividing_by_zero() -> None:
    rep = pair_report({"x": 1.0}, {"y": 2.0})
    assert rep["common"] == 0 and rep["a_first_share"] is None and rep["delta_s"]["n"] == 0


def test_union_coverage_counts_each_source_against_the_union() -> None:
    seen = {"nats": {"s1": 1.0, "s2": 1.0}, "logs": {"s1": 1.0, "s3": 1.0}, "pp": {"s1": 1.0}}
    cov = union_coverage(seen)
    assert cov["union"] == 3
    assert cov["by_source"]["nats"] == {"seen": 2, "share": pytest.approx(2 / 3)}
    assert cov["by_source"]["pp"] == {"seen": 1, "share": pytest.approx(1 / 3)}
    assert cov["in_all"] == 1


# --- logs_fact --------------------------------------------------------------------------------


def test_logs_fact_flags_a_pump_create_and_a_completed_curve() -> None:
    sig, slot, logs = _tx("t1b_rpc_pump_create_buy_completes_curve_43xbmthGPT_raw.json")
    fact = logs_fact(sig, slot, None, logs)
    assert fact["id"] == sig and fact["slot"] == slot
    assert fact["create"] is True and fact["complete"] is True
    assert fact["mints"] == ["Bm7Uxam9efqL8gu9CX5kZ3A7t5nj2v2titSC7nnpump"]


def test_logs_fact_reads_the_mint_of_a_plain_trade_and_no_create() -> None:
    sig, slot, logs = _tx("t48e_rpc_tx_buy_2qnMHiEaNfxX_raw.json")
    fact = logs_fact(sig, slot, None, logs)
    assert fact["create"] is False and fact["complete"] is False
    assert len(fact["mints"]) == 1 and fact["mints"][0].startswith("2AxC4pN9")


def test_logs_fact_marks_a_failed_transaction() -> None:
    sig, slot, logs = _tx("t48e_rpc_tx_buy_2qnMHiEaNfxX_raw.json")
    assert logs_fact(sig, slot, {"InstructionError": [0, "Custom"]}, logs)["err"] is True


def test_logs_fact_survives_empty_logs() -> None:
    fact = logs_fact("sigX", 5, None, [])
    assert fact["create"] is False and fact["mints"] == [] and fact["err"] is False


def test_pair_report_counts_a_difference_under_ten_milliseconds_as_a_tie() -> None:
    a = {"x": 10.000, "y": 20.0, "z": 30.0}
    b = {"x": 10.004, "y": 19.8, "z": 30.3}  # deltas -0.004 (tie), +0.2 (b first), -0.3 (a first)
    rep = pair_report(a, b)
    assert rep["tie_share"] == pytest.approx(1 / 3)
    assert rep["a_first_share"] == pytest.approx(1 / 3)
    assert rep["b_first_share"] == pytest.approx(1 / 3)
