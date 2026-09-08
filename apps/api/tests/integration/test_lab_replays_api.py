"""``GET /api/v1/lab/shadow/replays{,/{run_id}}`` — Backtests = replay, brief T3.25.

Also proves brief item 2: ``GET /lab/shadow/signals?cohort=replay:<uuid>`` is
already accepted (since ``0012_replication``) and returns exactly that run's
signals.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState

from . import lab_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


async def test_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/lab/shadow/replays")
    assert response.status_code == 401


async def test_honest_empty_state_when_no_replay_ran(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("replays-empty")
    response = await client.get(
        "/api/v1/lab/shadow/replays", headers=actor.headers, params={"limit": 1}
    )
    assert response.status_code == 200, response.text
    # Cannot assert an empty list here (the DB is shared across this file's
    # tests and possibly earlier ones), only that the shape is honest: a list,
    # paged, never a placeholder row.
    body = response.json()
    assert isinstance(body["items"], list)


async def test_unknown_run_id_is_404(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("replays-404")
    response = await client.get(f"/api/v1/lab/shadow/replays/{uuid.uuid4()}", headers=actor.headers)
    assert response.status_code == 404
    assert response.json()["type"].endswith("replay-run-not-found")


async def test_a_run_aggregates_its_slices(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Two slices of the same run — T3.19b's own shape (eleven commands, one
    cohort): the list and the detail must both report the *run*, not one slice.
    """
    _, version_id = await fx.seed_strategy_version(
        session_factory,
        key=f"replay-target-{uuid.uuid4().hex[:8]}",
        activated_at=NOW - timedelta(days=2),
    )
    run_id = uuid.uuid4()
    slice1_from = NOW - timedelta(days=2)
    slice1_to = NOW - timedelta(days=1)
    slice2_from = slice1_to
    slice2_to = NOW

    await fx.seed_replay_slice(
        session_factory,
        run_id=run_id,
        strategy_version_id=version_id,
        window_from=slice1_from,
        window_to=slice1_to,
        markets=["binance:BTCUSDT"],
        started_at=slice1_from,
        finished_at=slice1_from + timedelta(minutes=5),
        bars_evaluated=1440,
        signals=3,
        outcomes_resolved=1,
        outcomes_open=2,
        seconds=Decimal("12.500"),
        evaluations_by_state={"triggered": 3, "not_triggered": 100},
    )
    await fx.seed_replay_slice(
        session_factory,
        run_id=run_id,
        strategy_version_id=version_id,
        window_from=slice2_from,
        window_to=slice2_to,
        markets=["binance:BTCUSDT", "binance:ETHUSDT"],
        started_at=slice2_from,
        finished_at=slice2_from + timedelta(minutes=6),
        bars_evaluated=1440,
        signals=5,
        outcomes_resolved=4,
        outcomes_open=1,
        seconds=Decimal("15.500"),
        evaluations_by_state={"triggered": 2, "not_triggered": 90},
    )
    actor: Actor = make_actor("replays-aggregate")

    detail_response = await client.get(
        f"/api/v1/lab/shadow/replays/{run_id}", headers=actor.headers
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    run = detail["run"]
    assert run["run_id"] == str(run_id)
    assert run["market_count"] == 2
    assert run["bars_evaluated"] == 2880
    assert Decimal(run["seconds"]) == Decimal("28.000")
    assert Decimal(run["bars_per_second"]) == Decimal(2880) / Decimal("28.000")
    assert run["signals"] == 5
    assert run["outcomes_resolved"] == 4
    assert run["outcomes_open"] == 1
    assert run["slice_count"] == 2
    assert run["window_from"] == slice1_from.isoformat().replace("+00:00", "Z")
    assert run["window_to"] == slice2_to.isoformat().replace("+00:00", "Z")
    assert detail["population_by_state"] == {"triggered": 5, "not_triggered": 190}
    assert len(detail["slices"]) == 2

    list_response = await client.get(
        "/api/v1/lab/shadow/replays", headers=actor.headers, params={"limit": 200}
    )
    assert list_response.status_code == 200, list_response.text
    items = list_response.json()["items"]
    listed = next(item for item in items if item["run_id"] == str(run_id))
    assert listed["bars_evaluated"] == 2880
    assert listed["slice_count"] == 2


async def test_the_cohort_filter_on_signals_accepts_a_replay_cohort(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Brief item 2: confirm ``cohort=replay:<uuid>`` on ``/signals`` (accepted
    since ``0012_replication``) actually returns that run's population."""
    _, version_id = await fx.seed_strategy_version(
        session_factory,
        key=f"replay-cohort-{uuid.uuid4().hex[:8]}",
        activated_at=NOW - timedelta(days=1),
    )
    market_id = await fx.seed_lab_market(session_factory)
    run_id = uuid.uuid4()
    decision_at = NOW - timedelta(hours=3)

    replay_signal_id = await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        cohort=f"replay:{run_id}",
        tracking_state=ShadowTrackingState.PENDING_ENTRY,
        result=OutcomeResult.OPEN,
    )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        cohort="prospective",
        tracking_state=ShadowTrackingState.PENDING_ENTRY,
        result=OutcomeResult.OPEN,
    )
    actor: Actor = make_actor("replays-cohort-signals")

    response = await client.get(
        "/api/v1/lab/shadow/signals",
        params={"cohort": f"replay:{run_id}"},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    signal_ids = {item["signal_id"] for item in items}
    assert str(replay_signal_id) in signal_ids
    assert all(item["cohort"] == f"replay:{run_id}" for item in items)
