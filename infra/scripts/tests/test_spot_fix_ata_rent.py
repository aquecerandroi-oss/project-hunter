"""``spot_fix_ata_rent.py`` (KB-0171) against the real migrated schema
(testcontainers Postgres 16, ``alembic upgrade head``) with a fake read-only RPC
serving ``getTransaction`` metas (labeled test data shaped like the real
Jupiter buys: 1 488 440 lamports added to the new ATA; ``sendTransaction`` does
not exist on the fake). Skips cleanly without Docker.

Proved: the dry run writes nothing; ``--apply`` corrects the position from its
own entry transaction (+550 840 lamports of spend, pnl and R down by as much)
and writes one ``audit_logs`` row in the same transaction; a second run changes
nothing and audits nothing; an open candidate is skipped; a rent that cannot be
read, a delta that disagrees with the row, or a missing note refuse with
nothing written — even when another position was fixable.
"""

from __future__ import annotations

import json
import struct
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import spot_fix_ata_rent as script  # noqa: E402

from hunter_exchanges.pumpfun.solana_codec import (  # noqa: E402
    SYSTEM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    associated_token_address,
    b58encode,
    pubkey_bytes,
)

WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
MINT = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
ATA = associated_token_address(WALLET, MINT, token_program=TOKEN_PROGRAM_ID)
TAG = "kb0171fix"
RENT_PAID, RENT_CONSTANT = 1_488_440, 2_039_280
TICKET, FEES, TOKENS, RECEIVED = 50_000_000, 43_316, 3_123_456_789, 49_900_000
RISK = Decimal("0.00075")
NOTE = "obsidian/11-KNOWLEDGE/nota-aluguel.md"


KEYS = [WALLET, "WsolAta", SYSTEM_PROGRAM_ID, ATA]


def create_ix(lamports: int) -> dict[str, Any]:
    """The ATA program's inner ``system::createAccount`` funded by the wallet (raw json)."""
    data = struct.pack("<IQQ", 0, lamports, 165) + pubkey_bytes(TOKEN_PROGRAM_ID)
    return {"programIdIndex": 2, "accounts": [0, 3], "data": b58encode(data)}


def meta(*, rent: int | None = RENT_PAID, delta: int | None = None) -> dict[str, Any]:
    """A Jupiter SOL -> token buy (``encoding: json``): the ATA at index 3."""
    kept = RENT_PAID if rent is None else rent  # the wallet paid it either way
    wallet_delta = -(TICKET + FEES + kept) if delta is None else delta
    pre = [1_000_000_000, 0, 7_000_000_000, 0]
    post = [pre[0] + wallet_delta, 0, pre[2] + TICKET, kept]
    if rent is None:
        pre, post = pre[:3], post[:3]  # the new account's balance is missing: unreadable
    tb = {"accountIndex": 3, "mint": MINT, "owner": WALLET, "programId": TOKEN_PROGRAM_ID,
          "uiTokenAmount": {"amount": str(TOKENS), "decimals": 6}}  # fmt: skip
    return {
        "slot": 1,
        "blockTime": 1_759_000_000,
        "transaction": {"message": {"accountKeys": KEYS}},
        "meta": {
            "err": None,
            "fee": FEES,
            "preBalances": pre,
            "postBalances": post,
            "preTokenBalances": [],
            "postTokenBalances": [tb],
            "innerInstructions": [{"index": 2, "instructions": [create_ix(kept)]}],
        },  # fmt: skip
    }


class FakeRpc:
    def __init__(self, replies: dict[str, dict[str, Any] | None]) -> None:
        self.replies = replies
        self.calls: list[str] = []

    def get_transaction(self, signature: str, *, commitment: str = "confirmed") -> Any:
        assert commitment == "confirmed"
        self.calls.append(signature)
        return self.replies.get(signature)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    notes = tmp_path / "obsidian" / "11-KNOWLEDGE"
    notes.mkdir(parents=True)
    (notes / "nota-aluguel.md").write_text("# Aluguel\n\nPosições: {ids}\n", "utf-8")
    return tmp_path


@pytest_asyncio.fixture
async def engine(migrated_db_url: str) -> AsyncIterator[AsyncEngine]:
    created = create_async_engine(migrated_db_url, connect_args={"statement_cache_size": 0})
    try:
        yield created
    finally:
        async with created.begin() as conn:
            await conn.execute(
                text("DELETE FROM audit_logs WHERE action = :a"), {"a": script.ACTION}
            )
            await conn.execute(text("DELETE FROM spot_positions WHERE mint = :m"), {"m": MINT})
            await conn.execute(text("DELETE FROM spot_orders WHERE mint = :m"), {"m": MINT})
            for sql in (
                "DELETE FROM agent_signals WHERE params_hash = :tag",
                "DELETE FROM markets WHERE exchange_id IN (SELECT id FROM exchanges WHERE name = :tag)",
                "DELETE FROM exchanges WHERE name = :tag",
                "DELETE FROM strategy_versions WHERE strategy_id IN (SELECT id FROM strategies WHERE name = :tag)",
                "DELETE FROM strategies WHERE name = :tag",
            ):  # fmt: skip
                await conn.execute(text(sql), {"tag": TAG})
        await created.dispose()


async def _plant(engine: AsyncEngine, *, status: str = "closed") -> tuple[str, str]:
    """One buy that created an ATA, recorded with the old constant. ``(position_id, signature)``."""
    ids = {k: str(uuid.uuid4()) for k in ("strategy", "version", "exchange", "market", "signal")}
    position, order, signature = str(uuid.uuid4()), str(uuid.uuid4()), f"sig-{uuid.uuid4().hex}"
    delta = -(TICKET + FEES + RENT_PAID)
    spent_wrong = -delta - RENT_CONSTANT
    pnl = Decimal(RECEIVED - spent_wrong) / Decimal(1_000_000_000)
    entry = {"order_id": order, "signature": signature, "filled_atoms": TOKENS,
             "sol_delta_lamports": delta, "sol_spent_lamports": spent_wrong,
             "sol_spent_source": "signature_delta_minus_rent", "ata_rent_lamports": RENT_CONSTANT}  # fmt: skip
    closed = status == "closed"
    entry_at = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    async with engine.begin() as conn:
        key = f"{TAG}{uuid.uuid4().hex[:8]}"
        for sql in (
            "INSERT INTO strategies (id, key, name) VALUES (:strategy, :key, :tag)",
            "INSERT INTO strategy_versions (id, strategy_id, version) VALUES (:version, :strategy, 'v1')",
            "INSERT INTO exchanges (id, code, name) VALUES (:exchange, :key, :tag)",
            "INSERT INTO markets (id, exchange_id, symbol, market_type) "
            "VALUES (:market, :exchange, 'WIFUSDT', 'perpetual')",
            "INSERT INTO agent_signals (id, strategy_version_id, market_id, params_hash, direction, "
            "  confidence) VALUES (:signal, :version, :market, :tag, 'long', 0.5)",
        ):  # fmt: skip
            await conn.execute(text(sql), {**ids, "tag": TAG, "key": key})
        await conn.execute(
            text(
                "INSERT INTO spot_orders (id, signal_id, market_symbol, mint, side, client_order_id, "
                "  status, tx_signature, admission, fill, settled_at, updated_at) VALUES (:id, :s, "
                "  'WIFUSDT', :m, 'buy', :k, 'confirmed', :sig, CAST(:adm AS jsonb), "
                "  CAST(:fill AS jsonb), :at, :at)"
            ),
            {
                "id": order,
                "s": ids["signal"],
                "m": MINT,
                "k": f"spot:buy:{ids['signal']}",
                "sig": signature,
                "adm": json.dumps({"wallet_id": WALLET}),
                "fill": json.dumps(
                    {"ata_rent_lamports": RENT_CONSTANT, "sol_delta_lamports": delta}
                ),
                "at": entry_at,
            },  # fmt: skip
        )
        await conn.execute(
            text(
                "INSERT INTO spot_positions (id, signal_id, entry_order_id, market_symbol, mint, "
                "  status, entry_at, entry, tokens, sol_spent_lamports, initial_risk_sol, params, "
                "  ata_rent_lamports, exit_at, exit, sol_received_lamports, pnl_sol, r_multiple) "
                "VALUES (:id, :s, :o, 'WIFUSDT', :m, :st, :e, CAST(:entry AS jsonb), :tok, :spent, "
                "  :risk, CAST(:params AS jsonb), :rent, :x, CAST(:ex AS jsonb), :rcv, :pnl, :r)"
            ),
            {
                "id": position,
                "s": ids["signal"],
                "o": order,
                "m": MINT,
                "st": status,
                "e": entry_at,
                "entry": json.dumps(entry),
                "tok": 0 if closed else TOKENS,
                "spent": spent_wrong,
                "risk": RISK,
                "rent": RENT_CONSTANT,
                "params": json.dumps({"stop_frac": "0.015", "ata_rent_lamports": RENT_CONSTANT}),
                "x": entry_at + timedelta(hours=1) if closed else None,
                "ex": json.dumps({"reason": "time"}) if closed else None,
                "rcv": RECEIVED if closed else None,
                "pnl": pnl if closed else None,
                "r": pnl / RISK if closed else None,
            },  # fmt: skip
        )
    return position, signature


async def _run(engine: AsyncEngine, rpc: FakeRpc, repo_root: Path, **kw: Any) -> str:
    async with AsyncSession(engine) as session, session.begin():
        base: dict[str, Any] = {
            "apply": False,
            "note": None,
            "actor": "Everton",
            "repo_root": repo_root,
        }
        return await script.run(session, rpc, **{**base, **kw})


async def _rows(engine: AsyncEngine, sql: str) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        return [
            dict(r)
            for r in (await conn.execute(text(sql), {"m": MINT, "a": script.ACTION})).mappings()
        ]


_POS = "SELECT * FROM spot_positions WHERE mint = :m ORDER BY entry_at, id"
_AUDIT = "SELECT * FROM audit_logs WHERE action = :a ORDER BY created_at"


def _write_note(repo_root: Path, *ids: str) -> None:
    (repo_root / NOTE).write_text("# Aluguel\n\n" + "\n".join(f"- `{i[:8]}`" for i in ids), "utf-8")


@pytest.mark.integration
async def test_the_dry_run_shows_before_after_and_writes_nothing(
    engine: AsyncEngine, repo_root: Path
) -> None:
    pid, sig = await _plant(engine)
    before = await _rows(engine, _POS)
    report = await _run(engine, FakeRpc({sig: meta()}), repo_root)
    assert "dry-run" in report and "CORRECT" in report and "to_correct=1" in report
    assert f"{TICKET + FEES - 550_840} -> {TICKET + FEES}" in report
    assert pid[:8] in report and "--note" in report
    assert await _rows(engine, _POS) == before and await _rows(engine, _AUDIT) == []


@pytest.mark.integration
async def test_apply_corrects_from_the_transaction_and_audits_in_the_same_transaction(
    engine: AsyncEngine, repo_root: Path
) -> None:
    pid, sig = await _plant(engine)
    _write_note(repo_root, pid)
    (old,) = await _rows(engine, _POS)
    report = await _run(engine, FakeRpc({sig: meta()}), repo_root, apply=True, note=NOTE)
    assert "applied: 1 positions corrected" in report
    (row,) = await _rows(engine, _POS)
    assert row["sol_spent_lamports"] == TICKET + FEES == old["sol_spent_lamports"] + 550_840
    assert row["ata_rent_lamports"] == RENT_PAID
    assert row["pnl_sol"] == old["pnl_sol"] - Decimal("0.00055084")
    assert row["pnl_sol"] == Decimal(RECEIVED - TICKET - FEES) / Decimal(1_000_000_000)
    assert abs(row["r_multiple"] - row["pnl_sol"] / RISK) < Decimal("1e-9")
    assert row["entry"]["sol_spent_lamports"] == TICKET + FEES
    assert (
        row["entry"]["rent_correction"]["before"]["sol_spent_lamports"] == TICKET + FEES - 550_840
    )
    assert row["entry"]["filled_atoms"] == TOKENS, "the rest of the entry is kept"
    assert row["params"]["stop_frac"] == "0.015" and row["params"]["ata_rent_lamports"] == RENT_PAID
    (audit,) = await _rows(engine, _AUDIT)
    assert str(audit["entity_id"]) == pid and audit["organization_id"] is None
    assert audit["before"]["sol_spent_lamports"] == TICKET + FEES - 550_840
    assert audit["after"]["sol_spent_lamports"] == TICKET + FEES
    assert audit["metadata"]["note"] == NOTE and audit["metadata"]["signature"] == sig


@pytest.mark.integration
async def test_a_second_run_changes_nothing_and_audits_nothing(
    engine: AsyncEngine, repo_root: Path
) -> None:
    pid, sig = await _plant(engine)
    _write_note(repo_root, pid)
    rpc = FakeRpc({sig: meta()})
    await _run(engine, rpc, repo_root, apply=True, note=NOTE)
    after_first = await _rows(engine, _POS)
    report = await _run(engine, rpc, repo_root, apply=True, note=NOTE)
    assert "already correct" in report and "nothing to correct: nothing written" in report
    assert await _rows(engine, _POS) == after_first
    assert len(await _rows(engine, _AUDIT)) == 1


@pytest.mark.integration
async def test_an_open_candidate_is_skipped_by_name(engine: AsyncEngine, repo_root: Path) -> None:
    pid, sig = await _plant(engine, status="open")
    rpc = FakeRpc({sig: meta()})
    report = await _run(engine, rpc, repo_root, apply=True, note=NOTE)
    assert f"{pid} WIFUSDT [open: skipped" in report and rpc.calls == []
    assert await _rows(engine, _AUDIT) == []


@pytest.mark.integration
@pytest.mark.parametrize(
    "reply,reason",
    [
        (meta(rent=None), "rent_unreadable"),
        (meta(delta=-(TICKET + FEES + RENT_PAID + 1)), "sol_delta_mismatch"),
        (None, "tx_not_found"),
    ],
)
async def test_a_refusal_writes_nothing_even_when_another_position_was_fixable(
    engine: AsyncEngine, repo_root: Path, reply: dict[str, Any] | None, reason: str
) -> None:
    good, good_sig = await _plant(engine)
    bad, bad_sig = await _plant(engine)
    _write_note(repo_root, good, bad)
    before = await _rows(engine, _POS)
    with pytest.raises(script.Refused) as refused:
        await _run(
            engine, FakeRpc({good_sig: meta(), bad_sig: reply}), repo_root, apply=True, note=NOTE
        )
    assert refused.value.reason == reason
    assert await _rows(engine, _POS) == before and await _rows(engine, _AUDIT) == []


@pytest.mark.integration
async def test_apply_without_a_covering_note_refuses_and_writes_nothing(
    engine: AsyncEngine, repo_root: Path
) -> None:
    _, sig = await _plant(engine)
    for note, reason in ((None, "note_required"), (NOTE, "note_does_not_mention_target")):
        with pytest.raises(script.Refused) as refused:
            await _run(engine, FakeRpc({sig: meta()}), repo_root, apply=True, note=note)
        assert refused.value.reason == reason
    assert await _rows(engine, _AUDIT) == []


def _row(**over: Any) -> dict[str, Any]:
    """A closed row whose columns are already right (pure ``plan_fix`` input)."""
    spent = TICKET + FEES
    pnl = Decimal(RECEIVED - spent) / Decimal(1_000_000_000)
    entry = {"filled_atoms": TOKENS, "sol_delta_lamports": -(spent + RENT_PAID),
             "sol_spent_lamports": spent, "ata_rent_lamports": RENT_PAID,
             "sol_spent_source": "signature_delta_minus_rent"}  # fmt: skip
    per_atom = str(Decimal(spent) / Decimal(1_000_000_000) / Decimal(TOKENS))
    row: dict[str, Any] = {
        "id": str(uuid.uuid4()), "status": "closed", "mint": MINT, "market_symbol": "WIFUSDT",
        "entry": entry, "params": {"ata_rent_lamports": RENT_PAID, "entry_sol_per_atom": per_atom},
        "sol_spent_lamports": spent, "ata_rent_lamports": RENT_PAID,
        "sol_received_lamports": RECEIVED, "pnl_sol": pnl, "r_multiple": pnl / RISK,
        "initial_risk_sol": RISK, "tx_signature": "sig-x", "wallet": WALLET,
        "entry_fill": {"sol_delta_lamports": -(spent + RENT_PAID)},
    }  # fmt: skip
    row.update(over)
    return row


@pytest.mark.unit
def test_a_fully_correct_row_is_already_correct() -> None:
    assert script.plan_fix(_row(), meta()).changed is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "where,key",
    [
        ("entry", "sol_spent_lamports"),
        ("entry", "ata_rent_lamports"),
        ("params", "ata_rent_lamports"),
        ("params", "entry_sol_per_atom"),
    ],  # fmt: skip
)
def test_stale_json_fields_are_not_already_correct(where: str, key: str) -> None:
    """Astra, diff review (reproduced): right columns, stale ``entry``/``params``."""
    row = _row()
    row[where] = {**row[where], key: "0" if key == "entry_sol_per_atom" else RENT_CONSTANT}
    assert script.plan_fix(row, meta()).changed is True


@pytest.mark.unit
def test_the_order_s_own_fill_must_agree_with_the_transaction() -> None:
    with pytest.raises(script.Refused) as refused:
        script.plan_fix(_row(entry_fill={"sol_delta_lamports": 1}), meta())
    assert refused.value.reason == "fill_mismatch"


@pytest.mark.integration
async def test_a_failure_after_a_write_rolls_the_whole_batch_back(
    engine: AsyncEngine, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, first_sig = await _plant(engine)
    second, second_sig = await _plant(engine)
    _write_note(repo_root, first, second)
    before = await _rows(engine, _POS)
    real, calls = script._write, list[str]()  # pyright: ignore[reportPrivateUsage]

    async def flaky(session: Any, fix: Any, proof: Any, actor: str) -> None:
        calls.append(fix.position_id)
        if len(calls) == 2:
            raise script.Refused("position_moved", "simulated after one write")
        await real(session, fix, proof, actor)

    monkeypatch.setattr(script, "_write", flaky)
    rpc = FakeRpc({first_sig: meta(), second_sig: meta()})
    with pytest.raises(script.Refused):
        await _run(engine, rpc, repo_root, apply=True, note=NOTE)
    assert len(calls) == 2, "the first position was written before the failure"
    assert await _rows(engine, _POS) == before and await _rows(engine, _AUDIT) == []


@pytest.mark.unit
@pytest.mark.parametrize("column", ["pnl_sol", "r_multiple"])
def test_a_null_accounting_column_is_a_named_refusal(column: str) -> None:
    with pytest.raises(script.Refused) as refused:
        script.plan_fix(_row(**{column: None}), meta())
    assert refused.value.reason == "position_not_closable"


class BrokenRpc(FakeRpc):
    def get_transaction(self, signature: str, *, commitment: str = "confirmed") -> Any:
        raise ConnectionError("rpc down")


@pytest.mark.integration
async def test_an_rpc_failure_is_a_named_refusal_and_writes_nothing(
    engine: AsyncEngine, repo_root: Path
) -> None:
    pid, _ = await _plant(engine)
    _write_note(repo_root, pid)
    with pytest.raises(script.Refused) as refused:
        await _run(engine, BrokenRpc({}), repo_root, apply=True, note=NOTE)
    assert refused.value.reason == "rpc_failed" and "ConnectionError" in str(refused.value)
    assert await _rows(engine, _AUDIT) == []


@pytest.mark.integration
async def test_only_closed_rows_are_locked_while_the_chain_is_read(
    engine: AsyncEngine, repo_root: Path
) -> None:
    """Guardian F1: an OPEN position must never be row-locked by this script
    (even in a dry run) — the executor marks and sells it every tick."""
    opened, _ = await _plant(engine, status="open")
    closed, sig = await _plant(engine)
    lock = text("SELECT id FROM spot_positions WHERE id = :id FOR UPDATE NOWAIT")
    async with AsyncSession(engine) as session, session.begin():
        report = await script.run(session, FakeRpc({sig: meta()}), apply=False, note=None,
                                  actor="Everton", repo_root=repo_root)  # fmt: skip
        assert f"{opened} WIFUSDT [open: skipped" in report
        async with engine.connect() as other:  # a second connection, the executor's seat
            assert (await other.execute(lock, {"id": opened})).scalar() is not None
            await other.rollback()
            with pytest.raises(Exception, match="could not obtain lock|LockNotAvailable"):
                await other.execute(lock, {"id": closed})
