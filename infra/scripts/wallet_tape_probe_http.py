"""Wave 0 of "seguir carteiras que ganham de verdade" — the probe's HTTP side tasks and the loop watchdog.
Read-only JSON-RPC on the public endpoint, slow cadence (a few requests per 10 s, far under the public
limits); a 429/403 is a recorded event and a pause, never a silent retry loop.

* ``sampler``: ``getTransaction`` of a random delivered tx — do the logs hold every event the program
  emitted (compared with the inner-instruction self-CPI events)?
* ``tip_poller``: ``getSlot(confirmed)`` every 5 s — the lag reference that does not ride the websocket.
* ``loop_watchdog``: how late the event loop wakes up (is the probe itself the bottleneck?).
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
from typing import Any, cast

import httpx
from wallet_tape_probe_core import inner_event_counts
from wallet_tape_probe_rt import HTTP, HTTP_EVENTS, Runtime

_PAUSE_S = 60


async def _rpc(
    rt: Runtime, client: httpx.AsyncClient, method: str, params: list[Any], tag: str
) -> dict[str, Any] | None:
    """One JSON-RPC call; ``None`` on any failure (counted). 429/403 pause the caller's loop."""
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    HTTP[f"{tag}_requests"] += 1
    began = time.perf_counter()
    try:
        resp = await client.post(rt.args.http_url, json=body)
    except httpx.HTTPError as exc:
        HTTP[f"{tag}_errors"] += 1
        HTTP_EVENTS.append({"t": round(time.time() - rt.t0), "tag": tag, "error": str(exc)[:120]})
        return None
    if resp.status_code in (429, 403):
        HTTP[f"{tag}_http_{resp.status_code}"] += 1
        HTTP_EVENTS.append(
            {"t": round(time.time() - rt.t0), "tag": tag, "status": resp.status_code}
        )
        print(f"[{tag}] HTTP {resp.status_code}: pausing {_PAUSE_S} s (system_event)", flush=True)
        await asyncio.sleep(_PAUSE_S)
        return None
    if resp.status_code != 200:
        HTTP[f"{tag}_http_{resp.status_code}"] += 1
        return None
    rt.stats.observe(f"http_rtt_s.{tag}", time.perf_counter() - began, 0.05)
    try:
        out: Any = resp.json()
    except ValueError:
        HTTP[f"{tag}_bad_json"] += 1
        return None
    return cast(dict[str, Any], out) if isinstance(out, dict) else None


async def sampler(rt: Runtime) -> None:
    if rt.args.sample_every <= 0:
        return
    rng = random.Random(7)
    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            await asyncio.sleep(rt.args.sample_every)
            ripe = [c for c in rt.sample_candidates if time.time() - c[0] > 4.0]
            if not ripe:
                continue
            choice = rng.choice(ripe)
            _, sub, sig, from_logs, ctx_slot = choice
            with contextlib.suppress(ValueError):
                rt.sample_candidates.remove(choice)
            params = [sig, {"encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 1}]  # fmt: skip
            out = await _rpc(rt, client, "getTransaction", params, "getTransaction")
            tx = cast("dict[str, Any] | None", out.get("result")) if out else None
            if not tx:
                rt.sampler["unavailable"] += 1
                continue
            from_tx = dict(inner_event_counts(tx))
            rt.sampler["compared"] += 1
            if isinstance(tx.get("slot"), int):
                rt.sampler["slot_delta"][ctx_slot - tx["slot"]] += 1
            if from_tx == from_logs:
                rt.sampler["equal"] += 1
            elif len(rt.sampler["diff"]) < 20:
                rt.sampler["diff"].append(
                    {"sig": sig, "sub": sub, "logs": from_logs, "inner": from_tx}
                )


async def tip_poller(rt: Runtime) -> None:
    if rt.args.sample_every <= 0:
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        perf = await _rpc(
            rt, client, "getRecentPerformanceSamples", [30], "getRecentPerformanceSamples"
        )
        samples = cast("list[dict[str, Any]]", perf.get("result")) if perf else []
        rates = sorted(
            s["numSlots"] / s["samplePeriodSecs"] for s in samples if s.get("samplePeriodSecs")
        )
        rt.slots_per_s = rates[len(rates) // 2] if rates else None
        while True:
            await asyncio.sleep(5)
            out = await _rpc(rt, client, "getSlot", [{"commitment": "confirmed"}], "getSlot")
            result = out.get("result") if out else None
            if isinstance(result, int):
                rt.http_tip = result
                rt.stats.on_http_tip(result, time.time())


async def loop_watchdog(rt: Runtime) -> None:
    while True:
        began = time.perf_counter()
        await asyncio.sleep(0.1)
        rt.stats.observe("event_loop_lateness_s", time.perf_counter() - began - 0.1, 0.01)
