"""``run_outcomes`` only sweeps on shard 0 (T3.74f).

``sweep_outcomes`` itself is unpartitioned (it advances whatever tracking is
open, regardless of which shard's decision opened it) -- running it on every
shard of a sharded topology would multiply Postgres load for no benefit, so
every shard but 0 idles instead.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from hunter_strategy_worker import outcome_sweep as outcome_sweep_mod
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.outcome_sweep import run_outcomes

pytestmark = pytest.mark.unit


class _Runtime:
    def __init__(self) -> None:
        self.errors = 0
        self.successes = 0

    def mark_error(self) -> None:
        self.errors += 1

    def mark_success(self) -> None:
        self.successes += 1


class _Settings:
    market_universe_blocklist: list[str] = []


async def test_a_non_leader_shard_never_sweeps(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def fake_sweep(*_a: Any, **_kw: Any) -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr(outcome_sweep_mod, "sweep_outcomes", fake_sweep)

    task = asyncio.ensure_future(
        run_outcomes(
            None,  # type: ignore[arg-type]
            _Runtime(),  # type: ignore[arg-type]
            ShadowConfig(),
            _Settings(),  # type: ignore[arg-type]
            shard_index=1,
        )
    )
    await asyncio.sleep(0.05)
    assert not task.done(), "a non-leader shard's sweep loop must idle forever, not return"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == 0


async def test_shard_zero_sweeps(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    released = asyncio.Event()

    async def fake_sweep(*_a: Any, **_kw: Any) -> int:
        nonlocal calls
        calls += 1
        released.set()
        return 0

    async def fake_sleep(_delay: float) -> None:
        await asyncio.Event().wait()  # never returns -- one pass is enough

    monkeypatch.setattr(outcome_sweep_mod, "sweep_outcomes", fake_sweep)
    monkeypatch.setattr(outcome_sweep_mod.asyncio, "sleep", fake_sleep)

    task = asyncio.ensure_future(
        run_outcomes(
            None,  # type: ignore[arg-type]
            _Runtime(),  # type: ignore[arg-type]
            ShadowConfig(),
            _Settings(),  # type: ignore[arg-type]
            shard_index=0,
        )
    )
    await asyncio.wait_for(released.wait(), timeout=1.0)
    assert calls == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
