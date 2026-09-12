"""``repositories/meme_desk.py`` + ``services/meme_desk.py`` against a real
Postgres (T4.7) — testcontainer.

Schema source: the frozen contract
``.claude/state/contrato-T4.6-T4.7-mesa-meme.md`` §Tabelas, spelled out here
as literal DDL (the three T4.3 tables copied from
``test_meme_repository.py``, the four T4.6/T4.7 tables, their seven
indexes and the bets backlink copied verbatim from ``infra/migrations/ddl/meme_lab.py``
at ``0022``) —
**not** Alembic to head: migration ``0022_meme_lab`` is T4.6's and is being
written in parallel; depending on it here would make this suite's pass/fail
a function of another task's timing (``notes-T4.3.md`` took the same route
for ``0021``). Own database inside the shared ``postgres_container``.

The one place the real migration *is* exercised is
:func:`test_http_approve_against_the_real_migration`, marked
``xfail(strict=False)``: it goes through the real app (Alembic to head via
``tests/integration/conftest.py``) and simply cannot pass until ``0022``
lands — when it does, it starts passing on its own.

Seed data: the primary mint/reserves/creator values are T4.1's live capture
(``packages/exchange-adapters/tests/fixtures/pumpfun/mayhem_list_raw.json``,
2026-09-12), as in ``test_meme_repository.py``; every proposal/bet row is
synthetic (there is no loop yet) and labelled as such.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hunter_api.auth.principal import Principal
from hunter_api.auth.rbac import OrgContext
from hunter_api.repositories import meme_desk as meme_desk_repository_module
from hunter_api.repositories.meme_desk import MemeDeskRepository
from hunter_api.schemas.meme_desk import ApproveProposalIn, ManualProposalIn, RejectProposalIn
from hunter_api.services.meme_desk import (
    BetStateConflictError,
    DeskRefusedError,
    ProposalStateConflictError,
    approve_proposal,
    cancel_proposal,
    file_manual_proposal,
    reject_proposal,
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
from hunter_core.audit import InMemoryAuditSink, use_audit_sink
from hunter_core.db.models.system import AuditLog
from hunter_core.db.session import role_session, tenant_session
from hunter_core.domain.enums import OrganizationRole
from hunter_core.domain.types import uuid7

from .conftest import create_org

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    import httpx
    from testcontainers.community.postgres import PostgresContainer

    from .conftest import Actor

pytestmark = pytest.mark.integration

DB_NAME = "hunter_meme_desk_it"
NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)  # 09:00 Brasília
ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
CLERK_ID = "user_FAKE_desk_operator"

MINT_CURVE = "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump"  # T4.1 live capture
MINT_DONE = "Synthetic1CompletedNotMigratedxxxxxxxxxxxxx"  # synthetic, completed
RS_RESEARCH = uuid.uuid4()
RS_OPERATOR = uuid.uuid4()
P_PROPOSED = uuid7()
P_APPROVED = uuid7()
P_FILLED_OPEN = uuid7()
P_FILLED_CLOSED = uuid7()
P_REJECTED = uuid7()
P_UNFILLED = uuid7()
B_OPEN = uuid7()
B_CLOSED = uuid7()

DDL_STATEMENTS = [
    """
    CREATE TABLE meme_tokens (
        mint text PRIMARY KEY, name text, symbol text, uri text, creator text,
        created_at timestamptz, bonding_curve text,
        initial_virtual_sol_reserves numeric(28, 10), initial_virtual_token_reserves numeric(28, 10),
        initial_real_token_reserves numeric(28, 10), total_supply numeric(28, 10), pool text,
        mayhem_enabled boolean, mayhem_mode text, mayhem_state text,
        completed_at timestamptz, migrated_at timestamptz, migrated_pool text,
        first_seen_source text NOT NULL, first_seen_at timestamptz NOT NULL,
        last_seen_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
    )
    """,
    """
    CREATE TABLE meme_curve_snapshots (
        observed_at timestamptz NOT NULL, mint text NOT NULL, source text NOT NULL,
        received_at timestamptz NOT NULL,
        virtual_sol_reserves numeric(28, 10) NOT NULL, virtual_token_reserves numeric(28, 10) NOT NULL,
        real_sol_reserves numeric(28, 10) NOT NULL, real_token_reserves numeric(28, 10) NOT NULL,
        total_supply numeric(28, 10) NOT NULL, complete boolean NOT NULL,
        slot bigint, commitment text, mayhem_enabled boolean, mayhem_state text, mayhem_mode text,
        mcap_sol numeric(28, 10) GENERATED ALWAYS AS
            ((virtual_sol_reserves / NULLIF(virtual_token_reserves, 0)) * total_supply) STORED,
        PRIMARY KEY (observed_at, mint, source)
    )
    """,
    """
    CREATE TABLE meme_features_1m (
        end_time timestamptz NOT NULL, mint text NOT NULL, features_version text NOT NULL,
        curve_progress_pct numeric(9, 6), progress_reason text, mcap_sol numeric(28, 10),
        curve_reason text, unique_buyers integer, unique_buyers_reason text,
        buy_sell_ratio numeric(18, 8), buy_sell_ratio_reason text, top10_share numeric(9, 6),
        top10_share_reason text, creator_sold boolean, creator_sold_reason text,
        age_minutes integer, coverage numeric(9, 6) NOT NULL, snapshot_observed_at timestamptz,
        snapshot_source text, computed_at timestamptz NOT NULL,
        PRIMARY KEY (end_time, mint, features_version)
    )
    """,
    """
    CREATE TABLE meme_rule_sets (
        id uuid NOT NULL,
        name text NOT NULL,
        version text NOT NULL,
        kind text NOT NULL,
        params jsonb NOT NULL DEFAULT '{}'::jsonb,
        code_ref text NOT NULL,
        exp_ref text,
        status text NOT NULL DEFAULT 'active',
        created_at timestamptz NOT NULL DEFAULT now(),
        retired_at timestamptz,
        CONSTRAINT pk_meme_rule_sets PRIMARY KEY (id),
        CONSTRAINT uq_meme_rule_sets_name_version UNIQUE (name, version),
        CONSTRAINT ck_meme_rule_sets_kind_is_a_known_label
            CHECK (kind IN ('research_only', 'operator')),
        CONSTRAINT ck_meme_rule_sets_status_is_a_known_label CHECK (status IN ('active', 'retired')),
        CONSTRAINT ck_meme_rule_sets_a_retired_set_says_when
            CHECK ((status = 'retired') = (retired_at IS NOT NULL)),
        CONSTRAINT ck_meme_rule_sets_research_names_its_experiment
            CHECK (kind = 'operator' OR exp_ref IS NOT NULL),
        CONSTRAINT ck_meme_rule_sets_identity_is_not_empty
            CHECK (char_length(name) > 0 AND char_length(version) > 0 AND char_length(code_ref) > 0)
    )
    """,
    """
    CREATE TABLE meme_proposals (
        id uuid NOT NULL,
        mint text NOT NULL,
        rule_set_id uuid NOT NULL,
        origin text NOT NULL,
        status text NOT NULL DEFAULT 'proposed',
        proposed_at timestamptz NOT NULL DEFAULT now(),
        expires_at timestamptz NOT NULL,
        features_end_time timestamptz,
        quote jsonb NOT NULL DEFAULT '{}'::jsonb,
        reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
        suggested jsonb NOT NULL DEFAULT '{}'::jsonb,
        decision jsonb,
        decided_by text,
        decided_at timestamptz,
        bet_id uuid,
        refusal text,
        CONSTRAINT pk_meme_proposals PRIMARY KEY (id),
        CONSTRAINT fk_meme_proposals_rule_set_id_meme_rule_sets
            FOREIGN KEY (rule_set_id) REFERENCES meme_rule_sets (id),
        CONSTRAINT ck_meme_proposals_origin_is_a_known_label CHECK (origin IN ('rules', 'operator')),
        CONSTRAINT ck_meme_proposals_status_is_a_known_label
            CHECK (status IN ('proposed', 'approved', 'rejected', 'expired', 'filled', 'unfilled')),
        CONSTRAINT ck_meme_proposals_expiry_is_after_proposal CHECK (expires_at > proposed_at),
        CONSTRAINT ck_meme_proposals_a_rules_proposal_names_its_minute
            CHECK (origin = 'operator' OR features_end_time IS NOT NULL),
        CONSTRAINT ck_meme_proposals_a_decision_names_who_and_when
            CHECK ((decided_at IS NULL) = (decided_by IS NULL)),
        CONSTRAINT ck_meme_proposals_a_decided_status_carries_a_decision
            CHECK (status IN ('proposed', 'expired') OR decided_at IS NOT NULL),
        CONSTRAINT ck_meme_proposals_a_fill_names_its_bet
            CHECK ((status = 'filled') = (bet_id IS NOT NULL)),
        CONSTRAINT ck_meme_proposals_an_unfilled_proposal_names_its_refusal
            CHECK ((status = 'unfilled') = (refusal IS NOT NULL)),
        CONSTRAINT ck_meme_proposals_mint_is_not_empty CHECK (char_length(mint) > 0)
    )
    """,
    """
    CREATE TABLE meme_paper_bets (
        id uuid NOT NULL,
        proposal_id uuid NOT NULL,
        rule_set_id uuid NOT NULL,
        mint text NOT NULL,
        mode text NOT NULL DEFAULT 'paper',
        status text NOT NULL DEFAULT 'open',
        entry_at timestamptz NOT NULL,
        entry jsonb NOT NULL,
        initial_risk_sol numeric(28, 10) NOT NULL,
        params jsonb NOT NULL,
        exit_intent jsonb,
        exit_at timestamptz,
        exit jsonb,
        pnl_sol numeric(28, 10),
        r_multiple numeric(28, 10),
        mark_sol numeric(28, 10),
        mark_at timestamptz,
        high_water_x numeric(28, 10),
        sol_usd_at_entry numeric(28, 10),
        sol_usd_at_exit numeric(28, 10),
        CONSTRAINT pk_meme_paper_bets PRIMARY KEY (id),
        CONSTRAINT uq_meme_paper_bets_proposal_id UNIQUE (proposal_id),
        CONSTRAINT fk_meme_paper_bets_proposal_id_meme_proposals
            FOREIGN KEY (proposal_id) REFERENCES meme_proposals (id),
        CONSTRAINT fk_meme_paper_bets_rule_set_id_meme_rule_sets
            FOREIGN KEY (rule_set_id) REFERENCES meme_rule_sets (id),
        CONSTRAINT ck_meme_paper_bets_every_bet_is_paper CHECK (mode = 'paper'),
        CONSTRAINT ck_meme_paper_bets_status_is_a_known_label CHECK (status IN ('open', 'closed')),
        CONSTRAINT ck_meme_paper_bets_a_closed_bet_says_when
            CHECK ((status = 'closed') = (exit_at IS NOT NULL)),
        CONSTRAINT ck_meme_paper_bets_an_exit_carries_its_numbers
            CHECK ((exit_at IS NULL) = (exit IS NULL)
                   AND (exit_at IS NULL) = (pnl_sol IS NULL)
                   AND (exit_at IS NULL) = (r_multiple IS NULL)),
        CONSTRAINT ck_meme_paper_bets_an_exit_is_after_the_entry
            CHECK (exit_at IS NULL OR exit_at > entry_at),
        CONSTRAINT ck_meme_paper_bets_a_mark_says_when CHECK ((mark_sol IS NULL) = (mark_at IS NULL)),
        CONSTRAINT ck_meme_paper_bets_the_risk_is_what_was_spent CHECK (initial_risk_sol > 0),
        CONSTRAINT ck_meme_paper_bets_mint_is_not_empty CHECK (char_length(mint) > 0)
    )
    """,
    """
    CREATE TABLE meme_operator_commands (
        id uuid NOT NULL,
        bet_id uuid,
        proposal_id uuid,
        command text NOT NULL,
        issued_by text NOT NULL,
        issued_at timestamptz NOT NULL DEFAULT now(),
        applied_at timestamptz,
        result jsonb,
        CONSTRAINT pk_meme_operator_commands PRIMARY KEY (id),
        CONSTRAINT fk_meme_operator_commands_bet_id_meme_paper_bets
            FOREIGN KEY (bet_id) REFERENCES meme_paper_bets (id),
        CONSTRAINT fk_meme_operator_commands_proposal_id_meme_proposals
            FOREIGN KEY (proposal_id) REFERENCES meme_proposals (id),
        CONSTRAINT ck_meme_operator_commands_command_is_a_known_label
            CHECK (command IN ('sell_now', 'cancel')),
        CONSTRAINT ck_meme_operator_commands_exactly_one_target
            CHECK ((bet_id IS NULL) <> (proposal_id IS NULL)),
        CONSTRAINT ck_meme_operator_commands_a_sale_targets_a_bet
            CHECK (command <> 'sell_now' OR bet_id IS NOT NULL),
        CONSTRAINT ck_meme_operator_commands_a_cancel_targets_a_proposal
            CHECK (command <> 'cancel' OR proposal_id IS NOT NULL),
        CONSTRAINT ck_meme_operator_commands_an_application_says_what_happened
            CHECK ((applied_at IS NULL) = (result IS NULL)),
        CONSTRAINT ck_meme_operator_commands_issuer_is_not_empty CHECK (char_length(issued_by) > 0)
    )
    """,
    "ALTER TABLE meme_proposals ADD CONSTRAINT fk_meme_proposals_bet_id_meme_paper_bets "
    "FOREIGN KEY (bet_id) REFERENCES meme_paper_bets (id)",
    "CREATE INDEX ix_meme_proposals_status_proposed_at ON meme_proposals (status, proposed_at)",
    "CREATE INDEX ix_meme_proposals_mint_proposed_at ON meme_proposals (mint, proposed_at)",
    "CREATE UNIQUE INDEX uq_meme_proposals_one_per_rule_set_mint_minute "
    "ON meme_proposals (rule_set_id, mint, features_end_time) WHERE origin = 'rules'",
    "CREATE INDEX ix_meme_paper_bets_status_entry_at ON meme_paper_bets (status, entry_at)",
    "CREATE INDEX ix_meme_paper_bets_rule_set_id_entry_at ON meme_paper_bets (rule_set_id, entry_at)",
    "CREATE INDEX ix_meme_paper_bets_mint ON meme_paper_bets (mint)",
    "CREATE INDEX ix_meme_operator_commands_pending ON meme_operator_commands (issued_at) "
    "WHERE applied_at IS NULL",
]

_PARAMS_RESEARCH = {
    "size_sol": "0.2",
    "target_x": "2",
    "trailing_pct": "30",
    "max_hold_s": 900,
    "wallet_max_sol": "5",
    "max_sol_per_bet": "0.5",
    "daily_loss_cap_sol": "1",
}
_PARAMS_OPERATOR = {"wallet_max_sol": "3", "max_sol_per_bet": "0.5", "daily_loss_cap_sol": "1"}
_SUGGESTED = {"size_sol": "0.2", "target_x": "2", "trailing_pct": "30", "max_hold_s": 900}


def _j(value: object) -> str:
    return json.dumps(value)


async def _create_database(admin_url: str) -> str:
    engine = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": DB_NAME}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{DB_NAME}"'))
    finally:
        await engine.dispose()
    return admin_url.rsplit("/", 1)[0] + "/" + DB_NAME


async def _seed(connection: Any) -> None:
    await connection.execute(
        text(
            "INSERT INTO meme_tokens (mint, name, symbol, creator, created_at, completed_at, "
            "first_seen_source, first_seen_at, last_seen_at, updated_at) VALUES "
            "(:mint, :name, :symbol, :creator, :created_at, :completed_at, 'pumpportal_ws', "
            ":created_at, :created_at, :created_at)"
        ),
        [
            {
                "mint": MINT_CURVE,
                "name": "bum bum",
                "symbol": "bam bum",
                "creator": "s9uu4shkYUQUmnWN2jkwgA2Nbg2Rmv7vUprtjy71xgP",
                "created_at": NOW - timedelta(minutes=30),
                "completed_at": None,
            },
            {
                "mint": MINT_DONE,
                "name": "Synthetic Completed",
                "symbol": "SYNC1",
                "creator": "SyntheticCreator1xxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "created_at": NOW - timedelta(hours=3),
                "completed_at": NOW - timedelta(hours=1),
            },
        ],
    )
    await connection.execute(
        text(
            "INSERT INTO meme_curve_snapshots (observed_at, mint, source, received_at, "
            "virtual_sol_reserves, virtual_token_reserves, real_sol_reserves, real_token_reserves, "
            "total_supply, complete) VALUES (:observed_at, :mint, :source, :observed_at, :vsr, :vtr, "
            ":rsr, :rtr, 1000000000, false)"
        ),
        [
            {
                "observed_at": NOW - timedelta(minutes=6),
                "mint": MINT_CURVE,
                "source": "pumpfun_rest",
                "vsr": Decimal("9.713447588"),
                "vtr": Decimal("1072520031.280431"),
                "rsr": Decimal("0.019167922"),
                "rtr": Decimal("792620031.280431"),
            },
            {
                "observed_at": NOW - timedelta(minutes=1),
                "mint": MINT_CURVE,
                "source": "solana_rpc",
                "vsr": Decimal("9.8"),
                "vtr": Decimal("1071000000"),
                "rsr": Decimal("0.12"),
                "rtr": Decimal("791100000"),
            },
        ],
    )
    await connection.execute(
        text(
            "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status, "
            "created_at) VALUES (:id, :name, :version, :kind, CAST(:params AS jsonb), :code_ref, "
            ":exp_ref, 'active', :created_at)"
        ),
        [
            {
                "id": RS_RESEARCH,
                "name": "meme_paper_v0",
                "version": "1",
                "kind": "research_only",
                "params": _j(_PARAMS_RESEARCH),
                "code_ref": "hunter_indicators.meme.rules",
                "exp_ref": "EXP-M1",
                "created_at": NOW - timedelta(days=1),
            },
            {
                "id": RS_OPERATOR,
                "name": "operator",
                "version": "1",
                "kind": "operator",
                "params": _j(_PARAMS_OPERATOR),
                "code_ref": "hunter_api.services.meme_desk",
                "exp_ref": None,
                "created_at": NOW - timedelta(days=1) + timedelta(seconds=1),
            },
        ],
    )
    proposals = [
        (P_PROPOSED, RS_OPERATOR, "rules", "proposed", -30, None, None, None, None),
        (P_APPROVED, RS_OPERATOR, "rules", "approved", -60, _SUGGESTED, CLERK_ID, None, None),
        (P_FILLED_OPEN, RS_RESEARCH, "rules", "approved", -600, _SUGGESTED, "rules", None, None),
        (
            P_FILLED_CLOSED,
            RS_RESEARCH,
            "rules",
            "approved",
            -7200,
            _SUGGESTED,
            "rules",
            None,
            None,
        ),
        (P_REJECTED, RS_OPERATOR, "rules", "rejected", -300, {"note": "nao"}, CLERK_ID, None, None),
        (
            P_UNFILLED,
            RS_RESEARCH,
            "rules",
            "unfilled",
            -180,
            _SUGGESTED,
            "rules",
            None,
            "daily_loss_cap",
        ),
    ]
    await connection.execute(
        text(
            "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
            "expires_at, features_end_time, quote, reasons, suggested, decision, decided_by, "
            "decided_at, bet_id, refusal) VALUES (:id, :mint, :rule_set_id, :origin, :status, "
            ":proposed_at, :expires_at, :features_end_time, CAST(:quote AS jsonb), "
            "CAST(:reasons AS jsonb), CAST(:suggested AS jsonb), CAST(:decision AS jsonb), "
            ":decided_by, :decided_at, :bet_id, :refusal)"
        ),
        [
            {
                "id": pid,
                "mint": MINT_CURVE,
                "rule_set_id": rs,
                "origin": origin,
                "status": status,
                "proposed_at": NOW + timedelta(seconds=offset),
                "expires_at": NOW + timedelta(seconds=offset + 120),
                "features_end_time": NOW + timedelta(seconds=offset - 60),
                "quote": _j(
                    {
                        "observed_at": (NOW + timedelta(seconds=offset - 10)).isoformat(),
                        "source": "solana_rpc",
                        "mcap_sol": "9.14",
                        "size_sol": "0.2",
                        "fee_sol": "0.0035",
                        "cost_sol": "0.2",
                    }
                ),
                "reasons": _j(["progress_gate", "age_gate"]),
                "suggested": _j(_SUGGESTED),
                "decision": None if decision is None else _j(decision),
                "decided_by": decided_by,
                "decided_at": None if decided_by is None else NOW + timedelta(seconds=offset + 5),
                "bet_id": bet_id,
                "refusal": refusal,
            }
            for pid, rs, origin, status, offset, decision, decided_by, bet_id, refusal in proposals
        ],
    )
    await connection.execute(
        text(
            "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, status, entry_at, "
            "entry, initial_risk_sol, params, exit_at, exit, pnl_sol, r_multiple, mark_sol, mark_at, "
            "high_water_x, sol_usd_at_entry, sol_usd_at_exit) VALUES (:id, :proposal_id, "
            ":rule_set_id, :mint, 'paper', :status, :entry_at, CAST(:entry AS jsonb), 0.2, "
            "CAST(:params AS jsonb), :exit_at, CAST(:exit AS jsonb), :pnl_sol, :r_multiple, "
            ":mark_sol, :mark_at, :high_water_x, :sol_usd_at_entry, :sol_usd_at_exit)"
        ),
        [
            {
                "id": B_OPEN,
                "proposal_id": P_FILLED_OPEN,
                "rule_set_id": RS_RESEARCH,
                "mint": MINT_CURVE,
                "status": "open",
                "entry_at": NOW - timedelta(minutes=9),
                "entry": _j(
                    {
                        "sol_spent": "0.2",
                        "fee_sol": "0.0035",
                        "tokens": "21000000",
                        "sol_usd_source": "coingecko",
                    }
                ),
                "params": _j(_SUGGESTED),
                "exit_at": None,
                "exit": None,
                "pnl_sol": None,
                "r_multiple": None,
                "mark_sol": Decimal("0.25"),
                "mark_at": NOW - timedelta(minutes=1),
                "high_water_x": Decimal("1.3"),
                "sol_usd_at_entry": Decimal("180"),
                "sol_usd_at_exit": None,
            },
            {
                "id": B_CLOSED,
                "proposal_id": P_FILLED_CLOSED,
                "rule_set_id": RS_RESEARCH,
                "mint": MINT_CURVE,
                "status": "closed",
                "entry_at": NOW - timedelta(hours=2),
                "entry": _j({"sol_spent": "0.2", "fee_sol": "0.0035", "tokens": "20000000"}),
                "params": _j(_SUGGESTED),
                "exit_at": NOW - timedelta(hours=1),
                "exit": _j(
                    {
                        "reason": "target",
                        "sol_received": "0.38",
                        "fee_sol": "0.0066",
                        "sol_usd_source": "coingecko",
                    }
                ),
                "pnl_sol": Decimal("0.18"),
                "r_multiple": Decimal("0.9"),
                "mark_sol": Decimal("0.38"),
                "mark_at": NOW - timedelta(hours=1),
                "high_water_x": Decimal("2.0"),
                "sol_usd_at_entry": Decimal("179"),
                "sol_usd_at_exit": Decimal("181"),
            },
        ],
    )
    # The bets exist now: close the proposals -> bets -> proposals cycle the
    # real schema enforces (``fk_meme_proposals_bet_id_meme_paper_bets`` plus
    # ``a_fill_names_its_bet``), the way the loop itself fills a proposal.
    await connection.execute(
        text("UPDATE meme_proposals SET status = 'filled', bet_id = :bet WHERE id = :id"),
        [{"bet": B_OPEN, "id": P_FILLED_OPEN}, {"bet": B_CLOSED, "id": P_FILLED_CLOSED}],
    )


async def _setup_schema(url: str) -> None:
    """DDL + seed in a throwaway loop (``asyncio.run``): asyncpg's connections
    are bound to the loop that created them (``test_meme_repository.py``)."""
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            for statement in DDL_STATEMENTS:
                await connection.execute(text(statement))
            await _seed(connection)
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def desk_database_url(postgres_container: PostgresContainer) -> str:
    url = asyncio.run(_create_database(postgres_container.get_connection_url()))
    asyncio.run(_setup_schema(url))
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
            P_UNFILLED,
            P_REJECTED,
            P_FILLED_CLOSED,
        ]
        assert [r.rank for r in rows] == [0, 1, 2, 3, 3, 3]
        open_row = rows[2]
        assert open_row.bet is not None and open_row.bet.mark_sol == Decimal("0.25")
        assert open_row.token is not None and open_row.token.name == "bum bum"
        assert open_row.rule_set is not None and open_row.rule_set.name == "meme_paper_v0"
        assert rows[3].proposal.refusal == "daily_loss_cap"

    async def test_keyset_cursor_pages_without_overlap_or_gap(
        self, repo: MemeDeskRepository
    ) -> None:
        seen: list[uuid.UUID] = []
        cursor: tuple[int, datetime, uuid.UUID] | None = None
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
                    "SELECT status, decision, decided_by, decided_at, quote, suggested "
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
        assert stored.suggested == _SUGGESTED  # untouched
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
        out = await file_manual_proposal(
            repo,
            FakeStore(),
            context=_context(),
            idempotency_key="desk-it-manual-1",
            body=ManualProposalIn.model_validate(
                {
                    "mint": MINT_CURVE,
                    "size_sol": "0.25",
                    "target_x": "3",
                    "trailing_pct": "40",
                    "max_hold_s": 300,
                }
            ),
            now=NOW,
        )
        row = out.row
        assert row.origin == "operator" and row.status == "approved"
        assert row.rule_set is not None and row.rule_set.id == RS_OPERATOR
        assert row.quote.source == "solana_rpc"
        assert row.quote.observed_at == NOW - timedelta(minutes=1)
        assert row.quote.cost_sol == Decimal("0.25")
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


class TestCommands:
    async def test_sell_now_inserts_a_command_and_refuses_a_second_pending_one(
        self, repo: MemeDeskRepository
    ) -> None:
        out = await sell_now(
            repo,
            FakeStore(),
            context=_context(),
            bet_id=B_OPEN,
            idempotency_key="desk-it-sell-1",
            now=NOW,
        )
        stored = await repo.get_command(out.id)
        assert stored is not None and stored.command == "sell_now" and stored.bet_id == B_OPEN
        assert stored.applied_at is None and stored.result is None
        pending = await repo.pending_command(bet_id=B_OPEN, command="sell_now")
        assert pending is not None and pending.id == out.id
        with pytest.raises(BetStateConflictError, match="sell_now_already_pending"):
            await sell_now(
                repo,
                FakeStore(),
                context=_context(),
                bet_id=B_OPEN,
                idempotency_key="desk-it-sell-2",
                now=NOW,
            )

    async def test_sell_now_on_a_closed_bet_is_409(self, repo: MemeDeskRepository) -> None:
        with pytest.raises(BetStateConflictError, match="bet_not_open"):
            await sell_now(
                repo,
                FakeStore(),
                context=_context(),
                bet_id=B_CLOSED,
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
            proposal_id=P_APPROVED,
            idempotency_key="desk-it-cancel-1",
            now=NOW,
        )
        stored = await repo.get_command(out.id)
        assert stored is not None and stored.command == "cancel"
        assert stored.proposal_id == P_APPROVED and stored.bet_id is None
        with pytest.raises(ProposalStateConflictError, match="already_filled"):
            await cancel_proposal(
                repo,
                FakeStore(),
                context=_context(),
                proposal_id=P_FILLED_OPEN,
                idempotency_key="desk-it-cancel-2",
                now=NOW,
            )


class TestSummary:
    async def test_balances_per_rule_set_and_day_pnl(self, repo: MemeDeskRepository) -> None:
        balances = await repo.rule_set_balances(NOW)
        by_name = {b.rule_set.name: b for b in balances}
        research = by_name["meme_paper_v0"]
        assert research.open_sol == Decimal("0.2")
        assert research.open_bets == 1
        assert research.realized_today_sol == Decimal("0.18")
        assert research.closed_today == 1
        assert research.realized_total_sol == Decimal("0.18")
        operator = by_name["operator"]
        assert operator.open_sol == 0 and operator.open_bets == 0
        summary = build_summary(balances, await repo.latest_sol_usd_quote())
        research_out = next(r for r in summary.rule_sets if r.rule_set.name == "meme_paper_v0")
        assert research_out.balance_sol == Decimal("5") + Decimal("0.18") - Decimal("0.2")
        assert summary.day_pnl_sol == Decimal("0.18")
        assert summary.sol_usd is not None
        assert summary.sol_usd.rate == Decimal("180")  # the open bet's entry is the newest
        assert summary.sol_usd.observed_at == NOW - timedelta(minutes=9)
        assert summary.sol_usd.source == "coingecko"

    async def test_yesterdays_close_does_not_count_as_today(self, repo: MemeDeskRepository) -> None:
        balances = await repo.rule_set_balances(NOW + timedelta(days=1))
        research = next(b for b in balances if b.rule_set.name == "meme_paper_v0")
        assert research.realized_today_sol == 0
        assert research.closed_today == 0
        assert research.realized_total_sol == Decimal("0.18")


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


@pytest.mark.xfail(
    strict=False,
    reason="migration 0022_meme_lab (T4.6) may not have landed in infra/migrations yet",
)
async def test_http_approve_against_the_real_migration(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The real app over Alembic-to-head: seed as ``hunter_worker`` (the
    loop's role), approve as the org's OWNER with ``Idempotency-Key``, read
    the desk, and find the ``audit_logs`` row as ``hunter_app``."""
    actor = await create_org(client, make_actor("desk-owner"), "Desk Org")
    assert actor.org_id is not None
    proposal_id = uuid7()
    mint = "SyntheticDeskMintForMigrationProbexxxxxxxxxx"
    now = datetime.now(UTC)
    async with role_session(session_factory, db_role="hunter_worker") as session:
        await session.execute(
            text(
                "INSERT INTO meme_tokens (mint, name, symbol, first_seen_source, first_seen_at, "
                "last_seen_at, updated_at) VALUES (:mint, 'desk probe', 'PROBE', 'pumpportal_ws', "
                ":now, :now, :now)"
            ),
            {"mint": mint, "now": now},
        )
        real_rule_set_id = await session.scalar(
            text("SELECT id FROM meme_rule_sets WHERE name = 'operator' AND version = '1'")
        )
        assert real_rule_set_id is not None, "0022 seeds no operator/1 rule set"
        await session.execute(
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
                "quote": _j({"source": "solana_rpc", "observed_at": now.isoformat()}),
                "reasons": _j(["probe"]),
                "suggested": _j(_SUGGESTED),
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
    async with tenant_session(session_factory, actor.org_id) as session:
        rows = (
            (await session.execute(select(AuditLog).where(AuditLog.entity_id == proposal_id)))
            .scalars()
            .all()
        )
    assert [row.action for row in rows] == ["meme_desk.proposal.approved"]
