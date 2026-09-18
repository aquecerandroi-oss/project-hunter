"""Security review T4.62 (pure, no Docker): a single bad notification, a
failing DB write on reconnect, or a crash out of ``run_event_gate`` must
never take the whole gate down — each is counted and logged, never raised.
Reuses ``test_event_gate_notify.py``'s own ``FakeWs``/``_runtime`` fixtures.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from structlog.testing import capture_logs

import hunter_meme_worker.event_gate as event_gate
import hunter_meme_worker.event_gate_eval as event_gate_eval
from hunter_exchanges.pumpfun.rpc_ws_models import SlotNotification

from .test_event_gate_notify import FakeWs, _runtime

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


class _FailingSessionCM:
    """A fake ``async_sessionmaker`` result: entering it raises, exactly
    like a ``statement_timeout``/pool exhaustion error would mid-``INSERT``."""

    async def __aenter__(self) -> Any:
        raise RuntimeError("pool exhausted: too many connections")

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def _failing_session_factory() -> _FailingSessionCM:
    return _FailingSessionCM()


# ---- handle_reconnect: a DB failure must not propagate -----------------------------


async def test_handle_reconnect_with_a_failing_session_does_not_raise() -> None:
    ws = FakeWs()
    rt = _runtime(ws)
    rt.lab = replace(rt.lab, session_factory=_failing_session_factory)  # type: ignore[arg-type]
    await event_gate_eval.handle_reconnect(rt, NOW)  # must not raise
    assert rt.stats.gap_write_failed_total == 1


async def test_handle_reconnect_failure_is_logged_with_error_type() -> None:
    ws = FakeWs()
    rt = _runtime(ws)
    rt.lab = replace(rt.lab, session_factory=_failing_session_factory)  # type: ignore[arg-type]
    with capture_logs() as logs:
        await event_gate_eval.handle_reconnect(rt, NOW)
    failures = [line for line in logs if line["event"] == "meme_event_gate_gap_write_failed"]
    assert failures and failures[0]["error_type"] == "RuntimeError"


# ---- _evaluate_loop/_flush_loop: a bad frame is counted, never a crash -------------


async def test_evaluate_loop_counts_a_bad_frame_and_keeps_running(monkeypatch: Any) -> None:
    ws = FakeWs()
    rt = _runtime(ws)
    queue: asyncio.Queue[Any] = asyncio.Queue()

    def _boom(_rt: Any, notif: Any) -> str | None:
        # Only the first (bad) frame raises -- the second must still fold
        # normally, proving the loop kept running rather than dying with it.
        if notif.slot == 1:
            raise ValueError("malformed TradeEvent: timestamp out of range")
        return None

    monkeypatch.setattr(event_gate, "apply_notification", _boom)
    # A bare SlotNotification is a legitimate frame shape; the monkeypatch
    # above is what makes folding the first one raise, standing in for a real
    # malformed ``TradeEvent`` (trade_event.py's own ``datetime.fromtimestamp``).
    bad = SlotNotification(
        subscription_id=1, kind="slot", slot=1, parent=0, root=0, received_at=NOW
    )
    good = SlotNotification(
        subscription_id=1, kind="slot", slot=2, parent=1, root=0, received_at=NOW
    )
    await queue.put(bad)
    await queue.put(good)

    task = asyncio.create_task(event_gate._evaluate_loop(rt, queue))
    try:
        for _ in range(200):  # poll instead of a fixed sleep
            if queue.empty() and rt.stats.bad_frames_total:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert rt.stats.bad_frames_total == 1


async def test_evaluate_loop_bad_frame_is_logged_with_error_type(monkeypatch: Any) -> None:
    ws = FakeWs()
    rt = _runtime(ws)
    queue: asyncio.Queue[Any] = asyncio.Queue()

    def _boom(_rt: Any, _notif: Any) -> str | None:
        raise ValueError("boom")

    monkeypatch.setattr(event_gate, "apply_notification", _boom)
    notif = SlotNotification(
        subscription_id=1, kind="slot", slot=1, parent=0, root=0, received_at=NOW
    )
    await queue.put(notif)

    async def _run_once() -> None:
        item = await queue.get()
        try:
            event_gate.apply_notification(rt, item)
        except Exception as exc:  # exercised directly: same guard as _evaluate_loop
            event_gate._log_bad_frame(rt, "meme_event_gate_bad_frame", exc, mint=None)

    with capture_logs() as logs:
        await _run_once()
    bad = [line for line in logs if line["event"] == "meme_event_gate_bad_frame"]
    assert bad and bad[0]["error_type"] == "ValueError"


# ---- run_event_gate_forever: a crash restarts, counted and logged -----------------


async def test_run_event_gate_forever_counts_and_logs_a_restart(monkeypatch: Any) -> None:
    ws = FakeWs()
    rt = _runtime(ws)
    calls = 0

    async def _fake_run_event_gate(_rt: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom api-key=FAKE1234abcd")
        return None

    monkeypatch.setattr(event_gate, "run_event_gate", _fake_run_event_gate)
    monkeypatch.setattr(event_gate, "RESTART_DELAY_S", 0)

    with capture_logs() as logs:
        await event_gate.run_event_gate_forever(rt)

    assert rt.stats.restarts_total == 1
    restarts = [line for line in logs if line["event"] == "meme_event_gate_crashed_restarting"]
    assert restarts and restarts[0]["error_type"] == "RuntimeError"
