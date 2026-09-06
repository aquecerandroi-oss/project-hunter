"""Integration tests for ``GET /api/v1/anomalies``."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_core.domain.enums import AnomalyEvaluationState, AnomalyStatus, AnomalyType

from . import analysis_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def test_list_anomalies_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/anomalies")
    assert response.status_code == 401


async def test_list_anomalies_default_24h_window_excludes_older_rows(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    recent_id = await fx.seed_anomaly(session_factory, market_id)
    old_id = await fx.seed_anomaly(
        session_factory,
        market_id,
        anomaly_type=AnomalyType.PRICE_ACCELERATION,
        detected_at=datetime.now(UTC) - timedelta(hours=48),
    )
    actor: Actor = make_actor("anomalies-24h-window")

    response = await client.get("/api/v1/anomalies", headers=actor.headers)

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert str(recent_id) in ids
    assert str(old_id) not in ids


async def test_list_anomalies_window_hours_widens_the_cut(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    old_id = await fx.seed_anomaly(
        session_factory,
        market_id,
        detected_at=datetime.now(UTC) - timedelta(hours=48),
    )
    actor: Actor = make_actor("anomalies-window-hours")

    response = await client.get("/api/v1/anomalies?window_hours=72", headers=actor.headers)

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert str(old_id) in ids


async def test_list_anomalies_exposes_evaluation_state_unknown_never_reads_resolved(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    anomaly_id = await fx.seed_anomaly(
        session_factory,
        market_id,
        status=AnomalyStatus.ACTIVE,
        evaluation_state=AnomalyEvaluationState.UNKNOWN,
    )
    actor: Actor = make_actor("anomalies-evaluation-state")

    response = await client.get("/api/v1/anomalies", headers=actor.headers)

    assert response.status_code == 200, response.text
    row = next(i for i in response.json()["items"] if i["id"] == str(anomaly_id))
    assert row["status"] == "active"
    assert row["evaluation_state"] == "unknown"


async def test_list_anomalies_filters_by_type_status_and_min_severity(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _e1, _s1, market_id = await fx.seed_market(session_factory)
    matching_id = await fx.seed_anomaly(
        session_factory,
        market_id,
        anomaly_type=AnomalyType.FUNDING_ANOMALY,
        severity=Decimal("85.00"),
        status=AnomalyStatus.ACTIVE,
    )
    # A different market: two ``active`` anomalies of the same type on the
    # *same* market would violate ``uq_anomalies_active_per_market_type``.
    _e2, _s2, low_severity_market_id = await fx.seed_market(session_factory)
    await fx.seed_anomaly(
        session_factory,
        low_severity_market_id,
        anomaly_type=AnomalyType.FUNDING_ANOMALY,
        severity=Decimal("10.00"),
        status=AnomalyStatus.ACTIVE,
    )
    actor: Actor = make_actor("anomalies-filters")

    response = await client.get(
        "/api/v1/anomalies?type=FUNDING_ANOMALY&status=active&min_severity=50",
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {str(matching_id)}


async def test_list_anomalies_market_id_filter(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _e1, _s1, market_a = await fx.seed_market(session_factory)
    _e2, _s2, market_b = await fx.seed_market(session_factory)
    anomaly_a = await fx.seed_anomaly(session_factory, market_a)
    await fx.seed_anomaly(session_factory, market_b)
    actor: Actor = make_actor("anomalies-market-filter")

    response = await client.get(f"/api/v1/anomalies?market_id={market_a}", headers=actor.headers)

    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {str(anomaly_a)}


async def test_list_anomalies_garbage_cursor_returns_422(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("anomalies-garbage-cursor")

    response = await client.get(
        "/api/v1/anomalies?cursor=!!!not-a-valid-cursor!!!", headers=actor.headers
    )

    assert response.status_code == 422, response.text
    assert response.json()["type"].endswith("invalid-cursor")
