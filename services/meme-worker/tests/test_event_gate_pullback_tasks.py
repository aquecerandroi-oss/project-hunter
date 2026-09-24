"""risk-engine-guardian (review of T4.91), pure (no Docker):

- the arm's insert never touches ``EventGateRuntime.proposing`` — that guard
  belongs to the proposal transaction of whoever opened it (``operator/5``'s
  ``evaluate_mint``); the arm clearing it would let the periodic trail flush
  offer ``operator/5``'s tape unlinked while its session is still open;
- the insert runs in a bounded, tracked task pool: a slow database never
  holds the shared evaluation loop, a saturated pool drops with a counter,
  a failing task is counted and logged, and shutdown cancels what is left.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

import hunter_meme_worker.event_gate_pullback as egp
from hunter_meme_worker.bounded_tasks import BoundedTasks

pytestmark = pytest.mark.unit


def _patch_db(monkeypatch: pytest.MonkeyPatch, *, insert: Any) -> None:
    @contextlib.asynccontextmanager
    async def fake_session(*_a: object, **_k: object) -> AsyncGenerator[object]:
        yield object()

    async def fake_trail(*_a: object, **_k: object) -> int:
        return 0

    monkeypatch.setattr(egp, "role_session", fake_session)
    monkeypatch.setattr(egp, "insert_proposals_reserved", insert)
    monkeypatch.setattr(egp, "write_refusal_trail", fake_trail)


def _rt(proposing: set[str]) -> Any:
    return SimpleNamespace(
        proposing=proposing,
        lab=SimpleNamespace(
            caches=object(),
            session_factory=None,
            config=SimpleNamespace(lab_proposal_ttl_s=60),
            state=SimpleNamespace(trail=None),
        ),
    )


async def test_the_arms_insert_never_clears_a_guard_another_owner_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two owners at once: operator/5's transaction holds the guard for the
    mint while the arm's insert for the same mint opens and closes its own."""
    desk_open, arm_done = asyncio.Event(), asyncio.Event()

    async def insert(*_a: object, **_k: object) -> int:
        return 1

    _patch_db(monkeypatch, insert=insert)
    rt = _rt(set())

    async def desk() -> bool:
        rt.proposing.add("MINT")  # what evaluate_mint does around its own session
        desk_open.set()
        await arm_done.wait()
        held = "MINT" in rt.proposing
        rt.proposing.discard("MINT")
        return held

    async def arm() -> None:
        await desk_open.wait()
        entry = SimpleNamespace(spec_id="arm", spec=SimpleNamespace(ttl_s=None))
        ready: Any = [(entry, SimpleNamespace(id="d1"))]
        await egp._insert(rt, "MINT", ready, datetime.now(UTC))
        arm_done.set()

    held, _ = await asyncio.gather(desk(), arm())
    assert held, "the arm removed the guard of operator/5's open transaction"


async def test_a_slow_task_never_blocks_the_caller_and_the_pool_is_bounded() -> None:
    pool = BoundedTasks(limit=2, name="test")
    release = asyncio.Event()
    done: list[int] = []

    async def slow(k: int) -> None:
        await release.wait()
        done.append(k)

    assert pool.spawn(slow(1)) and pool.spawn(slow(2))
    assert pool.spawn(slow(3)) is False, "saturated: dropped, never queued behind"
    assert (pool.in_flight, pool.saturated) == (2, 1)
    release.set()
    await pool.join()
    assert sorted(done) == [1, 2] and pool.in_flight == 0


async def test_a_failing_task_is_counted_and_never_escapes() -> None:
    pool = BoundedTasks(limit=2, name="test")

    async def boom() -> None:
        raise RuntimeError("db gone")

    assert pool.spawn(boom())
    await pool.join()
    assert pool.failed == 1
    assert pool.heartbeat_fields("x_") == {
        "x_in_flight": "0",
        "x_saturated_total": "0",
        "x_failed_total": "1",
    }


async def test_shutdown_cancels_what_is_left() -> None:
    pool = BoundedTasks(limit=2, name="test")
    started = asyncio.Event()

    async def forever() -> None:
        started.set()
        await asyncio.Event().wait()

    assert pool.spawn(forever())
    await started.wait()
    await asyncio.wait_for(pool.aclose(), timeout=1)
    assert pool.in_flight == 0 and pool.failed == 0
