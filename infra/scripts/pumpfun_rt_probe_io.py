"""pump.fun realtime latency probe (2026-10-06) — the IO plumbing every feed shares: the event recorder,
the loop watchdog (a frozen loop or a sleeping laptop must not be read as a slow source), the clock-skew
sampler against ``pump.fun/api/server-time`` and a WebSocket loop with heartbeat, backoff + jitter and a
hard stop on a refusal (HTTP 403/418/429 or a NATS auth error is recorded as a ``system_event`` and that
source stops: no silent retry loop, nothing evaded). Read-only: nothing is ever signed or sent to a chain.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import websockets
from websockets.exceptions import InvalidStatus

BACKOFF_BASE_S, BACKOFF_MAX_S = 1.0, 30.0
REFUSAL_STATUS = frozenset({401, 403, 418, 429})
SERVER_TIME_URL = "https://pump.fun/api/server-time"
STALL_S = 3.0


class Refused(Exception):
    """The remote said no (rate limit, block, auth). The source stops; it is recorded, not retried."""


class Recorder:
    """``events.jsonl`` (one line per observed frame) plus counters; flushed by ``flusher``."""

    def __init__(self, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        self.out = out
        # "x": never truncate an earlier capture (FileExistsError)
        self._fh = (out / "events.jsonl").open("x", encoding="utf-8", buffering=1 << 16)
        self.counts: Counter[str] = Counter()
        self.samples: dict[str, list[str]] = {}
        self.refused: dict[str, str] = {}
        self.last_frame: dict[str, float] = {}

    def rec(self, s: str, k: str, id_: str, t: float, **extra: Any) -> None:
        self.counts[f"{s}.{k}"] += 1
        self._fh.write(
            json.dumps({"s": s, "k": k, "id": id_, "t": t, **extra}, separators=(",", ":")) + "\n"
        )

    def sys(self, s: str, what: str, **extra: Any) -> None:
        self.rec(s, "sys", what, time.time(), **extra)

    def sample(self, key: str, raw: str, *, keep: int = 4, width: int = 5000) -> None:
        got = self.samples.setdefault(key, [])
        if len(got) < keep:
            got.append(raw[:width])

    async def flusher(self) -> None:
        while True:
            await asyncio.sleep(2.0)
            self._fh.flush()

    def close(self) -> None:
        self._fh.flush()
        self._fh.close()
        (self.out / "samples.json").write_text(json.dumps(self.samples, indent=1), encoding="utf-8")


@dataclass
class Ctx:
    rec: Recorder
    stop: asyncio.Event
    lags: list[float] = field(default_factory=lambda: list[float]())
    stalls: list[tuple[float, float]] = field(default_factory=lambda: list[tuple[float, float]]())


async def guarded(ctx: Ctx, name: str, coro: Awaitable[None]) -> None:
    """Run a task so that an unexpected crash is recorded at once (not found at shutdown) and the other
    feeds keep running."""
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        ctx.rec.sys(name, "crashed", text=f"{type(exc).__name__}: {str(exc)[:300]}")


async def watchdog(ctx: Ctx) -> None:
    """Loop lag (a 0.1 s timer's overshoot) and wall-clock gaps (>3 s = sleep or freeze)."""
    last_wall = time.time()
    while not ctx.stop.is_set():
        mono = time.monotonic()
        await asyncio.sleep(0.1)
        now = time.time()
        ctx.lags.append(max(0.0, time.monotonic() - mono - 0.1))
        if now - last_wall > STALL_S:
            ctx.stalls.append((last_wall, now))
            ctx.rec.rec("sys", "stall", f"stall{len(ctx.stalls)}", now, t_from=last_wall)
        last_wall = now


async def clock_sampler(ctx: Ctx, *, every_s: float = 120.0) -> None:
    """offset = server_ms/1000 - midpoint(local send, local recv); positive = our clock runs behind."""
    n = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        while not ctx.stop.is_set():
            t_send = time.time()
            try:
                r = await client.get(SERVER_TIME_URL)
                t_recv = time.time()
                if r.status_code in REFUSAL_STATUS:
                    ctx.rec.refused["clock"] = f"HTTP {r.status_code}"
                    ctx.rec.sys("clock", "refused", status=r.status_code)
                    return
                now_ms = r.json()["nowMs"]
                n += 1
                ctx.rec.rec("clock", "sample", f"c{n}", t_recv, offset=now_ms / 1000 - (t_send + t_recv) / 2,
                            rtt=t_recv - t_send)  # fmt: skip
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                ctx.rec.sys("clock", "error", text=str(exc)[:200])
            await _sleep_or_stop(ctx, every_s)


async def _sleep_or_stop(ctx: Ctx, seconds: float) -> None:
    try:
        await asyncio.wait_for(ctx.stop.wait(), seconds)
    except TimeoutError:
        pass


OnOpen = Callable[[Any], Awaitable[None]]
OnFrame = Callable[[float, "str | bytes", Any], Awaitable[None]]


async def run_ws(
    ctx: Ctx, name: str, url: str, on_open: OnOpen, on_frame: OnFrame, *, idle_s: float = 60.0,
    max_size: int = 8_000_000,
) -> None:  # fmt: skip
    """Connect, ``on_open``, then hand every frame to ``on_frame`` with the arrival time taken first.
    Reconnect with exponential backoff and jitter; stop for good on a refusal."""
    attempt = 0
    rec = ctx.rec
    while not ctx.stop.is_set():
        try:
            async with websockets.connect(
                url,
                open_timeout=15,
                max_size=max_size,
                ping_interval=20,
                ping_timeout=30,
                max_queue=None,
            ) as ws:
                rec.sys(name, "connect", attempt=attempt)
                await on_open(ws)
                got_frame = False
                while not ctx.stop.is_set():
                    raw = await asyncio.wait_for(ws.recv(), timeout=idle_s)
                    t = time.time()
                    if not got_frame:
                        got_frame, attempt = True, 0
                    rec.last_frame[name] = t
                    await on_frame(t, raw, ws)
        except Refused as exc:
            rec.refused[name] = str(exc)
            rec.sys(name, "refused", text=str(exc)[:300])
            return
        except InvalidStatus as exc:
            status = exc.response.status_code
            if status in REFUSAL_STATUS:
                rec.refused[name] = f"handshake HTTP {status}"
                rec.sys(name, "refused", status=status)
                return
            rec.sys(name, "error", text=f"handshake HTTP {status}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            rec.sys(name, "disconnect", text=f"{type(exc).__name__}: {str(exc)[:200]}")
        if ctx.stop.is_set():
            return
        delay = min(BACKOFF_BASE_S * 2**attempt, BACKOFF_MAX_S) * (0.5 + random.random())
        attempt += 1
        rec.sys(name, "backoff", delay=round(delay, 2))
        await _sleep_or_stop(ctx, delay)
