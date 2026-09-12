"""``repositories/meme_desk.py`` + ``services/meme_desk.py`` (T4.7) against a
**real, migrated** Postgres (T4.7b), continued from
``test_meme_desk_repository_a.py`` (approve/reject/manual): operator commands,
the summary, the Redis idempotency store and — no longer ``xfail`` — the
end-to-end HTTP scenario over Alembic to ``head``.

``migrate_fresh_database`` (``conftest.py``, additive) gives this module its
own database inside the shared ``postgres_container``, distinct from file
A's: two modules seeding the same physical database would collide on the
seed's own primary keys.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hunter_api.auth.principal import Principal
from hunter_api.auth.rbac import OrgContext
from hunter_api.repositories import meme_desk as meme_desk_repository_module
from hunter_api.repositories.meme_desk import MemeDeskRepository
from hunter_api.services.meme_desk import (
    BetStateConflictError,
    ProposalStateConflictError,
    cancel_proposal,
    sell_now,
)
from hunter_api.services.meme_desk_idempotency import (
    DeskReplayConflictError,
    RedisIdempotencyStore,
    ReplayRecord,
    find_replay,
    remember,
)
from hunter_api.services.meme_desk_out import build_summary
from hunter_core.db.models.system import AuditLog
from hunter_core.db.session import role_session, tenant_session
from hunter_core.domain.enums import OrganizationRole
from hunter_core.domain.types import uuid7

from . import meme_desk_seed as seed
from .conftest import create_org
from .meme_desk_seed import CLERK_ID, NOW, ORG_ID, USER_ID

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    import httpx

    from .conftest import Actor

pytestmark = pytest.mark.integration

DB_NAME = "hunter_meme_desk_it_b"


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


class TestSummary:
    async def test_balances_per_rule_set_and_day_pnl(self, repo: MemeDeskRepository) -> None:
        balances = await repo.rule_set_balances(NOW)
        by_name = {b.rule_set.name: b for b in balances}
        research = by_name[seed.RS_RESEARCH_NAME]
        assert research.open_sol == Decimal("0.2")
        assert research.open_bets == 1
        assert research.realized_today_sol == Decimal("0.18")
        assert research.closed_today == 1
        assert research.realized_total_sol == Decimal("0.18")
        operator = by_name[seed.RS_OPERATOR_NAME]
        assert operator.open_sol == 0 and operator.open_bets == 0
        summary = build_summary(balances, await repo.latest_sol_usd_quote())
        research_out = next(
            r for r in summary.rule_sets if r.rule_set.name == seed.RS_RESEARCH_NAME
        )
        assert research_out.balance_sol == Decimal("5") + Decimal("0.18") - Decimal("0.2")
        assert summary.day_pnl_sol == Decimal("0.18")
        assert summary.sol_usd is not None
        assert summary.sol_usd.rate == Decimal("180")  # the open bet's entry is the newest
        assert summary.sol_usd.observed_at == NOW - timedelta(minutes=9)
        assert summary.sol_usd.source == "coingecko"

    async def test_yesterdays_close_does_not_count_as_today(self, repo: MemeDeskRepository) -> None:
        balances = await repo.rule_set_balances(NOW + timedelta(days=1))
        research = next(b for b in balances if b.rule_set.name == seed.RS_RESEARCH_NAME)
        assert research.realized_today_sol == 0
        assert research.closed_today == 0
        assert research.realized_total_sol == Decimal("0.18")


class TestCommands:
    async def test_sell_now_inserts_a_command_and_refuses_a_second_pending_one(
        self, repo: MemeDeskRepository
    ) -> None:
        out = await sell_now(
            repo,
            FakeStore(),
            context=_context(),
            bet_id=seed.B_OPEN,
            idempotency_key="desk-it-sell-1",
            now=NOW,
        )
        stored = await repo.get_command(out.id)
        assert stored is not None
        assert stored.command == "sell_now" and stored.bet_id == seed.B_OPEN
        assert stored.applied_at is None and stored.result is None
        pending = await repo.pending_command(bet_id=seed.B_OPEN, command="sell_now")
        assert pending is not None and pending.id == out.id
        with pytest.raises(BetStateConflictError, match="sell_now_already_pending"):
            await sell_now(
                repo,
                FakeStore(),
                context=_context(),
                bet_id=seed.B_OPEN,
                idempotency_key="desk-it-sell-2",
                now=NOW,
            )

    async def test_sell_now_on_a_closed_bet_is_409(self, repo: MemeDeskRepository) -> None:
        with pytest.raises(BetStateConflictError, match="bet_not_open"):
            await sell_now(
                repo,
                FakeStore(),
                context=_context(),
                bet_id=seed.B_CLOSED,
                idempotency_key="desk-it-sell-3",
                now=NOW,
            )

    async def test_cancel_on_approved_inserts_a_command_and_filled_is_409(
        self, repo: MemeDeskRepository
    ) -> None:
        out = await cancel_proposal(
            repo,
            FakeStore(),
            context=_context(),
            proposal_id=seed.P_APPROVED,
            idempotency_key="desk-it-cancel-1",
            now=NOW,
        )
        stored = await repo.get_command(out.id)
        assert stored is not None and stored.command == "cancel"
        assert stored.proposal_id == seed.P_APPROVED and stored.bet_id is None
        with pytest.raises(ProposalStateConflictError, match="already_filled"):
            await cancel_proposal(
                repo,
                FakeStore(),
                context=_context(),
                proposal_id=seed.P_FILLED_OPEN,
                idempotency_key="desk-it-cancel-2",
                now=NOW,
            )


def test_the_repository_never_writes_meme_paper_bets() -> None:
    """Contract §Papéis: bets are the loop's. A source-level guard so the
    forbidden write cannot slip in as a refactor."""
    source = inspect.getsource(meme_desk_repository_module)
    for forbidden in (
        "_b.insert(",
        "meme_paper_bets.insert(",
        "update(_b)",
        "update(meme_paper_bets)",
    ):
        assert forbidden not in source


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[redis_asyncio.Redis]:
    client = redis_asyncio.from_url(redis_url, decode_responses=False)
    try:
        yield client
    finally:
        await client.aclose()


class TestRedisStore:
    async def test_remember_then_find_replay_round_trips_and_mismatch_is_409(
        self, redis_client: redis_asyncio.Redis
    ) -> None:
        store = RedisIdempotencyStore(redis_client)
        org_id = uuid.uuid4()
        record = ReplayRecord(fingerprint="fp-1", entity_type="meme_proposal", entity_id="p-1")
        assert await find_replay(store, org_id, "k-1", "fp-1") is None
        await remember(store, org_id, "k-1", record)
        assert await find_replay(store, org_id, "k-1", "fp-1") == record
        with pytest.raises(DeskReplayConflictError):
            await find_replay(store, org_id, "k-1", "fp-2")
        # first writer wins: a second remember under the same key is a no-op
        await remember(store, org_id, "k-1", ReplayRecord("fp-1", "meme_proposal", "p-9"))
        assert (await find_replay(store, org_id, "k-1", "fp-1")) == record


async def test_http_approve_against_the_real_migration(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The real app over Alembic-to-head (T4.7b: no longer ``xfail`` — ``0022``
    through ``0031`` are all on the tree): seed as ``hunter_worker`` (the
    loop's role), approve as the org's OWNER with ``Idempotency-Key``, read
    the desk, and find the ``audit_logs`` row as ``hunter_app``."""
    actor = await create_org(client, make_actor("desk-owner"), "Desk Org")
    assert actor.org_id is not None
    proposal_id = uuid7()
    mint = "SyntheticDeskMintForMigrationProbexxxxxxxxxx"
    now = datetime.now(UTC)
    async with role_session(session_factory, db_role="hunter_worker") as db_session:
        await db_session.execute(
            text(
                "INSERT INTO meme_tokens (mint, name, symbol, first_seen_source, first_seen_at, "
                "last_seen_at, updated_at) VALUES (:mint, 'desk probe', 'PROBE', 'pumpportal_ws', "
                ":now, :now, :now)"
            ),
            {"mint": mint, "now": now},
        )
        real_rule_set_id = await db_session.scalar(
            text("SELECT id FROM meme_rule_sets WHERE name = 'operator' AND version = '1'")
        )
        assert real_rule_set_id is not None, "0022 seeds no operator/1 rule set"
        await db_session.execute(
            text(
                "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
                "expires_at, features_end_time, quote, reasons, suggested) VALUES (:id, :mint, :rs, "
                "'rules', 'proposed', :now, :expires, :now, CAST(:quote AS jsonb), "
                "CAST(:reasons AS jsonb), CAST(:suggested AS jsonb))"
            ),
            {
                "id": proposal_id,
                "mint": mint,
                "rs": real_rule_set_id,
                "now": now,
                "expires": now + timedelta(minutes=5),
                "quote": json.dumps({"source": "solana_rpc", "observed_at": now.isoformat()}),
                "reasons": json.dumps(["probe"]),
                "suggested": json.dumps(seed.SUGGESTED),
            },
        )
    headers = {**actor.headers, "Idempotency-Key": "desk-it-http-000001"}
    # below the seeded operator/1 ``max_sol_per_bet`` (0.05 as of 0022), on purpose
    body = {"size_sol": "0.01", "target_x": "2", "trailing_pct": "30", "max_hold_s": 600}
    url = f"/api/v1/orgs/{actor.org_id}/meme/proposals/{proposal_id}/approve"
    response = await client.post(url, json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["row"]["status"] == "approved"
    replay = await client.post(url, json=body, headers=headers)
    assert replay.status_code == 200, replay.text
    assert replay.json()["row"]["id"] == response.json()["row"]["id"]
    desk = await client.get(f"/api/v1/orgs/{actor.org_id}/meme/desk", headers=actor.headers)
    assert desk.status_code == 200, desk.text
    assert desk.json()["label"].startswith("PAPEL")
    async with tenant_session(session_factory, actor.org_id) as tenant_db:
        rows = (
            (await tenant_db.execute(select(AuditLog).where(AuditLog.entity_id == proposal_id)))
            .scalars()
            .all()
        )
    assert [row.action for row in rows] == ["meme_desk.proposal.approved"]
