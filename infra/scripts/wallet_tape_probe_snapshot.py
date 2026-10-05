"""Wave 0 of "seguir carteiras que ganham de verdade" — the JSON-serialisable snapshot of a ``ProbeStats``
(written every minute and at the end of the probe). Split out of ``wallet_tape_probe_stats`` for the
file-size budget; it only reads the stats object."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from wallet_tape_probe_math import per_sec_summary

if TYPE_CHECKING:
    from wallet_tape_probe_stats import ProbeStats


def snapshot_of(self: ProbeStats, now: float) -> dict[str, Any]:
    events: dict[str, Any] = {}
    for key, c in sorted(self.ev.items()):
        events[key] = {
            "n": c["n"], "payload_bytes": c["payload_bytes"],
            "decoded_ok": c["decoded_ok"], "decode_failed": c["decode_failed"],
            "not_attempted_raw": c["not_attempted_raw"],
            "failure_reasons": dict(self.fail_reasons.get(key, Counter()).most_common(8)),
            "layouts": dict(self.layouts.get(key, {})),
        }  # fmt: skip
    return {
        "elapsed_s": round(now - self.started, 1),
        "frames": {s: dict(c) for s, c in self.frames.items()},
        "notifications": {s: dict(c) for s, c in self.notif.items()},
        "tx": dict(self.tx),
        "delivery_both_programs": {
            k: self.delivery[k] for k in ("expected", "delivered_by_both", "only_pump", "only_amm")
        },  # fmt: skip
        "events": events,
        "instructions_top": {p: dict(c.most_common(12)) for p, c in self.ix.items()},
        "foreign_data_lines_by_program": dict(self.foreign.most_common(8)),
        "liquidity": {
            **{k: self.liq[k] for k in ("tx_without_swap_instruction", "tx_with_swap_instruction")},
            "instructions": dict(self.liq_ix),
        },  # fmt: skip
        "silence_gaps": {
            s: {"n": len(g), "max_s": max(g), "total_s": round(sum(g), 1)}
            for s, g in self.silence.items()
        },  # fmt: skip
        "lag_slots_ws_slotsubscribe_same_pipe_NOT_independent": {
            s: h.summary() for s, h in self.lag_slots.items()
        },
        "lag_slots_ws_slotsubscribe_same_pipe_by_10min": {
            s: [{"w": w, **h.summary()} for w, h in sorted(ws.items())]
            for s, ws in self.lag_windows.items()
        },  # fmt: skip
        "lag_slots_vs_http_tip": {s: h.summary() for s, h in self.lag_http.items()},
        "age_of_last_log_s_at_poll": {s: h.summary() for s, h in self.age_last_log.items()},
        "observations": {n: h.summary() for n, h in self.obs.items()},
        "size_bins_sol": dict(self.size_bins),
        "suspensions": list(self.suspensions),
        "swap_events_per_minute": {p: per_sec_summary(c) for p, c in self.per_min.items()},
        "lag_slots_vs_http_tip_by_10min": {
            s: [{"w": w, **h.summary()} for w, h in sorted(ws.items())]
            for s, ws in self.lag_http_windows.items()
        },
        "lag_event_ts_s": {p: h.summary() for p, h in self.lag_event.items()},
        "reconnects": {
            s: {k: v for k, v in rc.items() if k not in ("down_since", "await_first", "outages")}
            | {
                "downtime_s_incl_open": rc["downtime_s"]
                + (now - rc["down_since"] if rc["down_since"] is not None else 0.0)
            }
            for s, rc in self.rc.items()
        },  # fmt: skip
        "wallets": {k: len(v) for k, v in self.wallets.items()}
        | {
            "all": len(
                self.wallets["pump"] | self.wallets["amm"] | self.wallets["amm_buy_inferred"]
            )
        },  # fmt: skip
        "keys": {k: len(v) for k, v in self.keys.items()},
        "rows": dict(self.rows),
        "per_second_swap_events": {p: per_sec_summary(c) for p, c in self.per_sec.items()},
    }
