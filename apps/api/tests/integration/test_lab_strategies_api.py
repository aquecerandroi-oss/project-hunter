"""``GET /api/v1/lab/shadow/strategies`` — brief T3.25.

Global, no-RLS read (DATABASE.md §16), same pattern as ``test_lab_scoreboard_api.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState, StrategyVersionStatus

from . import lab_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def _unique_key(base: str) -> str:
    return f"{base}-{uuid.uuid4().hex[:8]}"


PARAM_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["lookback"],
    "properties": {
        "lookback": {"type": ["string", "integer"], "pattern": r"^-?[0-9]+$", "description": "bars"}
    },
}


async def test_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/lab/shadow/strategies")
    assert response.status_code == 401


async def test_honest_empty_state_when_there_are_no_strategies(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("strategies-empty")
    response = await client.get(
        "/api/v1/lab/shadow/strategies",
        params={"as_of": NOW.isoformat()},
        headers=actor.headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["items"], list)


async def test_a_version_carries_its_full_parameter_schema_and_lineage(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    key = _unique_key("momentum")
    parent_strategy_id, parent_version_id = await fx.seed_strategy_version(
        session_factory,
        key=key,
        version="v1",
        activated_at=NOW - timedelta(days=40),
        default_parameters={"lookback": "20"},
        parameters_schema=PARAM_SCHEMA,
        promising_at=NOW - timedelta(days=10),
        promising_by="scoreboard-v1",
    )
    _, sibling_version_id = await fx.seed_strategy_version(
        session_factory,
        strategy_id=parent_strategy_id,
        key=key,
        version="v2",
        status=StrategyVersionStatus.DRAFT,
        activated_at=None,
        purpose="paper",
        replication_parent_id=parent_version_id,
        replication_index=3,
    )
    actor: Actor = make_actor("strategies-lineage")

    response = await client.get(
        "/api/v1/lab/shadow/strategies",
        params={"as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    momentum = next(item for item in items if item["key"] == key)
    versions = {v["strategy_version_id"]: v for v in momentum["versions"]}

    parent = versions[str(parent_version_id)]
    assert parent["parameters_schema"] == PARAM_SCHEMA
    assert parent["default_parameters"] == {"lookback": "20"}
    assert parent["lineage"] is None
    assert parent["promising_at"] is not None
    assert parent["promising_by"] == "scoreboard-v1"
    assert parent["obsidian_page"] == f"03-TRADING/Estrategias/{key}-v1.md"
    assert parent["verdict"] == "inconclusivo"
    assert parent["signal_counts"] == {"prospective": 0, "replay": 0, "replication": 0}

    sibling = versions[str(sibling_version_id)]
    assert sibling["lineage"] == {
        "replication_parent_id": str(parent_version_id),
        "replication_index": 3,
    }
    assert sibling["purpose"] == "paper"
    assert sibling["obsidian_page"] == f"03-TRADING/Estrategias/{key}-v2.md"


async def test_signal_counts_are_bucketed_by_cohort_family(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    key = _unique_key("breakout")
    _, version_id = await fx.seed_strategy_version(
        session_factory, key=key, activated_at=NOW - timedelta(days=5)
    )
    market_id = await fx.seed_lab_market(session_factory)
    run_id = "3fbb3f0e-3e3f-4c8e-9a3b-6b6b6b6b6b6b"

    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=NOW - timedelta(hours=1),
        cohort="prospective",
        tracking_state=ShadowTrackingState.PENDING_ENTRY,
        result=OutcomeResult.OPEN,
    )
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=NOW - timedelta(hours=2),
        cohort=f"replay:{run_id}",
        tracking_state=ShadowTrackingState.PENDING_ENTRY,
        result=OutcomeResult.OPEN,
    )
    actor: Actor = make_actor("strategies-counts")

    response = await client.get(
        "/api/v1/lab/shadow/strategies",
        params={"as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    breakout = next(item for item in items if item["key"] == key)
    version = next(v for v in breakout["versions"] if v["strategy_version_id"] == str(version_id))
    assert version["signal_counts"] == {"prospective": 1, "replay": 1, "replication": 0}


async def test_verdict_matches_the_scoreboards_own_computation(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Same population, same rule — the two endpoints must never disagree."""
    key = _unique_key("mean-rev")
    _, version_id = await fx.seed_strategy_version(
        session_factory, key=key, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    decision_at = NOW - timedelta(hours=6)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=decision_at,
        entry_ts=decision_at,
        exit_ts=decision_at + timedelta(hours=1),
        exit_price=Decimal("100"),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1.5"),
    )
    actor: Actor = make_actor("strategies-verdict")

    strategies_response = await client.get(
        "/api/v1/lab/shadow/strategies",
        params={"as_of": NOW.isoformat()},
        headers=actor.headers,
    )
    scoreboard_response = await client.get(
        "/api/v1/lab/shadow/scoreboard",
        params={"as_of": NOW.isoformat()},
        headers=actor.headers,
    )

    assert strategies_response.status_code == 200, strategies_response.text
    assert scoreboard_response.status_code == 200, scoreboard_response.text
    items = strategies_response.json()["items"]
    mean_rev = next(item for item in items if item["key"] == key)
    version = next(v for v in mean_rev["versions"] if v["strategy_version_id"] == str(version_id))
    scoreboard_row = next(
        row for row in scoreboard_response.json()["rows"] if row["version"]["id"] == str(version_id)
    )
    assert version["verdict"] == scoreboard_row["verdict"]
    assert version["maturity"] == scoreboard_row["maturity"]
