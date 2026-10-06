"""Unit tests for ``infra/scripts/pumpfun_rt_probe_io.py`` — the recorder and the WebSocket loop of the
pump.fun realtime latency probe (2026-10-06). Offline: a loopback ``websockets`` server stands in for every
remote; nothing leaves the machine.

Run:
    uv run --no-sync pytest infra/scripts/tests/test_pumpfun_rt_probe_io.py -q
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from websockets.asyncio.server import ServerConnection, serve
from websockets.http11 import Request, Response

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:  # the layout every script in this folder uses
    sys.path.insert(0, str(SCRIPTS_DIR))

import pumpfun_rt_probe_io as io  # noqa: E402  (path surgery must come first)


def _ctx(tmp_path: Path) -> io.Ctx:
    return io.Ctx(rec=io.Recorder(tmp_path), stop=asyncio.Event())


def _events(tmp_path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in (tmp_path / "events.jsonl").read_text().splitlines()]


def test_recorder_writes_one_json_line_per_event_and_counts_by_source_and_kind(
    tmp_path: Path,
) -> None:
    rec = io.Recorder(tmp_path)
    rec.rec("nats_u", "create", "SIG1", 100.5, mint="M1")
    rec.rec("nats_u", "create", "SIG2", 100.7)
    rec.rec("pp", "create", "SIG1", 100.9)
    rec.sample("pp", "x" * 9000, keep=1, width=10)
    rec.sample("pp", "second", keep=1)
    rec.close()
    lines = _events(tmp_path)
    assert lines[0] == {"s": "nats_u", "k": "create", "id": "SIG1", "t": 100.5, "mint": "M1"}
    assert rec.counts["nats_u.create"] == 2 and rec.counts["pp.create"] == 1
    assert json.loads((tmp_path / "samples.json").read_text()) == {"pp": ["x" * 10]}


async def test_a_429_on_the_handshake_stops_the_source_and_records_it_without_retrying(
    tmp_path: Path,
) -> None:
    attempts = 0

    def deny(conn: ServerConnection, request: Request) -> Response | None:
        nonlocal attempts
        attempts += 1
        return conn.respond(429, "slow down\n")

    async def handler(ws: ServerConnection) -> None:  # never reached
        await ws.wait_closed()

    async def noop_open(ws: Any) -> None:  # pragma: no cover
        return None

    async def noop_frame(t: float, raw: str | bytes, ws: Any) -> None:  # pragma: no cover
        return None

    ctx = _ctx(tmp_path)
    async with serve(handler, "127.0.0.1", 0, process_request=deny) as server:
        port = server.sockets[0].getsockname()[1]
        await asyncio.wait_for(
            io.run_ws(ctx, "src", f"ws://127.0.0.1:{port}", noop_open, noop_frame), timeout=10
        )
    ctx.rec.close()
    assert attempts == 1
    assert ctx.rec.refused == {"src": "handshake HTTP 429"}
    assert [e["id"] for e in _events(tmp_path) if e["k"] == "sys"] == ["refused"]


async def test_a_dropped_connection_reconnects_with_backoff_and_frames_are_stamped_on_arrival(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(io, "BACKOFF_BASE_S", 0.05)
    connections = 0

    async def handler(ws: ServerConnection) -> None:
        nonlocal connections
        connections += 1
        await ws.send(f"hello{connections}")
        if connections == 1:
            await ws.close()  # the drop
        else:
            await ws.wait_closed()

    ctx = _ctx(tmp_path)
    got: list[tuple[float, str]] = []

    async def on_open(ws: Any) -> None:
        return None

    async def on_frame(t: float, raw: str | bytes, ws: Any) -> None:
        got.append((t, str(raw)))
        if len(got) == 2:
            ctx.stop.set()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        await asyncio.wait_for(
            io.run_ws(ctx, "src", f"ws://127.0.0.1:{port}", on_open, on_frame), timeout=10
        )
    ctx.rec.close()
    assert [g[1] for g in got] == ["hello1", "hello2"] and got[1][0] > got[0][0]
    sys_ids = [e["id"] for e in _events(tmp_path) if e["k"] == "sys"]
    assert sys_ids.count("connect") == 2 and "backoff" in sys_ids and "disconnect" in sys_ids


async def test_refused_raised_by_a_frame_handler_is_recorded_and_stops_the_source(
    tmp_path: Path,
) -> None:
    async def handler(ws: ServerConnection) -> None:
        await ws.send("-ERR 'Authorization Violation'")
        await ws.wait_closed()

    async def on_open(ws: Any) -> None:
        return None

    async def on_frame(t: float, raw: str | bytes, ws: Any) -> None:
        raise io.Refused("requires auth")

    ctx = _ctx(tmp_path)
    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        await asyncio.wait_for(
            io.run_ws(ctx, "nats", f"ws://127.0.0.1:{port}", on_open, on_frame), timeout=10
        )
    ctx.rec.close()
    assert ctx.rec.refused == {"nats": "requires auth"}


def test_recorder_refuses_to_overwrite_an_earlier_capture(tmp_path: Path) -> None:
    io.Recorder(tmp_path).close()
    with pytest.raises(FileExistsError):
        io.Recorder(tmp_path)


async def test_guarded_records_a_crash_instead_of_leaving_it_to_be_read_at_shutdown(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path)

    async def boom() -> None:
        raise RuntimeError("expiry died")

    await io.guarded(ctx, "nats_u.expiry", boom())
    ctx.rec.close()
    crashed = [e for e in _events(tmp_path) if e["id"] == "crashed"]
    assert crashed and "expiry died" in crashed[0]["text"] and crashed[0]["s"] == "nats_u.expiry"
