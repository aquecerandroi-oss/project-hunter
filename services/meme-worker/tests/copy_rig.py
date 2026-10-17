"""Shared rig of the copy-lane integration tests (H-037): a lane over a real Postgres with a fake
chain and a fake clock that sleeping advances. Labeled test code; nothing here ships."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.solana_codec import b58encode
from hunter_meme_worker.copy_history import LeaderHistory, MintTrace, WindowTrace
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

    def _quiet(self) -> bool:
        lane = self.lane
        return lane.queue.empty() and lane.executor.idle and not lane.outbox

    async def settle(self) -> None:
        for _ in range(2000):
            self.lane._flush_outbox()  # pyright: ignore[reportPrivateUsage]  # what the 1 s sweep does
            if self._quiet():
                await asyncio.sleep(0.02)
                self.lane._flush_outbox()  # pyright: ignore[reportPrivateUsage]
                if self._quiet():
                    return
            await asyncio.sleep(0.01)
        raise AssertionError("the executor never went idle")


@asynccontextmanager
async def running(
    spec: CopySpec,
    factory: async_sessionmaker[AsyncSession],
    *,
    recover: bool = False,
    history: LeaderHistory | None = None,
) -> AsyncGenerator[Rig]:
    async with running_many([spec], factory, recover=recover, history=history) as rigs:
        yield rigs[0]


@asynccontextmanager
async def running_many(
    specs: list[CopySpec],
    factory: async_sessionmaker[AsyncSession],
    *,
    recover: bool = False,
    history: LeaderHistory | None = None,
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
            history=history,
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
        for lane in lanes:
            await lane.executor.shutdown()


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


async def gap_rows(
    factory: async_sessionmaker[AsyncSession], spec: CopySpec
) -> list[dict[str, Any]]:
    """Every hole row this rule set wrote (and its alive markers), oldest first."""
    async with role_session(factory, db_role=WORKER) as session:
        rows = (
            await session.execute(
                text(
                    "SELECT stream, gap_start, gap_end, reason, detail FROM meme_ingest_gaps "
                    "WHERE detail ->> 'rule_set_id' = :r ORDER BY gap_start, gap_end, reason"
                ),
                {"r": spec.id},
            )
        ).mappings()
        return [dict(r) for r in rows]


class FakeHistory:
    """A labeled fake of the chain-history hook (`LeaderHistory`): what the source side must provide."""

    def __init__(
        self,
        *,
        complete: bool = True,
        bought: frozenset[str] = frozenset(),
        trace: MintTrace | None = None,
        boom: bool = False,
    ) -> None:
        self.complete, self.bought, self.trace, self.boom = complete, bought, trace, boom
        self.windows: list[tuple[str, datetime, datetime, int]] = []
        self.traces: list[tuple[str, str, datetime]] = []

    async def window(
        self, wallet: str, start: datetime, end: datetime, *, limit: int = 1000
    ) -> WindowTrace:
        self.windows.append((wallet, start, end, limit))
        if self.boom:
            raise RuntimeError("history node down")
        return WindowTrace(self.complete, self.bought)

    async def mint_trace(self, wallet: str, mint: str, since: datetime) -> MintTrace | None:
        self.traces.append((wallet, mint, since))
        return self.trace
