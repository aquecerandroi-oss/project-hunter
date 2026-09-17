# pyright: reportPrivateUsage=false
"""T4.52a: the Lab wakes the executor (``LabContext.wake``, Redis pub/sub in
production — ``hunter_meme_worker.main._wake_publisher``) the instant a tick
commits a proposal, through both the minute gate and the 15s fast lane
(T4.43), and never when a tick proposes nothing.

Reuses the fast-lane fixtures of ``test_lab_fast.py`` — the same real
Postgres container, one file, one proven path to a fast-lane proposal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from hunter_core.db.session import role_session
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.lab import LabContext, LabState, lab_tick
from hunter_meme_worker.repo import insert_snapshot
from hunter_meme_worker.repo_fast import insert_fast_rows

from .test_lab_fast import _fast_row, _flow_set, _plant_token  # pyright: ignore[reportPrivateUsage]
from .test_lab_persistence import (  # pyright: ignore[reportPrivateUsage]
    FakeQuotes,
    Heartbeats,
    _snapshot,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
CREATED = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


class Waker:
    """Records every call, exactly the shape ``LabContext.wake`` needs."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> None:
        self.calls += 1


async def _plant_fast_proposal_inputs(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine, mint: str
) -> datetime:
    """Everything ``test_lab_fast.py``'s proven flow-gate scenario needs: a
    token, one 15s row that passes the seeded ``flow_v2/1`` gate. Returns the
    tick that should turn it into a proposal."""
    await _flow_set(db_engine)
    await _plant_token(
        db_session_factory, mint, created_at=CREATED, creator=f"C_{mint}", symbol=f"S{mint[5:9]}"
    )
    photo = CREATED + timedelta(seconds=120)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_snapshot(session, _snapshot(mint, photo, "34", "946000000"))
        await insert_fast_rows(session, [_fast_row(mint, photo + timedelta(seconds=2), photo)])
    return photo + timedelta(seconds=3)


async def test_a_committed_proposal_wakes_the_executor(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    waker = Waker()
    ctx = LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=db_session_factory,
        state=LabState(),
        quotes=FakeQuotes(),
        heartbeat=Heartbeats(),
        wake=waker,
    )
    mint = f"WAKE_{uuid4().hex[:8]}"
    tick_1 = await _plant_fast_proposal_inputs(db_session_factory, db_engine, mint)
    report = await lab_tick(ctx, now=tick_1)
    assert report.proposals >= 1
    assert waker.calls == 1, "one wake per tick that committed at least one proposal"


async def test_a_tick_with_no_proposal_never_wakes(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    waker = Waker()
    ctx = LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=db_session_factory,
        state=LabState(),
        quotes=FakeQuotes(),
        heartbeat=Heartbeats(),
        wake=waker,
    )
    report = await lab_tick(ctx, now=CREATED)
    assert report.proposals == 0
    assert waker.calls == 0


async def test_wake_is_optional_and_a_missing_one_is_a_safe_no_op(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    """``wake=None`` (every test of this package before T4.52a, and any deploy
    of the Lab with no Redis wired in) must not raise — a quiet Lab stays
    correct, only slower to be picked up (``config.loop_s``, the fallback)."""
    ctx = LabContext(
        config=MemeConfig(enabled=True, lab_enabled=True),
        session_factory=db_session_factory,
        state=LabState(),
        quotes=FakeQuotes(),
        heartbeat=Heartbeats(),
    )
    mint = f"WAKE_{uuid4().hex[:8]}"
    tick_1 = await _plant_fast_proposal_inputs(db_session_factory, db_engine, mint)
    report = await lab_tick(ctx, now=tick_1)
    assert report.proposals >= 1
