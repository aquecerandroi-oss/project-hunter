# pyright: reportPrivateUsage=false
"""H-031b (EXP-M27) — the twin's bet through the real loop, against Postgres.

``test_creator_watch_persistence`` proves a bet of an ordinary set closes
``creator_dump`` one photo after the chain watch sees the creator sell. Here the
same scene runs on a set whose params say ``"exit_on_creator_dump": false``:
the fill records ``false`` on the bet, the watch still stamps the sale (the
observation is measured on both arms — H-031b's latency reads it), and the next
photo does **not** close the bet; reloaded from the row (a restart), the bet
still runs without the exit. Astra, ``H-031b-diff`` nice-to-have 1.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.creator_watch import CreatorWatchState, creator_watch_once
from hunter_meme_worker.lab import LabContext, LabState, lab_tick
from hunter_meme_worker.lab_repo_bets import load_open_bets
from hunter_meme_worker.repo import insert_snapshot

from .test_creator_watch_persistence import NOW, FakeChain, _account, _mint, _radar, _set_creator
from .test_lab_persistence import (
    WORKER,
    FakeQuotes,
    Heartbeats,
    _approve,
    _bet_of,
    _plant_curve,
    _rule_set,
    _snapshot,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def lab(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[LabContext]:
    yield LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=db_session_factory,
        state=LabState(),
        quotes=FakeQuotes(),
        heartbeat=Heartbeats(),
    )


async def test_the_twin_sees_the_sale_and_keeps_running(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    rule_set = await _rule_set(db_engine, f"twin_{uuid4().hex[:6]}")
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_rule_sets SET params = params || "
                "'{\"exit_on_creator_dump\": false}'::jsonb WHERE id = :id"
            ),
            {"id": rule_set},
        )
    mint = _mint("twin")
    decided = NOW - timedelta(seconds=60)
    entry_at = decided + timedelta(seconds=30)
    await _plant_curve(
        db_session_factory,
        mint,
        [(entry_at, "32.4", "993000000")],
        created_at=decided - timedelta(minutes=2),
    )
    await _set_creator(db_session_factory, mint)
    proposal = await _approve(
        db_session_factory, mint=mint, rule_set_id=rule_set, decided_at=decided
    )
    assert (await lab_tick(lab, now=NOW)).fills.filled >= 1
    opened = await _bet_of(db_session_factory, proposal)
    assert opened["params"]["exit_on_creator_dump"] is False, "the bet says what it runs on"

    chain = FakeChain([[_account("1000"), None], [_account("400"), None]])
    ctx, state = _radar(db_session_factory, chain), CreatorWatchState()
    await creator_watch_once(ctx, state)
    await creator_watch_once(ctx, state)
    seen_at = (await _bet_of(db_session_factory, proposal))["creator_sold_seen_at"]
    assert seen_at is not None, "the sale is still observed on the twin"

    photo = seen_at + timedelta(seconds=15)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, photo, "31", "1000000000"))
    await lab_tick(lab, now=photo + timedelta(seconds=5))

    after = await _bet_of(db_session_factory, proposal)
    assert after["status"] == "open", "no creator_dump on the twin"
    assert after["exit_intent"] is None
    async with role_session(db_session_factory, db_role=WORKER) as session:
        reloaded = {b.state.id: b for b in await load_open_bets(session)}
    bet = reloaded[str(after["id"])]
    assert bet.creator_sold_seen_at == seen_at
    assert bet.state.params.exit_rules().exit_on_creator_dump is False, "a restart keeps it off"
