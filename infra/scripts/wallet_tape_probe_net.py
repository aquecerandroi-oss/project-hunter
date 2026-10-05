"""Wave 0 of "seguir carteiras que ganham de verdade" — the websocket half of the probe: one connection per
program (``logsSubscribe`` ``mentions`` = the program, plus ``slotSubscribe``), a queue between the socket
and the parser, the minute snapshots and the final summary. Reconnect = exponential backoff with jitter
(cap 30 s), never a tight loop; a server refusal is recorded with its text, not retried silently.
Read-only: no transaction is ever sent, no ``.env`` is read (URLs come from argv)."""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any

import websockets
from wallet_tape_probe_audit import block_audit, settle
from wallet_tape_probe_core import log_event_counts
from wallet_tape_probe_http import loop_watchdog, sampler, tip_poller
from wallet_tape_probe_report import build_summary
from wallet_tape_probe_rt import (
    BACKOFF_BASE_S,
    BACKOFF_MAX_S,
    HTTP,
    HTTP_EVENTS,
    IDLE_S,
    PROGRAMS,
    QUEUE_MAX,
    Runtime,
)


async def reader(rt: Runtime, sub: str) -> None:
    url, program = rt.args.ws_url, PROGRAMS[sub]
    subscribe = [
        {"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
         "params": [{"mentions": [program]}, {"commitment": rt.args.commitment}]},
        {"jsonrpc": "2.0", "id": 2, "method": "slotSubscribe"},
    ]  # fmt: skip
    attempt = 0
    while True:
        try:
            async with websockets.connect(
                url, max_size=32 * 2**20, ping_interval=20, ping_timeout=30, open_timeout=15
            ) as ws:
                for req in subscribe:
                    await ws.send(json.dumps(req))
                rt.stats.on_connect(sub, time.time())
                acked = False
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=IDLE_S)
                    text = raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
                    rt.received[sub] += 1
                    rt.received_bytes[sub] += len(text)
                    if (
                        sub in rt.force_reconnect
                    ):  # a refused subscription is an outage, not a quiet socket
                        rt.force_reconnect.discard(sub)
                        raise RuntimeError("subscribe refused by the server")
                    if not acked and '"id"' in text[:40]:
                        acked = True
                        attempt = 0
                    q = rt.queues[sub]
                    try:
                        q.put_nowait((time.time(), text))
                        rt.queue_max[sub] = max(rt.queue_max[sub], q.qsize())
                    except asyncio.QueueFull:
                        rt.queue_dropped[sub] += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            now = time.time()
            if any(tag in msg for tag in ("429", "403", "401", "rate", "Too many", "refused")):
                rt.stats.on_reject(sub, now, msg)
            rt.stats.on_disconnect(sub, now, msg)
            print(f"[{now - rt.t0:8.1f}s] {sub} disconnect: {msg[:200]}", flush=True)
            attempt += 1
            await asyncio.sleep(min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2**attempt) + random.random())


def _handle(rt: Runtime, sub: str, stamp: float, text: str) -> None:
    payload = json.loads(text)
    if payload.get("id") is not None:
        if "error" in payload:
            rt.stats.on_reject(sub, stamp, f"subscribe error: {payload['error']}")
            rt.force_reconnect.add(sub)
        return
    method = payload["method"]
    result = payload["params"]["result"]
    if method == "slotNotification":
        rt.stats.on_slot(sub, int(result["slot"]), stamp)
    elif method == "logsNotification":
        value, slot = result["value"], int(result["context"]["slot"])
        sig = value["signature"]
        if len(rt.sample_frames[sub]) < 3:
            rt.sample_frames[sub].append(text[:8000])
        facts = rt.stats.on_logs(sub, slot, sig, value.get("err"), value["logs"], len(text), stamp)
        if rt.args.audit_every > 0:
            rt.sigs[sub].setdefault(slot, set()).add(sig)
        if value.get("err") is None and facts.events and random.random() < 0.01:
            rt.sample_candidates.append((stamp, sub, sig, dict(log_event_counts(facts)), slot))


async def worker(rt: Runtime, sub: str) -> None:
    q = rt.queues[sub]
    while True:
        stamp, text = await q.get()
        began = time.perf_counter()
        rt.stats.on_frame(sub, len(text))
        rt.stats.observe(f"queue_age_s.{sub}", time.time() - stamp, 0.1)
        try:
            _handle(rt, sub, stamp, text)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            rt.malformed[sub] += 1
        finally:
            rt.processed[sub] += 1
            rt.busy_s[sub] += time.perf_counter() - began
            q.task_done()


def _rss_mb() -> float | None:
    try:
        import psutil  # type: ignore[import-not-found,unused-ignore]

        return float(psutil.Process().memory_info().rss) / 2**20
    except Exception:
        return None


def chain_truth(rt: Runtime) -> dict[str, Any]:
    """What the chain really emitted, read from the audited blocks (independent of the websocket):
    per-block averages times the MEASURED slot rate (``getRecentPerformanceSamples``; 3.73 slots/s on
    05/10, not the 2.5 of a 400 ms slot). Few sampled blocks = a wide error: the stream is the better
    estimate while it is healthy."""
    t = rt.audit["truth"]
    slots = t["blocks_ok"]
    if not slots or rt.slots_per_s is None:
        return {}
    out: dict[str, Any] = {"blocks_ok": slots, "slots_per_s_measured": rt.slots_per_s}
    for sub in PROGRAMS:
        per_s = {k: v / slots * rt.slots_per_s for k, v in t[sub]["events"].items()}
        out[sub] = {
            "mentioning_tx_per_s": t[sub]["txs"] / slots * rt.slots_per_s,
            "successful_mentioning_tx_per_s": t[sub]["success_txs"] / slots * rt.slots_per_s,
            "events_per_s": per_s,
            "events_per_day": {k: round(v * 86400) for k, v in per_s.items()},
        }
    return out


def summary_of(rt: Runtime, now: float) -> dict[str, Any]:
    el = max(1.0, now - rt.t0)
    pipeline: dict[str, Any] = {
        "received_frames": dict(rt.received),
        "received_bytes": dict(rt.received_bytes),
        "processed_frames": dict(rt.processed),
        "queue_max_depth": dict(rt.queue_max),
        "queue_dropped": dict(rt.queue_dropped),
        "queue_residual_at_end": {s: q.qsize() for s, q in rt.queues.items()},
        "worker_busy_share": {s: v / el for s, v in rt.busy_s.items()},
        "malformed_frames": dict(rt.malformed),
        "process_cpu_share_of_one_core": time.process_time() / el,
        "rss_mb": _rss_mb(),
    }
    meta: dict[str, Any] = {
        "chain_truth_from_block_audit": chain_truth(rt),
        "ws_url_host": rt.args.ws_url.split("//")[-1].split("/")[0],
        "commitment": rt.args.commitment,
        "getTransaction_sampler": rt.sampler
        | {"http": dict(HTTP), "http_events": HTTP_EVENTS[-20:]},
        "independent_block_audit": rt.audit,
        "pipeline": pipeline,
    }
    return build_summary(rt.stats, rt.t0, now, meta)


async def reporter(rt: Runtime) -> None:
    n = 0
    while True:
        await asyncio.sleep(60)
        n += 1
        now = time.time()
        point = rt.stats.distinct_point(now)
        snap = rt.stats.snapshot(now)
        with (rt.out / "snapshots.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"point": point, "queue": {s: q.qsize() for s, q in rt.queues.items()},
                                 "snapshot": snap}) + "\n")  # fmt: skip
        if n % 5 == 0:
            (rt.out / "summary.json").write_text(
                json.dumps(summary_of(rt, now), indent=1), encoding="utf-8"
            )
        notif = snap["notifications"]
        tip = snap["lag_slots_vs_http_tip"]
        print(
            f"[{now - rt.t0:7.0f}s] notif pump={notif.get('pump', {}).get('n', 0)} "
            f"amm={notif.get('amm', {}).get('n', 0)} wallets={point['wallets_all']} "
            f"lag_vs_http p50 pump={tip.get('pump', {}).get('p50')} amm={tip.get('amm', {}).get('p50')} "
            f"disconnects={ {s: r['disconnects'] for s, r in snap['reconnects'].items()} }",
            flush=True,
        )


async def run(rt: Runtime) -> None:
    for sub in PROGRAMS:
        rt.queues[sub] = asyncio.Queue(maxsize=QUEUE_MAX)
    readers = [asyncio.create_task(reader(rt, s)) for s in PROGRAMS]
    workers = [asyncio.create_task(worker(rt, s)) for s in PROGRAMS]
    side = [
        asyncio.create_task(f(rt))
        for f in (sampler, tip_poller, block_audit, loop_watchdog, reporter)
    ]
    try:
        while (
            time.time() - rt.t0 < rt.args.seconds
        ):  # wall clock; a suspension is flagged, not hidden
            await asyncio.sleep(5)
            rt.stats.on_tick(time.time(), 5.0)
    finally:
        for t in readers + side:  # stop intake first, then drain what is already queued
            t.cancel()
        await asyncio.gather(*readers, *side, return_exceptions=True)
        try:
            await asyncio.wait_for(asyncio.gather(*(q.join() for q in rt.queues.values())), 60)
        except TimeoutError:
            print("queue did not drain in 60 s", flush=True)
        for t in workers:
            t.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        now = time.time()
        settle(rt, now, final=True)
        rt.stats.distinct_point(now)
        rt.stats.flush(now)  # natural expiry only: a tx still inside the window stays uncounted
        (rt.out / "summary.json").write_text(
            json.dumps(summary_of(rt, now), indent=1), encoding="utf-8"
        )
        (rt.out / "samples.json").write_text(
            json.dumps(
                {"frames": rt.sample_frames, "undecodable": rt.stats.undecodable_samples}, indent=1
            ),
            encoding="utf-8",
        )
        print("DONE", rt.out / "summary.json", flush=True)
