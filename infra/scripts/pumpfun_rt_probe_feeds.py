"""pump.fun realtime latency probe (2026-10-06) — the five feeds, one connection each (trenches: one per
board). All anonymous, all read-only, the same access an anonymous visitor of the site has:

* ``nats_u``  — ``wss://unified-prod.nats.realtime.pump.fun``: ``unifiedCoinCreationEvent`` (every new coin) and,
  for a bounded set of just-created coins, ``unifiedTradeEvent.processed.<mint>`` / ``.lite.<mint>``;
* ``nats_c``  — ``wss://prod-v2.nats.realtime.pump.fun`` (the site's ``CORE`` instance): ``account_balance_change.<wallet>.*``
  for a bounded set of wallets seen trading those coins;
* ``pp``      — PumpPortal's free ``subscribeNewToken`` / ``subscribeMigration`` (no key);
* ``rpc``     — the Solana public RPC ``logsSubscribe`` on the pump program at ``processed`` (the chain reference);
* ``tr_new`` / ``tr_grad`` — the site's ``/ws/trenches`` boards ``new`` and ``graduated``.

The reader stamps ``time.time()`` the instant a frame wakes it, before any parsing.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any
from urllib.parse import quote

import httpx
from pumpfun_rt_probe_conv import (
    CREATION_SUBJECT,
    as_list,
    as_obj,
    conv_core,
    conv_pumpportal,
    conv_rpc_logs,
    conv_trenches,
    conv_unified,
)
from pumpfun_rt_probe_io import REFUSAL_STATUS, Ctx, Refused, guarded, run_ws
from pumpfun_rt_probe_nats import (
    HOME_URL,
    NatsConfig,
    NatsParser,
    classify_err,
    connect_line,
    decode_payload,
    site_nats_configs,
)
from pumpfun_rt_probe_sel import MintPlan, WalletPlan
from wallet_tape_probe_core import PUMP

PUMPPORTAL_WS = "wss://pumpportal.fun/api/data"
RPC_WS = "wss://api.mainnet-beta.solana.com"
TRENCHES_WS = "wss://advanced-indexer.pump.fun/ws/trenches"


async def fetch_nats_configs(ctx: Ctx) -> dict[str, NatsConfig]:
    """The anonymous home page is where the site's own client gets its NATS credential."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.get(HOME_URL)
    if r.status_code in REFUSAL_STATUS:
        ctx.rec.refused["home"] = f"HTTP {r.status_code}"
        raise Refused(f"home page HTTP {r.status_code}")
    return site_nats_configs(r.text)


def _subject_family(subject: str) -> str:
    """``unifiedTradeEvent.processed`` / ``.lite`` apart; per-wallet and per-coin tails dropped."""
    parts = subject.split(".")
    return ".".join(parts[:2]) if parts[0] == "unifiedTradeEvent" else parts[0]


class NatsFeed:
    """One NATS-over-WS connection. ``on_event(t, subject, payload)`` is called per decoded message."""

    def __init__(self, ctx: Ctx, name: str, cfg: NatsConfig, initial: list[str], conv: Any) -> None:
        self.ctx, self.name, self.cfg, self.conv = ctx, name, cfg, conv
        self.desired: list[str] = list(initial)
        self.sids: dict[str, int] = {}
        self.ws: Any = None
        self.ready = False
        self.parser = NatsParser()
        self.hook: Any = None
        self._sid = 0

    async def _send(self, text: str, *, strict: bool = False) -> None:
        """A failed send marks the session not ready (the reconnect re-subscribes ``desired``); only the
        handshake send is strict, so a dead socket surfaces to ``run_ws`` there."""
        if self.ws is None:
            return
        try:
            await self.ws.send(text.encode())
        except Exception as exc:
            if strict:
                raise
            self.ready = False
            self.ctx.rec.sys(
                self.name, "send_failed", text=f"{type(exc).__name__}: {str(exc)[:160]}"
            )

    async def sub(self, subject: str) -> None:
        if subject not in self.desired:
            self.desired.append(subject)
        if self.ready and subject not in self.sids:
            await self._sub_now(subject)

    async def _sub_now(self, subject: str) -> None:
        self._sid += 1
        self.sids[subject] = self._sid
        self.ctx.rec.rec(self.name, "sub", subject, time.time())
        await self._send(f"SUB {subject} {self._sid}\r\n")

    async def unsub(self, subject: str) -> None:
        if subject in self.desired:
            self.desired.remove(subject)
        sid = self.sids.pop(subject, None)
        if sid is not None and self.ready:
            self.ctx.rec.rec(self.name, "unsub", subject, time.time())
            await self._send(f"UNSUB {sid}\r\n")

    async def on_open(self, ws: Any) -> None:
        self.ws, self.ready, self.parser, self.sids = ws, False, NatsParser(), {}
        info = await asyncio.wait_for(
            ws.recv(), timeout=15
        )  # like the site's worker: INFO, then CONNECT
        self.parser.push(info if isinstance(info, bytes) else info.encode())
        await self._send(connect_line(self.cfg), strict=True)

    async def on_frame(self, t: float, raw: str | bytes, ws: Any) -> None:
        data = raw if isinstance(raw, bytes) else raw.encode()
        for op in self.parser.push(data):
            if op.kind == "ping":
                await self._send("PONG\r\n")
            elif op.kind == "pong" and not self.ready:
                self.ready = True
                self.ctx.rec.sys(self.name, "ready")
                for subject in list(self.desired):
                    await self._sub_now(subject)
            elif op.kind == "err":
                kind = classify_err(op.text)
                self.ctx.rec.sys(self.name, "err", kind=kind, text=op.text[:200])
                if kind == "auth":
                    raise Refused(f"requires auth: {op.text[:120]}")
                if kind in ("permissions", "subscription_limit"):
                    await self._drop_refused(op.text)
            elif op.kind == "msg":
                payload = decode_payload(op.payload)
                if payload is None:
                    self.ctx.rec.counts[f"{self.name}.malformed"] += 1
                    continue
                self.ctx.rec.sample(
                    f"{self.name}:{_subject_family(op.subject)}", json.dumps(payload)
                )
                got = self.conv(op.subject, payload)
                if got is not None:
                    kind_, id_, extra = got
                    self.ctx.rec.rec(self.name, kind_, id_, t, **extra)
                    if self.hook is not None:
                        try:
                            await self.hook(t, kind_, extra)
                        except Exception as exc:  # a planning bug must not take the feed down
                            self.ctx.rec.sys(
                                self.name,
                                "hook_error",
                                text=f"{type(exc).__name__}: {str(exc)[:160]}",
                            )

    async def _drop_refused(self, text: str) -> None:
        for subject in list(self.sids):
            if f'"{subject}"' in text:
                self.sids.pop(subject, None)
                if subject in self.desired:
                    self.desired.remove(subject)

    async def heartbeat(self) -> None:
        """Client PING every 20 s (the site pings every 5 s): a silent socket must still show traffic."""
        while not self.ctx.stop.is_set():
            await asyncio.sleep(20.0)
            if self.ready:
                # a dead socket is run_ws's to notice and reconnect
                with contextlib.suppress(Exception):
                    await self._send("PING\r\n")

    async def run(self) -> None:
        beat = asyncio.create_task(self.heartbeat())
        try:
            await run_ws(
                self.ctx, self.name, self.cfg.servers, self.on_open, self.on_frame, idle_s=60.0
            )
        finally:
            beat.cancel()


async def run_nats(
    ctx: Ctx, cfgs: dict[str, NatsConfig], mints: MintPlan, wallets: WalletPlan
) -> None:
    """The site's two default instances: UNIFIED (coins, trades) and CORE (per-wallet balance changes)."""
    unified = NatsFeed(ctx, "nats_u", cfgs["UNIFIED"], [CREATION_SUBJECT], conv_unified)
    core = NatsFeed(ctx, "nats_c", cfgs["CORE"], [], conv_core)

    async def on_unified(t: float, kind: str, extra: dict[str, Any]) -> None:
        if kind == "create" and extra.get("program") == "pump" and extra.get("mint"):
            for subject in mints.on_creation(str(extra["mint"]), now=t):
                await unified.sub(subject)
        elif kind == "trade" and extra.get("user"):
            subject = wallets.on_trade(str(extra["user"]))
            if subject:
                await core.sub(subject)

    unified.hook = on_unified

    async def expiry() -> None:
        while not ctx.stop.is_set():
            await asyncio.sleep(5.0)
            for subject in mints.expire(now=time.time()):
                await unified.unsub(subject)

    await asyncio.gather(
        guarded(ctx, "nats_u", unified.run()),
        guarded(ctx, "nats_c", core.run()),
        guarded(ctx, "nats_u.expiry", expiry()),
    )


async def run_pumpportal(ctx: Ctx) -> None:
    async def on_open(ws: Any) -> None:
        await ws.send(json.dumps({"method": "subscribeNewToken"}))
        await ws.send(json.dumps({"method": "subscribeMigration"}))

    async def on_frame(t: float, raw: str | bytes, ws: Any) -> None:
        try:
            msg = as_obj(json.loads(raw))
        except ValueError:
            ctx.rec.counts["pp.malformed"] += 1
            return
        ctx.rec.sample("pp", raw if isinstance(raw, str) else raw.decode("utf-8", "replace"))
        got = conv_pumpportal(msg)
        if got is not None:
            ctx.rec.rec("pp", got[0], got[1], t, **got[2])

    await run_ws(ctx, "pp", PUMPPORTAL_WS, on_open, on_frame, idle_s=120.0)


async def run_rpc_logs(ctx: Ctx, ws_url: str = RPC_WS, commitment: str = "processed") -> None:
    params = [{"mentions": [PUMP]}, {"commitment": commitment}]

    async def on_open(ws: Any) -> None:
        await ws.send(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe", "params": params})
        )

    async def on_frame(t: float, raw: str | bytes, ws: Any) -> None:
        try:
            msg = as_obj(json.loads(raw))
        except ValueError:
            ctx.rec.counts["rpc.malformed"] += 1
            return
        if "error" in msg:
            err_text = json.dumps(msg["error"])
            ctx.rec.sys("rpc", "err", text=err_text[:300])
            raise Refused(f"rpc error {err_text[:120]}")
        ctx.rec.counts["rpc.bytes"] += len(raw)
        fact = conv_rpc_logs(msg)
        if fact is None:
            ctx.rec.sample("rpc:ack", json.dumps(msg)[:300])
            return
        if fact["err"]:  # a failed tx is no chain event for any other source: counted, not written
            ctx.rec.counts["rpc.logs_err"] += 1
            return
        extra = {
            k: v for k, v in fact.items() if k not in ("id", "err") and v not in (False, [], None)
        }
        ctx.rec.rec("rpc", "logs", fact["id"], t, **extra)

    await run_ws(ctx, "rpc", ws_url, on_open, on_frame, idle_s=60.0, max_size=32 * 2**20)


async def run_trenches(ctx: Ctx, board: str, name: str) -> None:
    sub = {"board": board, "tier": "web", "filterKey": "default"}
    url = TRENCHES_WS + "?subscription=" + quote(json.dumps(sub, separators=(",", ":")), safe="")
    hello = {
        "event": "subscribe",
        "data": {"board": board, "tier": "web", "platform": "WEB", "surface": "WEB"},
    }

    async def on_open(ws: Any) -> None:
        await ws.send(json.dumps(hello))

    async def on_frame(t: float, raw: str | bytes, ws: Any) -> None:
        try:
            msg = as_obj(json.loads(raw))
        except ValueError:
            ctx.rec.counts[f"{name}.malformed"] += 1
            return
        ctx.rec.counts[f"{name}.patches"] += len(as_list(msg.get("patches")))
        for kind, id_, extra in conv_trenches(board, msg):
            ctx.rec.rec(name, kind, id_, t, **extra)
        if msg.get("type") == "delta":
            ctx.rec.sample(name, json.dumps(msg)[:2500], keep=2)

    await run_ws(ctx, name, url, on_open, on_frame, idle_s=90.0)
