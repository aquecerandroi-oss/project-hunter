"""Shared rig of the copy-lane integration tests (H-037): a lane over a real Postgres with a fake
chain and a fake clock that sleeping advances. Labeled test code; nothing here ships."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.solana_codec import b58encode
from hunter_meme_worker.copy_lane import CopyLane
from hunter_meme_worker.copy_spec import CopySpec

from .copy_fakes import FakeChain, FakeClock
from .copy_support import PARAMS, T0

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

WORKER = "hunter_worker"
LATENCY_MS = 250


def addr(prefix: str) -> str:
    return b58encode(os.urandom(32))[:43] + prefix


async def rule_set(engine: AsyncEngine, wallet_a: str, wallet_b: str, **overrides: Any) -> CopySpec:
    rule_set_id = str(uuid4())
    params: dict[str, Any] = {
        **PARAMS,
        "exec_latency_s": str(Decimal(LATENCY_MS) / 1000),
        "leaders": [
            {"wallet": wallet_a, "stratum": "regra"},
            {"wallet": wallet_b, "stratum": "regra"},
        ],
        **overrides,
    }
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref) "
                "VALUES (:id, :name, '1', 'research_only', CAST(:params AS jsonb), 'test', 'EXP-M28')"
            ),
            {
                "id": rule_set_id,
                "name": f"copy_test_{uuid4().hex[:10]}",
                "params": json.dumps(params),
            },
        )
    return CopySpec.from_params(id=rule_set_id, name="copy_v0", version="1", params=params)


class Rig:
    def __init__(self, lane: CopyLane, clock: FakeClock, chain: FakeChain) -> None:
        self.lane, self.clock, self.chain = lane, clock, chain

    async def settle(self) -> None:
        for _ in range(2000):
            if self.lane.queue.empty() and self.lane.executor.idle:
                await asyncio.sleep(0.02)
                if self.lane.queue.empty() and self.lane.executor.idle:
                    return
            await asyncio.sleep(0.01)
        raise AssertionError("the executor never went idle")


@asynccontextmanager
async def running(
    spec: CopySpec, factory: async_sessionmaker[AsyncSession], *, recover: bool = False
) -> AsyncGenerator[Rig]:
    async with running_many([spec], factory, recover=recover) as rigs:
        yield rigs[0]


@asynccontextmanager
async def running_many(
    specs: list[CopySpec], factory: async_sessionmaker[AsyncSession], *, recover: bool = False
) -> AsyncGenerator[list[Rig]]:
    """One lane per rule set, sharing a clock and a chain (what the fleet does in production)."""
    clock = FakeClock(T0 + timedelta(milliseconds=10))
    chain = FakeChain(clock)
    lanes = [
        CopyLane(
            spec=spec,
            session_factory=factory,
            chain=chain,  # type: ignore[arg-type]
            clock=clock,
            sleep=clock.sleep,
            t0=T0 - timedelta(hours=1),
        )
        for spec in specs
    ]
    if recover:
        for lane in lanes:
            await lane.recover()
    runners = [asyncio.create_task(lane.executor.run(lane.queue)) for lane in lanes]
    try:
        yield [Rig(lane, clock, chain) for lane in lanes]
    finally:
        for runner in runners:
            runner.cancel()
        await asyncio.gather(*runners, return_exceptions=True)


async def bets(factory: async_sessionmaker[AsyncSession], spec: CopySpec) -> list[dict[str, Any]]:
    async with role_session(factory, db_role=WORKER) as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, mint, status, entry_at, entry, exit_at, exit, pnl_sol, mark_source, "
                    "  mark_sol, outcome_quality, outcome_quality_reason, proposal_id "
                    "FROM meme_paper_bets WHERE rule_set_id = CAST(:rs AS uuid) ORDER BY entry_at"
                ),
                {"rs": spec.id},
            )
        ).mappings()
        return [dict(r) for r in rows]


async def proposals(
    factory: async_sessionmaker[AsyncSession], spec: CopySpec
) -> list[dict[str, Any]]:
    async with role_session(factory, db_role=WORKER) as session:
        rows = (
            await session.execute(
                text(
                    "SELECT mint, status, refusal, bet_id, decided_by, decision, quote FROM meme_proposals "
                    "WHERE rule_set_id = CAST(:rs AS uuid) ORDER BY proposed_at"
                ),
                {"rs": spec.id},
            )
        ).mappings()
        return [dict(r) for r in rows]


async def retire_copy_sets(engine: AsyncEngine) -> None:
    """No copy rule set stays active in the shared test database."""
    async with engine.begin() as connection:
        await connection.execute(  # a retired set is only kept while it holds open copies: close them
            text(
                "UPDATE meme_paper_bets SET status = 'closed', exit_at = entry_at + interval '1 second', "
                '  exit = CAST(\'{"reason": "test_cleanup"}\' AS jsonb), pnl_sol = 0, r_multiple = 0 '
                "WHERE status = 'open' AND rule_set_id IN "
                "  (SELECT id FROM meme_rule_sets WHERE params ->> 'clock' = 'copy')"
            )
        )
        await connection.execute(
            text(
                "UPDATE meme_rule_sets SET status = 'retired', retired_at = now() "
                "WHERE params ->> 'clock' = 'copy' AND status = 'active'"
            )
        )


def mint_address() -> str:
    return addr("M")
