# pyright: reportPrivateUsage=false
"""T4.2h-b — the creator watch against a real Postgres at ``head``: one loop,
two ledgers, and the latency measured instead of assumed.

What only a database can prove, and why each line is here:

1. **Two readings, one sale.** A first ``getMultipleAccounts`` teaches the loop
   the creator's balance and marks nothing (a restart starts blind, it never
   invents a previous balance); the second, 1000 → 400, stamps
   ``creator_sold_seen_at`` with ``creator_sold_fraction = 0.6`` on the open
   **paper bet** (``0036``) *and* on the open **real position** (``0038``), from
   the same reading, in one transaction.
2. **The reader sees it.** ``lab_repo_bets.load_open_bets`` reports
   ``creator_net_seller = true`` off the stamp alone — no tape needed — and the
   executor's ``open_positions`` reports ``creator_dump_seen(None) is True``,
   which is exactly what its 5-second tick calls.
3. **The exit lands on the next photo, inside 30 s.** The sale is an
   observation with its own clock, so the intent is the sale's instant and the
   **first** later snapshot prices it. Before this task the loop needed one
   photo to decide and another to price — two 15-second photos on a young mint,
   a whole minute on an older one, which is the 149 s measured on 15/09.
4. **A creator with no token account is unmeasured.** ``creator_ata_missing``
   on both ledgers, ``creator_sold_seen_at`` still ``NULL``, and no exit — the
   bet keeps running on its other rules. Silence is never "the dev did not sell".

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.base58 import b58encode
from hunter_meme_executor.repo_positions import open_positions
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.creator_stats import CreatorWatchStats, sale_to_exit_samples
from hunter_meme_worker.creator_watch import (
    ATA_MISSING,
    CreatorWatchState,
    ata_targets,
    creator_watch_once,
)
from hunter_meme_worker.lab import LabContext, LabState, lab_tick
from hunter_meme_worker.lab_repo_bets import load_open_bets
from hunter_meme_worker.repo import insert_snapshot
from hunter_meme_worker.tracker import MintTracker

from .test_lab_persistence import (
    APP,
    RESEARCH_ID,
    WORKER,
    FakeQuotes,
    Heartbeats,
    _approve,
    _bet_of,
    _one,
    _plant_curve,
    _rule_set,
    _snapshot,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

CREATOR = b58encode(b"t42hb-creator-wallet-xxxxxxxxxxx")
"""A real 32-byte pubkey: ``associated_token_address`` derives a PDA from it, so
a made-up ``CREATOR_abc`` string would not survive base58."""

NOW = utcnow().replace(microsecond=0)
"""**The wall clock, on purpose.** ``creator_watch_once`` stamps the reading
with its own ``utcnow()`` — it is a chain read, not a replay — so a fixture
pinned to a fictional month would produce a sale stamped before the bet was
even opened. Everything this file plants is placed around the real instant, and
every assertion is relative (``exit_at − creator_sold_seen_at``), never a date."""


def _mint(tag: str) -> str:
    """A unique, base58-decodable 32-byte mint for one test."""
    body = f"t42hb-{tag}-".encode() + uuid4().hex.encode()
    return b58encode(body[:32].ljust(32, b"x"))


def _account(amount: str) -> dict[str, Any]:
    return {"data": {"parsed": {"info": {"tokenAmount": {"amount": amount}}}}}


class FakeChain:
    """``ctx.chain`` as the watch uses it: one ``call`` per cycle, scripted.

    Each script entry is the list the RPC would answer for the addresses of
    **one** cycle, in the order ``ata_targets`` asks for them (classic ATA then
    Token-2022 ATA, per mint).
    """

    def __init__(self, script: list[list[Any]]) -> None:
        self.script = script
        self.asked: list[list[str]] = []

    async def call(self, method: str, params: list[Any]) -> dict[str, Any]:
        assert method == "getMultipleAccounts"
        self.asked.append(list(params[0]))
        return {"value": self.script[len(self.asked) - 1]}


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


def _radar(
    factory: async_sessionmaker[AsyncSession],
    chain: FakeChain,
    stats: CreatorWatchStats | None = None,
) -> RadarContext:
    return RadarContext(
        config=MemeConfig(),
        session_factory=factory,
        tracker=MintTracker(window_minutes=60, cap=10, young_minutes=30),
        state=RadarState(),
        events=None,  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=chain,  # type: ignore[arg-type]
        creator=stats or CreatorWatchStats(),
    )


async def _set_creator(factory: async_sessionmaker[AsyncSession], mint: str) -> None:
    async with role_session(factory, db_role=WORKER) as session:
        await session.execute(
            text("UPDATE meme_tokens SET creator = :creator WHERE mint = :mint"),
            {"creator": CREATOR, "mint": mint},
        )


async def _open_bet_with_creator(
    ctx: LabContext,
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    tag: str,
) -> tuple[str, str, Any]:
    """A filled paper bet on a base58 mint whose creator is known."""
    rule_set = await _rule_set(engine, f"{tag}_{uuid4().hex[:6]}")
    mint = _mint(tag)
    decided = NOW - timedelta(seconds=60)
    entry_at = decided + timedelta(seconds=30)
    await _plant_curve(
        factory, mint, [(entry_at, "32.4", "993000000")], created_at=decided - timedelta(minutes=2)
    )
    await _set_creator(factory, mint)
    proposal = await _approve(factory, mint=mint, rule_set_id=rule_set, decided_at=decided)
    assert (await lab_tick(ctx, now=NOW)).fills.filled >= 1
    return mint, proposal, entry_at


async def _open_live_position(
    factory: async_sessionmaker[AsyncSession], mint: str, *, entry_at: Any
) -> str:
    """The executor's own row shape (``0028``): proposal → confirmed buy → position."""
    proposal_id, order_id, position_id = str(uuid4()), str(uuid4()), str(uuid4())
    rule_set = RESEARCH_ID
    async with role_session(factory, db_role=WORKER) as session:
        await session.execute(
            text(
                "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
                "  expires_at, decision, decided_by, decided_at, mode) VALUES (:id, :mint, "
                "  :rule_set, 'operator', 'approved', :at, :expires, '{}'::jsonb, 'user_test', "
                "  :at, 'paper')"
            ),
            {
                "id": proposal_id,
                "mint": mint,
                "rule_set": rule_set,
                "at": entry_at,
                "expires": entry_at + timedelta(seconds=120),
            },
        )
        await session.execute(
            text(
                "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, attempt, "
                "  status, tx_signature, fill) VALUES (:id, :proposal, 'buy', :key, 1, "
                "  'confirmed', :signature, '{}'::jsonb)"
            ),
            {
                "id": order_id,
                "proposal": proposal_id,
                "key": f"meme:{proposal_id}",
                "signature": f"sig-{order_id}",
            },
        )
        await session.execute(
            text(
                "INSERT INTO meme_live_positions (id, proposal_id, entry_order_id, mint, status, "
                "  entry_at, entry, tokens, sol_spent_lamports, initial_risk_sol, params) "
                "VALUES (:id, :proposal, :order, :mint, 'open', :at, '{}'::jsonb, 1000000, "
                "  50000000, 0.05, CAST(:params AS jsonb))"
            ),
            {
                "id": position_id,
                "proposal": proposal_id,
                "order": order_id,
                "mint": mint,
                "at": entry_at,
                "params": json.dumps({"target_x": "3", "max_hold_s": 1800}),
            },
        )
    return position_id


async def _position(factory: async_sessionmaker[AsyncSession], position_id: str) -> Any:
    return await _one(
        factory,
        "SELECT creator_sold_seen_at, creator_sold_fraction, creator_balance_reason "
        "FROM meme_live_positions WHERE id = :id",
        id=position_id,
    )


async def test_the_second_reading_stamps_the_sale_on_the_bet_and_on_the_real_position(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    mint, proposal, entry_at = await _open_bet_with_creator(lab, db_session_factory, db_engine, "a")
    position_id = await _open_live_position(db_session_factory, mint, entry_at=entry_at)
    chain = FakeChain([[_account("1000"), None], [_account("400"), None]])
    stats = CreatorWatchStats()
    ctx, state = _radar(db_session_factory, chain, stats), CreatorWatchState()

    first = await creator_watch_once(ctx, state)
    assert (first.mints, first.live_mints, first.drops) == (1, 1, 0), (
        "a first reading is not a sale"
    )
    assert (await _bet_of(db_session_factory, proposal))["creator_sold_seen_at"] is None
    assert (await _position(db_session_factory, position_id))["creator_sold_seen_at"] is None
    assert chain.asked[0] == [address for _mint_, address in ata_targets([(mint, CREATOR)])]

    second = await creator_watch_once(ctx, state)
    assert (second.drops, second.missing, second.live_mints) == (1, 0, 1)
    bet = await _bet_of(db_session_factory, proposal)
    position = await _position(db_session_factory, position_id)
    assert bet["creator_sold_seen_at"] is not None
    assert bet["creator_sold_fraction"] == Decimal("0.600000")
    assert position["creator_sold_seen_at"] == bet["creator_sold_seen_at"], "one reading, one stamp"
    assert position["creator_sold_fraction"] == Decimal("0.600000")

    async with role_session(db_session_factory, db_role=WORKER) as session:
        opened = {b.state.mint: b for b in await load_open_bets(session)}
        live = {p.mint: p for p in await open_positions(session)}
    assert opened[mint].creator_net_seller is True, "the reader needs no tape to know"
    assert opened[mint].creator_sold_seen_at == bet["creator_sold_seen_at"]
    assert live[mint].creator_sold_seen_at == bet["creator_sold_seen_at"]
    assert live[mint].creator_dump_seen(None) is True, "what the 5 s exit tick asks"
    assert stats.heartbeat_fields(NOW)["creator_watch_drops_1h"] == "1"


async def test_the_exit_lands_on_the_next_photo_and_inside_thirty_seconds(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    mint, proposal, _entry = await _open_bet_with_creator(lab, db_session_factory, db_engine, "b")
    chain = FakeChain([[_account("1000"), None], [_account("400"), None]])
    ctx, state = _radar(db_session_factory, chain), CreatorWatchState()
    await creator_watch_once(ctx, state)
    await creator_watch_once(ctx, state)
    seen_at = (await _bet_of(db_session_factory, proposal))["creator_sold_seen_at"]

    photo = seen_at + timedelta(seconds=15)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, photo, "31", "1000000000"))
    await lab_tick(lab, now=photo + timedelta(seconds=5))

    closed = await _bet_of(db_session_factory, proposal)
    assert closed["status"] == "closed", "one photo after the sale, not two"
    assert closed["exit"]["reason"] == "creator_dump"
    assert closed["exit"]["trigger"] == "creator_watch"
    assert closed["exit_intent"]["decided_at"] == seen_at.isoformat()
    assert closed["exit_at"] == photo
    latency = (closed["exit_at"] - seen_at).total_seconds()
    assert latency <= 30, f"seen-sale → exit took {latency} s"
    async with role_session(db_session_factory, db_role=WORKER) as session:
        samples = await sale_to_exit_samples(session)
    assert samples and samples[0] == int(latency), "the heartbeat measures it from the rows"


async def test_a_creator_without_a_token_account_is_unmeasured_never_a_sale(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    mint, proposal, entry_at = await _open_bet_with_creator(lab, db_session_factory, db_engine, "c")
    position_id = await _open_live_position(db_session_factory, mint, entry_at=entry_at)
    chain = FakeChain([[None, None]])
    ctx = _radar(db_session_factory, chain)

    report = await creator_watch_once(ctx, CreatorWatchState())
    assert (report.missing, report.drops) == (1, 0)
    bet = await _bet_of(db_session_factory, proposal)
    position = await _position(db_session_factory, position_id)
    assert bet["creator_balance_reason"] == ATA_MISSING
    assert position["creator_balance_reason"] == ATA_MISSING
    assert bet["creator_sold_seen_at"] is None and position["creator_sold_seen_at"] is None

    photo = NOW + timedelta(seconds=15)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, photo, "32.4", "993000000"))
    await lab_tick(lab, now=photo + timedelta(seconds=5))
    assert (await _bet_of(db_session_factory, proposal))["status"] == "open"


async def test_the_app_role_cannot_write_the_watch_columns_of_a_real_position(
    lab: LabContext,
    db_session_factory: async_sessionmaker[AsyncSession],
    db_engine: AsyncEngine,
) -> None:
    """``0038`` grants nothing: the API may still only ask for a sale."""
    from sqlalchemy.exc import ProgrammingError

    mint, _proposal, entry_at = await _open_bet_with_creator(
        lab, db_session_factory, db_engine, "d"
    )
    position_id = await _open_live_position(db_session_factory, mint, entry_at=entry_at)
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with role_session(db_session_factory, db_role=APP) as session:
            await session.execute(
                text("UPDATE meme_live_positions SET creator_sold_seen_at = now() WHERE id = :id"),
                {"id": position_id},
            )
