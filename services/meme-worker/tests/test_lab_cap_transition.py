"""A bet that crosses the deploy of the sale-cap fix (bug of 07/10) against a
real Postgres at ``head``: its entry was written before ``sell_cap_model``
existed, the exit after. The row must show the crossing (exit stamped, entry
not) and the cap must use the bet's own ``curve_cost_sol`` read back from the
row — never a zero that would bring the old cap back silently.

The pre-deploy entry is SYNTHETIC: a bet filled by today's code with the
stamp removed by the owner, which is the only difference between the two.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker.lab import LabContext, lab_tick
from hunter_meme_worker.lab_repo_bets import load_open_bets
from hunter_meme_worker.lab_values import SELL_CAP_MODEL
from hunter_meme_worker.repo import insert_snapshot

from .test_lab_mayhem import (
    OWN,
    RECEIVED,
    VAULT,
    WORKER,
    _plant_mayhem,  # pyright: ignore[reportPrivateUsage]
    _pushed,  # pyright: ignore[reportPrivateUsage]
)
from .test_lab_persistence import (
    NOW,
    FakeQuotes,
    Heartbeats,
    _approve,  # pyright: ignore[reportPrivateUsage]
    _bet_of,  # pyright: ignore[reportPrivateUsage]
    _rule_set,  # pyright: ignore[reportPrivateUsage]
    _snapshot,  # pyright: ignore[reportPrivateUsage]
    lab,
)

__all__ = ["lab"]  # the fixture travels with its module

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def _open_mayhem_bet(
    ctx: LabContext, factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> tuple[str, str]:
    rule_set = await _rule_set(engine, f"captr_{uuid4().hex[:6]}")
    mint = f"CAPT_{uuid4().hex[:8]}"
    decided = NOW - timedelta(seconds=60)
    entry_at = decided + timedelta(seconds=30)
    await _plant_mayhem(factory, mint, created_at=decided - timedelta(minutes=2))
    async with role_session(factory, db_role=WORKER) as session:
        await insert_snapshot(
            session, replace(_snapshot(mint, entry_at, "32.4", "993000000"), mayhem_enabled=True)
        )
    proposal = await _approve(factory, mint=mint, rule_set_id=rule_set, decided_at=decided)
    assert (await lab_tick(ctx, now=NOW)).fills.filled == 1
    return proposal, mint


async def _strip_entry_key(engine: AsyncEngine, bet_id: str, key: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE meme_paper_bets SET entry = entry - CAST(:key AS text) WHERE id = :id"),
            {"key": key, "id": bet_id},
        )


async def test_a_bet_filled_before_the_fix_is_sold_with_its_own_buy_and_shows_the_crossing(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    proposal, mint = await _open_mayhem_bet(ctx, db_session_factory, db_engine)
    opened = await _bet_of(db_session_factory, proposal)
    await _strip_entry_key(db_engine, str(opened["id"]), "sell_cap_model")
    old = await _bet_of(db_session_factory, proposal)
    assert "sell_cap_model" not in old["entry"], "the synthetic pre-deploy entry"
    assert Decimal(old["entry"]["curve_cost_sol"]) == OWN

    trigger = NOW + timedelta(seconds=30)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _pushed(mint, trigger))  # type: ignore[arg-type]
    await lab_tick(ctx, now=trigger + timedelta(seconds=5))
    sale_at = trigger + timedelta(seconds=30)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _pushed(mint, sale_at))  # type: ignore[arg-type]
    await lab_tick(ctx, now=sale_at + timedelta(seconds=5))

    closed = await _bet_of(db_session_factory, proposal)
    assert closed["status"] == "closed"
    assert "sell_cap_model" not in closed["entry"]
    assert closed["exit"]["sell_cap_model"] == SELL_CAP_MODEL, "exit stamped, entry not: crossing"
    assert closed["exit"]["own_curve_sol"] == str(OWN) != "0"
    assert closed["exit"]["sell_cap_sol"] == str(VAULT)
    assert closed["exit"]["sol_received"] == RECEIVED


async def test_a_bet_row_without_its_curve_cost_is_refused_never_read_as_zero(
    lab: tuple[LabContext, FakeQuotes, Heartbeats],
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    ctx, _quotes, _beats = lab
    proposal, _mint = await _open_mayhem_bet(ctx, db_session_factory, db_engine)
    opened = await _bet_of(db_session_factory, proposal)
    await _strip_entry_key(db_engine, str(opened["id"]), "curve_cost_sol")
    try:
        async with role_session(db_session_factory, db_role=WORKER) as session:
            with pytest.raises(KeyError, match="curve_cost_sol"):
                await load_open_bets(session)
    finally:
        async with db_engine.begin() as connection:  # leave no poisoned open bet behind
            await connection.execute(
                text(
                    "UPDATE meme_paper_bets SET entry = entry || "
                    "jsonb_build_object('curve_cost_sol', CAST(:own AS text)) WHERE id = :id"
                ),
                {"own": opened["entry"]["curve_cost_sol"], "id": str(opened["id"])},
            )
