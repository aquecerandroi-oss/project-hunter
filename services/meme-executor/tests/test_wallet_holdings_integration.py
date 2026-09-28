"""KB-0165 on a real, migrated Postgres (testcontainers): the recognized set's
SQL over every lane's rows, and the desk's ``entries.py`` end to end with the
real reader — a foreign mint refuses ``wallet_unrecognized_holdings`` by name,
the quote mints do not, an unreadable wallet defers (no row, nothing sent), and
the heartbeat publishes the verdict."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_exchanges.jupiter import WRAPPED_SOL_MINT
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID
from hunter_meme_executor.chain import TokenHolding
from hunter_meme_executor.entries import entries_once
from hunter_meme_executor.heartbeat import heartbeat_fields
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.treasury_rules import USDC_MINT
from hunter_meme_executor.wallet_holdings import holdings_once, recognized_mints

from . import test_live_persistence as _live
from .test_live_persistence import OPERATOR_RULE_SET, Harness, _plant_proposal, _rows

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

harness = _live.harness  # the Postgres rig and its per-test cleanup, shared as is

FOREIGN = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"


def _holding(mint: str, amount: int = 50_000_000, decimals: int = 9) -> TokenHolding:
    return TokenHolding(mint, TOKEN_PROGRAM_ID, amount, decimals)


async def _orders(engine: AsyncEngine, proposal_id: str) -> list[dict[str, Any]]:
    return await _rows(
        engine, "SELECT * FROM meme_live_orders WHERE proposal_id = :p", p=proposal_id
    )


# ---- entries.py, end to end ----------------------------------------------------------
async def test_a_foreign_mint_refuses_the_desk_entry_by_name(
    harness: Harness, db_engine: AsyncEngine
) -> None:
    harness.chain.holdings = [_holding(FOREIGN)]
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    orders = await _orders(db_engine, proposal_id)
    assert len(orders) == 1 and orders[0]["status"] == "refused", orders
    assert orders[0]["reason"] == "wallet_unrecognized_holdings"
    check = next(c for c in orders[0]["admission"]["checks"] if c["name"] == "wallet_cap")
    assert check["state"] == "failed" and check["message"] == FOREIGN
    assert orders[0]["admission"]["wallet_holdings"]["unrecognized"] == [FOREIGN]
    assert harness.rpc.sent == []


async def test_quote_mints_alone_leave_the_desk_entry_to_the_other_checks(
    harness: Harness, db_engine: AsyncEngine
) -> None:
    harness.chain.holdings = [_holding(USDC_MINT, 5_000_000, 6), _holding(WRAPPED_SOL_MINT)]
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    orders = await _orders(db_engine, proposal_id)
    assert len(orders) == 1 and orders[0]["status"] == "confirmed", orders
    assert orders[0]["admission"]["wallet_holdings"]["unrecognized_count"] == 0
    assert orders[0]["admission"]["wallet_holdings"]["accounts"] == 2


async def test_an_unreadable_wallet_defers_the_desk_entry(
    harness: Harness, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    real, down = harness.chain.token_holdings, [True]

    def flaky(owner: str) -> Any:
        if down[0]:
            raise RuntimeError("rpc down")
        return real(owner)

    monkeypatch.setattr(harness.chain, "token_holdings", flaky)
    proposal_id = await _plant_proposal(db_engine, decided_at=datetime.now(UTC))
    await entries_once(harness.ctx)
    assert await _orders(db_engine, proposal_id) == []
    assert harness.rpc.sent == [] and harness.ctx.holdings.deferrals == 1
    down[0] = False
    harness.ctx.holdings.retry_at = None  # the failure's 10 s backoff has elapsed (F3)
    await entries_once(harness.ctx)  # the read is back: the same approval is admitted
    assert [o["status"] for o in await _orders(db_engine, proposal_id)] == ["confirmed"]


async def test_the_tick_publishes_the_verdict_on_the_heartbeat(harness: Harness) -> None:
    harness.chain.holdings = [_holding(FOREIGN)]
    await holdings_once(harness.ctx)
    fields = await heartbeat_fields(harness.ctx)
    assert fields["wallet_holdings_state"] == "valid"
    assert fields["wallet_unrecognized_mints"] == FOREIGN
    assert fields["wallet_unrecognized_count"] == "1"


# ---- the recognized set's SQL --------------------------------------------------------
_MINTS = {k: f"Wh{k}{uuid.uuid4().hex[:30]}" for k in "ABCDEFG"}
_SPOT = {k: f"Ws{k}{uuid.uuid4().hex[:30]}" for k in "ABCD"}


async def _proposal(conn: Any, mint: str, at: datetime) -> str:
    pid = str(uuid.uuid4())
    await conn.execute(
        text(
            "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, last_seen_at, "
            "  created_at) VALUES (:m, 'pumpportal_ws', :t, :t, :t) ON CONFLICT (mint) DO NOTHING"
        ),
        {"m": mint, "t": at},
    )
    await conn.execute(
        text(
            "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, proposed_at, "
            "  expires_at, quote, reasons, suggested, decision, decided_by, decided_at, mode) "
            "VALUES (:id, :m, :rs, 'operator', 'approved', :t, :exp, '{}', '[]', '{}', '{}', "
            "  'user_x', :t, 'live')"
        ),
        {"id": pid, "m": mint, "rs": OPERATOR_RULE_SET, "t": at, "exp": at + timedelta(minutes=2)},
    )
    return pid


async def _buy(conn: Any, pid: str, status: str, settled: datetime | None) -> str:
    oid = str(uuid.uuid4())
    confirmed = status in ("confirmed", "submitted_unconfirmed")
    await conn.execute(
        text(
            "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, status, reason, "
            "  tx_signature, fill, settled_at, updated_at) VALUES (:id, :p, 'buy', :k, :s, :r, "
            "  :sig, CAST(:fill AS jsonb), :settled, :upd)"
        ),
        {
            "id": oid, "p": pid, "k": f"meme:{pid}", "s": status,
            "r": "x" if status in ("refused", "failed") else None,
            "sig": "sig" + oid if confirmed else None,
            "fill": json.dumps({"token_amount": 1}) if status == "confirmed" else None,
            "settled": settled, "upd": settled or datetime.now(UTC),
        },
    )  # fmt: skip
    return oid


async def _position(conn: Any, pid: str, oid: str, mint: str, closed_at: datetime | None) -> None:
    entry = (closed_at or datetime.now(UTC)) - timedelta(hours=1)
    await conn.execute(
        text(
            "INSERT INTO meme_live_positions (id, proposal_id, entry_order_id, mint, status, "
            "  entry_at, entry, tokens, sol_spent_lamports, initial_risk_sol, params, exit_at, "
            "  exit, pnl_sol, r_multiple, updated_at) VALUES (:id, :p, :o, :m, :st, :e, '{}', 1, "
            "  1, 0.001, '{}', :x, CAST(:ex AS jsonb), :pnl, :pnl, :upd)"
        ),
        {
            "id": str(uuid.uuid4()), "p": pid, "o": oid, "m": mint,
            "st": "open" if closed_at is None else "closed", "e": entry, "x": closed_at,
            "ex": None if closed_at is None else "{}", "pnl": None if closed_at is None else 0,
            "upd": closed_at or datetime.now(UTC),
        },
    )  # fmt: skip


async def _plant_meme(engine: AsyncEngine, now: datetime) -> None:
    old = now - timedelta(hours=2)
    async with engine.begin() as conn:
        a = await _proposal(conn, _MINTS["A"], old)  # open position
        await _position(conn, a, await _buy(conn, a, "confirmed", old), _MINTS["A"], None)
        b = await _proposal(conn, _MINTS["B"], old)  # closed long ago
        await _position(conn, b, await _buy(conn, b, "confirmed", old), _MINTS["B"], old)
        c = await _proposal(conn, _MINTS["C"], old)  # closed within the grace
        c_close = now - timedelta(seconds=30)
        await _position(conn, c, await _buy(conn, c, "confirmed", old), _MINTS["C"], c_close)
        await _buy(conn, await _proposal(conn, _MINTS["D"], now), "submitted_unconfirmed", None)
        await _buy(conn, await _proposal(conn, _MINTS["E"], now), "refused", now)
        f_settled = now - timedelta(seconds=10)  # confirmed, no position yet
        await _buy(conn, await _proposal(conn, _MINTS["F"], now), "confirmed", f_settled)
        await _buy(conn, await _proposal(conn, _MINTS["G"], old), "confirmed", old)


_SIGNAL_ROWS = (
    "INSERT INTO strategies (id, key, name) VALUES (:strategy, :key, 'kb0165')",
    "INSERT INTO strategy_versions (id, strategy_id, version) VALUES (:version, :strategy, 'v1')",
    "INSERT INTO exchanges (id, code, name) VALUES (:exchange, :key, 'kb0165')",
    "INSERT INTO markets (id, exchange_id, symbol, market_type) "
    "VALUES (:market, :exchange, 'WIFUSDT', 'perpetual')",
)


async def _plant_spot(engine: AsyncEngine, now: datetime) -> None:
    ids = {k: str(uuid.uuid4()) for k in ("strategy", "version", "exchange", "market")}
    old = now - timedelta(hours=2)
    async with engine.begin() as conn:
        for statement in _SIGNAL_ROWS:
            await conn.execute(text(statement), {**ids, "key": f"kb{uuid.uuid4().hex[:12]}"})
        for key, (status, closed) in {
            "A": ("confirmed", None), "B": ("confirmed", old),
            "C": ("submitted_unconfirmed", "no_position"), "D": ("refused", "no_position"),
        }.items():  # fmt: skip
            signal, order = str(uuid.uuid4()), str(uuid.uuid4())
            await conn.execute(
                text(
                    "INSERT INTO agent_signals (id, strategy_version_id, market_id, params_hash, "
                    "  direction, confidence) VALUES (:s, :version, :market, 'kb0165', 'long', 0.5)"
                ),
                {**ids, "s": signal},
            )
            await conn.execute(
                text(
                    "INSERT INTO spot_orders (id, signal_id, market_symbol, mint, side, "
                    "  client_order_id, status, reason, tx_signature, fill, settled_at, "
                    "  updated_at) VALUES (:id, :s, 'WIFUSDT', :m, 'buy', :k, :st, :r, :sig, "
                    "  CAST(:fill AS jsonb), :at, :at)"
                ),
                {
                    "id": order, "s": signal, "m": _SPOT[key], "k": f"spot:buy:{signal}",
                    "st": status, "r": "x" if status == "refused" else None,
                    "sig": None if status == "refused" else "sig" + order,
                    "fill": json.dumps({"out": 1}) if status == "confirmed" else None, "at": old,
                },
            )  # fmt: skip
            if closed == "no_position":
                continue
            await conn.execute(
                text(
                    "INSERT INTO spot_positions (id, signal_id, entry_order_id, market_symbol, "
                    "  mint, status, entry_at, entry, tokens, sol_spent_lamports, "
                    "  initial_risk_sol, params, exit_at, exit, pnl_sol, r_multiple, updated_at) "
                    "VALUES (:id, :s, :o, 'WIFUSDT', :m, :st, :e, '{}', 1, 1, 0.001, '{}', :x, "
                    "  CAST(:ex AS jsonb), :pnl, :pnl, :upd)"
                ),
                {
                    "id": str(uuid.uuid4()), "s": signal, "o": order, "m": _SPOT[key],
                    "st": "open" if closed is None else "closed", "e": old - timedelta(hours=1),
                    "x": closed, "ex": None if closed is None else "{}",
                    "pnl": None if closed is None else 0, "upd": old,
                },
            )  # fmt: skip


async def test_the_recognized_set_covers_every_lane_and_only_what_it_should(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    try:
        await _plant_meme(db_engine, now)
        await _plant_spot(db_engine, now)
        async with role_session(db_session_factory, db_role=WORKER_ROLE) as session:
            got = await recognized_mints(session, since=now - timedelta(seconds=60))
    finally:
        await _clean(db_engine)
    mine = got & (set(_MINTS.values()) | set(_SPOT.values()))
    assert mine == {_MINTS["A"], _MINTS["C"], _MINTS["D"], _MINTS["F"], _SPOT["A"], _SPOT["C"]}


async def _clean(engine: AsyncEngine) -> None:
    """An unmarked open position left behind would refuse other tests' entries."""
    meme, spot = list(_MINTS.values()), list(_SPOT.values())
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL app.meme_retention = 'on'"))  # test rows only
        for statement, mints in (
            ("DELETE FROM meme_live_positions WHERE mint = ANY(:m)", meme),
            ("DELETE FROM meme_live_orders WHERE proposal_id IN "
             "(SELECT id FROM meme_proposals WHERE mint = ANY(:m))", meme),
            ("DELETE FROM meme_proposals WHERE mint = ANY(:m)", meme),
            ("DELETE FROM meme_tokens WHERE mint = ANY(:m)", meme),
            ("DELETE FROM spot_positions WHERE mint = ANY(:m)", spot),
            ("DELETE FROM spot_orders WHERE mint = ANY(:m)", spot),
        ):  # fmt: skip
            await conn.execute(text(statement), {"m": mints})
        for statement in (
            "DELETE FROM agent_signals WHERE params_hash = 'kb0165'",
            "DELETE FROM markets WHERE exchange_id IN (SELECT id FROM exchanges WHERE name = 'kb0165')",
            "DELETE FROM exchanges WHERE name = 'kb0165'",
            "DELETE FROM strategy_versions WHERE strategy_id IN "
            "(SELECT id FROM strategies WHERE name = 'kb0165')",
            "DELETE FROM strategies WHERE name = 'kb0165'",
        ):
            await conn.execute(text(statement))
