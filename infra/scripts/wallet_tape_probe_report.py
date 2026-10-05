"""Wave 0 of "seguir carteiras que ganham de verdade" — the final report of the probe, built from a
``ProbeStats`` (pure: no network, no clock besides the ``now`` it is handed)."""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from wallet_tape_probe_core import find_in_index, pubkey_index
from wallet_tape_probe_math import heaps_fit
from wallet_tape_probe_stats import ProbeStats


def liquidity_join(stats: ProbeStats) -> dict[str, Any]:
    """Which liquidity events (no committed decoder) mention a pool that also swapped in the window."""
    pools = stats.keys["pools"]
    index = pubkey_index(pools)
    by_name: Counter[str] = Counter()
    matched: Counter[str] = Counter()
    for name, payload in stats.liq_payloads:
        by_name[name] += 1
        matched[name] += bool(find_in_index(payload, index))
    return {"events": dict(by_name), "on_a_pool_that_swapped_in_window": dict(matched),
            "pools_known": len(pools)}  # fmt: skip


def extrapolation(stats: ProbeStats, t0: float, now: float) -> dict[str, Any]:
    """Wallets/day SCENARIOS from the discovery curve (a 2 h window at ONE time of day: not bounds,
    not intervals — the curve itself is the result; Astra, wallet-tape-probe, must-fix 5)."""
    curve = [p for p in stats.curve if p["swap_events"] > 0]
    elapsed = max(1.0, now - t0)
    events = curve[-1]["swap_events"] if curve else 0
    per_day = events / elapsed * 86400
    out: dict[str, Any] = {"swap_events_per_day_at_window_rate": round(per_day)}
    if len(curve) >= 8:
        k, beta = heaps_fit(
            [(p["swap_events"], p["wallets_all"]) for p in curve[len(curve) // 5 :]]
        )
        tail = curve[-max(2, len(curve) // 4) :]
        marginal = (tail[-1]["wallets_all"] - tail[0]["wallets_all"]) / max(
            1, tail[-1]["swap_events"] - tail[0]["swap_events"]
        )
        out |= {
            "heaps_k": k, "heaps_beta": beta,
            "curve_is_the_primary_result": "see snapshot/curve (every minute)",
            "scenario_wallets_day_if_no_new_after_window": curve[-1]["wallets_all"],
            "scenario_wallets_day_heaps_fit": round(k * per_day**beta),
            "scenario_wallets_day_linear_at_last_quarter_marginal_rate": round(
                curve[-1]["wallets_all"] + marginal * max(0.0, per_day - events)),
        }  # fmt: skip
    return out


def build_summary(stats: ProbeStats, t0: float, now: float, meta: dict[str, Any]) -> dict[str, Any]:
    snap = stats.snapshot(now)
    el = max(1.0, now - t0)
    rates: dict[str, Any] = {}
    for sub, c in snap["frames"].items():
        rates[sub] = {"frames_per_s": c["frames"] / el, "bytes_per_s": c["bytes"] / el,
                      "gb_per_day_uncompressed": c["bytes"] / el * 86400 / 1e9}  # fmt: skip
    for sub, c in snap["notifications"].items():
        down = snap["reconnects"].get(sub, {}).get("downtime_s_incl_open", 0.0)
        active = max(1.0, el - down)
        rates[sub] |= {
            "notifications_per_s_total_time": c["n"] / el,
            "notifications_per_s_active_time": c["n"] / active,
            "active_s": round(active, 1),
            "downtime_s_incl_open": round(down, 1),
            "failed_share": c["failed"] / max(1, c["n"]),
            "gb_per_day_uncompressed_active_time": c["bytes"] / active * 86400 / 1e9,
        }
    swaps = sum(v["n"] for k, v in snap["events"].items() if k in ("pump.TradeEvent", "pAMM.SellEvent", "pAMM.BuyEvent"))  # fmt: skip
    rows = snap["rows"]
    row_est = (
        {
            "decoded_rows": rows["n"],
            "json_bytes_per_row": rows["json"] / rows["n"],
            "pg_heap_bytes_per_row_estimate": rows["heap"] / rows["n"],
            "pg_with_indexes_bytes_per_row_estimate": rows["indexed"] / rows["n"],
            "hypothesis_bytes_per_row": 350,
        }  # fmt: skip
        if rows["n"]
        else {}
    )
    if rows["n"]:
        per_day = swaps / el * 86400
        row_est |= {"rows_per_day": round(per_day),
                    "gb_per_day_at_hypothesis_350B": per_day * 350 / 1e9,
                    "gb_per_day_at_measured_indexed_estimate": per_day * row_est["pg_with_indexes_bytes_per_row_estimate"] / 1e9}  # fmt: skip
    return meta | {
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)),
        "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "elapsed_s": round(el, 1),
        "rates": rates,
        "swap_events_per_s": swaps / el,
        "row_size": row_est,
        "extrapolation_wallets_per_day": extrapolation(stats, t0, now),
        "liquidity_join": liquidity_join(stats),
        "wallet_concentration_by_swaps_in_window": stats.wallet_concentration(),
        "snapshot": snap,
    }
