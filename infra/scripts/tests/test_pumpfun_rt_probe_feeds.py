"""Unit tests for the NATS feed of ``infra/scripts/pumpfun_rt_probe_feeds.py`` against a loopback NATS-over-
WebSocket server that speaks just enough protocol (INFO, CONNECT+PING -> PONG, SUB, UNSUB, MSG, -ERR).
Offline: nothing leaves the machine; the credential is a placeholder.

Run:
    uv run --no-sync pytest infra/scripts/tests/test_pumpfun_rt_probe_feeds.py -q
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from websockets.asyncio.server import ServerConnection, serve

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:  # the layout every script in this folder uses
    sys.path.insert(0, str(SCRIPTS_DIR))

from pumpfun_rt_probe_conv import conv_unified  # noqa: E402  (path surgery must come first)
from pumpfun_rt_probe_feeds import NatsFeed  # noqa: E402
from pumpfun_rt_probe_io import Ctx, Recorder  # noqa: E402
from pumpfun_rt_probe_nats import NatsConfig  # noqa: E402

CREATE = {"slot_index_id": "00045377553700023900000002", "tx": "SIG1", "mint": "M1", "program": "pump",
          "created_timestamp": "2026-10-06T03:06:42+00:00"}  # fmt: skip


def _msg(subject: str, sid: int, body: dict[str, Any]) -> bytes:
    raw = json.dumps(body).encode()
    return b"MSG %s %d %d\r\n%s\r\n" % (subject.encode(), sid, len(raw), raw)


async def test_feed_connects_subscribes_decodes_and_unsubscribes(tmp_path: Path) -> None:
    seen_lines: list[str] = []
    connect_body: dict[str, Any] = {}

    async def server(ws: ServerConnection) -> None:
        await ws.send(b'INFO {"auth_required":true}\r\n')
        buf = ""
        while True:
            try:
                data = await ws.recv()
            except Exception:
                return
            buf += data.decode() if isinstance(data, bytes) else data
            while "\r\n" in buf:
                line, buf = buf.split("\r\n", 1)
                seen_lines.append(line)
                if line.startswith("CONNECT "):
                    connect_body.update(json.loads(line[8:]))
                elif line == "PING":
                    await ws.send(b"PONG\r\n")
                elif line.startswith("SUB unifiedCoinCreationEvent"):
                    await ws.send(_msg("unifiedCoinCreationEvent", 1, CREATE))

    ctx = Ctx(rec=Recorder(tmp_path), stop=asyncio.Event())
    async with serve(server, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        feed = NatsFeed(ctx, "nats_u", NatsConfig(f"ws://127.0.0.1:{port}", "subscriber", "PW"),
                        ["unifiedCoinCreationEvent"], conv_unified)  # fmt: skip
        hooked: list[tuple[str, str]] = []

        async def hook(t: float, kind: str, extra: dict[str, Any]) -> None:
            hooked.append((kind, str(extra["mint"])))
            await feed.sub("unifiedTradeEvent.processed.M1")

        feed.hook = hook
        run = asyncio.create_task(feed.run())
        for _ in range(100):
            if any(line.startswith("SUB unifiedTradeEvent.processed.M1") for line in seen_lines):
                break
            await asyncio.sleep(0.05)
        await feed.unsub("unifiedTradeEvent.processed.M1")
        await asyncio.sleep(0.2)
        ctx.stop.set()
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)
    ctx.rec.close()
    assert connect_body["user"] == "subscriber" and connect_body["pass"] == "PW"
    assert hooked == [("create", "M1")]
    assert any(line.startswith("SUB unifiedTradeEvent.processed.M1 ") for line in seen_lines)
    assert any(line.startswith("UNSUB ") for line in seen_lines)
    events = [json.loads(x) for x in (tmp_path / "events.jsonl").read_text().splitlines()]
    creates = [e for e in events if e["k"] == "create"]
    assert creates[0]["id"] == "SIG1" and creates[0]["slot"] == 453775537
    assert "PW" not in (tmp_path / "events.jsonl").read_text()


async def test_auth_violation_stops_the_feed_as_requires_auth(tmp_path: Path) -> None:
    async def server(ws: ServerConnection) -> None:
        await ws.send(b'INFO {"auth_required":true}\r\n')
        await ws.recv()
        await ws.send(b"-ERR 'Authorization Violation'\r\n")
        await ws.wait_closed()

    ctx = Ctx(rec=Recorder(tmp_path), stop=asyncio.Event())
    async with serve(server, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        feed = NatsFeed(
            ctx,
            "nats_u",
            NatsConfig(f"ws://127.0.0.1:{port}", "subscriber", "PW"),
            [],
            conv_unified,
        )
        await asyncio.wait_for(feed.run(), timeout=10)
    ctx.rec.close()
    assert ctx.rec.refused["nats_u"].startswith("requires auth")


async def test_a_permissions_violation_drops_that_subject_and_keeps_the_session(
    tmp_path: Path,
) -> None:
    async def server(ws: ServerConnection) -> None:
        await ws.send(b'INFO {"auth_required":true}\r\n')
        async for data in ws:
            text = data.decode() if isinstance(data, bytes) else data
            if "PING" in text:
                await ws.send(b"PONG\r\n")
            if "SUB secret.thing" in text:
                await ws.send(
                    b"-ERR 'Permissions Violation for Subscription to \"secret.thing\"'\r\n"
                )

    ctx = Ctx(rec=Recorder(tmp_path), stop=asyncio.Event())
    async with serve(server, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        feed = NatsFeed(ctx, "nats_c", NatsConfig(f"ws://127.0.0.1:{port}", "subscriber", "PW"),
                        ["secret.thing"], conv_unified)  # fmt: skip
        run = asyncio.create_task(feed.run())
        for _ in range(100):
            if ctx.rec.counts["nats_c.sys"] >= 3:
                break
            await asyncio.sleep(0.05)
        ctx.stop.set()
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)
    ctx.rec.close()
    assert "secret.thing" not in feed.desired and ctx.rec.refused == {}


async def test_unsub_on_a_dead_socket_does_not_raise_and_a_failing_hook_does_not_kill_the_feed(
    tmp_path: Path,
) -> None:
    ctx = Ctx(rec=Recorder(tmp_path), stop=asyncio.Event())
    feed = NatsFeed(
        ctx, "nats_u", NatsConfig("ws://127.0.0.1:1", "subscriber", "PW"), [], conv_unified
    )

    class Dead:
        async def send(self, data: bytes) -> None:
            raise ConnectionError("socket closed")

    feed.ws, feed.ready = Dead(), True
    feed.sids["x"] = 1
    feed.desired.append("x")
    await feed.unsub("x")  # must not raise
    assert feed.ready is False and "x" not in feed.desired

    async def bad_hook(t: float, kind: str, extra: dict[str, Any]) -> None:
        raise RuntimeError("hook bug")

    feed.hook = bad_hook
    feed.ready = False
    await feed.on_frame(1.0, _msg("unifiedCoinCreationEvent", 1, CREATE), None)  # must not raise
    ctx.rec.close()
    errs = [json.loads(x) for x in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert any(e["id"] == "hook_error" for e in errs)
