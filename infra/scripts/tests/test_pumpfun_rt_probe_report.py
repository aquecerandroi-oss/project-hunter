"""Unit tests for ``infra/scripts/pumpfun_rt_probe_report.py`` and ``pumpfun_rt_probe_trades.py`` — the
analysis of a pump.fun realtime latency capture (2026-10-06). Offline: tiny synthetic captures whose answer
is known by construction. The trade cases encode what Astra's review of the instrument found (program
mix, reconnects rewriting exposure, edge asymmetry, signature vs leg).

Run:
    uv run --no-sync pytest infra/scripts/tests/test_pumpfun_rt_probe_report.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:  # the layout every script in this folder uses
    sys.path.insert(0, str(SCRIPTS_DIR))

from pumpfun_rt_probe_report import analyze  # noqa: E402  (path surgery must come first)

META: dict[str, Any] = {"started": 0.0, "ended": 1000.0, "stalls": []}
PROC = "unifiedTradeEvent.processed."
BAL = "account_balance_change."


def ev(s: str, k: str, id_: str, t: float, **x: Any) -> dict[str, Any]:
    return {"s": s, "k": k, "id": id_, "t": t, **x}


def _creates() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [ev("clock", "sample", "c1", 150.0, offset=0.1, rtt=0.2)]
    for i, base in enumerate((200.0, 300.0, 400.0)):
        sig, mint = f"S{i}", f"M{i}"
        out += [
            ev(
                "nats_u",
                "create",
                sig,
                base,
                mint=mint,
                program="pump",
                slot=1000 + i,
                bt=base - 0.5,
            ),
            ev("pp", "create", sig, base + 0.1, mint=mint, pool="pump"),
            ev("rpc", "logs", sig, base + 0.15, slot=1000 + i, create=True),
            ev("tr_new", "add", mint, base + 0.5, entry={"pg": "pump", "kol": i % 2}),
        ]
    # noise that must not count: another launchpad, a create before the warm-up, a duplicate frame
    out += [
        ev("pp", "create", "SB", 210.0, mint="MB", pool="bonk"),
        ev("nats_u", "create", "SEARLY", 10.0, mint="ME", program="pump"),
        ev("nats_u", "create", "S0", 200.3, mint="M0", program="pump"),
    ]
    return out


def test_creation_deltas_are_taken_per_signature_and_positive_means_later_than_nats() -> None:
    rep = analyze(_creates(), META, {})
    c = rep["create"]
    assert c["coverage"]["union"] == 3
    assert c["coverage"]["by_source"]["nats_u"]["seen"] == 3
    assert c["pairs"]["pp_vs_nats"]["delta_s"]["p50"] == pytest.approx(0.1)
    assert c["pairs"]["rpc_vs_nats"]["delta_s"]["p50"] == pytest.approx(0.15)
    assert c["pairs"]["rpc_vs_pp"]["delta_s"]["p50"] == pytest.approx(0.05)
    assert c["pairs"]["pp_vs_nats"]["a_first_share"] == 0.0
    assert c["pairs"]["pp_vs_nats"]["b_first_share"] == 1.0
    assert c["pairs"]["tr_new_vs_nats"]["delta_s"]["p50"] == pytest.approx(0.5)  # by mint


def test_events_inside_a_stall_are_removed_before_any_delta() -> None:
    meta = {**META, "stalls": [(299.0, 301.0)]}
    rep = analyze(_creates(), meta, {})
    assert rep["create"]["coverage"]["union"] == 2


def test_an_empty_analysis_window_is_refused_instead_of_reporting_zeros() -> None:
    with pytest.raises(ValueError, match="window"):
        analyze(_creates(), {"started": 0.0, "ended": 100.0, "stalls": []}, {})


def test_clock_offset_is_the_median_of_the_server_time_samples() -> None:
    rep = analyze(_creates(), META, {})
    assert rep["clock"]["offset_s"] == pytest.approx(0.1) and rep["clock"]["samples"] == 1


def test_kol_at_add_and_later_kol_updates_are_counted() -> None:
    evs = _creates() + [ev("tr_new", "kol", "M0", 215.0, kol=2)]
    k = analyze(evs, META, {})["kol"]
    assert k["adds_pump"] == 3 and k["kol_gt0_at_add"] == 1
    assert k["kol_update_delay_s"]["p50"] == pytest.approx(14.5)  # M0 was added at 200.5


def _trade(sig: str, t: float, *, mint: str = "M1", user: str = "W1", **x: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {"program": "pump", "slot": 2000, "bt": t - 0.4, **x}
    return ev("nats_u", "trade", sig, t, mint=mint, user=user, **fields)


def _trades() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [ev("clock", "sample", "c1", 150.0, offset=0.0, rtt=0.1)]
    out += [
        ev("nats_u", "sub", PROC + "M1", 200.0),
        ev("nats_c", "sub", BAL + "W1.*", 200.0),
    ]
    for i in range(4):
        t = 210.0 + i * 10
        sig = f"T{i}"
        out += [
            _trade(sig, t),
            ev("rpc", "logs", sig, t + 0.2, slot=2000, mints=["M1"]),
            ev("nats_c", "balance", sig, t + 0.5, wallet="W1", slot=2000, srv_ts=t + 0.2),
        ]
    out += [_trade("TOLD", 200.5, user="W9", bt=150.0)]  # block second long before the subscription
    out += [ev("rpc", "logs", "TOTHER", 250.0, slot=5, mints=["MX"])]  # a coin nobody watches
    out += [ev("rpc", "logs", "TSELF", 260.0, slot=6)]  # a tx with no TradeEvent
    return out


def test_trade_pairs_coverage_replay_share_and_balance_coverage() -> None:
    t = analyze(_trades(), META, {})["trade"]
    assert t["pairs"]["rpc_vs_nats"]["delta_s"]["p50"] == pytest.approx(0.2)
    assert t["pairs"]["balance_vs_nats"]["delta_s"]["p50"] == pytest.approx(0.5)
    assert t["pairs"]["balance_vs_rpc"]["delta_s"]["p50"] == pytest.approx(0.3)
    assert t["coverage"]["union"] == 4  # the replay-like TOLD is not a live delivery
    assert t["coverage"]["by_source"]["rpc"]["seen"] == 4  # only mints being watched count
    assert t["replay_like_share"] == pytest.approx(1 / 5)
    assert t["balance_coverage"] == {"expected": 4, "delivered": 4, "share": 1.0}
    assert t["wire_lower_bound_s"]["p50"] == pytest.approx(0.3)  # t_recv - srv_ts


def test_delay_against_block_time_uses_the_clock_offset_and_calls_block_time_an_estimate() -> None:
    t = analyze(_trades(), META, {})["trade"]
    d = t["delay_vs_block_time_s"]
    assert d["nats_u"]["p50"] == pytest.approx(0.4)
    assert d["rpc"]["p50"] == pytest.approx(0.6)
    assert "estimate" in t["delay_note"].lower()


def test_pump_amm_trades_are_not_compared_with_a_pump_only_reference() -> None:
    evs = _trades() + [
        _trade("AMM1", 230.0, program="pump_amm"),
        _trade("AMM2", 231.0, program="pump_amm"),
    ]
    t = analyze(evs, META, {})["trade"]
    assert t["coverage"]["union"] == 4  # the two PumpSwap legs are not rpc's to deliver
    assert t["nats_programs"] == {"pump": 5, "pump_amm": 2}


def test_a_reconnect_gives_a_second_exposure_interval_instead_of_rewriting_the_first() -> None:
    evs = [
        ev("clock", "sample", "c1", 150.0, offset=0.0, rtt=0.1),
        ev("nats_u", "sub", PROC + "M1", 100.0),
        _trade("A", 150.0),
        ev("rpc", "logs", "A", 150.2, slot=1, mints=["M1"]),
        ev("nats_u", "sys", "disconnect", 160.0),
        ev("nats_u", "sub", PROC + "M1", 200.0),  # the re-subscription after the drop
        _trade("B", 250.0),
        ev("rpc", "logs", "B", 250.3, slot=2, mints=["M1"]),
        _trade("OLD", 205.0, bt=140.0),  # older than the second subscription: replay-like there
    ]
    t = analyze(evs, META, {})["trade"]
    assert t["coverage"]["union"] == 2  # A and B both live; OLD is not
    assert t["pairs"]["rpc_vs_nats"]["common"] == 2
    assert t["replay_like_share"] == pytest.approx(1 / 3)


def test_edge_arrivals_find_their_counterpart_outside_the_window_and_do_not_count_as_misses() -> (
    None
):
    evs = [
        ev("clock", "sample", "c1", 150.0, offset=0.0, rtt=0.1),
        ev("nats_u", "sub", PROC + "M1", 100.0),
        # the rpc frame lands 0.1 s before the interior starts (103 s), nats 1.1 s later, inside it
        ev("rpc", "logs", "X", 102.9, slot=1, mints=["M1"]),
        _trade("X", 104.0, bt=103.7),
        # an edge-only nats frame at 101 s (before the interior): neither a pair nor a miss
        _trade("EDGE", 101.0, bt=100.8),
    ]
    p = analyze(evs, META, {})["trade"]["pairs"]["rpc_vs_nats"]
    assert p["common"] == 1 and p["only_a"] == 0 and p["only_b"] == 0
    assert p["delta_s"]["p50"] == pytest.approx(-1.1)


def test_balance_is_matched_on_signature_and_wallet_not_on_signature_alone() -> None:
    evs = [
        ev("clock", "sample", "c1", 150.0, offset=0.0, rtt=0.1),
        ev("nats_u", "sub", PROC + "M1", 100.0),
        ev("nats_c", "sub", BAL + "W1.*", 100.0),
        ev("nats_c", "sub", BAL + "W2.*", 100.0),
        _trade("T", 210.0, user="W1"),
        ev("rpc", "logs", "T", 210.2, slot=1, mints=["M1"]),
        ev(
            "nats_c", "balance", "T", 210.1, wallet="W2", slot=1, srv_ts=210.0
        ),  # another wallet's leg
        ev("nats_c", "balance", "T", 210.6, wallet="W1", slot=1, srv_ts=210.3),
        _trade("U", 220.0, user="W1"),  # W1's balance never arrives; W2's does
        ev("nats_c", "balance", "U", 220.1, wallet="W2", slot=1, srv_ts=220.0),
    ]
    t = analyze(evs, META, {})["trade"]
    assert t["balance_coverage"] == {"expected": 2, "delivered": 1, "share": 0.5}
    assert t["pairs"]["balance_vs_nats"]["delta_s"]["p50"] == pytest.approx(0.6)


def test_block_time_check_compares_the_nats_second_with_the_chain_block_time() -> None:
    evs = _trades()
    for e in evs:
        if e["id"] == "T0":
            e["slot"] = 2000
        if e["id"] == "T1":
            e["slot"] = 2001
    rep = analyze(evs, META, {"2000": 209, "2001": 220, "2002": None})
    chk = rep["block_time_check"]
    assert chk["n"] == 2
    assert chk["nats_minus_chain_s"]["p50"] == pytest.approx(0.1, abs=0.5)


def test_a_long_stall_splits_the_capture_and_only_the_longest_valid_segment_is_analysed() -> None:
    evs = _creates() + [
        ev("nats_u", "create", "SLATE", 900.0, mint="ML", program="pump"),
        ev("pp", "create", "SLATE", 900.1, mint="ML", pool="pump"),
    ]
    meta = {**META, "stalls": [(500.0, 800.0)]}
    rep = analyze(evs, meta, {})
    assert (
        rep["create"]["coverage"]["union"] == 3
    )  # the post-wake pair at 900 s is not in the segment
    assert rep["segment"] == {"start": 0.0, "end": 500.0, "segments": 2}


def test_replay_sensitivity_publishes_the_replay_like_share_for_each_slack() -> None:
    evs = [
        ev("clock", "sample", "c1", 150.0, offset=0.0, rtt=0.1),
        ev("nats_u", "sub", PROC + "M1", 100.0),
        _trade("EARLY", 101.0, bt=99.0),  # 1 s before the subscription: replay-like only at slack 0
        _trade("LIVE", 200.0),
        ev("rpc", "logs", "LIVE", 200.2, slot=1, mints=["M1"]),
    ]
    sens = {x["slack_s"]: x for x in analyze(evs, META, {})["trade"]["replay_sensitivity"]}
    assert sens[0.0]["replay_like_share"] == pytest.approx(0.5)
    assert sens[2.0]["replay_like_share"] == 0.0 and sens[4.0]["replay_like_share"] == 0.0


def test_kol_counts_distinct_coins_at_their_first_add_not_re_adds() -> None:
    evs = _creates() + [
        ev(
            "tr_new", "add", "M0", 250.0, entry={"pg": "pump", "kol": 3}
        ),  # the same coin back on the board
        ev(
            "tr_new", "add", "M3", 260.0, entry={"pg": "pump", "kol": 1}
        ),  # a new coin born with kol
    ]
    k = analyze(evs, META, {})["kol"]
    assert k["add_events_pump"] == 5 and k["adds_pump"] == 4  # M0, M1, M2, M3
    assert k["kol_gt0_at_add"] == 2  # M1 (kol 1) and M3 (kol 1); the first add of M0 had kol 0


def test_balance_coverage_counts_each_wallet_leg_of_a_transaction() -> None:
    evs = [
        ev("clock", "sample", "c1", 150.0, offset=0.0, rtt=0.1),
        ev("nats_u", "sub", PROC + "M1", 100.0),
        ev("nats_c", "sub", BAL + "W1.*", 100.0),
        ev("nats_c", "sub", BAL + "W2.*", 100.0),
        _trade("T", 210.0, user="W1"),
        _trade("T", 210.0, user="W2"),  # two followed wallets traded inside one transaction
        ev("rpc", "logs", "T", 210.2, slot=1, mints=["M1"]),
        ev("nats_c", "balance", "T", 210.5, wallet="W1", slot=1, srv_ts=210.2),
        ev("nats_c", "balance", "T", 210.7, wallet="W2", slot=1, srv_ts=210.2),
    ]
    t = analyze(evs, META, {})["trade"]
    assert t["balance_coverage"] == {"expected": 2, "delivered": 2, "share": 1.0}
    assert t["pairs"]["balance_vs_nats"]["common"] == 2  # one delta per wallet leg


def test_a_late_nats_counterpart_after_the_unsubscribe_is_still_found() -> None:
    evs = [
        ev("clock", "sample", "c1", 150.0, offset=0.0, rtt=0.1),
        ev("nats_u", "sub", PROC + "M1", 100.0),
        ev("nats_u", "unsub", PROC + "M1", 200.0),
        ev("rpc", "logs", "L", 196.0, slot=1, mints=["M1"]),  # inside the interior of [100, 200]
        _trade("L", 206.0, bt=195.0),  # nats lands 6 s late, after the unsubscribe plus slack
    ]
    p = analyze(evs, META, {})["trade"]["pairs"]["rpc_vs_nats"]
    assert p["common"] == 1 and p["only_a"] == 0
    assert p["delta_s"]["p50"] == pytest.approx(-10.0)


def test_a_failed_send_closes_the_exposure_of_that_connection() -> None:
    evs = [
        ev("clock", "sample", "c1", 150.0, offset=0.0, rtt=0.1),
        ev("nats_u", "sub", PROC + "M1", 100.0),
        ev("nats_u", "sys", "send_failed", 150.0),
        _trade("AFTER", 170.0),  # nobody can claim M1 was exposed after the send failed
        ev("rpc", "logs", "AFTER", 170.2, slot=1, mints=["M1"]),
    ]
    assert analyze(evs, META, {})["trade"]["coverage"]["union"] == 0


def test_source_health_counts_the_connection_events_inside_the_analysed_segment() -> None:
    evs = _creates() + [
        ev("pp", "sys", "disconnect", 250.0),
        ev("pp", "sys", "error", 251.0),
        ev("pp", "sys", "disconnect", 5000.0),  # outside the capture
    ]
    h = analyze(evs, META, {})["health"]
    assert h["pp"] == {"disconnect": 1, "error": 1}
