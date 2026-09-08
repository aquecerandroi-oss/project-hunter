"""Integration tests: ``ScoreboardRowOut.replay`` — brief T3.18b, item 1 (D14/D15).

Proves the block is populated from ``replay:<uuid>`` cohorts and
``replay_runs`` receipts, and — the brief's explicit assertion — that a
version whose replay is positive and whose prospective is negative still
gets its verdict and maturity from prospective alone.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from hunter_core.domain.enums import OutcomeResult

from . import lab_fixtures as fx
from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


async def _row(client: httpx.AsyncClient, actor: Actor, version_id: uuid.UUID) -> dict[str, Any]:
    response = await client.get(
        "/api/v1/lab/shadow/scoreboard", params={"as_of": NOW.isoformat()}, headers=actor.headers
    )
    assert response.status_code == 200, response.text
    return next(r for r in response.json()["rows"] if r["version"]["id"] == str(version_id))


async def test_no_replay_evidence_is_null(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=1)
    )
    market_id = await fx.seed_lab_market(session_factory)
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=NOW - timedelta(hours=1),
        exit_ts=NOW - timedelta(minutes=30),
        entry_ts=NOW - timedelta(minutes=59),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1"),
    )
    actor = make_actor("replay-block-null")

    row = await _row(client, actor, version_id)

    assert row["replay"] is None


async def test_replay_positive_and_prospective_negative_never_swap_the_verdict(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """The brief's own assertion (item 1): a version whose ``replay`` block is
    positive and whose prospective population is negative keeps its verdict
    and maturity computed on prospective alone."""
    _, version_id = await fx.seed_strategy_version(
        session_factory, activated_at=NOW - timedelta(days=2)
    )
    market_id = await fx.seed_lab_market(session_factory)

    # prospective: a single mature loss -> immature (verdict "inconclusivo"),
    # but if it ever counted, strictly negative expectancy.
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=version_id,
        market_id=market_id,
        decision_at=NOW - timedelta(hours=6),
        exit_ts=NOW - timedelta(hours=5),
        entry_ts=NOW - timedelta(hours=6) + timedelta(minutes=1),
        result=OutcomeResult.STOP,
        r_multiple=Decimal("-1"),
        cohort="prospective",
    )

    # replay: several winners under one receipted run.
    run_id = uuid.uuid4()
    decision_at = NOW - timedelta(days=10)
    for i in range(3):
        await fx.seed_shadow_signal(
            session_factory,
            strategy_version_id=version_id,
            market_id=market_id,
            decision_at=decision_at + timedelta(minutes=i),
            exit_ts=decision_at + timedelta(hours=1, minutes=i),
            entry_ts=decision_at + timedelta(minutes=i + 1),
            result=OutcomeResult.TARGET,
            r_multiple=Decimal("2"),
            cohort=f"replay:{run_id}",
        )
    await fx.seed_replay_slice(
        session_factory,
        run_id=run_id,
        strategy_version_id=version_id,
        window_from=decision_at - timedelta(hours=1),
        window_to=NOW - timedelta(days=9),
        markets=["labex:LABUSDT"],
        started_at=decision_at,
        finished_at=decision_at + timedelta(minutes=5),
        bars_evaluated=288,
        signals=3,
        outcomes_resolved=3,
        outcomes_open=0,
        seconds=Decimal("12.500"),
    )
    actor = make_actor("replay-verdict-isolation")

    row = await _row(client, actor, version_id)

    # verdict/maturity: prospective only, one immature loss.
    assert row["evaluable"] == 1
    assert row["maturity"]["mature"] is False
    assert row["verdict"] == "inconclusivo"

    # replay block: positive, separate, labelled, never touching the above.
    replay = row["replay"]
    assert replay is not None
    assert replay["runs"] == 1
    assert replay["decisions_simulated"] == 288
    assert replay["operations_closed"] == 3
    assert replay["expectancy_r"]["value"] == "2"
    assert replay["net_profit_rate"] == {
        "value": "1",
        "reason": None,
        "numerator": 3,
        "denominator": 3,
    }
    assert replay["label"] == "replay — não conta para o veredito"
    assert replay["window_from"] is not None
    assert replay["window_to"] is not None
