"""T4.35 — the fast lane's refusal trail repo against a real Postgres at
head: :func:`insert_refusal_trail` is idempotent per ``(rule_set_id, mint,
as_of)`` and :func:`prune_refusal_trail` keeps only what is younger than its
cutoff, batched.

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker.gate_refusal_trail import RefusalTrailRow
from hunter_meme_worker.lab_repo_fast import insert_refusal_trail, prune_refusal_trail

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
FLOW_V2_ID = "01994d00-6c1a-7000-8000-000000000008"
"""``flow_v2/1``, seeded by ``0030_meme_gate_v2`` — an existing rule set to
satisfy the foreign key, the same id ``test_lab_fast.py`` reads."""
AS_OF = datetime(2026, 9, 16, 16, 20, tzinfo=UTC)


async def test_insert_refusal_trail_writes_a_proposal_row_and_a_near_miss_row(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    proposal_mint, miss_mint = f"Prop{uuid4().hex[:8]}", f"Miss{uuid4().hex[:8]}"
    rows = [
        RefusalTrailRow(as_of=AS_OF, rule_set_id=FLOW_V2_ID, mint=proposal_mint, refusal=None),
        RefusalTrailRow(
            as_of=AS_OF,
            rule_set_id=FLOW_V2_ID,
            mint=miss_mint,
            refusal="snipers_above_max",
            value=64,
            limit=20,
        ),
    ]
    async with role_session(db_session_factory, db_role=WORKER) as session:
        assert await insert_refusal_trail(session, rows) == 2
        written = (
            await session.execute(
                text(
                    'SELECT mint, refusal, value, "limit" FROM meme_gate_refusals_by_mint '
                    "WHERE mint IN (:a, :b) ORDER BY mint"
                ),
                {"a": proposal_mint, "b": miss_mint},
            )
        ).all()
    by_mint = {r.mint: r for r in written}
    assert by_mint[proposal_mint].refusal is None
    assert by_mint[miss_mint].refusal == "snipers_above_max"
    assert by_mint[miss_mint].value == 64 and by_mint[miss_mint].limit == 20


async def test_insert_refusal_trail_is_idempotent_on_the_same_instant(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mint = f"Idem{uuid4().hex[:8]}"
    row = RefusalTrailRow(as_of=AS_OF, rule_set_id=FLOW_V2_ID, mint=mint, refusal=None)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_refusal_trail(session, [row])
        await insert_refusal_trail(session, [row])  # a restart re-judging the same instant
        count = await session.scalar(
            text("SELECT count(*) FROM meme_gate_refusals_by_mint WHERE mint = :mint"),
            {"mint": mint},
        )
    assert count == 1


async def test_insert_refusal_trail_with_no_rows_is_a_no_op(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=WORKER) as session:
        assert await insert_refusal_trail(session, []) == 0


async def test_prune_refusal_trail_deletes_only_rows_older_than_the_cutoff(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    old_mint, new_mint = f"Old{uuid4().hex[:8]}", f"New{uuid4().hex[:8]}"
    old_as_of = AS_OF - timedelta(days=10)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_refusal_trail(
            session,
            [
                RefusalTrailRow(
                    as_of=old_as_of, rule_set_id=FLOW_V2_ID, mint=old_mint, refusal=None
                ),
                RefusalTrailRow(as_of=AS_OF, rule_set_id=FLOW_V2_ID, mint=new_mint, refusal=None),
            ],
        )
        cutoff = AS_OF - timedelta(days=7)
        deleted = await prune_refusal_trail(session, cutoff=cutoff, batch=500)
        assert deleted == 1
        remaining = (
            (
                await session.execute(
                    text("SELECT mint FROM meme_gate_refusals_by_mint WHERE mint IN (:a, :b)"),
                    {"a": old_mint, "b": new_mint},
                )
            )
            .scalars()
            .all()
        )
    assert remaining == [new_mint]


async def test_prune_refusal_trail_respects_its_batch_size(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    prefix = f"Batch{uuid4().hex[:6]}"
    old_as_of = AS_OF - timedelta(days=10)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await insert_refusal_trail(
            session,
            [
                RefusalTrailRow(
                    as_of=old_as_of + timedelta(seconds=i),
                    rule_set_id=FLOW_V2_ID,
                    mint=f"{prefix}{i}",
                    refusal=None,
                )
                for i in range(3)
            ],
        )
        deleted = await prune_refusal_trail(session, cutoff=AS_OF - timedelta(days=7), batch=2)
        assert deleted == 2
        remaining = await session.scalar(
            text("SELECT count(*) FROM meme_gate_refusals_by_mint WHERE mint LIKE :p"),
            {"p": f"{prefix}%"},
        )
    assert remaining == 1
