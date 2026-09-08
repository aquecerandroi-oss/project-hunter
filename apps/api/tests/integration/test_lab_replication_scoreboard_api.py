"""Integration tests: ``ScoreboardRowOut.replication`` — brief T3.18b, item 2.

A seeded parent with ``promising_at`` and one sibling cohort
(``replication:<parent>:<k>``), proving the block: null before the version
was ever validated, populated (status ``promissora``) once ``promising_at``
is set, and carrying the sibling's D15 ``evidence`` label once it has
outcomes of its own.
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


async def test_never_validated_is_null(
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
    actor = make_actor("replication-null")

    row = await _row(client, actor, version_id)

    assert row["replication"] is None


async def test_promising_with_no_siblings_yet_is_promissora(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    promising_at = NOW - timedelta(days=5)
    _, version_id = await fx.seed_strategy_version(
        session_factory,
        activated_at=NOW - timedelta(days=10),
        promising_at=promising_at,
        promising_by="validada",
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
    actor = make_actor("replication-promissora")

    row = await _row(client, actor, version_id)

    replication = row["replication"]
    assert replication is not None
    assert replication["status"] == "promissora"
    assert replication["promising_at"] is not None
    assert replication["siblings"] == {
        "passed": None,
        "reason": "sem_irmas",
        "n": 0,
        "expected": 10,
        "required": 7,
        "mature": 0,
        "positive": 0,
        "arms": [],
    }


async def test_one_sibling_cohort_shows_up_with_its_evidence_label(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    promising_at = NOW - timedelta(days=20)
    parent_strategy_id, parent_id = await fx.seed_strategy_version(
        session_factory,
        activated_at=NOW - timedelta(days=30),
        promising_at=promising_at,
        promising_by="validada",
    )
    market_id = await fx.seed_lab_market(session_factory)
    # the parent needs at least one *prospective* signal to appear on the
    # scoreboard at all (T3.18's population rule: "ever emitted prospective").
    await fx.seed_shadow_signal(
        session_factory,
        strategy_version_id=parent_id,
        market_id=market_id,
        decision_at=NOW - timedelta(hours=1),
        exit_ts=NOW - timedelta(minutes=30),
        entry_ts=NOW - timedelta(minutes=59),
        result=OutcomeResult.TARGET,
        r_multiple=Decimal("1"),
    )

    _, sibling_id = await fx.seed_strategy_version(
        session_factory,
        strategy_id=parent_strategy_id,
        version="v2",
        activated_at=NOW - timedelta(days=19),
        replication_parent_id=parent_id,
        replication_index=1,
        changelog=(
            f"replication:{parent_id}:1 | irmã 1 de v1 (T3.19, docs/plans/REPLICATION.md) "
            f"| promising_at={promising_at.isoformat()} | seed=99 | pct=0.15 | teste"
        ),
    )
    live_cohort = f"replication:{parent_id}:1"
    decision_at = NOW - timedelta(days=10)
    for i in range(4):
        await fx.seed_shadow_signal(
            session_factory,
            strategy_version_id=sibling_id,
            market_id=market_id,
            decision_at=decision_at + timedelta(minutes=i),
            exit_ts=decision_at + timedelta(hours=1, minutes=i),
            entry_ts=decision_at + timedelta(minutes=i + 1),
            result=OutcomeResult.TARGET,
            r_multiple=Decimal("1"),
            cohort=live_cohort,
        )
    actor = make_actor("replication-one-sibling")

    row = await _row(client, actor, parent_id)

    replication = row["replication"]
    assert replication is not None
    assert replication["siblings"]["n"] == 1
    arm = replication["siblings"]["arms"][0]
    assert arm["k"] == 1
    assert arm["version"] == "v2"
    assert arm["evaluable"] == 4
    assert arm["evidence"] == "prospective"
    # a sibling's own signals live under its ``replication:<parent>:<k>``
    # cohort, never ``prospective`` — so it does not get a scoreboard row of
    # its own under T3.18's population rule (out of this brief's scope:
    # ``versions_with_signals`` is unchanged). The parent's card, asserted
    # above, is the sibling's only representation on this endpoint today.
