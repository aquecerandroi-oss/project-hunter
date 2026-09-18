"""``prune_outbox_events.py`` — the loop that drives ``prune_dispatched``.

No database here on purpose: the SQL is ``outbox_store.prune_dispatched`` and
its own integration tests own it (``packages/core/tests/integration/
test_outbox_integration.py``). What this script adds is control flow — stop on
a short batch, honour ``--max-batches``, refuse a nonsense cutoff — and that is
what is checked, with a fake batch function.

Run: ``uv run pytest infra/scripts/tests/test_prune_outbox_events.py -q``
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load() -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        "prune_outbox_events", SCRIPTS_DIR / "prune_outbox_events.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return _load()


def _fake_batches(sizes: list[int]):
    calls: list[int] = []
    queue = list(sizes)

    async def delete_batch() -> int:
        went = queue.pop(0) if queue else 0
        calls.append(went)
        return went

    return delete_batch, calls


def test_loop_stops_on_the_first_short_batch(script: ModuleType) -> None:
    delete_batch, calls = _fake_batches([5, 5, 3, 5])
    deleted, batches = asyncio.run(script.prune_in_batches(delete_batch, batch=5))
    assert (deleted, batches) == (13, 3)
    assert calls == [5, 5, 3], "the fourth batch must never be asked for"


def test_an_empty_table_costs_exactly_one_statement(script: ModuleType) -> None:
    delete_batch, calls = _fake_batches([0])
    deleted, batches = asyncio.run(script.prune_in_batches(delete_batch, batch=5))
    assert (deleted, batches) == (0, 1)
    assert calls == [0]


def test_max_batches_caps_the_loop_even_with_rows_left(script: ModuleType) -> None:
    delete_batch, calls = _fake_batches([5, 5, 5, 5, 5])
    deleted, batches = asyncio.run(script.prune_in_batches(delete_batch, batch=5, max_batches=2))
    assert (deleted, batches) == (10, 2)
    assert calls == [5, 5]


def test_zero_max_batches_means_no_cap(script: ModuleType) -> None:
    delete_batch, _ = _fake_batches([5] * 7 + [1])
    deleted, batches = asyncio.run(script.prune_in_batches(delete_batch, batch=5, max_batches=0))
    assert (deleted, batches) == (36, 8)


def test_non_positive_batch_is_refused(script: ModuleType) -> None:
    delete_batch, _ = _fake_batches([0])
    with pytest.raises(ValueError):
        asyncio.run(script.prune_in_batches(delete_batch, batch=0))


def test_negative_max_batches_is_refused_not_read_as_no_cap(script: ModuleType) -> None:
    delete_batch, calls = _fake_batches([5, 5, 1])
    with pytest.raises(ValueError):
        asyncio.run(script.prune_in_batches(delete_batch, batch=5, max_batches=-1))
    assert calls == [], "nothing may be deleted on a refused argument"
    with pytest.raises(ValueError):
        asyncio.run(script.prune_in_batches(delete_batch, batch=5, pause_s=-0.1))


def test_pause_runs_between_full_batches_only(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(script.asyncio, "sleep", fake_sleep)
    delete_batch, _ = _fake_batches([5, 5, 2])
    asyncio.run(script.prune_in_batches(delete_batch, batch=5, pause_s=0.05))
    assert slept == [0.05, 0.05], "no pause after the short batch that ends the loop"


def test_cutoff_is_now_minus_retention_and_tz_aware(script: ModuleType) -> None:
    now = datetime(2026, 9, 18, 22, 0, tzinfo=UTC)
    assert script.cutoff(7, now) == now - timedelta(days=7)
    assert script.cutoff(7, now).tzinfo is not None


def test_cutoff_refuses_zero_retention_and_naive_clocks(script: ModuleType) -> None:
    with pytest.raises(ValueError):
        script.cutoff(0, datetime(2026, 9, 18, tzinfo=UTC))
    with pytest.raises(ValueError):
        script.cutoff(7, datetime(2026, 9, 18))  # noqa: DTZ001 — the naive clock is the point


def test_default_retention_matches_database_md(script: ModuleType) -> None:
    assert script.RETENTION_DAYS == 7
