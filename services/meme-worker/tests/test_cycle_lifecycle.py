"""Database-architect review of the cycle history (round 3): how a generation ends,
proven through the real ``run_meme`` — not by calling ``cycles.close()`` directly.

- a loop that crashes takes the ``TaskGroup`` down: the generation must NOT get a clean
  ``generation_end`` (``clean = false``); a SIGTERM (a cancel) does (``clean = true``);
- the cause survives the cleanup: a crash followed by a SIGTERM while the radar is closing its
  clients is still a crash, and a writer that raises is restarted instead of dying;
- ``MEME_ENABLED=false`` still persists the generation it announced (the writer is
  supervised in that branch too) and closes it on SIGTERM.

Everything outside the cycle instruments is stubbed on the ``main`` module; the cycle
history, its flush loop and its closing are the real ones, over the fake ``system_events``
of ``test_cycle_history``.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from hunter_meme_worker import cycle_wiring
from hunter_meme_worker import main as meme_main
from hunter_meme_worker.config import MemeConfig

from .test_cycle_history import _Db  # pyright: ignore[reportPrivateUsage]
from .test_cycle_history import db as db

pytestmark = pytest.mark.unit


class _Redis:
    async def hset(self, key: str, mapping: dict[str, str]) -> None:
        return None


class _Chain:
    """Stands in for ``chain_once``: parks until told to crash (or forever)."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.crash = False
        self.hold_cleanup = False  # the radar's own closing (``close_clients``) parks
        self.cleaning = asyncio.Event()

    async def close_clients(self, *args: object, **kwargs: object) -> None:
        self.cleaning.set()
        if self.hold_cleanup:
            await asyncio.Event().wait()

    async def __call__(self, ctx: object) -> None:
        self.started.set()
        if self.crash:
            raise RuntimeError("the chain step crashed")
        await asyncio.Event().wait()


async def _park(*args: object, **kwargs: object) -> None:
    await asyncio.Event().wait()


async def _noop(*args: object, **kwargs: object) -> None:
    return None


def _none(*args: object, **kwargs: object) -> None:
    return None


def _object(*args: object, **kwargs: object) -> object:
    return object()


def _gate_off(*args: object, **kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(enabled=False)


@pytest.fixture
def chain(monkeypatch: pytest.MonkeyPatch, db: _Db) -> _Chain:
    stub = _Chain()
    real_forever = meme_main.forever

    def forever(name: str, interval_s: float, step: Any, ctx: object) -> Any:
        return real_forever(name, interval_s, step, ctx) if name == "chain" else _park()

    ctx = SimpleNamespace(
        session_factory=object(), trades=None, activity=None, risk=None, wallets=None,
        launch_lane=None,
    )  # fmt: skip

    def _context(*args: object, **kwargs: object) -> tuple[SimpleNamespace, dict[str, object]]:
        return ctx, {}

    patches: dict[str, Any] = {
        "create_session_factory": _object,
        "build_launch_lane": _none,
        "wake_publisher": _none,
        "register_launch_lane_health": _none,
        "build_context": _context,
        "register_health": _none,
        "register_lab_health": _none,
        "load_event_gate_config": _gate_off,
        "write_lab_heartbeat": _noop,
        "build_event_gate": _none,
        "attach_event_gate": _none,
        "register_event_gate_health": _none,
        "warm_tracked_set": _noop,
        "run_discovery": _park,
        "spawn_events_match": _none,
        "close_clients": stub.close_clients,
        "forever": forever,
        "chain_once": stub,
    }
    for name, value in patches.items():
        monkeypatch.setattr(meme_main, name, value)
    return stub


def _runtime() -> Any:
    return SimpleNamespace(
        settings=object(),
        engine=object(),
        role="meme",
        instance="t1",
        redis=_Redis(),
        status_details={},
        mark_success=lambda: None,
    )


def _use(monkeypatch: pytest.MonkeyPatch, config: MemeConfig) -> None:
    def load_config(settings: object) -> MemeConfig:
        return config

    monkeypatch.setattr(meme_main, "load_config", load_config)


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    """An enabled radar with only the chain loop of interest (the Lab and the rest off)."""
    _use(
        monkeypatch,
        MemeConfig(
            enabled=True, lab_enabled=False, creator_watch_enabled=False, fast_lane_enabled=False
        ),
    )


def _ends(db: _Db) -> list[tuple[str, bool]]:
    return [
        (json.loads(r["data"])["loop"], json.loads(r["data"])["clean"])
        for r in db.rows
        if r["event"] == "generation_end"
    ]


async def _cancelled(task: asyncio.Task[None]) -> None:
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_crashed_loop_does_not_get_a_clean_generation_end(
    monkeypatch: pytest.MonkeyPatch, chain: _Chain, db: _Db
) -> None:
    _configure(monkeypatch)
    chain.crash = True
    with pytest.raises(ExceptionGroup) as raised:
        await asyncio.wait_for(meme_main.run_meme(_runtime()), timeout=10)
    assert raised.group_contains(RuntimeError, match="chain step crashed")
    assert _ends(db) == [("chain", False), ("lab", False)]
    assert [r["event"] for r in db.rows].count("generation_start") == 2


async def test_a_sigterm_is_a_clean_generation_end(
    monkeypatch: pytest.MonkeyPatch, chain: _Chain, db: _Db
) -> None:
    _configure(monkeypatch)
    task = asyncio.ensure_future(meme_main.run_meme(_runtime()))
    await asyncio.wait_for(chain.started.wait(), timeout=5)
    await _cancelled(task)
    assert _ends(db) == [("chain", True), ("lab", True)]


async def test_a_disabled_radar_persists_its_generations_while_it_runs_and_closes_them(
    monkeypatch: pytest.MonkeyPatch, chain: _Chain, db: _Db
) -> None:
    _use(monkeypatch, MemeConfig(enabled=False))
    task = asyncio.ensure_future(meme_main.run_meme(_runtime()))
    for _ in range(100):  # the writer runs although nothing is collected
        if len(db.rows) >= 2:
            break
        await asyncio.sleep(0.02)
    assert [r["event"] for r in db.rows] == ["generation_start", "generation_start"]
    assert not any(json.loads(r["data"])["enabled"] for r in db.rows)
    await _cancelled(task)
    assert _ends(db) == [("chain", True), ("lab", True)]


async def test_a_crash_followed_by_a_sigterm_during_the_cleanup_is_still_a_crash(
    monkeypatch: pytest.MonkeyPatch, chain: _Chain, db: _Db
) -> None:
    """The cancel that arrives while ``_run`` closes its clients replaces the
    ``ExceptionGroup`` in flight: the cause must be remembered before the cleanup starts."""
    _configure(monkeypatch)
    chain.crash = True
    chain.hold_cleanup = True
    task = asyncio.ensure_future(meme_main.run_meme(_runtime()))
    await asyncio.wait_for(chain.cleaning.wait(), timeout=5)
    await _cancelled(task)
    assert _ends(db) == [("chain", False), ("lab", False)]


async def test_a_writer_that_raises_is_restarted_not_left_dead(
    monkeypatch: pytest.MonkeyPatch, chain: _Chain, db: _Db
) -> None:
    calls = 0
    real = cycle_wiring.flush_once

    async def flaky(*args: Any, **kwargs: Any) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("an unexpected failure escaped the flush")
        return await real(*args, **kwargs)

    monkeypatch.setattr(cycle_wiring, "flush_once", flaky)
    monkeypatch.setattr(cycle_wiring, "FLUSH_EVERY_S", 0.01)
    _use(monkeypatch, MemeConfig(enabled=False))
    task = asyncio.ensure_future(meme_main.run_meme(_runtime()))
    for _ in range(100):
        if len(db.rows) >= 2:
            break
        await asyncio.sleep(0.02)
    assert len(db.rows) == 2  # written by the second try
    await _cancelled(task)
