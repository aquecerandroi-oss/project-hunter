"""``repositories/meme_desk.py`` + ``services/meme_desk.py`` (T4.7) against a
**real, migrated** Postgres (T4.7b) — decisions, manual buys and operator
commands. ``test_meme_desk_repository_b.py`` carries the summary, the Redis
idempotency store and the end-to-end HTTP scenario; ``meme_desk_seed.py``
carries the rows both modules insert.

The schema comes from Alembic to ``head`` (``conftest.py``'s
``migrate_fresh_database``), never from a literal DDL copy: T4.7's original
version froze the contract's ``0022`` shape and fell behind every column
``0023``-``0031`` added (``mode``, ``mark_source``, ``outcome_quality``…),
failing on every migration since. A database of its own inside the shared
``postgres_container`` — module-scoped so every test in this file shares one
migrated, seeded instance and only rolls back its own writes (the ``session``
fixture below never commits).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hunter_api.auth.principal import Principal
from hunter_api.auth.rbac import OrgContext
from hunter_api.repositories.meme_desk import MemeDeskRepository
from hunter_api.schemas.meme_desk import ApproveProposalIn, ManualProposalIn, RejectProposalIn
from hunter_api.services.meme_desk import (
    DeskRefusedError,
    ProposalStateConflictError,
    approve_proposal,
    file_manual_proposal,
    reject_proposal,
)
from hunter_core.audit import InMemoryAuditSink, use_audit_sink
from hunter_core.domain.enums import OrganizationRole

from . import meme_desk_seed as seed
from .meme_desk_seed import (
    CLERK_ID,
    MINT_CURVE,
    MINT_DONE,
    NOW,
    ORG_ID,
    P_APPROVED,
    P_FILLED_OPEN,
    P_PROPOSED,
    P_REJECTED,
    RS_RESEARCH_NAME,
    USER_ID,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

pytestmark = pytest.mark.integration

DB_NAME = "hunter_meme_desk_it_a"


@pytest.fixture(scope="module")
def desk_database_url(migrate_fresh_database: Callable[[str], str]) -> str:
    url = migrate_fresh_database(DB_NAME)
    asyncio.run(seed.seed(url))
    return url


@pytest_asyncio.fixture
async def session(desk_database_url: str) -> AsyncIterator[AsyncSession]:
    """A fresh engine per test; the session is never committed, so every
    write a test makes rolls back at close and the seed stays pristine."""
    engine = create_async_engine(desk_database_url, connect_args={"statement_cache_size": 0})
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as s:
            yield s
            await s.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def repo(session: AsyncSession) -> MemeDeskRepository:
    return MemeDeskRepository(session)


class FakeStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def load(self, key: str) -> str | None:
        return self.values.get(key)

    async def save(self, key: str, value: str, *, ttl_s: int) -> None:
        del ttl_s
        self.values.setdefault(key, value)


def _context() -> OrgContext:
    principal = Principal(user_id=USER_ID, external_auth_id=CLERK_ID)
    return OrgContext(org_id=ORG_ID, role=OrganizationRole.TRADER, principal=principal)


def _approve_body(size_sol: str = "0.3") -> ApproveProposalIn:
    return ApproveProposalIn.model_validate(
        {"size_sol": size_sol, "target_x": "2.5", "trailing_pct": "25", "max_hold_s": 600}
    )


class TestListDesk:
    async def test_open_proposals_then_open_bets_then_history(
        self, repo: MemeDeskRepository
    ) -> None:
        rows = await repo.list_desk(status=None, limit=10, cursor=None)
        assert [r.proposal.id for r in rows] == [
            P_PROPOSED,
            P_APPROVED,
            P_FILLED_OPEN,
            seed.P_UNFILLED,
            P_REJECTED,
            seed.P_FILLED_CLOSED,
        ]
        assert [r.rank for r in rows] == [0, 1, 2, 3, 3, 3]
        open_row = rows[2]
        assert open_row.bet is not None and open_row.bet.mark_sol == Decimal("0.25")
        assert open_row.token is not None and open_row.token.name == "bum bum"
        assert open_row.rule_set is not None and open_row.rule_set.name == RS_RESEARCH_NAME
        assert rows[3].proposal.refusal == "daily_loss_cap"

    async def test_keyset_cursor_pages_without_overlap_or_gap(
        self, repo: MemeDeskRepository
    ) -> None:
        seen: list[uuid.UUID] = []
        cursor = None
        while True:
            page = await repo.list_desk(status=None, limit=2, cursor=cursor)
            if not page:
                break
            seen.extend(r.proposal.id for r in page)
            last = page[-1]
            cursor = (last.rank, last.proposal.proposed_at, last.proposal.id)
            if len(page) < 2:
                break
        assert len(seen) == 6
        assert len(set(seen)) == 6

    async def test_status_filter(self, repo: MemeDeskRepository) -> None:
        rows = await repo.list_desk(status="proposed", limit=10, cursor=None)
        assert [r.proposal.id for r in rows] == [P_PROPOSED]


class TestApproveReject:
    async def test_approve_writes_only_the_decision_columns_and_audits(
        self, repo: MemeDeskRepository, session: AsyncSession
    ) -> None:
        sink = InMemoryAuditSink()
        with use_audit_sink(sink):
            out = await approve_proposal(
                repo,
                FakeStore(),
                context=_context(),
                proposal_id=P_PROPOSED,
                idempotency_key="desk-it-approve-1",
                body=_approve_body(),
                now=NOW,
            )
        assert out.row.status == "approved"
        stored = (
            await session.execute(
                text(
                    "SELECT status, decision, decided_by, decided_at, quote, suggested, mode "
                    "FROM meme_proposals WHERE id = :id"
                ),
                {"id": P_PROPOSED},
            )
        ).one()
        assert stored.status == "approved"
        assert stored.decision["size_sol"] == "0.3"
        assert stored.decision["max_hold_s"] == 600
        assert stored.decided_by == CLERK_ID
        assert stored.decided_at == NOW
        assert stored.quote["source"] == "solana_rpc"  # untouched
        assert stored.suggested == seed.SUGGESTED  # untouched
        assert stored.mode == "paper"  # 0028: default, ApproveProposalIn.mode not sent
        assert [e.action for e in sink.events] == ["meme_desk.proposal.approved"]
        assert "desk-it-approve-1" not in str(sink.events[0].after)

    async def test_second_decision_is_409_and_same_key_replays(
        self, repo: MemeDeskRepository
    ) -> None:
        store = FakeStore()
        first = await approve_proposal(
            repo,
            store,
            context=_context(),
            proposal_id=P_PROPOSED,
            idempotency_key="desk-it-approve-2",
            body=_approve_body(),
            now=NOW,
        )
        with pytest.raises(ProposalStateConflictError, match="not_proposed"):
            await approve_proposal(
                repo,
                store,
                context=_context(),
                proposal_id=P_PROPOSED,
                idempotency_key="desk-it-approve-3",
                body=_approve_body(),
                now=NOW,
            )
        replay = await approve_proposal(
            repo,
            store,
            context=_context(),
            proposal_id=P_PROPOSED,
            idempotency_key="desk-it-approve-2",
            body=_approve_body(),
            now=NOW,
        )
        assert replay == first

    async def test_reject(self, repo: MemeDeskRepository) -> None:
        out = await reject_proposal(
            repo,
            FakeStore(),
            context=_context(),
            proposal_id=P_PROPOSED,
            idempotency_key="desk-it-reject-1",
            body=RejectProposalIn(note="não"),
            now=NOW,
        )
        assert out.row.status == "rejected"
        assert out.row.decision is not None and out.row.decision.note == "não"


class TestManual:
    async def test_inserts_an_approved_operator_proposal_priced_on_the_latest_snapshot(
        self, repo: MemeDeskRepository
    ) -> None:
        """Filed under the **real** migrated ``operator`` set (``operator/2``
        as of ``0029``; ``meme_desk_seed.py``'s own docstring): the size stays
        under its ``max_sol_per_bet`` (0,05 SOL)."""
        operator_rule_set = await repo.get_operator_rule_set()
        assert operator_rule_set is not None
        out = await file_manual_proposal(
            repo,
            FakeStore(),
            context=_context(),
            idempotency_key="desk-it-manual-1",
            body=ManualProposalIn.model_validate(
                {
                    "mint": MINT_CURVE,
                    "size_sol": "0.04",
                    "target_x": "3",
                    "trailing_pct": "40",
                    "max_hold_s": 300,
                }
            ),
            now=NOW,
        )
        row = out.row
        assert row.origin == "operator" and row.status == "approved"
        assert row.rule_set is not None and row.rule_set.id == operator_rule_set.id
        assert row.quote.source == "solana_rpc"
        assert row.quote.observed_at == NOW - timedelta(minutes=1)
        assert row.quote.cost_sol == Decimal("0.04")
        assert row.quote.tokens is not None and row.quote.tokens > 0
        assert row.features_end_time == NOW - timedelta(minutes=1)
        listed = await repo.list_desk(status="approved", limit=10, cursor=None)
        assert row.id in {r.proposal.id for r in listed}

    async def test_refusals_are_named(self, repo: MemeDeskRepository) -> None:
        body = {"size_sol": "0.2", "target_x": "2", "trailing_pct": "30", "max_hold_s": 300}
        with pytest.raises(DeskRefusedError, match="curve_completed"):
            await file_manual_proposal(
                repo,
                FakeStore(),
                context=_context(),
                idempotency_key="desk-it-manual-2",
                body=ManualProposalIn.model_validate({**body, "mint": MINT_DONE}),
                now=NOW,
            )
        with pytest.raises(DeskRefusedError, match="mint_unknown"):
            await file_manual_proposal(
                repo,
                FakeStore(),
                context=_context(),
                idempotency_key="desk-it-manual-3",
                body=ManualProposalIn.model_validate(
                    {**body, "mint": "Synthetic9NeverSeenxxxxxxxxxxxxxxxxxxxxxxxxx"}
                ),
                now=NOW,
            )
