"""T4.70b (incident 2026-09-19 18:05:32 UTC): T4.70's subscribe-at-create
hook (``event_gate_subscriptions.subscribe_at_create``) let a transient RPC
WS error escape into ``discovery._handle``'s own ``TaskGroup`` and killed the
whole meme-worker process (``ConnectionError: solana ws connection closed``
out of ``rpc_ws.py``'s own ``_send_request``). The event gate already
reconnects on its own dime (``event_gate.py``'s ``_read_loop``/
``handle_reconnect``); a failed subscribe-at-create must degrade to "this
mint is picked up by the periodic sync instead" — never a crash.

Reuses ``test_event_gate_notify.py``'s own ``FakeWs``/``_runtime``/``_create``
fixtures, exactly like ``test_event_gate_resilience.py`` reuses them.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from structlog.testing import capture_logs

from hunter_meme_worker.event_gate_subscriptions import subscribe_at_create

from .test_event_gate_notify import MINT_A, MINT_NEW, NOW, FakeWs, _create, _runtime

pytestmark = pytest.mark.unit


class _ConnectionErrorWs(FakeWs):
    """``subscribe_logs`` fails exactly like the incident: the connection
    closed mid ``_send_request`` (``rpc_ws.py:338``)."""

    async def subscribe_logs(self, *, mentions: list[str], commitment: str) -> int:
        raise ConnectionError("solana ws connection closed")


class _TimeoutWs(FakeWs):
    """``subscribe_logs`` fails the way ``asyncio.wait_for`` does when the
    RPC node never answers the subscribe request in time."""

    async def subscribe_logs(self, *, mentions: list[str], commitment: str) -> int:
        raise TimeoutError("timed out waiting for subscribe response")


class _FlakyThenFineWs(FakeWs):
    """The first mint's subscribe fails; the second one (the "next create"
    discovery must keep processing) succeeds normally."""

    def __init__(self) -> None:
        super().__init__()
        self._fail_next = True

    async def subscribe_logs(self, *, mentions: list[str], commitment: str) -> int:
        if self._fail_next:
            self._fail_next = False
            raise ConnectionError("solana ws connection closed")
        return await super().subscribe_logs(mentions=mentions, commitment=commitment)


class _CancelWs(FakeWs):
    async def subscribe_logs(self, *, mentions: list[str], commitment: str) -> int:
        raise asyncio.CancelledError()


async def test_subscribe_at_create_survives_a_connection_error() -> None:
    ws = _ConnectionErrorWs()
    rt = _runtime(ws)
    await subscribe_at_create(rt, _create(MINT_A, NOW), now=NOW)  # must not raise
    assert MINT_A not in rt.subs  # degrades to the periodic sync instead
    assert rt.stats.subscribe_at_create_failed_total == 1


async def test_subscribe_at_create_survives_a_timeout_error() -> None:
    ws = _TimeoutWs()
    rt = _runtime(ws)
    await subscribe_at_create(rt, _create(MINT_A, NOW), now=NOW)  # must not raise
    assert MINT_A not in rt.subs
    assert rt.stats.subscribe_at_create_failed_total == 1


async def test_subscribe_at_create_failure_is_logged_with_mint8_and_error_type() -> None:
    ws = _ConnectionErrorWs()
    rt = _runtime(ws)
    with capture_logs() as logs:
        await subscribe_at_create(rt, _create(MINT_A, NOW), now=NOW)
    lines = [line for line in logs if line["event"] == "meme_event_gate_subscribe_at_create_failed"]
    assert len(lines) == 1
    assert lines[0]["mint8"] == MINT_A[:8]
    assert lines[0]["error_type"] == "ConnectionError"


async def test_subscribe_at_create_keeps_processing_the_next_mint() -> None:
    ws = _FlakyThenFineWs()
    rt = _runtime(ws)
    await subscribe_at_create(rt, _create(MINT_A, NOW), now=NOW)  # fails, swallowed
    await subscribe_at_create(rt, _create(MINT_NEW, NOW), now=NOW)  # discovery kept running
    assert MINT_A not in rt.subs
    assert MINT_NEW in rt.subs
    assert rt.stats.subscribe_at_create_failed_total == 1
    assert rt.stats.subscribed_at_create_total == 1


async def test_subscribe_at_create_does_not_swallow_cancelled_error() -> None:
    ws = _CancelWs()
    rt = _runtime(ws)
    with pytest.raises(asyncio.CancelledError):
        await subscribe_at_create(rt, _create(MINT_A, NOW), now=NOW)


async def test_subscribe_at_create_failure_log_is_rate_limited() -> None:
    ws = _ConnectionErrorWs()
    rt = _runtime(ws)
    with capture_logs() as logs:
        await subscribe_at_create(rt, _create(MINT_A, NOW), now=NOW)
        await subscribe_at_create(rt, _create(MINT_NEW, NOW), now=NOW + timedelta(seconds=1))
    lines = [line for line in logs if line["event"] == "meme_event_gate_subscribe_at_create_failed"]
    assert len(lines) == 1  # second failure within the window: counted, not logged again
    assert rt.stats.subscribe_at_create_failed_total == 2
