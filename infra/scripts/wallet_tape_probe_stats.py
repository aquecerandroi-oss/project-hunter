"""Wave 0 of "seguir carteiras que ganham de verdade" — the aggregator of the program-wide probe.

Pure (no IO, clock injected as epoch seconds). ``ProbeStats`` takes the notifications the
network half hands over and keeps every counter the design asks for (events/s, bytes/s, decode
success/failure by type, reconnects and gaps, distinct wallets, row size, tx touching both
programs, liquidity without swap, lag). ``snapshot`` is JSON-serialisable and is what the
probe writes every minute and at the end. See ``wallet_tape_probe_core`` for the log reading.
"""

from __future__ import annotations

import base64
from collections import Counter
from typing import Any

from wallet_tape_probe_core import (
    AMM,
    LIQUIDITY_INSTRUCTIONS,
    PUMP,
    SWAP_INSTRUCTIONS,
    LogEvent,
    NotifFacts,
    decode_event,
    event_name,
    parse_logs,
)
from wallet_tape_probe_math import Hist, row_estimates, swap_row
from wallet_tape_probe_snapshot import snapshot_of

SILENCE_GAP_S = 3.0
DEDUPE_WINDOW_S = 300.0
_PROG = {PUMP: "pump", AMM: "pAMM"}
_BIT = {"pump": 1, "amm": 2}
_SAMPLE_CAP = 50
_LIQ_PAYLOAD_CAP = 20_000


class ProbeStats:
    def __init__(self, started: float) -> None:
        self.started = started
        self.frames: dict[str, Counter[str]] = {}
        self.notif: dict[str, Counter[str]] = {}
        self.tx: Counter[str] = Counter()
        self.delivery: Counter[str] = Counter()
        self.ev: dict[str, Counter[str]] = {}
        self.fail_reasons: dict[str, Counter[str]] = {}
        self.layouts: dict[str, Counter[str]] = {}
        self.foreign: Counter[str] = Counter()
        self.ix: dict[str, Counter[str]] = {"pump": Counter(), "pAMM": Counter()}
        self.liq: Counter[str] = Counter()
        self.liq_ix: Counter[str] = Counter()
        self.liq_payloads: list[tuple[str, bytes]] = []
        self.wallets: dict[str, set[str]] = {k: set() for k in ("pump", "amm", "amm_buy_inferred")}
        self.keys: dict[str, set[str]] = {"mints": set(), "pools": set()}
        self.rows = {"n": 0, "json": 0, "heap": 0, "indexed": 0}
        self.lag_slots: dict[str, Hist] = {}
        self.lag_windows: dict[str, dict[int, Hist]] = {}
        self.lag_event: dict[str, Hist] = {}
        self.lag_http: dict[str, Hist] = {}
        self.lag_http_windows: dict[str, dict[int, Hist]] = {}
        self.per_sec: dict[str, Counter[int]] = {"pump": Counter(), "pAMM": Counter()}
        self.tip: dict[str, int] = {}
        self.max_slot: dict[str, int] = {}
        self.first_slot: dict[str, int] = {}
        self.suspensions: list[dict[str, float]] = []
        self.size_bins: Counter[str] = Counter()
        self.wallet_trades: Counter[str] = Counter()
        self._last_tick: float | None = None
        self.age_last_log: dict[str, Hist] = {}
        self.obs: dict[str, Hist] = {}
        self.per_min: dict[str, Counter[int]] = {"pump": Counter(), "pAMM": Counter()}
        self.last_t: dict[str, float] = {}
        self.silence: dict[str, list[float]] = {}
        self.rc: dict[str, dict[str, Any]] = {}
        self.curve: list[dict[str, Any]] = []
        self.undecodable_samples: list[dict[str, Any]] = []
        self.sample_frames: dict[str, list[str]] = {}
        self._seen: dict[str, list[float | int]] = {}  # sig -> [first_t, mask, expected]
        self._next_evict = started + 30

    # -- transport-level hooks ------------------------------------------------------
    def on_frame(self, sub: str, nbytes: int) -> None:
        c = self.frames.setdefault(sub, Counter())
        c["frames"] += 1
        c["bytes"] += nbytes

    def on_slot(self, sub: str, slot: int, now: float) -> None:
        self.tip[sub] = max(self.tip.get(sub, 0), slot)

    def on_http_tip(self, slot: int, now: float) -> None:
        """Slot read over HTTP (a path independent of the websocket): how far the newest notified
        slot of each subscription is behind it."""
        bucket = int((now - self.started) // 600)
        for (
            sub,
            newest,
        ) in self.max_slot.items():  # the NEWEST slot received, not the last processed
            self.lag_http.setdefault(sub, Hist()).add(slot - newest)
            self.lag_http_windows.setdefault(sub, {}).setdefault(bucket, Hist()).add(slot - newest)
        for sub, seen in self.last_t.items():
            self.age_last_log.setdefault(sub, Hist(0.5)).add(now - seen)

    def outage_overlaps(self, lo: float, hi: float) -> bool:
        """Did any subscription have an outage (disconnect -> first log, or still open) that intersects
        ``[lo, hi]`` (epoch seconds)? Intervals, not instants: an outage that began before ``lo`` and
        ended before ``hi`` still taints the window."""
        return any(
            start <= hi and (end is None or end >= lo)
            for rc in self.rc.values()
            for start, end in rc["outages"]
        )

    def on_tick(self, now: float, cadence_s: float) -> None:
        """Called on a fixed cadence: a tick that comes far later than its cadence means the process
        was frozen (the machine slept) — the data across that gap does not exist."""
        last = self._last_tick if self._last_tick is not None else now - cadence_s
        if now - last > 2.5 * cadence_s + 5:
            self.suspensions.append(
                {"at_elapsed_s": round(now - self.started, 1), "gap_s": round(now - last, 1)}
            )
        self._last_tick = now

    def observe(self, name: str, value: float, step: float = 1.0) -> None:
        self.obs.setdefault(name, Hist(step)).add(value)

    def _rc(self, sub: str) -> dict[str, Any]:
        return self.rc.setdefault(sub, {
            "connects": 0, "disconnects": 0, "rejects": 0, "downtime_s": 0.0,
            "gap_slots_total": 0, "down_since": self.started, "await_first": False, "events": [],
            "outages": [[self.started, None]],
        })  # fmt: skip

    def on_connect(self, sub: str, now: float) -> None:
        rc = self._rc(sub)
        rc["connects"] += 1  # the outage ends at the FIRST LOG after this, not at the socket
        self.last_t.pop(sub, None)

    def on_disconnect(self, sub: str, now: float, reason: str) -> None:
        rc = self._rc(sub)
        rc["disconnects"] += 1
        if rc["down_since"] is None:  # a failed retry does not restart an open outage
            rc["down_since"] = now
            rc["outages"].append([now, None])
        rc["await_first"] = True
        rc["events"].append({"t": round(now - self.started, 1), "reason": reason[:160]})
        del rc["events"][:-30]

    def on_reject(self, sub: str, now: float, reason: str) -> None:
        rc = self._rc(sub)
        rc["rejects"] += 1
        rc["events"].append({"t": round(now - self.started, 1), "reject": reason[:160]})
        del rc["events"][:-30]

    # -- one logsNotification -------------------------------------------------------
    def on_logs(
        self, sub: str, slot: int, sig: str, err: Any, logs: list[str], nbytes: int, now: float
    ) -> NotifFacts:
        facts = parse_logs(logs)
        n = self.notif.setdefault(sub, Counter())
        n["n"] += 1
        n["bytes"] += nbytes
        n["failed"] += err is not None
        n["truncated"] += facts.truncated
        n["bad_base64_lines"] += facts.bad_b64
        if sub in self.tip:
            lag = self.tip[sub] - slot
            self.lag_slots.setdefault(sub, Hist()).add(lag)
            bucket = int((now - self.started) // 600)
            self.lag_windows.setdefault(sub, {}).setdefault(bucket, Hist()).add(lag)
        prev = self.last_t.get(sub)
        if prev is not None and now - prev > SILENCE_GAP_S:
            self.silence.setdefault(sub, []).append(now - prev)
        self.last_t[sub] = now
        rc = self._rc(sub)
        if rc["down_since"] is not None:
            rc["downtime_s"] += now - rc["down_since"]
            rc["down_since"] = None
            rc["outages"][-1][1] = now
        if rc["await_first"]:
            rc["await_first"] = False
            rc["gap_slots_total"] += max(0, slot - self.max_slot.get(sub, slot))
        self.max_slot[sub] = max(self.max_slot.get(sub, 0), slot)
        self.first_slot.setdefault(sub, slot)
        self._tx(sub, sig, err, facts, slot, now)
        if now >= self._next_evict:
            self._evict(now - DEDUPE_WINDOW_S)
            self._next_evict = now + 30
        return facts

    def _tx(self, sub: str, sig: str, err: Any, facts: NotifFacts, slot: int, now: float) -> None:
        mask = _BIT[sub]
        entry = self._seen.get(sig)
        if entry is not None:
            entry[1] = int(entry[1]) | mask
            return
        expected = (PUMP in facts.invoked) * 1 | (AMM in facts.invoked) * 2
        self._seen[sig] = [now, mask, expected]
        self.tx["unique"] += 1
        self.tx["failed" if err is not None else "success"] += 1
        kind = {1: "pump_only", 2: "amm_only", 3: "both_programs"}.get(int(expected), "neither")
        self.tx[kind] += 1
        if err is None:
            self.tx[f"success_{kind}"] += 1
        for prog, name in facts.instructions:
            if prog in _PROG:
                self.ix[_PROG[prog]][name] += 1
        for prog, cnt in facts.foreign_data.items():
            self.foreign[prog] += cnt
        if err is not None:
            return
        amm_ix = {name for prog, name in facts.instructions if prog == AMM}
        has_swap_event = False
        for event in facts.events:
            has_swap_event |= self._event(event, slot, sig, now)
        liq = amm_ix & LIQUIDITY_INSTRUCTIONS
        if liq:
            self.liq_ix.update(name for prog, name in facts.instructions if prog == AMM and name in liq)  # fmt: skip
            with_swap = bool(amm_ix & SWAP_INSTRUCTIONS) or has_swap_event
            self.liq["tx_with_swap_instruction" if with_swap else "tx_without_swap_instruction"] += 1  # fmt: skip

    def _event(self, event: LogEvent, slot: int, sig: str, now: float) -> bool:
        prog = _PROG[event.program]
        name = event_name(event.program, event.disc)
        key = f"{prog}.{name}"
        c = self.ev.setdefault(key, Counter())
        c["n"] += 1
        c["payload_bytes"] += len(event.payload)
        d = decode_event(event)
        if d.ok is True:
            c["decoded_ok"] += 1
            self.layouts.setdefault(key, Counter())[d.layout or "?"] += 1
        elif d.ok is False:
            c["decode_failed"] += 1
            self.fail_reasons.setdefault(key, Counter())[d.reason or "?"] += 1
            if len(self.undecodable_samples) < _SAMPLE_CAP:
                self.undecodable_samples.append({"event": key, "reason": d.reason, "sig": sig,
                    "slot": slot, "payload_b64": base64.b64encode(event.payload).decode()})  # fmt: skip
        else:
            c["not_attempted_raw"] += 1
        if d.kind == "liquidity" and len(self.liq_payloads) < _LIQ_PAYLOAD_CAP:
            self.liq_payloads.append((name, event.payload))
        if d.kind != "swap":
            return False
        self.per_sec[prog][int(now)] += 1
        self.per_min[prog][int((now - self.started) // 60)] += 1
        if d.event_ts:
            self.lag_event.setdefault(prog, Hist(0.5)).add(now - d.event_ts)
        wallet = d.wallet or d.inferred_wallet
        if wallet:
            self.wallet_trades[wallet] += 1
        if d.ok and d.sol_lamports is not None:
            self.size_bins[_size_bin(d.sol_lamports)] += 1
        if d.wallet:
            self.wallets["pump" if event.program == PUMP else "amm"].add(d.wallet)
        if d.inferred_wallet:
            self.wallets["amm_buy_inferred"].add(d.inferred_wallet)
        if event.program == PUMP and d.key:
            self.keys["mints"].add(d.key)
        pool = d.key if event.program == AMM else None
        pool = pool or d.inferred_pool
        if pool:
            self.keys["pools"].add(pool)
        if d.ok:
            est = row_estimates(swap_row(event.program, slot, sig, event.ordinal, d))
            self.rows["n"] += 1
            self.rows["json"] += est["json_bytes"]
            self.rows["heap"] += est["pg_heap_bytes"]
            self.rows["indexed"] += est["pg_with_indexes_bytes"]
        return True

    def _evict(self, older_than: float) -> None:
        for sig in [s for s, e in self._seen.items() if e[0] < older_than]:
            first, mask, expected = self._seen.pop(sig)
            del first
            if expected == 3:
                self.delivery["expected"] += 1
                if mask == 3:
                    self.delivery["delivered_by_both"] += 1
                elif mask == 1:
                    self.delivery["only_pump"] += 1
                else:
                    self.delivery["only_amm"] += 1

    def flush(self, now: float) -> None:
        self._evict(now - DEDUPE_WINDOW_S)

    # -- output ---------------------------------------------------------------------
    def wallet_concentration(self) -> dict[str, dict[str, int]]:
        """Wallets and events by how many swaps a wallet made in the window: what an ingest filter that
        keeps only wallets with enough activity would keep, and what the robots (500+) weigh."""
        out = {label: {"wallets": 0, "events": 0} for label, _ in _TRADE_BINS}
        for n in self.wallet_trades.values():
            label = next(lbl for lbl, upper in _TRADE_BINS if n <= upper)
            out[label]["wallets"] += 1
            out[label]["events"] += n
        return out

    def distinct_point(self, now: float) -> dict[str, Any]:
        swaps = sum(c["n"] for k, c in self.ev.items() if k in _SWAP_KEYS)
        allw = self.wallets["pump"] | self.wallets["amm"] | self.wallets["amm_buy_inferred"]
        point = {
            "t": round(now - self.started), "swap_events": swaps, "wallets_all": len(allw),
            "wallets_pump": len(self.wallets["pump"]),
            "wallets_amm_decoded_sell": len(self.wallets["amm"]),
            "wallets_amm_buy_inferred": len(self.wallets["amm_buy_inferred"]),
            "mints": len(self.keys["mints"]), "pools": len(self.keys["pools"]),
        }  # fmt: skip
        self.curve.append(point)
        return point

    def snapshot(self, now: float) -> dict[str, Any]:
        return snapshot_of(self, now)


_SWAP_KEYS = frozenset({"pump.TradeEvent", "pAMM.SellEvent", "pAMM.BuyEvent"})


_TRADE_BINS = (
    ("1", 1),
    ("2-4", 4),
    ("5-19", 19),
    ("20-99", 99),
    ("100-499", 499),
    ("500+", 10**12),
)


def _size_bin(lamports: int) -> str:
    sol = lamports / 1e9
    for label, upper in (
        ("<0.001", 0.001),
        ("0.001-0.01", 0.01),
        ("0.01-0.1", 0.1),
        ("0.1-1", 1),
        ("1-10", 10),
    ):
        if sol < upper:
            return label
    return ">=10"
