"""Integration tests: ``GET /lab/shadow/curve?cohort=`` — brief T3.18b, item 3.

``prospective`` (default), the ``replay`` wildcard (every run of the version
at once) and one exact cohort string all read the *same* population the
scoreboard would, through ``LabScoreboardRepository.rows_for``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_core.domain.enums import OutcomeResult

from . import lab_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


async def test_default_cohort_is_prospective(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=2)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        exit_ts=decision_at + timedelta(minutes=30),
        entry_ts=decision_at + timedelta(minutes=1),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1"),
        cohort="prospective",
    )
    run_id = uuid.uuid4()
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        exit_ts=decision_at + timedelta(minutes=45),
        entry_ts=decision_at + timedelta(minutes=1),
        result=OutcomeResult.STOP,
        r_multiple=Decimal("-1"),
        cohort=f"replay:{run_id}",
    )
    actor = make_actor("curve-cohort-default")

    response = await client.get(
        "/api/v1/lab/shadow/curve",
        params={"version_id": str(version_id), "as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cohort"] == "prospective", "a curva ecoa a coorte que desenhou"
    points = body["points"]
    assert len(points) == 1
    assert points[0]["r"] == "1"


async def test_replay_wildcard_reads_every_run_of_the_version(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=3)
    run_a, run_b = uuid.uuid4(), uuid.uuid4()
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        exit_ts=decision_at + timedelta(minutes=10),
        entry_ts=decision_at + timedelta(minutes=1),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("0.5"),
        cohort=f"replay:{run_a}",
    )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        exit_ts=decision_at + timedelta(minutes=20),
        entry_ts=decision_at + timedelta(minutes=1),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1.5"),
        cohort=f"replay:{run_b}",
    )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        exit_ts=decision_at + timedelta(minutes=5),
        entry_ts=decision_at + timedelta(minutes=1),
        result=OutcomeResult.STOP,
        r_multiple=Decimal("-1"),
        cohort="prospective",
    )
    actor = make_actor("curve-cohort-replay-wildcard")

    response = await client.get(
        "/api/v1/lab/shadow/curve",
        params={"version_id": str(version_id), "as_of": NOW.isoformat(), "cohort": "replay"},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    points = response.json()["points"]
    assert {p["r"] for p in points} == {"0.5", "1.5"}
    assert len(points) == 2


async def test_one_exact_replay_cohort_reads_only_that_run(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=4)
    run_a, run_b = uuid.uuid4(), uuid.uuid4()
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        exit_ts=decision_at + timedelta(minutes=10),
        entry_ts=decision_at + timedelta(minutes=1),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("3"),
        cohort=f"replay:{run_a}",
    )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        exit_ts=decision_at + timedelta(minutes=20),
        entry_ts=decision_at + timedelta(minutes=1),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("4"),
        cohort=f"replay:{run_b}",
    )
    actor = make_actor("curve-cohort-exact")

    response = await client.get(
        "/api/v1/lab/shadow/curve",
        params={
            "version_id": str(version_id),
            "as_of": NOW.isoformat(),
            "cohort": f"replay:{run_a}",
        },
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    points = response.json()["points"]
    assert len(points) == 1
    assert points[0]["r"] == "3"


async def test_invalid_cohort_is_422(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor = make_actor("curve-cohort-invalid")

    response = await client.get(
        "/api/v1/lab/shadow/curve",
        params={"version_id": str(uuid.uuid4()), "cohort": "not-a-cohort"},
        headers=actor.headers,
    )

    assert response.status_code == 422, response.text
    assert response.json()["type"].endswith("invalid-cohort")


async def test_the_replay_wildcard_refuses_overlapping_runs(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """T3.18c, item 10: duas corridas sobre a mesma janela não são somadas.

    Somá-las numa curva acumulada dobraria o R e sugeriria o dobro da
    evidência; a recusa nomeia o motivo e a saída (uma corrida por vez).
    """
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=40)
    )
    market_id = await fx.seed_lab_market(session_factory)
    window_from, window_to = NOW - timedelta(days=31), NOW - timedelta(days=1)
    for _ in range(2):
        run_id = uuid.uuid4()
        decision_at = NOW - timedelta(days=20)
        await fx.seed_shadow_signal(
            session_factory,
            strategy_version_id=version_id,
            market_id=market_id,
            decision_at=decision_at,
            entry_ts=decision_at + timedelta(minutes=1),
            exit_ts=decision_at + timedelta(hours=1),
            result=OutcomeResult.TARGET,
            r_multiple=Decimal("1"),
            cohort=f"replay:{run_id}",
        )
        await fx.seed_replay_slice(
            session_factory,
            run_id=run_id,
            strategy_version_id=version_id,
            window_from=window_from,
            window_to=window_to,
            markets=["labex:LABUSDT"],
            started_at=NOW - timedelta(hours=2),
            finished_at=NOW - timedelta(hours=1),
            bars_evaluated=1000,
            signals=1,
            outcomes_resolved=1,
            outcomes_open=0,
            seconds=Decimal("10.000"),
        )
    actor = make_actor("curve-overlapping-runs")

    response = await client.get(
        "/api/v1/lab/shadow/curve",
        params={"version_id": str(version_id), "as_of": NOW.isoformat(), "cohort": "replay"},
        headers=actor.headers,
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["type"].endswith("janelas-sobrepostas")
    assert "janelas_sobrepostas" in body["detail"]


async def test_adjacent_runs_are_not_overlapping_and_are_drawn(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Janela semi-aberta: corridas encostadas não repetem uma única barra."""
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=40)
    )
    market_id = await fx.seed_lab_market(session_factory)
    edges = [
        (NOW - timedelta(days=31), NOW - timedelta(days=16)),
        (NOW - timedelta(days=16), NOW - timedelta(days=1)),
    ]
    for index, (window_from, window_to) in enumerate(edges):
        run_id = uuid.uuid4()
        decision_at = window_from + timedelta(days=1)
        await fx.seed_shadow_signal(
            session_factory,
            strategy_version_id=version_id,
            market_id=market_id,
            decision_at=decision_at,
            entry_ts=decision_at + timedelta(minutes=1),
            exit_ts=decision_at + timedelta(hours=1),
            result=OutcomeResult.TARGET,
            r_multiple=Decimal(index + 1),
            cohort=f"replay:{run_id}",
        )
        await fx.seed_replay_slice(
            session_factory,
            run_id=run_id,
            strategy_version_id=version_id,
            window_from=window_from,
            window_to=window_to,
            markets=["labex:LABUSDT"],
            started_at=NOW - timedelta(hours=2),
            finished_at=NOW - timedelta(hours=1),
            bars_evaluated=500,
            signals=1,
            outcomes_resolved=1,
            outcomes_open=0,
            seconds=Decimal("5.000"),
        )
    actor = make_actor("curve-adjacent-runs")

    response = await client.get(
        "/api/v1/lab/shadow/curve",
        params={"version_id": str(version_id), "as_of": NOW.isoformat(), "cohort": "replay"},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cohort"] == "replay"
    assert [point["cum_r"] for point in body["points"]] == ["1", "3"]
