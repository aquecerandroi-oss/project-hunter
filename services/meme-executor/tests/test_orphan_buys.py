"""T4.96b — an ``admitted`` buy that never got a signature stops holding the
small-test scope forever. Against a real Postgres (testcontainers).

The executor writes the ``admitted`` row, then the submitter takes the signing
lock (``signing_at``), signs, **records the signature** (``status =
'simulated'``) and only then sends (``hunter_core.execution.meme.submit``). A
row still ``admitted`` with no signature therefore never left the process —
there is no signature to look up on chain, and none can appear once the row
is refused: the journal no longer locks nor records a signature on a row that
is not ``admitted``. Interruptions covered: a restart between the commit and
``begin_signing`` (``signing_at`` NULL) and a journal failure that left the
lock behind (``signing_at`` set). The step never raises (it rides the
reconcile loop, next to the exits' settlement).
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.execution.meme.journal import SigningLocked
from hunter_meme_executor.orphan_buys import (
    ADMITTED_ORPHAN_EXPIRED,
    ORPHAN_MARGIN_S,
    expire_orphan_buys,
)
from hunter_meme_executor.repo import order_key
from hunter_meme_executor.scope import legacy_extra_sol, read_scope_use

from . import test_live_persistence as _live
from .test_live_persistence import (
    Harness,
    _context,
    _plant_proposal,
    _rows,
    _signer,
    _small_test,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

harness = _live.harness  # the Postgres rig and its per-test cleanup, shared as is


async def _plant_order(
    engine: AsyncEngine,
    *,
    admitted_at: datetime,
    signing_at: datetime | None = None,
    side: str = "buy",
    status: str = "admitted",
    signature: str | None = None,
) -> str:
    proposal_id = await _plant_proposal(engine, decided_at=admitted_at)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, intent, "
                "  status, tx_signature, signatures, signing_at, received_at, admitted_at) "
                "VALUES (:id, :p, :side, :key, CAST(:intent AS jsonb), :status, :sig, "
                "  CAST(:sigs AS jsonb), :signing, :at, :at)"
            ),
            {
                "id": str(uuid4()),
                "p": proposal_id,
                "side": side,
                "key": order_key(proposal_id, side=side),
                "intent": json.dumps({"scope_reserve_sol": "0.03"}),
                "status": status,
                "sig": signature,
                "sigs": json.dumps([] if signature is None else [signature]),
                "signing": signing_at,
                "at": admitted_at,
            },
        )
    return order_key(proposal_id, side=side)


async def _status(engine: AsyncEngine, key: str) -> tuple[str, str | None]:
    row = (
        await _rows(
            engine, "SELECT status, reason FROM meme_live_orders WHERE client_order_id = :k", k=key
        )
    )[0]
    return row["status"], row["reason"]


def _unsigned_bound_s(h: Harness) -> float:
    return h.ctx.config.limits.reservation_ttl_s + ORPHAN_MARGIN_S


def _signing_bound_s(h: Harness) -> float:
    return _unsigned_bound_s(h) + h.ctx.config.confirm_timeout_s


async def test_a_restart_between_the_commit_and_begin_signing_frees_the_scope(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test("0.05"))
    now = datetime.now(UTC)
    old = await _plant_order(
        db_engine, admitted_at=now - timedelta(seconds=_unsigned_bound_s(armed) + 1)
    )
    fresh = await _plant_order(db_engine, admitted_at=now - timedelta(seconds=10))
    small, extra = _small_test("0.05"), legacy_extra_sol(armed.ctx.config)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        before = await read_scope_use(
            session, small, requested_sol=Decimal("0"), legacy_extra=extra
        )
    assert before.trades_done == 2 and before.used_sol == Decimal("0.06")

    assert await expire_orphan_buys(armed.ctx, now=now) == [old]
    assert await _status(db_engine, old) == ("refused", ADMITTED_ORPHAN_EXPIRED)
    assert await _status(db_engine, fresh) == ("admitted", None), "a young row may still sign"
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        after = await read_scope_use(session, small, requested_sol=Decimal("0"), legacy_extra=extra)
    assert after.trades_done == 1 and after.used_sol == Decimal("0.03")
    assert armed.ctx.state.refusals.get(ADMITTED_ORPHAN_EXPIRED) == 1
    assert await expire_orphan_buys(armed.ctx, now=now) == [], "idempotent"


async def test_a_lock_left_by_a_journal_failure_waits_for_the_longer_bound(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """``signing_at`` set, no signature: the submitter held the lock and never
    recorded a signature (a journal exception whose ``release_signing`` failed
    too). Refused only after TTL + the confirmation window + the margin, counted
    from ``signing_at`` — never while a slow submit could still be running."""
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test("0.05"))
    now = datetime.now(UTC)
    admitted = now - timedelta(seconds=_signing_bound_s(armed) + 60)
    recent_lock = await _plant_order(
        db_engine,
        admitted_at=admitted,
        signing_at=now - timedelta(seconds=_unsigned_bound_s(armed) + 1),
    )
    old_lock = await _plant_order(
        db_engine,
        admitted_at=admitted,
        signing_at=now - timedelta(seconds=_signing_bound_s(armed) + 1),
    )
    assert await expire_orphan_buys(armed.ctx, now=now) == [old_lock]
    assert await _status(db_engine, recent_lock) == ("admitted", None)
    assert await _status(db_engine, old_lock) == ("refused", ADMITTED_ORPHAN_EXPIRED)


async def test_rows_with_a_signature_sells_and_settled_rows_are_never_touched(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test("0.05"))
    now = datetime.now(UTC)
    ancient = now - timedelta(days=2)
    signed = await _plant_order(
        db_engine, admitted_at=ancient, signing_at=ancient, status="simulated", signature="s1"
    )
    sell = await _plant_order(db_engine, admitted_at=ancient, side="sell")
    # Each signature guard on its own (the journal writes both together; a row
    # carrying either one may have left the process, so it is never refused).
    only_tx = await _plant_order(db_engine, admitted_at=ancient, signature="s2")
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE meme_live_orders SET signatures = '[]'::jsonb WHERE client_order_id = :k"),
            {"k": only_tx},
        )
    only_list = await _plant_order(db_engine, admitted_at=ancient)
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_orders SET signatures = '[\"s3\"]'::jsonb "
                "WHERE client_order_id = :k"
            ),
            {"k": only_list},
        )
    assert await expire_orphan_buys(armed.ctx, now=now) == []
    assert await _status(db_engine, only_tx) == ("admitted", None)
    assert await _status(db_engine, only_list) == ("admitted", None)
    assert await _status(db_engine, signed) == ("simulated", None), "settled by its signature"
    assert await _status(db_engine, sell) == ("admitted", None)


async def test_a_refused_orphan_can_never_be_locked_nor_signed_afterwards(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The structural half: even a submitter that woke up late cannot take the
    lock of a refused row, nor record a signature on it (so it never sends)."""
    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test("0.05"))
    now = datetime.now(UTC)
    unsigned = await _plant_order(
        db_engine, admitted_at=now - timedelta(seconds=_unsigned_bound_s(armed) + 1)
    )
    locked = await _plant_order(
        db_engine,
        admitted_at=now - timedelta(seconds=_signing_bound_s(armed) + 60),
        signing_at=now - timedelta(seconds=_signing_bound_s(armed) + 1),
    )
    assert sorted(await expire_orphan_buys(armed.ctx, now=now)) == sorted([unsigned, locked])
    journal = armed.ctx.journal
    with pytest.raises(SigningLocked):
        await asyncio.to_thread(journal.begin_signing, unsigned)
    with pytest.raises(SigningLocked):
        await asyncio.to_thread(journal.record_signature, locked, "late", last_valid_block_height=1)
    assert await _status(db_engine, unsigned) == ("refused", ADMITTED_ORPHAN_EXPIRED)
    assert await _status(db_engine, locked) == ("refused", ADMITTED_ORPHAN_EXPIRED)
    rows = await _rows(
        db_engine, "SELECT signatures FROM meme_live_orders WHERE client_order_id = :k", k=locked
    )
    assert rows[0]["signatures"] == []


async def test_the_step_never_raises(harness: Harness) -> None:
    class Broken:
        def __call__(self, *_a: Any, **_k: Any) -> Any:
            raise RuntimeError("database down")

    harness.ctx.session_factory = Broken()  # type: ignore[assignment]
    assert await expire_orphan_buys(harness.ctx, now=datetime.now(UTC)) == []


async def test_a_journal_exception_before_the_signature_sends_nothing_and_expires(
    harness: Harness, db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The real submitter against the real journal whose signature write fails:
    the exception leaves ``submit`` (the lock released), nothing reaches the RPC,
    the row stays ``admitted`` without a signature — and once past the bound the
    step refuses it, freeing the scope."""
    from hunter_core.execution.meme.submit import ApprovedSubmission, MemeSubmitter, SubmitPolicy
    from hunter_meme_executor.build import decode_fills
    from hunter_meme_executor.journal_db import PostgresOrderJournal

    class FailingJournal(PostgresOrderJournal):
        def record_signature(self, *_a: Any, **_k: Any) -> None:
            raise ConnectionError("journal down")

    armed = _context(db_session_factory, _signer(), harness.redis, auto=_small_test("0.05"))
    now = datetime.now(UTC)
    key = await _plant_order(db_engine, admitted_at=now)
    submitter = MemeSubmitter(
        rpc=armed.rpc,
        signer=armed.ctx.signer,
        journal=FailingJournal(db_session_factory, asyncio.get_running_loop()),
        verify=lambda _raw: None,
        decode_fill=decode_fills,
        policy=SubmitPolicy(allow_send=True, cluster="devnet"),
        now=lambda: datetime.now(UTC),
    )
    approval = ApprovedSubmission(key, now + timedelta(seconds=5), b"message", 100)
    with pytest.raises(ConnectionError):
        await asyncio.to_thread(submitter.submit, approval)
    assert armed.rpc.sent == [], "the send comes after the signature is recorded"
    rows = await _rows(
        db_engine,
        "SELECT status, tx_signature, signing_at FROM meme_live_orders WHERE client_order_id = :k",
        k=key,
    )
    assert rows[0]["status"] == "admitted" and rows[0]["tx_signature"] is None
    assert rows[0]["signing_at"] is None, "the lock was released on the way out"
    later = now + timedelta(seconds=_unsigned_bound_s(armed) + 1)
    assert await expire_orphan_buys(armed.ctx, now=later) == [key]


async def test_the_reconcile_tick_runs_the_step_last(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the settlements (the sells' confirmation and repair), so the step
    can never delay an exit; a raise inside it is impossible (``never raises``)."""
    import hunter_meme_executor.main as main

    calls: list[str] = []

    async def spot(_ctx: Any) -> None:
        calls.append("spot")

    async def repair(_ctx: Any) -> None:
        calls.append("repair_sells")

    async def orphans(_ctx: Any, *, now: datetime) -> list[str]:
        calls.append("orphans")
        return []

    async def fees(_ctx: Any, *, now: datetime) -> list[str]:
        calls.append("failed_fees")
        return []

    async def none(_session: Any) -> list[str]:
        return []

    monkeypatch.setattr(main, "spot_reconcile_once", spot)
    monkeypatch.setattr(main, "unconfirmed_orders", none)
    monkeypatch.setattr(main, "repair_confirmed_sells", repair)
    monkeypatch.setattr(main, "expire_orphan_buys", orphans)
    monkeypatch.setattr(main, "recover_failed_fees", fees)
    await main.reconcile_once(harness.ctx)
    assert calls == ["spot", "repair_sells", "orphans", "failed_fees"]


@pytest.mark.parametrize("lane", ["entries", "launch"])
async def test_a_late_submitter_on_a_refused_row_stops_its_lane_quietly(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, lane: str
) -> None:
    """Astra, T4.96b diff review (must-fix): the journal refusing to record a
    signature (the row left ``admitted`` meanwhile) must stop *this* buy — never
    escape into ``forever`` and cancel the TaskGroup with the exits in it. The
    row keeps its terminal state (no ``_fail`` rewrites it)."""
    from types import SimpleNamespace

    import hunter_meme_executor.entry_submit as entry_submit
    import hunter_meme_executor.launch_submit as launch_submit
    from hunter_meme_executor.launch_repo import LaunchCandidate
    from hunter_meme_executor.repo import Candidate

    class LateSubmitter:
        def __init__(self, **_k: Any) -> None:
            pass

        def submit(self, _approval: Any) -> Any:
            raise SigningLocked("k: not admitted any more, nothing sent")

    module = entry_submit if lane == "entries" else launch_submit
    monkeypatch.setattr(module, "MemeSubmitter", LateSubmitter)
    now = datetime.now(UTC)

    def verify(_raw: bytes) -> None:
        return None

    built: Any = SimpleNamespace(verify=verify, message=b"m", last_valid_block_height=1)
    candidate = Candidate(
        id="p",
        mint="m",
        decision={},
        decided_at=now,
        decided_by="x",
        status="approved",
        proposed_at=now,
    )
    if lane == "entries":
        await entry_submit.submit_entry_buy(harness.ctx, candidate, built, "k", "o", now)
    else:
        launch = LaunchCandidate(
            candidate=candidate,
            suggested={},
            quote={},
            reasons=[],
            rule_set_params={},
            rule_set_version="1",
        )
        await launch_submit.submit_launch_buy(
            harness.ctx,
            launch,
            built,
            key="k",
            order_id="o",
            curve=cast(Any, None),
            age_s=0.1,
        )
    assert harness.ctx.state.last_refusal == "signing_refused:not_admitted"
    assert harness.ctx.state.entries_confirmed == 0
