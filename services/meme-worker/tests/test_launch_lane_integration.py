"""T4.67a against a real Postgres (testcontainers): a ``create`` writes one
proposal for ``launch_v0/1`` and — behind ``paper``/``on`` — opens and closes
one ``meme_paper_bets`` row from a replayed exit event; ``off`` never calls
this module at all (``launch_lane_wiring.build_launch_lane`` returns
``None`` — proved in ``test_launch_lane_wiring.py``, pure, no Docker).

**What "replayed" means here.** The WS wire-decoding of a ``TradeEvent`` off
a ``logsSubscribe`` frame is already proven against real captures in
``packages/exchange-adapters/tests/unit/test_pumpfun_rpc_ws.py`` (T4.52b-1)
and ``event_gate_notify.py`` for the event gate. This module replays the
**decoded** shape instead — a sequence of ``NormalizedCurveTrade`` folded
into the same ``MintEventState`` the notification path would have built —
so what is proved here is the launch lane's own logic (the +1 s entry, the
three exits, the DB writes), not the decoder a second time. Run alone
(``timeout 590``): shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.models import NormalizedCurveTrade, NormalizedMemeTokenCreated
from hunter_exchanges.pumpfun.solana_codec import b58encode
from hunter_indicators.meme.curve import INITIAL_REAL_TOKEN_RESERVES, INITIAL_VIRTUAL_TOKEN_RESERVES
from hunter_meme_worker.launch_lane_config import LAUNCH_LANE_PAPER, LaunchLaneConfig
from hunter_meme_worker.launch_lane_eval import on_create, progress_mint
from hunter_meme_worker.launch_lane_repo import LaunchRuleSpec
from hunter_meme_worker.launch_lane_runtime import LaunchLaneRuntime

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
CREATED = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
CREATOR = "CreatorWa11etAddress1111111111111111111111"
BUYER = "ThirdPartyBuyerAddress111111111111111111111"


class Waker:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> None:
        self.calls += 1


@dataclass
class FakeWs:
    """The two subscribe calls the launch lane makes per watch, and nothing
    else — ``listen()``/reconnect are the event gate's own, already proven."""

    next_id: int = 1
    subscribed: list[tuple[str, str]] = field(default_factory=lambda: list[tuple[str, str]]())
    unsubscribed: list[int] = field(default_factory=lambda: list[int]())

    async def subscribe_logs(self, *, mentions: list[str], commitment: str) -> int:
        self.subscribed.append(("logs", mentions[0]))
        self.next_id += 1
        return self.next_id - 1

    async def subscribe_account(self, pubkey: str, *, commitment: str) -> int:
        self.subscribed.append(("account", pubkey))
        self.next_id += 1
        return self.next_id - 1

    async def unsubscribe(self, logical_id: int) -> bool:
        self.unsubscribed.append(logical_id)
        return True


def _mint() -> str:
    return b58encode(os.urandom(32))


def _spec(rule_set_id: str) -> LaunchRuleSpec:
    return LaunchRuleSpec(
        id=rule_set_id,
        name="launch_test",
        version="1",
        kind="research_only",
        exp_ref="EXP-M18",
        status="active",
        size_sol=Decimal("0.01"),
        max_creator_initial_sol=Decimal(2),
        exit_key="lancamento_6s_ou_primeiro_sell",
        time_stop_s=6,
        exit_on_first_third_party_sell=True,
        max_drawdown_from_peak_pct=Decimal(20),
    )


async def _insert_launch_rule_set(engine: AsyncEngine, rule_set_id: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref) "
                "VALUES (:id, :name, '1', 'research_only', "
                '  \'{"size_sol": "0.01", "max_creator_initial_sol": "2", '
                '     "exit_key": "lancamento_6s_ou_primeiro_sell", "time_stop_s": 6, '
                '     "exit_on_first_third_party_sell": true, '
                '     "max_drawdown_from_peak_pct": "20", "clock": "event"}\'::jsonb, '
                "  'test', 'EXP-M18')"
            ),
            {"id": rule_set_id, "name": f"launch_test_{uuid4().hex[:10]}"},
        )


def _event(mint: str) -> NormalizedMemeTokenCreated:
    return NormalizedMemeTokenCreated(
        mint=mint,
        name="Fresh",
        symbol=f"F{mint[-6:]}",
        uri="https://example.test/f.json",
        creator=CREATOR,
        created_at=CREATED,
        bonding_curve=f"curve-{mint}",
        initial_virtual_sol_reserves=Decimal(30),
        initial_virtual_token_reserves=INITIAL_VIRTUAL_TOKEN_RESERVES,
        creator_initial_tokens=Decimal(0),
        creator_initial_sol=Decimal("0.5"),
        signature=f"sig-{mint}",
        mayhem_enabled=False,
        observed_at=CREATED,
        received_at=CREATED,
    )


def _trade(
    mint: str, *, at: datetime, side: str, trader: str, real_sol: Decimal, real_token: Decimal
) -> NormalizedCurveTrade:
    return NormalizedCurveTrade(
        mint=mint,
        slot=1,
        signature=f"sig-{mint}-{at.timestamp()}-{trader}",
        trader=trader,
        side=side,  # type: ignore[arg-type]
        lamports=Decimal(1_000_000),
        virtual_sol_reserves=Decimal(31),
        virtual_token_reserves=Decimal(1_000_000_000),
        real_sol_reserves=real_sol,
        real_token_reserves=real_token,
        creator=CREATOR,
        mayhem=False,
        block_time=at,
        received_at=at,
    )


async def _proposal_row(
    factory: async_sessionmaker[AsyncSession], mint: str, rule_set_id: str
) -> dict[str, Any]:
    async with role_session(factory, db_role=WORKER) as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT status, decided_by, features_end_time, reasons, quote FROM meme_proposals "
                        "WHERE mint = :m AND rule_set_id = CAST(:rs AS uuid)"
                    ),
                    {"m": mint, "rs": rule_set_id},
                )
            )
            .mappings()
            .all()
        )
    assert len(row) == 1, row
    return dict(row[0])


async def _bet_rows(factory: async_sessionmaker[AsyncSession], mint: str) -> list[dict[str, Any]]:
    async with role_session(factory, db_role=WORKER) as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT status, exit, mark_source, pnl_sol FROM meme_paper_bets WHERE mint = :m"
                    ),
                    {"m": mint},
                )
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]


@pytest.mark.asyncio
async def test_a_create_writes_one_proposal_with_the_launch_series(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    rule_set_id = str(uuid4())
    await _insert_launch_rule_set(db_engine, rule_set_id)
    mint = _mint()
    rt = LaunchLaneRuntime(
        config=LaunchLaneConfig(mode=LAUNCH_LANE_PAPER, ws_url="", commitment="confirmed"),
        ws=FakeWs(),  # type: ignore[arg-type]
        session_factory=db_session_factory,
        wake=Waker(),
        specs=(_spec(rule_set_id),),
    )
    await on_create(rt, _event(mint), CREATED)
    proposal = await _proposal_row(db_session_factory, mint, rule_set_id)
    assert proposal["status"] == "approved"
    assert proposal["decided_by"] == "rules"
    assert proposal["reasons"][0]["series"] == "meme_launch_lane_v1"
    assert mint in rt.watches, "paper mode subscribes for the +1s entry"
    assert rt.wake.calls == 1  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_a_replayed_exit_event_opens_and_closes_one_paper_bet(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    rule_set_id = str(uuid4())
    await _insert_launch_rule_set(db_engine, rule_set_id)
    mint = _mint()
    rt = LaunchLaneRuntime(
        config=LaunchLaneConfig(mode=LAUNCH_LANE_PAPER, ws_url="", commitment="confirmed"),
        ws=FakeWs(),  # type: ignore[arg-type]
        session_factory=db_session_factory,
        wake=Waker(),
        specs=(_spec(rule_set_id),),
    )
    await on_create(rt, _event(mint), CREATED)
    watch = rt.watches[mint]

    # +1.2 s: the entry price arrives.
    entry_at = CREATED + timedelta(seconds=1, milliseconds=200)
    watch.state.apply_trade(
        _trade(
            mint,
            at=entry_at,
            side="buy",
            trader=CREATOR,
            real_sol=Decimal(2),
            real_token=INITIAL_REAL_TOKEN_RESERVES - Decimal(1_000_000),
        )
    )
    await progress_mint(rt, mint, entry_at, None)
    assert watch.entered is True
    open_rows = await _bet_rows(db_session_factory, mint)
    assert len(open_rows) == 1 and open_rows[0]["status"] == "open"

    # +2.5 s: a third party sells — the replayed exit event.
    from hunter_meme_worker.features_tape import TapeTrade

    sell_at = entry_at + timedelta(seconds=1, milliseconds=300)
    watch.state.apply_trade(
        _trade(
            mint,
            at=sell_at,
            side="sell",
            trader=BUYER,
            real_sol=Decimal("1.9"),
            real_token=INITIAL_REAL_TOKEN_RESERVES,
        )
    )
    sell_trade = TapeTrade(
        block_time=sell_at, received_at=sell_at, trader=BUYER, side="sell", sol_lamports=1_000_000
    )
    await progress_mint(rt, mint, sell_at, sell_trade)
    assert watch.closed is True
    assert mint not in rt.watches, "closed watches are unsubscribed and dropped"
    closed_rows = await _bet_rows(db_session_factory, mint)
    assert len(closed_rows) == 1
    assert closed_rows[0]["status"] == "closed"
    assert closed_rows[0]["exit"]["reason"] == "first_third_party_sell"
    assert closed_rows[0]["mark_source"] == "solana_ws"
    assert rt.wake.calls == 2  # type: ignore[union-attr]  # one on the proposal, one on the close
