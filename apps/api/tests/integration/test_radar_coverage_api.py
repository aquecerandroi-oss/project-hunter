"""Integration tests for ``GET /api/v1/radar/coverage`` (T3.46,
``.claude/state/notes-T3.46.md``) -- real Postgres + real Redis, real T2.1
models, same fixtures ``test_radar_api.py`` uses.

**Not run by this task** (operational rule: no testcontainers, API unit
tests only for this brief -- see ``.claude/state/notes-T3.46c.md``). Written
so the orchestrator's next testcontainers slot can run it as-is; the
assertions below were designed against the real model constructors and the
real ``services/radar_coverage.py``/``repositories/radar_coverage.py``
contracts, not guessed shapes.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio

from hunter_core.db.models.analysis import OpportunityHistory, OpportunityWeights
from hunter_core.db.models.analysis_baselines import FeatureBaseline
from hunter_core.domain.enums import (
    AnomalyType,
    BaselineSampling,
    BaselineSource,
    OpportunityStage,
    OpportunityStatus,
)
from hunter_core.redis import keys

from . import analysis_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[redis_asyncio.Redis]:
    client = redis_asyncio.from_url(redis_url, decode_responses=False)
    try:
        yield client
    finally:
        await client.aclose()


async def _scanner_heartbeat_with_baselines(redis_client: redis_asyncio.Redis) -> str:
    """A `hb:scanner:*` hash carrying every field
    `services/radar_coverage.py::_freshest_scanner_heartbeat` reads -- the
    real shape `health.py::write_heartbeat` writes."""
    key = keys.heartbeat("scanner", f"scanner-{uuid.uuid4().hex[:8]}")
    await redis_client.hset(
        key,
        mapping={
            "ts": datetime.now(UTC).isoformat(),
            "errors": "0",
            "baselines_usable": "9029",
            "baselines_under_construction": "102597",
            "baselines_state": "bootstrapping 1000FLOKIUSDT (4/200)",
            "detectors_disarmed": (
                "CROSS_EXCHANGE_DIVERGENCE:single_exchange_until_m1b=200,"
                "FUNDING_ANOMALY:funding_unavailable=200"
            ),
        },
    )
    return key


async def test_get_radar_coverage_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/radar/coverage")
    assert response.status_code == 401


async def test_get_radar_coverage_real_numbers_no_heartbeat(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """No `hb:scanner:*` heartbeat at all -- every heartbeat-derived field
    reads its honest absent state, never a fabricated number."""
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    await fx.seed_anomaly(session_factory, market_id, anomaly_type=AnomalyType.VOLUME_SPIKE)
    actor: Actor = make_actor("radar-coverage-no-heartbeat")

    response = await client.get("/api/v1/radar/coverage", headers=actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["markets_with_anomaly"] >= 1
    assert body["markets_monitored"] >= 1
    assert body["baselines_usable"] == 0
    assert body["baselines_under_construction"] == 0
    assert body["bootstrap_pointer"] is None
    assert body["baseline_gate_v2_pct"] is None
    assert len(body["detectors"]) == 12
    assert body["as_of"] is not None


async def test_get_radar_coverage_reads_the_scanner_heartbeat(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    key = await _scanner_heartbeat_with_baselines(redis_client)
    try:
        actor: Actor = make_actor("radar-coverage-heartbeat")

        response = await client.get("/api/v1/radar/coverage", headers=actor.headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["baselines_usable"] == 9029
        assert body["baselines_under_construction"] == 102597
        assert body["bootstrap_pointer"] == "bootstrapping 1000FLOKIUSDT (4/200)"
        disarmed_by_type = {d["type"]: d["disarmed_reason"] for d in body["detectors"]}
        assert disarmed_by_type["CROSS_EXCHANGE_DIVERGENCE"] == "single_exchange_until_m1b"
        assert disarmed_by_type["FUNDING_ANOMALY"] == "funding_unavailable"
        # Declared-disarmed-with-no-rows vs silent-with-no-reason must stay
        # tellable apart -- ORDERBOOK_IMBALANCE has neither rows nor a
        # declared reason in this fixture, the T3.46 defect this page exists
        # to surface.
        assert disarmed_by_type["ORDERBOOK_IMBALANCE"] is None
    finally:
        await redis_client.delete(key)


async def test_get_radar_coverage_max_score_ever_reads_opportunity_history(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """The ceiling comes off `opportunity_history`'s full series, not
    `Opportunity.peak_score` -- a later, higher history sample must count
    even once the episode itself has expired."""
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    opportunity_id = await fx.seed_opportunity(
        session_factory, market_id, score=Decimal("10.00"), status=OpportunityStatus.NORMAL
    )
    async with session_factory() as session:
        session.add(
            OpportunityHistory(
                opportunity_id=opportunity_id,
                ts=datetime.now(UTC),
                score=Decimal("38.33"),
                confidence=Decimal("0.4000"),
                status=OpportunityStatus.NORMAL,
                stage=OpportunityStage.NONE,
            )
        )
        await session.commit()
    actor: Actor = make_actor("radar-coverage-max-score")

    response = await client.get("/api/v1/radar/coverage", headers=actor.headers)

    assert response.status_code == 200, response.text
    assert response.json()["max_score_ever"] == "38.33"


async def test_get_radar_coverage_baseline_gate_v2_pct_against_the_active_weight_vector(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """One passing, one failing `feature_baselines` row against an active
    `opportunity_weights.baseline_gate` -- 50 %, not a fabricated ``None``."""
    _exchange, _symbol, market_id = await fx.seed_market(session_factory)
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add(
            OpportunityWeights(
                version=f"gate-test-{uuid.uuid4().hex[:8]}",
                weights={
                    "baseline_gate": {
                        "min_distinct_days": 3,
                        "min_valid_observations": 120,
                        "expected_size": 420,
                    }
                },
                is_active=True,
            )
        )
        common = {
            "market_id": market_id,
            "feature": "relative_volume_1h",
            "feature_version": 1,
            "algo_version": "median_mad_v1",
            "hour_of_day": 12,
            "window_start": now - timedelta(days=7),
            "window_end": now,
            "available_at": now,
            "median": Decimal("1.0000"),
            "mad": Decimal("0.1000"),
            "expected_size": 420,
            "coverage": Decimal("1.0000"),
            "source": BaselineSource.LIVE,
            "sampling": BaselineSampling.PER_MINUTE,
        }
        session.add(
            FeatureBaseline(
                **common,
                sample_size=200,
                distinct_days=5,
                input_fingerprint=f"pass-{uuid.uuid4().hex[:8]}",
            )
        )
        session.add(
            FeatureBaseline(
                **common,
                sample_size=10,
                distinct_days=1,
                input_fingerprint=f"fail-{uuid.uuid4().hex[:8]}",
            )
        )
        await session.commit()
    actor: Actor = make_actor("radar-coverage-gate")

    response = await client.get("/api/v1/radar/coverage", headers=actor.headers)

    assert response.status_code == 200, response.text
    assert response.json()["baseline_gate_v2_pct"] == "50.00"
