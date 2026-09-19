"""T4.67b against a real Postgres at ``head`` (testcontainers; the chain is the
``test_live_persistence`` fake fed by T4.8's recorded mainnet fixtures): a
``launch_v0/1`` proposal (``research_only``, born approved by ``rules``,
``mode = 'paper'``, ``reasons[0].series = 'meme_launch_lane_v1'``) with
``MEME_LAUNCH_LANE=on`` becomes **one** confirmed buy order with
``admission.profile = 'launch'`` (the skipped checks recorded by name), the
proposal claimed ``mode = 'live'`` in the same transaction, and an open
position with ``params.lane = 'launch'``; a second pass writes nothing; a
replayed third-party sell (``t452b`` line 3 re-addressed to the mint) through
the event runtime produces **one** confirmed sell with ``exit_reason =
third_party_sell`` and the position closed; and with the flag ``paper``/``off``
the same proposal is never touched."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from hunter_exchanges.pumpfun.rpc_ws_models import LogsNotification
from hunter_exchanges.pumpfun.trade_event import trade_events_from_logs
from hunter_meme_executor.entries import entries_once
from hunter_meme_executor.event_exits import EventExitsRuntime, handle_notification, sync_watch
from hunter_meme_executor.event_exits_config import EventExitsConfig
from hunter_meme_executor.heartbeat import heartbeat_fields
from hunter_meme_executor.launch_config import LAUNCH_SERIES, LaunchConfig
from hunter_meme_executor.launch_entries import launch_entries_once
from hunter_meme_executor.launch_exits import launch_exits_once

from .test_event_exits import LOGS_ID, LOGS_LINES, FakeWs
from .test_event_exits import MINT as LAUNCH_MINT
from .test_live_persistence import (
    CREATOR,
    FakeRedis,
    Harness,
    _context,
    _fixture,
    _rows,
    _signer,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration]

HOLDER = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"
"""The mint is the ``t452b`` fixture's own (``HMfRWjo6…``): no ``meme_tokens`` row
exists for it in this database — exactly a coin seconds old — and fixture line 3
is a holder's sell of it, replayed as is. ``HOLDER`` is that seller."""
LAUNCH_POLICY = {
    "MEME_WALLET_MAX_SOL": "0.5",
    "MEME_MAX_SOL_PER_TRADE": "0.05",
    "MEME_DAILY_LOSS_CAP_SOL": "0.1",
    "MEME_MAX_OPEN_POSITIONS": "3",
    "MEME_COOLDOWN_S": "3600",
}
"""The live floor stays at its 0,02 default: the launch floor follows the 0,01 ticket."""


@pytest_asyncio.fixture
async def launch_harness(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[Harness]:
    """An empty ledger, an unlatched switch, **no** faked token context (the
    launch path reads the real ``meme_tokens`` row, which does not exist for a
    coin seconds old — ``LAUNCH_MINT`` has none), the launch lane ``on``."""
    async with db_engine.begin() as connection:
        await connection.execute(text("DELETE FROM meme_live_positions"))
        await connection.execute(text("DELETE FROM meme_live_orders"))
        await connection.execute(
            text(
                "DELETE FROM meme_proposals WHERE mode = 'live' OR rule_set_id IN "
                "(SELECT id FROM meme_rule_sets WHERE name = 'launch_v0')"
            )
        )
        assert (
            await connection.scalar(
                text("SELECT count(*) FROM meme_tokens WHERE mint = :mint"), {"mint": LAUNCH_MINT}
            )
        ) == 0, "the launch mint must have no token row: that is the case under test"
        await connection.execute(
            text(
                "UPDATE meme_live_kill_switch SET state = 'ACTIVE', reason = NULL, latched_at = NULL, "
                "released_at = NULL, released_by = NULL WHERE scope = 'wallet'"
            )
        )
    harness = _context(db_session_factory, _signer(), FakeRedis(), policy=LAUNCH_POLICY)
    harness.ctx.config = replace(harness.ctx.config, launch=LaunchConfig(mode="on"))
    yield harness


async def _launch_rule_set(engine: AsyncEngine) -> str:
    async with engine.begin() as connection:
        existing = await connection.scalar(
            text("SELECT id FROM meme_rule_sets WHERE name = 'launch_v0' AND version = '1'")
        )
        if existing is not None:
            return str(existing)
        rule_set_id = str(uuid4())
        await connection.execute(
            text(
                "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref) "
                "VALUES (:id, 'launch_v0', '1', 'research_only', CAST(:params AS jsonb), "
                "  'tests/test_launch_integration', 'EXP-M18')"
            ),
            {
                "id": rule_set_id,
                "params": json.dumps(
                    {
                        "clock": "event",
                        "size_sol": "0.01",
                        "time_stop_s": 6,
                        "max_drawdown_from_peak_pct": "20",
                        "exit_on_first_third_party_sell": True,
                    }
                ),
            },
        )
        return rule_set_id


async def _plant_launch_proposal(engine: AsyncEngine, *, proposed_at: datetime) -> str:
    """What the radar's launch lane (T4.67a) writes: research-only, born approved."""
    rule_set_id = await _launch_rule_set(engine)
    proposal_id = str(uuid4())
    created_at = proposed_at - timedelta(milliseconds=400)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
                "  expires_at, features_end_time, quote, reasons, suggested, decision, decided_by, "
                "  decided_at, mode) "
                "VALUES (:id, :mint, :rs, 'rules', 'approved', :proposed, :expires, :fet, '{}', "
                "  CAST(:reasons AS jsonb), CAST(:suggested AS jsonb), CAST(:suggested AS jsonb), "
                "  'rules', :proposed, 'paper')"
            ),
            {
                "id": proposal_id,
                "mint": LAUNCH_MINT,
                "rs": rule_set_id,
                "proposed": proposed_at,
                "expires": proposed_at + timedelta(seconds=30),
                "fet": created_at,
                # T4.67a's own shape (``launch_lane_entry._reasons``/``_suggested``):
                # the create instant is ``features_end_time``; no ``created_at`` key.
                "reasons": json.dumps(
                    [
                        {
                            "rule": "launch_v0/1",
                            "series": LAUNCH_SERIES,
                            "is_mayhem": False,
                            "creator_initial_sol": "0.5",
                            "max_creator_initial_sol": "2",
                            "initial_real_token_reserves": "793100000",
                            "symbol_clone_recent": False,
                            "symbol": "TEST",
                        }
                    ]
                ),
                "suggested": json.dumps(
                    {
                        "size_sol": "0.01",
                        "time_stop_s": 6,
                        "exit_key": "lancamento_6s_ou_primeiro_sell",
                        "exit_on_first_third_party_sell": True,
                        "max_drawdown_from_peak_pct": "20",
                    }
                ),
            },
        )
    return proposal_id


def _third_party_sell_frame(*, at: datetime) -> LogsNotification:
    """``t452b`` line 3 — a holder's sell of the launch mint, replayed as captured."""
    frame = json.loads(LOGS_LINES[3])["params"]["result"]
    logs = [str(line) for line in frame["value"]["logs"]]
    events = trade_events_from_logs(logs)
    assert len(events) == 1 and events[0].mint == LAUNCH_MINT and events[0].user == HOLDER
    assert events[0].is_buy is False and events[0].user != CREATOR
    return LogsNotification(
        subscription_id=LOGS_ID,
        kind="logs",
        slot=int(frame["context"]["slot"]),
        signature=str(frame["value"]["signature"]),
        err=None,
        logs=tuple(logs),
        received_at=at,
    )


async def _orders(engine: AsyncEngine, proposal_id: str, side: str) -> list[dict[str, Any]]:
    return await _rows(
        engine,
        "SELECT * FROM meme_live_orders WHERE proposal_id = :p AND side = :s ORDER BY attempt",
        p=proposal_id,
        s=side,
    )


async def test_a_launch_proposal_in_on_becomes_one_launch_buy_then_one_sell_on_a_third_party_sell(
    launch_harness: Harness,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    live = launch_harness
    proposal_id = await _plant_launch_proposal(db_engine, proposed_at=datetime.now(UTC))
    # The regular entries loop never sees a paper research row.
    await entries_once(live.ctx)
    assert await _orders(db_engine, proposal_id, "buy") == []

    await launch_entries_once(live.ctx)
    buys = await _orders(db_engine, proposal_id, "buy")
    assert len(buys) == 1 and buys[0]["status"] == "confirmed", buys
    assert buys[0]["client_order_id"] == f"meme:{proposal_id}"
    admission = buys[0]["admission"]
    assert admission["profile"] == "launch" and admission["approved"] is True
    states = {c["name"]: c["state"] for c in admission["checks"]}
    assert states["creator_behaviour"] == "skipped" and states["bundled_share"] == "skipped"
    assert states["top10_share"] == "skipped" and states["conviction"] == "skipped"
    assert states["launch_open_cap"] == "passed" and states["state_freshness"] == "passed"
    assert admission["launch"]["quote_commitment"] == "processed"
    assert admission["launch"]["token_row_present"] is False
    assert admission["launch"]["token_age_source"] == "meme_proposals.features_end_time"
    assert admission["launch"]["denominator_source"] == (
        "meme_proposals.reasons[0].initial_real_token_reserves"
    )
    assert set(admission["launch"]["skipped_reads"]) >= {"creator_ata", "risk_snapshot_on_demand"}
    assert buys[0]["intent"]["lane"] == "launch" and buys[0]["intent"]["max_slippage_bps"] == 1000
    assert buys[0]["intent"]["priority_fee"]["micro_lamports"] >= 1_000_000
    assert len(live.rpc.sent) == 1
    claimed = await _rows(
        db_engine, "SELECT mode, decision FROM meme_proposals WHERE id = :p", p=proposal_id
    )
    assert (
        claimed[0]["mode"] == "live"
        and claimed[0]["decision"]["launch_lane"]["by"] == "executor:launch"
    )
    positions = await _rows(
        db_engine, "SELECT * FROM meme_live_positions WHERE proposal_id = :p", p=proposal_id
    )
    assert len(positions) == 1 and positions[0]["status"] == "open"
    params = positions[0]["params"]
    assert params["lane"] == "launch" and params["time_stop_s"] == 6
    assert params["exit_on_first_third_party_sell"] is True and params["creator"] == CREATOR
    assert live.ctx.launch.buys_total == 1 and len(live.ctx.launch.submit_latencies_ms) == 1

    # Idempotent: a second pass of either loop writes nothing and sends nothing.
    await launch_entries_once(live.ctx)
    await entries_once(live.ctx)
    assert len(await _orders(db_engine, proposal_id, "buy")) == 1 and len(live.rpc.sent) == 1

    # The event runtime on a "restarted" process (the chain holds the tokens now):
    # the third-party sell of the fixture, re-addressed, sells once.
    restarted = _context(db_session_factory, _signer(), live.redis, policy=LAUNCH_POLICY)
    restarted.ctx.config = replace(
        restarted.ctx.config,
        launch=LaunchConfig(mode="on"),
        event_exits=EventExitsConfig(enabled=True, ws_url="ws://x"),
    )
    restarted.chain.tokens_on_chain = 10**9
    restarted.rpc.transaction = json.loads(json.dumps(_fixture("rpc_tx_probe_raw.json")["result"]))
    rt = EventExitsRuntime(ctx=restarted.ctx, ws=FakeWs(), config=restarted.ctx.config.event_exits)
    await sync_watch(rt, now=datetime.now(UTC))
    (w,) = rt.watched.values()
    assert w.launch is True and w.creator == CREATOR, (
        "creator learned from the params: no token row"
    )
    await handle_notification(
        rt, _third_party_sell_frame(at=datetime.now(UTC)), now=datetime.now(UTC)
    )
    assert w.selling is not None
    await w.selling
    sells = await _orders(db_engine, proposal_id, "sell")
    assert len(sells) == 1 and sells[0]["status"] == "confirmed", sells
    assert sells[0]["intent"]["exit_reason"] == "third_party_sell"
    closed = await _rows(
        db_engine,
        "SELECT status, exit FROM meme_live_positions WHERE proposal_id = :p",
        p=proposal_id,
    )
    assert closed[0]["status"] == "closed" and closed[0]["exit"]["reason"] == "third_party_sell"
    assert restarted.ctx.launch.sells_total == 1
    # The 2 s launch tick right after finds nothing left to sell.
    await launch_exits_once(restarted.ctx)
    assert len(await _orders(db_engine, proposal_id, "sell")) == 1
    fields = await heartbeat_fields(restarted.ctx)
    assert fields["launch_lane_mode"] == "on" and fields["launch_open"] == "0"
    assert (
        fields["launch_sells_total"] == "1" and fields["event_exits_third_party_sells_seen"] == "1"
    )


@pytest.mark.parametrize("mode", ["paper", "off"])
async def test_in_paper_or_off_the_launch_proposal_is_never_touched(
    launch_harness: Harness, db_engine: AsyncEngine, mode: str
) -> None:
    live = launch_harness
    live.ctx.config = replace(live.ctx.config, launch=LaunchConfig(mode=mode))  # type: ignore[arg-type]
    proposal_id = await _plant_launch_proposal(db_engine, proposed_at=datetime.now(UTC))
    await launch_entries_once(live.ctx)
    await entries_once(live.ctx)
    assert await _orders(db_engine, proposal_id, "buy") == [] and live.rpc.sent == []
    row = await _rows(
        db_engine, "SELECT mode, status FROM meme_proposals WHERE id = :p", p=proposal_id
    )
    assert row[0]["mode"] == "paper" and row[0]["status"] == "approved"
    fields = await heartbeat_fields(live.ctx)
    assert fields["launch_lane_mode"] == mode and fields["launch_buys_total"] == "0"


async def test_a_stale_launch_proposal_is_refused_by_name_and_claimed(
    launch_harness: Harness, db_engine: AsyncEngine
) -> None:
    live = launch_harness
    proposal_id = await _plant_launch_proposal(
        db_engine, proposed_at=datetime.now(UTC) - timedelta(seconds=7)
    )
    await launch_entries_once(live.ctx)
    buys = await _orders(db_engine, proposal_id, "buy")
    assert len(buys) == 1 and buys[0]["status"] == "refused"
    assert buys[0]["reason"] == "launch_proposal_stale" and live.rpc.sent == []
    row = await _rows(db_engine, "SELECT mode FROM meme_proposals WHERE id = :p", p=proposal_id)
    assert row[0]["mode"] == "live", "claimed, so neither loop re-reads it"
    await launch_entries_once(live.ctx)
    assert len(await _orders(db_engine, proposal_id, "buy")) == 1
