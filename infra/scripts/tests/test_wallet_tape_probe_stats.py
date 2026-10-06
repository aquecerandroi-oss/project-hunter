"""Unit tests for ``infra/scripts/wallet_tape_probe_stats.py`` — the aggregator of the wave-0 probe.

Offline, clock injected (every call passes ``now`` as epoch seconds).

Run:
    uv run --no-sync pytest infra/scripts/tests/test_wallet_tape_probe_stats.py -q
"""

from __future__ import annotations

import base64
import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from wallet_tape_probe_core import AMM, PUMP  # noqa: E402
from wallet_tape_probe_math import Hist, heaps_fit, row_estimates  # noqa: E402
from wallet_tape_probe_stats import ProbeStats  # noqa: E402

FIX = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures"
T0 = 1_791_217_470.0  # the epoch second inside the fixtures' own event timestamps


def _logs(path: str) -> list[str]:
    raw: Any = json.loads((FIX / path).read_text())
    return list(raw.get("result", raw)["meta"]["logMessages"])


def _data(disc: bytes, body: bytes = b"") -> str:
    return "Program data: " + base64.b64encode(disc + body).decode()


def test_a_tx_on_both_subscriptions_counts_one_tx_and_events_once() -> None:
    s = ProbeStats(T0)
    logs = _logs("pumpswap/t48f_rpc_amm_tx_nocreator_2bYPbC8hziYA_raw.json")
    s.on_logs("amm", 10, "SIG1", None, logs, 5000, T0 + 1)
    s.on_logs("pump", 10, "SIG1", None, logs, 5000, T0 + 2)
    s.flush(T0 + 400)
    snap = s.snapshot(T0 + 200)
    assert snap["tx"]["unique"] == 1
    assert snap["events"]["pAMM.SellEvent"]["n"] == 1
    assert snap["events"]["pAMM.BuyEvent"]["n"] == 1
    assert snap["events"]["pAMM.SellEvent"]["decoded_ok"] == 1
    assert snap["events"]["pAMM.BuyEvent"]["not_attempted_raw"] == 1


def test_a_tx_that_invokes_both_programs_but_arrives_once_is_a_delivery_miss() -> None:
    s = ProbeStats(T0)
    both = [
        f"Program {PUMP} invoke [1]",
        f"Program {PUMP} success",
        f"Program {AMM} invoke [1]",
        f"Program {AMM} success",
    ]
    s.on_logs("pump", 1, "A", None, both, 100, T0)
    s.on_logs("pump", 1, "B", None, both, 100, T0)
    s.on_logs("amm", 1, "B", None, both, 100, T0 + 0.5)
    s.flush(T0 + 400)
    d = s.snapshot(T0 + 100)["delivery_both_programs"]
    assert d == {"expected": 2, "delivered_by_both": 1, "only_pump": 1, "only_amm": 0}
    assert s.snapshot(T0 + 100)["tx"]["both_programs"] == 2


def test_failed_tx_is_counted_and_yields_no_event() -> None:
    s = ProbeStats(T0)
    logs = _logs("pumpswap/t48e_rpc_amm_tx_5mrYZLam93Kd_raw.json")
    s.on_logs("amm", 3, "F", {"InstructionError": [0, {"Custom": 6}]}, logs, 100, T0)
    snap = s.snapshot(T0)
    assert snap["notifications"]["amm"]["failed"] == 1
    assert snap["events"] == {}
    assert snap["tx"]["failed"] == 1


def test_undecodable_trade_event_is_counted_with_its_reason() -> None:
    s = ProbeStats(T0)
    logs = [
        f"Program {PUMP} invoke [1]",
        _data(bytes.fromhex("bddb7fd34ee661ee"), b"\x01" * 10),
        f"Program {PUMP} success",
    ]
    s.on_logs("pump", 1, "U", None, logs, 100, T0)
    ev = s.snapshot(T0)["events"]["pump.TradeEvent"]
    assert ev["decode_failed"] == 1 and ev["decoded_ok"] == 0
    assert any("truncated" in r.lower() for r in ev["failure_reasons"])
    assert len(s.undecodable_samples) == 1


def test_liquidity_without_swap_is_separated_from_liquidity_with_a_swap() -> None:
    s = ProbeStats(T0)
    dep = bytes.fromhex("78f83d531f8e6b90")
    only = [
        f"Program {AMM} invoke [1]",
        "Program log: Instruction: Deposit",
        _data(dep, b"\x00" * 40),
        f"Program {AMM} success",
    ]
    both = [
        f"Program {AMM} invoke [1]",
        "Program log: Instruction: Deposit",
        _data(dep, b"\x00" * 40),
        f"Program {AMM} success",
        f"Program {AMM} invoke [1]",
        "Program log: Instruction: Buy",
        f"Program {AMM} success",
    ]
    s.on_logs("amm", 1, "L1", None, only, 100, T0)
    s.on_logs("amm", 1, "L2", None, both, 100, T0)
    liq = s.snapshot(T0)["liquidity"]
    assert liq["tx_without_swap_instruction"] == 1
    assert liq["tx_with_swap_instruction"] == 1
    assert liq["instructions"] == {"Deposit": 2}


def test_silence_longer_than_the_threshold_is_recorded_as_a_gap() -> None:
    s = ProbeStats(T0)
    s.on_logs("pump", 1, "a", None, [], 10, T0)
    s.on_logs("pump", 2, "b", None, [], 10, T0 + 7.5)
    gaps = s.snapshot(T0 + 8)["silence_gaps"]["pump"]
    assert gaps["n"] == 1 and gaps["max_s"] == pytest.approx(7.5)


def test_slot_lag_uses_the_latest_slot_seen_on_the_same_connection() -> None:
    s = ProbeStats(T0)
    s.on_slot("pump", 1000, T0)
    s.on_logs("pump", 997, "x", None, [], 10, T0 + 0.1)
    lag = s.snapshot(T0 + 1)["lag_slots_ws_slotsubscribe_same_pipe_NOT_independent"]["pump"]
    assert lag["n"] == 1 and lag["p50"] == 3


def test_reconnect_records_the_slot_span_that_was_not_seen() -> None:
    s = ProbeStats(T0)
    s.on_logs("pump", 100, "a", None, [], 10, T0)
    s.on_disconnect("pump", T0 + 1, "closed")
    s.on_connect("pump", T0 + 5)
    s.on_logs("pump", 112, "b", None, [], 10, T0 + 6)
    rc = s.snapshot(T0 + 7)["reconnects"]["pump"]
    assert rc["disconnects"] == 1 and rc["gap_slots_total"] == 12
    assert rc["downtime_s"] == pytest.approx(5.0)


def test_hist_percentiles() -> None:
    h = Hist()
    for x in range(1, 101):
        h.add(x)
    assert h.n == 100
    assert h.pct(50) == 50 and h.pct(99) == 99 and h.pct(100) == 100


def test_heaps_fit_recovers_a_power_law() -> None:
    pts: list[tuple[float, float]] = [
        (n, 3.0 * n**0.8) for n in (1_000, 5_000, 20_000, 80_000, 300_000)
    ]
    k, beta = heaps_fit(pts)
    assert math.isclose(beta, 0.8, abs_tol=1e-6) and math.isclose(k, 3.0, rel_tol=1e-6)


def test_row_estimates_are_positive_and_labelled() -> None:
    row = {"signature": "s" * 88, "wallet": "w" * 44, "mint": "m" * 44, "slot": 452_000_000}
    est = row_estimates(row)
    assert est["json_bytes"] > 150 and est["pg_heap_bytes"] > 100
    assert est["pg_with_indexes_bytes"] > est["pg_heap_bytes"]


def test_independent_slot_lag_compares_an_http_tip_with_the_last_notified_slot() -> None:
    """The websocket's own slotSubscribe rides the same pipe as the logs, so it cannot see a delay
    in that pipe; an HTTP ``getSlot`` can."""
    s = ProbeStats(T0)
    s.on_logs("pump", 100, "a", None, [], 10, T0)
    s.on_logs("amm", 98, "b", None, [], 10, T0)
    s.on_http_tip(103, T0 + 1)
    lag = s.snapshot(T0 + 2)["lag_slots_vs_http_tip"]
    assert lag["pump"]["p50"] == 3 and lag["amm"]["p50"] == 5


def test_downtime_runs_until_the_first_log_and_includes_an_open_outage() -> None:
    s = ProbeStats(T0)
    s.on_connect("pump", T0 + 1)  # socket up, but nothing subscribed/flowing yet
    assert s.snapshot(T0 + 11)["reconnects"]["pump"]["downtime_s_incl_open"] == pytest.approx(11)
    s.on_logs("pump", 100, "a", None, [], 10, T0 + 12)
    s.on_disconnect("pump", T0 + 20, "closed")  # run ends while disconnected
    rc = s.snapshot(T0 + 50)["reconnects"]["pump"]
    assert rc["downtime_s"] == pytest.approx(12)
    assert rc["downtime_s_incl_open"] == pytest.approx(42)


def test_http_tip_lag_uses_the_max_slot_received_and_keeps_negative_values() -> None:
    s = ProbeStats(T0)
    s.on_logs("pump", 100, "a", None, [], 10, T0)
    s.on_logs("pump", 90, "b", None, [], 10, T0 + 0.1)  # an old log arriving late
    s.on_http_tip(103, T0 + 1)
    s.on_http_tip(99, T0 + 2)  # the HTTP node is momentarily behind the websocket one
    lag = s.snapshot(T0 + 3)["lag_slots_vs_http_tip"]["pump"]
    assert lag["n"] == 2 and lag["max"] == 3
    assert s.lag_http["pump"].pct(1) == -1


def test_observations_are_kept_in_named_histograms() -> None:
    s = ProbeStats(T0)
    s.observe("queue_age_s.pump", 0.3, 0.1)
    s.observe("queue_age_s.pump", 0.5, 0.1)
    assert s.snapshot(T0)["observations"]["queue_age_s.pump"]["n"] == 2


def test_age_of_the_last_log_is_sampled_at_each_http_poll() -> None:
    s = ProbeStats(T0)
    s.on_logs("amm", 100, "a", None, [], 10, T0)
    s.on_http_tip(101, T0 + 4)
    assert s.snapshot(T0 + 5)["age_of_last_log_s_at_poll"]["amm"]["p50"] == 4.0


def test_a_wall_clock_jump_between_ticks_is_recorded_as_a_suspension() -> None:
    """The first 2 h run froze for 4 651 s when the machine slept (05/10): the counters kept
    wall time but no data. A tick that arrives far later than its cadence marks the run."""
    s = ProbeStats(T0)
    s.on_tick(T0 + 5, 5.0)
    s.on_tick(T0 + 10, 5.0)
    s.on_tick(T0 + 4661, 5.0)  # the lid was closed
    snap = s.snapshot(T0 + 4662)
    assert snap["suspensions"] == [{"at_elapsed_s": 4661.0, "gap_s": 4651.0}]


def test_size_bins_and_wallet_concentration_describe_what_an_ingest_filter_would_drop() -> None:
    s = ProbeStats(T0)
    logs = _logs("pumpswap/t48f_rpc_amm_tx_nocreator_2bYPbC8hziYA_raw.json")  # one Sell + one Buy
    for i in range(3):
        s.on_logs("amm", 10, f"S{i}", None, logs, 100, T0 + i)  # the same wallets, three txs
    snap = s.snapshot(T0 + 5)
    # The decoded Sell carries an amount, but a log line has no accounts: the pool's quote mint is
    # unknown, so it is NOT binned as SOL (wave 1b: WSOL-base pools make it atoms of another token).
    assert sum(snap["size_bins_sol"].values()) == 0
    assert snap["size_unverified_quote"] == 3  # counted apart: the denominator stays honest
    conc = s.wallet_concentration()
    assert (
        sum(b["wallets"] for b in conc.values()) == 2
    )  # the Sell wallet and the inferred Buy wallet
    assert conc["5-19"]["events"] == 0 and conc["2-4"]["events"] == 6


def test_failed_reconnect_attempts_do_not_reset_the_start_of_the_outage() -> None:
    """Astra (wallet-tape-probe-results, must-fix 3): down at 10, a retry fails at 20, first log at 30
    is a 20 s outage, not 10."""
    s = ProbeStats(T0)
    s.on_logs("pump", 100, "a", None, [], 10, T0)
    s.on_disconnect("pump", T0 + 10, "closed")
    s.on_disconnect("pump", T0 + 20, "connect failed")
    s.on_connect("pump", T0 + 25)
    s.on_logs("pump", 150, "b", None, [], 10, T0 + 30)
    rc = s.snapshot(T0 + 31)["reconnects"]["pump"]
    assert rc["downtime_s"] == pytest.approx(20.0)
    assert rc["disconnects"] == 2


def test_an_outage_that_spans_the_window_taints_it_even_if_it_ended_before_the_judgement() -> None:
    """must-fix 4: outage [10, 300], block fetched at 200, judged at 380 -> tainted (interval overlap)."""
    s = ProbeStats(T0)
    s.on_logs("amm", 100, "a", None, [], 10, T0)
    s.on_disconnect("amm", T0 + 10, "closed")
    s.on_connect("amm", T0 + 12)
    s.on_logs("amm", 900, "b", None, [], 10, T0 + 300)
    assert s.outage_overlaps(T0 + 140, T0 + 380) is True  # fetch 200 - 60 s margin = 140
    assert s.outage_overlaps(T0 + 301, T0 + 380) is False
    assert s.outage_overlaps(T0 - 50, T0 - 10) is False


def test_a_late_second_copy_inside_the_dedupe_window_is_not_a_new_tx() -> None:
    """must-fix 5: a both-program tx whose second copy arrives 200 s late is still the same tx."""
    s = ProbeStats(T0)
    logs = [f"Program {PUMP} invoke [1]", f"Program {PUMP} success"]
    s.on_logs("pump", 1, "SAME", None, logs, 10, T0)
    for i in range(40):  # unrelated traffic drives the eviction clock
        s.on_logs("pump", 2 + i, f"x{i}", None, [], 10, T0 + 5 * i)
    s.on_logs("amm", 1, "SAME", None, logs, 10, T0 + 200)
    assert s.snapshot(T0 + 201)["tx"]["unique"] == 41


def test_row_estimate_counts_each_physical_column_once() -> None:
    """must-fix 6: signature(88)+wallet(44)+mint(44) texts, bigints, and the six fixed columns once."""
    row = {
        "block_time": 1, "slot": 2, "signature": "s" * 88, "program": "pump", "event_ordinal": 0,
        "wallet": "w" * 44, "mint": "m" * 44, "venue": "pump", "side": "buy",
        "sol_lamports": 5, "token_amount": 6, "fee_lamports": 7, "received_at": "x" * 32,
    }  # fmt: skip
    est = row_estimates(row)
    # 24 header + fixed (block_time 8 + received_at 8 + program 2 + ordinal 2 + venue 2 + side 1)
    # + slot 8 + signature 89 + wallet 45 + mint 45 + 3 bigints 24
    assert est["pg_heap_bytes"] == 24 + 23 + 8 + 89 + 45 + 45 + 24
