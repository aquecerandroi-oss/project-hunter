"""T4.96b fix — the network fee of a buy that landed **with an error** reaches the
row's ``fill`` on the real flow, and so the small-test counter (and T4.59's day
fees). Against a real Postgres (testcontainers).

The bug (independent guardian review of T4.96b): ``submit._fail`` records
``FAILED`` with ``fill = None``; the journal writes it as JSON ``null`` (not SQL
NULL), and the fee write required ``fill IS NULL`` — so it never touched a row
(VPS 27/09: 13 failed buys and 9 sells since 17/09, none with its fee). Now the
write accepts both nulls, and the reconcile tick re-reads the fee of any failed
buy still without one (the first read may have returned nothing, timed out, or
the process died between ``FAILED`` and the write) — bounded, backed off, never
raising.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import SubmitResult
from hunter_meme_executor.failed_fees import (
    FAILED_FEE_BATCH,
    FAILED_FEE_RETRY_S,
    recover_failed_fees,
)
from hunter_meme_executor.repo import order_key
from hunter_meme_executor.scope import legacy_extra_sol, read_scope_use
from hunter_meme_executor.send_path import record_failed_onchain_fee

from . import test_live_persistence as _live
from .test_live_persistence import Harness, _context, _plant_proposal, _rows, _signer, _small_test

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

harness = _live.harness  # the Postgres rig and its per-test cleanup, shared as is

REASON = "onchain_error:{'InstructionError': [2, {'Custom': 6002}]}"
FEE_LAMPORTS = 1_234_567


async def _failed_buy_on_the_real_flow(
    armed: Harness, engine: AsyncEngine, *, signature: str, side: str = "buy"
) -> str:
    """``admitted`` → the journal records the signature → the journal records
    ``FAILED`` with no fill, exactly as ``submit._fail`` does."""
    proposal_id = await _plant_proposal(engine, decided_at=datetime.now(UTC))
    key = order_key(proposal_id, side=side)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, intent, "
                "  status, admitted_at) "
                "VALUES (:id, :p, :side, :key, CAST(:intent AS jsonb), 'admitted', now())"
            ),
            {
                "id": str(uuid4()),
                "p": proposal_id,
                "side": side,
                "key": key,
                "intent": json.dumps({"scope_reserve_sol": "0.03"}),
            },
        )
    journal = armed.ctx.journal
    await asyncio.to_thread(journal.record_signature, key, signature, last_valid_block_height=1)
    await asyncio.to_thread(journal.record_state, key, SubmitState.FAILED, REASON, None)
    return key


def _landed_with_error(armed: Harness) -> list[str]:
    """The fake RPC answers ``getTransaction`` with a landed, errored transaction."""
    tx = json.loads(json.dumps(armed.rpc.transaction))
    tx["meta"]["err"] = {"InstructionError": [2, {"Custom": 6002}]}
    tx["meta"]["fee"] = FEE_LAMPORTS
    armed.rpc.transaction = tx
    fetched: list[str] = []
    original = armed.rpc.get_transaction

    def counting(signature: str, **kw: Any) -> Any:
        fetched.append(signature)
        return original(signature, **kw)

    armed.rpc.get_transaction = counting  # type: ignore[method-assign]
    return fetched


async def _fill_of(engine: AsyncEngine, key: str) -> Any:
    rows = await _rows(
        engine,
        "SELECT fill, jsonb_typeof(fill) AS kind FROM meme_live_orders WHERE client_order_id = :k",
        k=key,
    )
    return rows[0]


async def _used(armed: Harness, factory: async_sessionmaker[AsyncSession]) -> Any:
    async with role_session(factory, db_role="hunter_worker") as session:
        return await read_scope_use(
            session,
            _small_test("5"),
            requested_sol=Decimal(0),
            legacy_extra=legacy_extra_sol(armed.ctx.config),
        )


async def test_the_real_flow_writes_the_fee_and_the_scope_counts_it(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test("5"))
    key = await _failed_buy_on_the_real_flow(armed, db_engine, signature="sig-f1")
    assert (await _fill_of(db_engine, key))["kind"] == "null", "JSON null, not SQL NULL"
    # Astra, fee-fix review: until the fee is known the counter charges the
    # conservative reserve (network + rent + the priority cap), never zero — so
    # several unread failures can't let the scope pass its cap.
    pending = await _used(armed, db_session_factory)
    assert pending.used_sol == legacy_extra_sol(armed.ctx.config) and pending.trades_done == 0
    fetched = _landed_with_error(armed)
    result = SubmitResult(key, SubmitState.FAILED, REASON, "sig-f1", None)
    await record_failed_onchain_fee(armed.ctx, key, result)
    assert fetched == ["sig-f1"]
    row = await _fill_of(db_engine, key)
    assert row["kind"] == "object" and row["fill"]["network_fee_lamports"] == FEE_LAMPORTS
    use = await _used(armed, db_session_factory)
    assert use.trades_done == 0, "a failed buy takes no slot"
    assert use.used_sol == Decimal(FEE_LAMPORTS) / Decimal(10**9)


async def test_the_reconcile_recovers_a_fee_the_first_write_never_made(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The process died between ``FAILED`` and the fee write: the next reconcile
    tick reads the transaction and writes the fee; later ticks read nothing."""
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test("5"))
    key = await _failed_buy_on_the_real_flow(armed, db_engine, signature="sig-f2")
    sell = await _failed_buy_on_the_real_flow(armed, db_engine, signature="sig-s2", side="sell")
    fetched = _landed_with_error(armed)
    now = datetime.now(UTC) + timedelta(seconds=FAILED_FEE_RETRY_S + 1)
    assert await recover_failed_fees(armed.ctx, now=now) == [key]
    assert fetched == ["sig-f2"], "buys only; the sell is not this step's"
    assert (await _fill_of(db_engine, key))["fill"]["network_fee_lamports"] == FEE_LAMPORTS
    assert (await _fill_of(db_engine, sell))["kind"] == "null"
    later = now + timedelta(seconds=FAILED_FEE_RETRY_S + 1)
    assert await recover_failed_fees(armed.ctx, now=later) == []
    assert fetched == ["sig-f2"], "a written fee is never read again"
    assert (await _used(armed, db_session_factory)).used_sol == Decimal("0.001234567")


async def test_an_unanswered_read_is_retried_only_after_the_backoff(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test("5"))
    key = await _failed_buy_on_the_real_flow(armed, db_engine, signature="sig-f3")
    calls: list[str] = []

    def nothing(signature: str, **_kw: Any) -> None:
        calls.append(signature)

    real = armed.rpc.get_transaction
    armed.rpc.get_transaction = nothing  # type: ignore[method-assign]
    first = datetime.now(UTC) + timedelta(seconds=FAILED_FEE_RETRY_S + 1)
    assert await recover_failed_fees(armed.ctx, now=first) == []
    assert calls == ["sig-f3"]
    assert await recover_failed_fees(armed.ctx, now=first + timedelta(seconds=5)) == []
    assert calls == ["sig-f3"], "backed off: no read every tick"
    armed.rpc.get_transaction = real  # type: ignore[method-assign]
    fetched = _landed_with_error(armed)
    again = first + timedelta(seconds=FAILED_FEE_RETRY_S + 1)
    assert await recover_failed_fees(armed.ctx, now=again) == [key]
    assert fetched == ["sig-f3"]


async def test_the_batch_is_bounded(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test("5"))
    for i in range(FAILED_FEE_BATCH + 2):
        await _failed_buy_on_the_real_flow(armed, db_engine, signature=f"sig-b{i}")
    fetched = _landed_with_error(armed)
    now = datetime.now(UTC) + timedelta(seconds=FAILED_FEE_RETRY_S + 1)
    assert len(await recover_failed_fees(armed.ctx, now=now)) == FAILED_FEE_BATCH
    assert len(fetched) == FAILED_FEE_BATCH
    assert len(await recover_failed_fees(armed.ctx, now=now)) == 2


async def test_the_step_never_raises(harness: Harness) -> None:
    class Broken:
        def __call__(self, *_a: Any, **_k: Any) -> Any:
            raise RuntimeError("database down")

    harness.ctx.session_factory = Broken()  # type: ignore[assignment]
    assert await recover_failed_fees(harness.ctx, now=datetime.now(UTC)) == []
