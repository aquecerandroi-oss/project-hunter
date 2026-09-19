"""T4.63 against a real Postgres at ``head`` (testcontainers; reuses
``test_live_persistence.py``'s harness — the chain is the same fake fed by
T4.8's recorded mainnet fixtures): an open real position plus **one** WS
drawdown notification produces exactly one confirmed sell order row with
``intent.exit_reason = 'trailing'``, the position closed with that reason, the
heartbeat's ``event_exits_*`` counters and the ``event_to_sell_submit_s``
latency — and the tick that runs right after finds nothing left to sell. A
creator sell in a ``logsNotification`` stamps ``creator_sold_seen_at`` on the
row and sells ``creator_dump`` with the panic tolerance.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.pdas import bonding_curve_address
from hunter_exchanges.pumpfun.rpc_ws_models import AccountNotification, LogsNotification
from hunter_exchanges.pumpfun.solana_codec import pubkey_bytes
from hunter_exchanges.pumpfun.trade_event import trade_events_from_logs
from hunter_meme_executor.entries import entries_once
from hunter_meme_executor.event_exits import EventExitsRuntime, handle_notification, sync_watch
from hunter_meme_executor.event_exits_config import EventExitsConfig
from hunter_meme_executor.event_exits_eval import creator_sold_fraction
from hunter_meme_executor.exits import exits_once
from hunter_meme_executor.heartbeat import heartbeat_fields
from hunter_meme_executor.repo import open_positions

from .test_event_exits import ACCOUNT_ID, LOGS_ID, LOGS_LINES, FakeWs, _encode_curve
from .test_live_persistence import (
    CREATOR,
    DEV_BUY_TOKENS,
    MINT,
    FakeRedis,
    Harness,
    _context,
    _fixture,
    _full_token_context,
    _plant_proposal,
    _rows,
    _signer,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration]

PDA = bonding_curve_address(MINT)


@pytest_asyncio.fixture
async def live_harness(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Harness]:
    """``test_live_persistence.harness``, rebuilt here (a fixture imported under
    the name a test parameter also uses is a ruff F811): an empty ledger, an
    unlatched switch, the entry loop's token context faked — the event runtime's
    own reads (``event_exits_watch``) hit the real ``meme_tokens`` row."""
    import hunter_meme_executor.admission_context as admission_context_module
    import hunter_meme_executor.exits as exits_module

    async def token_context(
        _session: AsyncSession, _mint: str, *, now: datetime | None = None
    ) -> Any:
        return _full_token_context(now or datetime.now(UTC))

    monkeypatch.setattr(admission_context_module, "token_context", token_context)
    monkeypatch.setattr(exits_module, "token_context", token_context)
    async with db_engine.begin() as connection:
        await connection.execute(text("DELETE FROM meme_live_positions"))
        await connection.execute(text("DELETE FROM meme_live_orders"))
        await connection.execute(
            text(
                "DELETE FROM meme_proposals WHERE mode = 'live' OR (status = 'proposed' AND mint = :mint)"
            ),
            {"mint": MINT},
        )
        await connection.execute(
            text("DELETE FROM meme_risk_snapshots WHERE mint = :mint"), {"mint": MINT}
        )
        await connection.execute(
            text(
                "UPDATE meme_live_kill_switch SET state = 'ACTIVE', reason = NULL, latched_at = NULL, "
                "released_at = NULL, released_by = NULL WHERE scope = 'wallet'"
            )
        )
    yield _context(db_session_factory, _signer(), FakeRedis())


def _account_frame(virtual_sol: int, *, slot: int, at: datetime) -> AccountNotification:
    """The harness's own curve (``FakeChain.curve``: 36,4 SOL virtual) after a
    move to ``virtual_sol`` — the same bytes ``accountSubscribe`` would carry."""
    return AccountNotification(
        subscription_id=ACCOUNT_ID,
        kind="account",
        slot=slot,
        data_base64=_encode_curve(
            virtual_sol=virtual_sol,
            virtual_token=900_000_000_000_000,
            real_sol=max(0, virtual_sol - 30_000_000_000),
            real_token=793_100_000_000_000 * 8 // 10,
        ),
        encoding="base64",
        owner=PUMP_PROGRAM_ID,
        lamports=0,
        received_at=at,
    )


def _creator_sell_frame(*, at: datetime) -> LogsNotification:
    """The fixture's real creator sell (``t452b`` line 4), re-addressed to the
    harness's mint and creator: the ``TradeEvent`` layout puts ``mint`` at
    bytes 8..40 and ``user`` at 57..89 (``trade_event.decode_trade_event``);
    everything else — amounts, reserves, fees — is the captured event's."""
    frame = json.loads(LOGS_LINES[4])["params"]["result"]
    logs: list[str] = []
    for line in frame["value"]["logs"]:
        if not line.startswith("Program data: "):
            logs.append(line)
            continue
        raw = bytearray(base64.b64decode(line[len("Program data: ") :]))
        raw[8:40] = pubkey_bytes(MINT)
        raw[57:89] = pubkey_bytes(CREATOR)
        logs.append("Program data: " + base64.b64encode(bytes(raw)).decode("ascii"))
    events = trade_events_from_logs(logs)
    assert len(events) == 1 and events[0].mint == MINT and events[0].user == CREATOR
    assert events[0].is_buy is False
    return LogsNotification(
        subscription_id=LOGS_ID,
        kind="logs",
        slot=int(frame["context"]["slot"]),
        signature=str(frame["value"]["signature"]),
        err=None,
        logs=tuple(logs),
        received_at=at,
    )


async def _open_position(live: Harness, db_engine: AsyncEngine) -> str:
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(live.ctx)
    positions = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert len(positions) == 1 and positions[0]["status"] == "open"
    # The fixtures are real transactions dated 12/09 (entry and exit block times,
    # ``an_exit_is_after_the_entry``): the hold is widened so the ``time_stop``
    # (900 s) is not what fires — the frame under test is.
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE meme_live_positions SET params = params || '{\"max_hold_s\": 100000000}'::jsonb "
                "WHERE proposal_id = :p"
            ),
            {"p": proposal_id},
        )
    return proposal_id


def _runtime(live: Harness) -> tuple[Harness, EventExitsRuntime, FakeWs]:
    ws = FakeWs()
    config = EventExitsConfig(enabled=True, ws_url="ws://x")
    live.ctx.config = replace(live.ctx.config, event_exits=config)  # the flag on
    return live, EventExitsRuntime(ctx=live.ctx, ws=ws, config=config), ws


async def _sells(db_engine: AsyncEngine, proposal_id: str) -> list[dict[str, Any]]:
    return await _rows(
        db_engine,
        "SELECT * FROM meme_live_orders WHERE proposal_id = :p AND side = 'sell' ORDER BY attempt",
        p=proposal_id,
    )


async def test_one_drawdown_notification_sells_once_and_the_tick_finds_nothing_left(
    live_harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await _open_position(live_harness, db_engine)
    # "Restart": a fresh context over the same rows, the chain holding the tokens.
    restarted = _context(db_session_factory, _signer(), live_harness.redis)
    restarted.chain.tokens_on_chain = 10**9
    restarted.rpc.transaction = json.loads(json.dumps(_fixture("rpc_tx_probe_raw.json")["result"]))
    _, rt, ws = _runtime(restarted)
    await sync_watch(rt, now=datetime.now(UTC))
    assert ws.subscribed == [("logs", PDA), ("account", PDA)]
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        position = [p for p in await open_positions(session) if p.proposal_id == proposal_id][0]
    w = rt.watched[position.id]
    assert w.creator == CREATOR

    # The curve as the buy saw it (36,4 SOL virtual): the mark and the peak land on the row.
    t0 = datetime.now(UTC)
    await handle_notification(rt, _account_frame(36_400_000_000, slot=10, at=t0), now=t0)
    assert w.selling is None and rt.stats.triggered_total == 0
    peak = w.high_water
    marked = await _rows(
        db_engine,
        "SELECT mark_sol, high_water_sol, mark_source FROM meme_live_positions WHERE id = :id",
        id=position.id,
    )
    assert marked[0]["mark_source"] == "solana_rpc" and Decimal(marked[0]["high_water_sol"]) == peak

    # One frame, −35 % (the proposal's trailing is 30 %): CITIZEN's drain, seen at once.
    t1 = datetime.now(UTC)
    await handle_notification(rt, _account_frame(23_000_000_000, slot=11, at=t1), now=t1)
    selling = rt.watched[position.id].selling  # re-read: the frame above set it
    assert rt.stats.triggered_total == 1 and selling is not None
    await selling

    sells = await _sells(db_engine, proposal_id)
    assert len(sells) == 1 and sells[0]["status"] == "confirmed", sells
    assert sells[0]["client_order_id"] == f"meme:{proposal_id}:exit:1"
    assert sells[0]["intent"]["exit_reason"] == "trailing"
    assert sells[0]["intent"]["max_slippage_bps"] == 500, (
        "a trailing exit uses the normal tolerance"
    )
    assert sells[0]["submitted_at"] >= t1
    closed = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE id = :id", id=position.id
    )
    assert closed[0]["status"] == "closed" and closed[0]["exit"]["reason"] == "trailing"
    assert Decimal(closed[0]["high_water_sol"]) == peak, "the drawdown frame never lowered the peak"
    assert len(restarted.rpc.sent) == 1

    hb = await heartbeat_fields(restarted.ctx)
    assert hb["event_exits_enabled"] == "true"
    assert hb["event_exits_triggered_total"] == "1"
    assert hb["event_exits_updates_60s"] == "2"
    assert hb["event_exits_subscriptions"] == "2"
    assert hb["event_exits_marks_written"] == "2"
    latency = float(hb["event_to_sell_submit_s_p50"])
    assert (
        0 <= latency < 10 and hb["event_to_sell_submit_s_p95"] == hb["event_to_sell_submit_s_p50"]
    )

    # The tick right after: the row is closed, nothing to sell, nothing sent twice.
    await exits_once(restarted.ctx)
    assert len(await _sells(db_engine, proposal_id)) == 1
    assert len(restarted.rpc.sent) == 1
    # And the sync unsubscribes the closed position.
    await sync_watch(rt, now=datetime.now(UTC))
    assert rt.watched == {} and sorted(ws.unsubscribed) == [LOGS_ID, ACCOUNT_ID]
    assert (await heartbeat_fields(restarted.ctx))["event_exits_subscriptions"] == "0"


async def test_a_creator_sell_in_the_trade_event_stamps_the_row_and_sells_creator_dump(
    live_harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    proposal_id = await _open_position(live_harness, db_engine)
    restarted = _context(db_session_factory, _signer(), live_harness.redis)
    restarted.chain.tokens_on_chain = 10**9
    restarted.rpc.transaction = json.loads(json.dumps(_fixture("rpc_tx_probe_raw.json")["result"]))
    _, rt, _ws = _runtime(restarted)
    await sync_watch(rt, now=datetime.now(UTC))
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        position = [p for p in await open_positions(session) if p.proposal_id == proposal_id][0]
    assert position.creator_sold_seen_at is None
    w = rt.watched[position.id]
    # The denominator of the stamped fraction (``0048``). ``meme_tokens`` is shared
    # across this package's tests and the column is write-once (a trigger refuses
    # any change), so it is handed to the watch in memory here rather than recorded
    # on the row — ``test_live_persistence.test_token_context_reads_the_creators_recorded_allocation``
    # is the proof that ``token_context`` reads it from the real row, and it needs
    # the row still unrecorded when it starts.
    assert w.creator_initial_tokens is None
    w.creator_initial_tokens = DEV_BUY_TOKENS

    t0 = datetime.now(UTC)
    await handle_notification(rt, _creator_sell_frame(at=t0), now=t0)
    assert rt.stats.creator_sells_seen_total == 1 and w.creator_sold is True
    assert w.selling is not None
    await w.selling

    sells = await _sells(db_engine, proposal_id)
    assert len(sells) == 1 and sells[0]["status"] == "confirmed", sells
    assert sells[0]["intent"]["exit_reason"] == "creator_dump"
    assert sells[0]["intent"]["max_slippage_bps"] == 1500, (
        "a creator dump sells with the panic tolerance"
    )
    closed = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE id = :id", id=position.id
    )
    assert closed[0]["status"] == "closed" and closed[0]["exit"]["reason"] == "creator_dump"
    assert closed[0]["creator_sold_seen_at"] is not None, "the evidence stays on the row"
    assert closed[0]["creator_sold_seen_at"] >= t0
    sold = trade_events_from_logs(_creator_sell_frame(at=t0).logs)[0].token_amount
    fraction = Decimal(closed[0]["creator_sold_fraction"])
    assert fraction == creator_sold_fraction(sold, DEV_BUY_TOKENS)
    assert Decimal("0.11") < fraction < Decimal("0.12"), "sold ÷ allocation, measured"
    assert closed[0]["creator_balance_reason"] is None
    assert len(restarted.rpc.sent) == 1
    await exits_once(restarted.ctx)
    assert len(await _sells(db_engine, proposal_id)) == 1


async def test_a_watched_position_survives_a_restart_of_the_runtime_with_its_peak(
    live_harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The peak lives on the row (``high_water_sol``): a new runtime over the same
    rows measures the trailing stop from it, never from zero."""
    proposal_id = await _open_position(live_harness, db_engine)
    restarted = _context(db_session_factory, _signer(), live_harness.redis)
    _, rt, _ws = _runtime(restarted)
    await sync_watch(rt, now=datetime.now(UTC))
    t0 = datetime.now(UTC)
    await handle_notification(rt, _account_frame(40_000_000_000, slot=10, at=t0), now=t0)
    peak = next(iter(rt.watched.values())).high_water
    assert peak > 0
    again = _context(db_session_factory, _signer(), live_harness.redis)
    _, rt2, _ws2 = _runtime(again)
    await sync_watch(rt2, now=datetime.now(UTC))
    assert next(iter(rt2.watched.values())).high_water == peak
    async with db_engine.begin() as connection:  # closed as the ledger would close it
        await connection.execute(
            text(
                "UPDATE meme_live_positions SET status = 'closed', exit_at = now(), "
                '  exit = \'{"reason": "test"}\'::jsonb, pnl_sol = 0, r_multiple = 0 '
                "WHERE proposal_id = :p"
            ),
            {"p": proposal_id},
        )
    await sync_watch(rt2, now=datetime.now(UTC))
    assert rt2.watched == {}
    assert rt2.stats.subscriptions == 0
