"""``wallet_holding_exception.py`` against the real migrated schema
(testcontainers Postgres 16, ``alembic upgrade head``) with a fake read-only RPC
(canned ``jsonParsed`` answers; ``sendTransaction`` is never called and no key is
ever read). Skips cleanly without Docker. Decision 2026-09-28.

What is proved: the dry run writes nothing and names the note it would need;
``--apply`` writes the row **and** its ``audit_logs`` row in one transaction (an
audit that fails leaves no row); the note gate refuses a note that does not
mention the mint; a recognized mint, a missing account, an unfrozen account
without ``--allow-unfrozen`` and a second active exception refuse by name with
nothing written; ``--allow-unfrozen`` is recorded; revocation is audited, final,
and needs no chain; ``--list`` shows both states.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

pytestmark = pytest.mark.integration

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for extra in (SCRIPTS_DIR, SCRIPTS_DIR / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import wallet_holding_exception as script  # noqa: E402
from test_wallet_holding_exception_rules import (  # noqa: E402
    ACCOUNT,
    ATOMS,
    MINT,
    WALLET,
    accounts_answer,
    mint_answer,
    token_account,
)
from wallet_holding_exception_rules import Refused  # noqa: E402

from hunter_exchanges.pumpfun.solana_codec import TOKEN_2022_PROGRAM_ID  # noqa: E402

OPERATOR_RULE_SET = "01994d00-6c1a-7000-8000-000000000002"
NOTE = "obsidian/06-DECISIONS/nota-golpe.md"
REASON = "token de phishing congelado pelo emissor"


class FakeRpc:
    def __init__(self, accounts: dict[str, Any] | None = None) -> None:
        self.accounts = accounts_answer(token_account()) if accounts is None else accounts
        self.calls: list[str] = []

    def call(self, method: str, params: list[Any]) -> Any:
        assert method != "sendTransaction"
        self.calls.append(method)
        if method == "getTokenAccountsByOwner":
            assert params[0] == WALLET and params[1] == {"mint": MINT}
            assert params[2] == {"encoding": "jsonParsed", "commitment": "confirmed"}
            return self.accounts
        assert method == "getAccountInfo" and params[0] == MINT
        return mint_answer()


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    notes = tmp_path / "obsidian" / "06-DECISIONS"
    notes.mkdir(parents=True)
    (notes / "nota-golpe.md").write_text(f"# Exceção\n\nMint `{MINT}` congelado.\n", "utf-8")
    (notes / "outra.md").write_text("# Outra nota sem o mint\n", "utf-8")
    return tmp_path


@pytest_asyncio.fixture
async def engine(migrated_db_url: str) -> AsyncIterator[AsyncEngine]:
    created = create_async_engine(migrated_db_url, connect_args={"statement_cache_size": 0})
    try:
        yield created
    finally:
        async with created.begin() as conn:  # the guard holds the owner too; tests lift it
            await conn.execute(text(f"ALTER TABLE {script.TABLE} DISABLE TRIGGER USER"))
            await conn.execute(text(f"DELETE FROM {script.TABLE}"))  # noqa: S608
            await conn.execute(text(f"ALTER TABLE {script.TABLE} ENABLE TRIGGER USER"))
            await conn.execute(text("DELETE FROM audit_logs WHERE action LIKE 'wallet.holding%'"))
        await created.dispose()


async def _act(engine: AsyncEngine, act: str, **kw: Any) -> str:
    async with AsyncSession(engine) as session, session.begin():
        if act == "add":
            base: dict[str, Any] = {
                "wallet": WALLET, "program": TOKEN_2022_PROGRAM_ID, "mint": MINT,
                "reason": REASON, "actor": "Everton", "note": NOTE,
                "allow_unfrozen": False, "apply": False,
            }  # fmt: skip
            base.update(kw)
            rpc = base.pop("rpc", FakeRpc())
            return await script.add(session, rpc, **base)
        if act == "revoke":
            return await script.revoke(session, **kw)
        return await script.list_exceptions(session, **kw)


async def _rows(engine: AsyncEngine, sql: str) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        return [dict(r) for r in (await conn.execute(text(sql))).mappings()]


_EXC = f"SELECT * FROM {script.TABLE} ORDER BY created_at"  # noqa: S608
_AUDIT = "SELECT * FROM audit_logs WHERE action LIKE 'wallet.holding%' ORDER BY created_at"


async def test_the_dry_run_writes_nothing_and_names_the_note(
    engine: AsyncEngine, repo_root: Path
) -> None:
    report = await _act(engine, "add", repo_root=repo_root, note=None)
    assert "dry-run" in report and MINT in report and "--note" in report
    assert await _rows(engine, _EXC) == [] and await _rows(engine, _AUDIT) == []


async def test_apply_writes_the_row_and_its_audit_together(
    engine: AsyncEngine, repo_root: Path
) -> None:
    rpc = FakeRpc()
    await _act(engine, "add", rpc=rpc, repo_root=repo_root, apply=True)
    assert rpc.calls == ["getTokenAccountsByOwner", "getAccountInfo"]
    (row,) = await _rows(engine, _EXC)
    assert (row["wallet"], row["mint"], row["token_program"]) == (
        WALLET,
        MINT,
        TOKEN_2022_PROGRAM_ID,
    )
    assert (int(row["max_atoms"]), row["decimals"], row["require_frozen"]) == (ATOMS, 6, True)
    assert row["note_path"] == NOTE and len(row["note_sha256"]) == 64
    assert row["evidence"]["accounts"][0]["address"] == ACCOUNT
    assert row["evidence"]["frozen_by_third_party"] is True
    (audit,) = await _rows(engine, _AUDIT)
    assert audit["action"] == "wallet.holding_exception.add"
    assert audit["organization_id"] is None and audit["entity_id"] == row["id"]
    assert audit["after"]["mint"] == MINT and audit["metadata"]["actor_input"] == "Everton"
    assert audit["metadata"]["note"] == NOTE
    listing = await _act(engine, "list")
    assert MINT in listing and "active" in listing


async def test_a_failed_audit_leaves_no_exception(
    engine: AsyncEngine, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script, "_AUDIT", text("SELECT 1/0"))
    with pytest.raises(Exception, match="division by zero"):
        await _act(engine, "add", repo_root=repo_root, apply=True)
    assert await _rows(engine, _EXC) == []


@pytest.mark.parametrize(
    ("kw", "reason"),
    [
        ({"note": "obsidian/06-DECISIONS/outra.md"}, "note_does_not_mention_target"),
        ({"note": None}, "note_required"),
        ({"rpc": FakeRpc(accounts_answer())}, "account_not_found"),
        (
            {"rpc": FakeRpc(accounts_answer(token_account(state="initialized")))},
            "account_not_frozen_by_third_party",
        ),
    ],
)
async def test_named_refusals_write_nothing(
    engine: AsyncEngine, repo_root: Path, kw: dict[str, Any], reason: str
) -> None:
    with pytest.raises(Refused, match=f"^{reason}"):
        await _act(engine, "add", repo_root=repo_root, apply=True, **kw)
    assert await _rows(engine, _EXC) == [] and await _rows(engine, _AUDIT) == []


async def test_a_second_active_exception_refuses(engine: AsyncEngine, repo_root: Path) -> None:
    await _act(engine, "add", repo_root=repo_root, apply=True)
    with pytest.raises(Refused, match="^exception_already_active"):
        await _act(engine, "add", repo_root=repo_root, apply=True)
    assert len(await _rows(engine, _AUDIT)) == 1


async def test_a_mint_the_executor_holds_refuses(engine: AsyncEngine, repo_root: Path) -> None:
    now = datetime.now(UTC)
    pid = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, last_seen_at, "
                "created_at) VALUES (:m, 'pumpportal_ws', :t, :t, :t) ON CONFLICT (mint) DO NOTHING"
            ),
            {"m": MINT, "t": now},
        )
        await conn.execute(
            text(
                "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
                "expires_at, quote, reasons, suggested, decision, decided_by, decided_at, mode) "
                "VALUES (:id, :m, :rs, 'operator', 'approved', :t, :exp, '{}', '[]', '{}', '{}', "
                "'user_x', :t, 'live')"
            ),
            {
                "id": pid,
                "m": MINT,
                "rs": OPERATOR_RULE_SET,
                "t": now,
                "exp": now + timedelta(minutes=2),
            },
        )
        await conn.execute(
            text(
                "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, status, "
                "tx_signature) VALUES (:id, :p, 'buy', :k, 'submitted_unconfirmed', :sig)"
            ),
            {"id": str(uuid.uuid4()), "p": pid, "k": f"meme:{pid}", "sig": f"sig{pid}"},
        )
    try:
        with pytest.raises(Refused, match="^mint_recognized"):
            await _act(engine, "add", repo_root=repo_root, apply=True)
        assert await _rows(engine, _EXC) == []
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM meme_live_orders WHERE proposal_id = :p"), {"p": pid}
            )
            await conn.execute(text("DELETE FROM meme_proposals WHERE id = :p"), {"p": pid})


async def test_allow_unfrozen_is_explicit_and_recorded(
    engine: AsyncEngine, repo_root: Path
) -> None:
    rpc = FakeRpc(accounts_answer(token_account(state="initialized")))
    await _act(engine, "add", rpc=rpc, repo_root=repo_root, apply=True, allow_unfrozen=True)
    (row,) = await _rows(engine, _EXC)
    assert row["require_frozen"] is False and row["evidence"]["allow_unfrozen"] is True
    (audit,) = await _rows(engine, _AUDIT)
    assert audit["after"]["require_frozen"] is False


async def test_revocation_is_audited_final_and_needs_no_chain(
    engine: AsyncEngine, repo_root: Path
) -> None:
    await _act(engine, "add", repo_root=repo_root, apply=True)
    kw: dict[str, Any] = {"wallet": WALLET, "mint": MINT, "reason": "o emissor descongelou"}
    report = await _act(engine, "revoke", actor="Everton", apply=False, **kw)
    assert "dry-run" in report
    assert (await _rows(engine, _EXC))[0]["revoked_at"] is None
    await _act(engine, "revoke", actor="Everton", apply=True, **kw)
    (row,) = await _rows(engine, _EXC)
    assert row["revoked_by"] == "Everton" and row["revoke_reason"] == "o emissor descongelou"
    audits = await _rows(engine, _AUDIT)
    assert [a["action"] for a in audits] == [
        "wallet.holding_exception.add",
        "wallet.holding_exception.revoke",
    ]
    assert audits[1]["entity_id"] == row["id"] and audits[1]["before"]["revoked_at"] is None
    with pytest.raises(Refused, match="^exception_not_found"):
        await _act(engine, "revoke", actor="Everton", apply=True, **kw)
    assert "revoked" in await _act(engine, "list", wallet=WALLET)


def test_the_args_take_one_act_and_what_it_needs() -> None:
    args = script.parse_args(
        ["--add", "--wallet", WALLET, "--mint", MINT, "--program", "token-2022", "--reason", REASON]
    )
    assert args.program == TOKEN_2022_PROGRAM_ID and args.apply is False
    for bad in (
        ["--add", "--revoke", "--wallet", WALLET, "--mint", MINT, "--reason", REASON],
        ["--add", "--mint", MINT, "--program", "token-2022", "--reason", REASON],  # no wallet
        ["--add", "--wallet", WALLET, "--mint", MINT, "--reason", REASON],  # no program
        ["--add", "--wallet", WALLET, "--mint", MINT, "--program", "spl-memo", "--reason", REASON],
        [],
    ):
        with pytest.raises(SystemExit):
            script.parse_args(bad)
