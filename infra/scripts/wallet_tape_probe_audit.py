"""Wave 0 of "seguir carteiras que ganham de verdade" — the probe's INDEPENDENT coverage audit.

``getBlock`` of a slot chosen without looking at the websocket (HTTP tip minus ``AUDIT_SLOT_LAG``), the
transactions that mention a program (``wallet_tape_probe_core.block_view``) kept, and judged against what
the websocket delivered **later**: at the moment of the fetch (lag-confounded: a socket 28 s behind has
not delivered a 24 s old slot yet, and that is *late*, not *lost*) and ``SETTLE_AFTER_S`` after it (the
verdict). A block whose window had a reconnect goes to its own bucket. The block also gives the chain's
real event rate, whatever the socket managed to deliver (``audit["truth"]``).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, cast

import httpx
from wallet_tape_probe_core import block_view, coverage
from wallet_tape_probe_http import _rpc  # pyright: ignore[reportPrivateUsage]
from wallet_tape_probe_rt import AUDIT_SLOT_LAG, PROGRAMS, SETTLE_AFTER_S, Runtime


def _tainted(rt: Runtime, fetched_at: float, now: float) -> bool:
    """An outage (interval, or still open) on either subscription, or a suspension of the machine,
    intersecting ``[fetch - 60 s, settlement]`` taints the block."""
    lo = fetched_at - 60
    if rt.stats.outage_overlaps(lo, now):
        return True
    return any(lo - rt.t0 <= x["at_elapsed_s"] <= now - rt.t0 for x in rt.stats.suspensions)


def settle(rt: Runtime, now: float, *, final: bool = False) -> None:
    """Judge every pending block at least ``SETTLE_AFTER_S`` old; at the end of the run the younger ones
    are censored and counted as such."""
    wait = SETTLE_AFTER_S  # also at the end: a younger block is censored, never judged early
    keep: list[dict[str, Any]] = []
    for p in rt.audit_pending:
        if now - p["t"] < wait:
            keep.append(p)
            continue
        received = {PROGRAMS[s]: rt.sigs[s].get(p["slot"], set()) for s in PROGRAMS}
        result = coverage(p["mentions"], received)
        bucket = rt.audit["settled"][
            "affected_by_reconnect" if _tainted(rt, p["t"], now) else "clean"
        ]
        bucket["blocks"] += 1
        for sub, program in PROGRAMS.items():
            for key in ("txs", "received", "missed", "missed_failed"):
                bucket[sub][key] += result[program][key]
            if result[program]["missed_sigs"] and len(rt.audit["missed_examples"]) < 40:
                rt.audit["missed_examples"].append(
                    {"slot": p["slot"], "program": sub, "sigs": result[program]["missed_sigs"][:3]}
                )
        if len(rt.audit["per_block"]) < 400:
            rt.audit["per_block"].append(
                [p["slot"], bucket is rt.audit["settled"]["affected_by_reconnect"]]
                + [
                    [result[g]["txs"], result[g]["missed"], p["at_fetch_missed"][g]]
                    for g in PROGRAMS.values()
                ]
            )
    rt.audit["pending_censored_at_end"] = len(keep) if final else 0
    rt.audit_pending = [] if final else keep
    for sub in PROGRAMS:  # keep signatures only for slots still awaiting a verdict (+ margin)
        floor = min((p["slot"] for p in rt.audit_pending), default=None)
        newest = rt.stats.max_slot.get(sub, 0)
        for old in [
            k for k in rt.sigs[sub] if k < (floor if floor is not None else newest - 400) - 5
        ]:
            del rt.sigs[sub][old]


async def block_audit(rt: Runtime) -> None:
    if rt.args.audit_every <= 0:
        return
    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            await asyncio.sleep(rt.args.audit_every)
            settle(rt, time.time())
            if rt.http_tip is None:
                continue
            slot = rt.http_tip - AUDIT_SLOT_LAG
            firsts = [rt.stats.first_slot.get(sub) for sub in PROGRAMS]
            if any(f is None or slot <= f + 2 for f in firsts):
                rt.audit["blocks_before_both_subscriptions_flowed"] += 1  # nothing to compare yet
                continue
            rt.audit["blocks_requested"] += 1
            params = [slot, {"encoding": "json", "transactionDetails": "full", "rewards": False, "commitment": "confirmed", "maxSupportedTransactionVersion": 1}]  # fmt: skip
            out = await _rpc(rt, client, "getBlock", params, "getBlock")
            block = cast("dict[str, Any] | None", out.get("result")) if out else None
            if not block:
                rt.audit["blocks_skipped_or_unavailable"] += 1
                continue
            view = block_view(block)
            mentions = {p: v["mentions"] for p, v in view.items()}
            now_received = {PROGRAMS[s]: rt.sigs[s].get(slot, set()) for s in PROGRAMS}
            first = coverage(mentions, now_received)
            truth = rt.audit["truth"]
            truth["blocks_ok"] += 1
            for sub, program in PROGRAMS.items():
                truth[sub]["txs"] += len(mentions[program])
                truth[sub]["success_txs"] += view[program]["success_txs"]
                for name, n in view[program]["events"].items():
                    truth[sub]["events"][name] = truth[sub]["events"].get(name, 0) + n
                rt.audit["at_fetch"][sub]["txs"] += first[program]["txs"]
                rt.audit["at_fetch"][sub]["received"] += first[program]["received"]
            rt.audit_pending.append(
                {
                    "slot": slot,
                    "t": time.time(),
                    "mentions": mentions,
                    "at_fetch_missed": {g: first[g]["missed"] for g in first},
                }  # fmt: skip
            )
