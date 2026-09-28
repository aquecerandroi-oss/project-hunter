"""F1 on a real, migrated Postgres (testcontainers): Everton's audited per-mint
exception (decision 2026-09-28) through the executor's own reader and the
desk's ``entries.py`` end to end.

What is proved: the active exception of **this** wallet for the frozen scam mint
lets the desk entry go through and the admission records the mint apart
(``wallet_holdings.excepted``); a second foreign mint still refuses by name; a
revoked exception, an exception of another wallet, or the scam account thawed
all refuse again; the heartbeat publishes the excepted mints apart; the SQL
returns only this wallet's unrevoked rows."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.solana_codec import TOKEN_2022_PROGRAM_ID, TOKEN_PROGRAM_ID
from hunter_meme_executor.chain import TokenHolding
from hunter_meme_executor.entries import entries_once
from hunter_meme_executor.heartbeat import heartbeat_fields
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.wallet_exceptions import HoldingException, active_exceptions
from hunter_meme_executor.wallet_holdings import holdings_once

from . import test_live_persistence as _live
from .test_live_persistence import Harness, _plant_proposal, _rows

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

harness = _live.harness  # the Postgres rig and its per-test cleanup, shared as is

SCAM = "DgY9Z8xPG1346Ydrq98ASAZcVdyrurT4tCQ7TDapHcJg"
FOREIGN = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"
ATOMS = 100_000 * 10**6
STRANGER = "Stranger11111111111111111111111111111111111"
_INSERT = text(
    "INSERT INTO meme_wallet_holding_exceptions (id, wallet, token_program, mint, max_atoms, "
    "  decimals, require_frozen, evidence, reason, note_path, note_sha256, created_by) "
    "VALUES (:id, :wallet, :program, :mint, :atoms, 6, true, CAST(:evidence AS jsonb), "
    "  'token de phishing congelado pelo emissor', "
    "  'obsidian/06-DECISIONS/2026-09-28-excecao-auditada-token-golpe.md', :sha, 'Everton') "
    "RETURNING id"
)
_REVOKE = text(
    "UPDATE meme_wallet_holding_exceptions SET revoked_at = now(), revoked_by = 'pytest', "
    "  revoke_reason = 'limpeza do teste de integração' "
    "WHERE revoked_at IS NULL AND mint IN (:scam, :foreign)"
)


def _scam(state: str = "frozen") -> TokenHolding:
    return TokenHolding(SCAM, TOKEN_2022_PROGRAM_ID, ATOMS, 6, False, state)


def _foreign() -> TokenHolding:
    return TokenHolding(FOREIGN, TOKEN_PROGRAM_ID, 50_000_000, 9, False, "initialized")


async def _except(engine: AsyncEngine, wallet: str, mint: str = SCAM) -> str:
    async with engine.begin() as conn:
        row = await conn.execute(
            _INSERT,
            {
                "id": str(uuid.uuid4()), "wallet": wallet, "program": TOKEN_2022_PROGRAM_ID,
                "mint": mint, "atoms": ATOMS, "sha": "b" * 64,
                "evidence": json.dumps({"accounts": [{"state": "frozen"}]}),
            },
        )  # fmt: skip
        return str(row.scalar_one())


async def _revoke(engine: AsyncEngine, exception_id: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE meme_wallet_holding_exceptions SET revoked_at = now(), "
                "revoked_by = 'Everton', revoke_reason = 'o emissor descongelou a conta' "
                "WHERE id = :id"
            ),
            {"id": exception_id},
        )


@pytest_asyncio.fixture
async def clean(db_engine: AsyncEngine) -> AsyncIterator[None]:
    """Rows are never deleted (trigger): each test revokes what it left active."""
    yield
    async with db_engine.begin() as conn:
        await conn.execute(_REVOKE, {"scam": SCAM, "foreign": FOREIGN})


async def _admit(harness: Harness, db_engine: AsyncEngine) -> dict[str, Any]:
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    orders = await _rows(
        db_engine, "SELECT * FROM meme_live_orders WHERE proposal_id = :p", p=proposal_id
    )
    assert len(orders) == 1, orders
    return orders[0]


def _pubkey(harness: Harness) -> str:
    assert harness.ctx.signer is not None
    return harness.ctx.signer.pubkey


async def test_the_excepted_scam_token_no_longer_blocks_the_desk_entry(
    harness: Harness, db_engine: AsyncEngine, clean: None
) -> None:
    harness.chain.holdings = [_scam()]
    exception_id = await _except(db_engine, _pubkey(harness))
    order = await _admit(harness, db_engine)
    assert order["status"] == "confirmed", order
    holdings = order["admission"]["wallet_holdings"]
    assert holdings["unrecognized"] == []
    assert [(e["mint"], e["exception_id"]) for e in holdings["excepted"]] == [(SCAM, exception_id)]
    assert holdings["excepted_count"] == 1


async def test_another_foreign_mint_still_refuses_by_name(
    harness: Harness, db_engine: AsyncEngine, clean: None
) -> None:
    harness.chain.holdings = [_scam(), _foreign()]
    await _except(db_engine, _pubkey(harness))
    order = await _admit(harness, db_engine)
    assert order["status"] == "refused" and order["reason"] == "wallet_unrecognized_holdings"
    assert order["admission"]["wallet_holdings"]["unrecognized"] == [FOREIGN]
    assert [e["mint"] for e in order["admission"]["wallet_holdings"]["excepted"]] == [SCAM]
    assert harness.rpc.sent == []


@pytest.mark.parametrize("case", ["revoked", "another_wallet", "thawed"])
async def test_no_valid_exception_refuses_the_scam_token_again(
    harness: Harness, db_engine: AsyncEngine, clean: None, case: str
) -> None:
    harness.chain.holdings = [_scam("initialized" if case == "thawed" else "frozen")]
    exception_id = await _except(
        db_engine, STRANGER if case == "another_wallet" else _pubkey(harness)
    )
    if case == "revoked":
        await _revoke(db_engine, exception_id)
    order = await _admit(harness, db_engine)
    assert order["status"] == "refused" and order["reason"] == "wallet_unrecognized_holdings"
    assert order["admission"]["wallet_holdings"]["unrecognized"] == [SCAM]
    assert order["admission"]["wallet_holdings"]["excepted"] == []
    assert harness.rpc.sent == []


async def test_the_heartbeat_publishes_the_excepted_mints_apart(
    harness: Harness, db_engine: AsyncEngine, clean: None
) -> None:
    harness.chain.holdings = [_scam(), _foreign()]
    await _except(db_engine, _pubkey(harness))
    await holdings_once(harness.ctx)
    fields = await heartbeat_fields(harness.ctx)
    assert fields["wallet_unrecognized_mints"] == FOREIGN
    assert fields["wallet_unrecognized_count"] == "1"
    assert fields["wallet_excepted_mints"] == SCAM and fields["wallet_excepted_count"] == "1"


async def test_the_sql_reads_only_this_wallets_unrevoked_rows(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession], clean: None
) -> None:
    wallet = "SqlWallet111111111111111111111111111111111"
    revoked = await _except(db_engine, wallet, FOREIGN)
    await _revoke(db_engine, revoked)
    active = await _except(db_engine, wallet)
    await _except(db_engine, STRANGER, FOREIGN)
    async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
        got = await active_exceptions(session, wallet=wallet)
    assert len(got) == 1
    assert got[0].created_at.tzinfo is not None
    assert got[0] == HoldingException(
        TOKEN_2022_PROGRAM_ID, SCAM, ATOMS, 6, True, active, got[0].created_at
    )
