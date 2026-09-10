"""``_drain`` refuses to pop a queued request while the live lane is degraded (T3.74).

``budget.live_lane_degraded`` existed, was tested and was documented as the
gate checked "before every slice" — but nothing on the replay CLI's actual
execution path ever called it (grep, 2026-09-10: only tests imported it), so a
queue drain kept taking slices at full ``ReplayBudget`` while the live
decision lag climbed past two minutes on 2026-09-09/10. These tests exercise
the wiring itself, not :func:`hunter_strategy_worker.replay.budget.live_lane_degraded`
(covered by ``test_replay_contract.py::TestReadinessGate``): the thing that
was missing was the *call*, so the thing under test is the call site.

No Postgres, no real Redis: ``create_engine``/``create_session_factory`` are
faked because ``_drain`` builds them unconditionally before the loop, and
``take_next`` is a spy — the assertion that matters is whether it was ever
called, which is exactly the "pop, then discover it should not have run" bug
this closes.
"""

from __future__ import annotations

import argparse
from typing import Any

import pytest

from hunter_strategy_worker.replay import run as run_module
from hunter_strategy_worker.replay.budget import ReplayBudget

pytestmark = pytest.mark.unit


class _FakeEngine:
    async def dispose(self) -> None:
        return None


class _FakeRedis:
    def __init__(self, fields: dict[str, str]) -> None:
        self._fields = fields
        self.closed = False

    async def hgetall(self, _key: str) -> dict[str, str]:
        return dict(self._fields)

    async def aclose(self) -> None:
        self.closed = True


def _args() -> argparse.Namespace:
    return argparse.Namespace(max_runs=3)


async def _run_drain(monkeypatch: pytest.MonkeyPatch, *, fields: dict[str, str]) -> list[str]:
    calls: list[str] = []
    fake_redis = _FakeRedis(fields)

    async def fake_take_next(_redis: Any, *, key: str) -> None:
        del key
        calls.append("take_next")
        return None

    def fake_create_redis(settings: object) -> _FakeRedis:
        del settings
        return fake_redis

    def fake_create_engine(settings: object) -> _FakeEngine:
        del settings
        return _FakeEngine()

    def fake_create_session_factory(engine: object) -> object:
        del engine
        return object()

    monkeypatch.setattr("hunter_core.redis.create_redis", fake_create_redis)
    monkeypatch.setattr(run_module, "create_engine", fake_create_engine)
    monkeypatch.setattr(run_module, "create_session_factory", fake_create_session_factory)
    monkeypatch.setattr(run_module, "take_next", fake_take_next)

    runs = await run_module._drain(_args(), ReplayBudget())
    assert runs == []
    assert fake_redis.closed is True
    return calls


class TestDrainPausesOnDegraded:
    async def test_a_degraded_lane_never_pops_a_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = await _run_drain(monkeypatch, fields={})  # empty heartbeat -> heartbeat_missing
        assert calls == [], "take_next must not run once the gate refuses the slice"

    async def test_a_healthy_lane_still_reaches_take_next(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datetime import UTC, datetime

        fresh = datetime.now(UTC).isoformat()
        calls = await _run_drain(monkeypatch, fields={"ts": fresh, "outbox_lag_s": "0"})
        assert calls == ["take_next"], "the gate must not block a healthy live lane"
