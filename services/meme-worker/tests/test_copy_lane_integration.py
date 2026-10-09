"""The copy lane against a real Postgres (testcontainers) with a fake chain (H-037), the life of a
copy: entry priced at the market after the declared latency, exit on the leader's sale, the Lab's own
cap stamps, our own exits (safety stop, time cap), recovery after a restart and the inert rule set.
Paper only: nothing here touches an executor or a wallet. Run alone (``timeout 590``): shares the
container fixture of ``conftest.py``."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_indicators.meme.curve import CurveReserves, quote_buy
from hunter_meme_worker.copy_spec import load_copy_specs
from hunter_meme_worker.lab_values import SELL_CAP_MODEL

from .copy_fakes import Curve
from .copy_rig import (
    LATENCY_MS,
    WORKER,
    addr,
    bets,
    mint_address,
    proposals,
    retire_copy_sets,
    rule_set,
    running,
)
from .copy_support import PARAMS, T0, buy, sell

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_the_whole_life_of_a_copy_priced_after_the_declared_latency(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, other, mint = addr("A"), addr("B"), mint_address()
    spec = await rule_set(db_engine, leader, other)
    async with running(spec, db_session_factory) as rig:
        decided = rig.clock.now
        # the market the decision would see, and the one 250 ms later that the fill must use
        rig.chain.set(mint, Curve(vsol="30", vtok="1073000000"), at=decided - timedelta(seconds=5))
        rig.chain.set(
            mint, Curve(vsol="31", vtok="1036000000"), at=decided + timedelta(milliseconds=100)
        )
        event = buy(leader, mint, at=T0, position_after=1_000_000)
        rig.lane.on_item(event)
        await rig.settle()

        [bet] = await bets(db_session_factory, spec)
        entry = bet["entry"]
        later = quote_buy(
            CurveReserves(Decimal(31), Decimal(1_036_000_000), Decimal(700_000_000)),
            spec.size_sol,
            spec.fee_pct,
        )
        earlier = quote_buy(
            CurveReserves(Decimal(30), Decimal(1_073_000_000), Decimal(700_000_000)),
            spec.size_sol,
            spec.fee_pct,
        )
        assert Decimal(entry["tokens"]) == later.tokens != earlier.tokens
        assert bet["entry_at"] == decided + timedelta(milliseconds=LATENCY_MS)
        copy = entry["copy"]
        assert copy["leader_wallet"] == leader and copy["leader"]["stratum"] == "regra"
        assert copy["leader_signature"] == event.signature
        assert copy["leader_observed_at"] == T0.isoformat(timespec="milliseconds")
        ts = copy["ts"]
        assert ts["decided_at"] == decided.isoformat(timespec="milliseconds")
        assert ts["priced_at"] == (decided + timedelta(milliseconds=250)).isoformat(
            timespec="milliseconds"
        )
        assert ts["persisted_at"] is not None and ts["leader_block_time"] is not None
        assert copy["latency_ms"]["decided_to_priced_ms"] == 250.0
        assert bet["status"] == "open" and entry["sell_cap_model"] == SELL_CAP_MODEL
        [proposal] = await proposals(db_session_factory, spec)
        assert proposal["status"] == "filled" and str(proposal["bet_id"]) == str(bet["id"])
        assert proposal["decided_by"] == "rules:copy"

        # the leader sells everything; the paper sells at the market 250 ms after the decision
        rig.clock.advance(seconds=60)
        rig.chain.set(mint, Curve(vsol="33", vtok="975000000", real_sol="3"))
        sale = sell(leader, mint, at=rig.clock.now, position_after=0)
        rig.lane.on_item(sale)
        sold_decided = rig.clock.now
        await rig.settle()

        [bet] = await bets(db_session_factory, spec)
        assert bet["status"] == "closed" and bet["outcome_quality"] == "measured"
        out = bet["exit"]
        assert out["reason"] == "leader_exit_full" and out["copy"]["trigger"] == "copy_leader"
        assert out["copy"]["leader_signature"] == sale.signature
        assert bet["exit_at"] == sold_decided + timedelta(milliseconds=LATENCY_MS)
        assert out["sell_cap_model"] == SELL_CAP_MODEL
        assert out["own_curve_sol"] == entry["curve_cost_sol"]
        expected = Decimal(out["sol_received"]) - Decimal(entry["sol_spent"])
        assert abs(Decimal(str(bet["pnl_sol"])) - expected) < Decimal("1e-9")
        assert bet["mark_source"] == "curve"
        assert rig.lane.book.open_count == 0

        fields = rig.lane.fields()
        assert fields["copy_entries"] == "1" and fields["copy_exits"] == "1"
        assert fields["copy_open"] == "0" and fields["copy_leaders"] == "2"
        assert fields["copy_observed_to_decided_ms_p99"] != ""
        per = json.loads(fields["copy_per_leader"])
        assert (
            per[leader]["entries"] == 1 and per[leader]["exits"] == 1 and per[other]["events"] == 0
        )


@pytest.mark.asyncio
async def test_a_mayhem_exit_carries_the_fixed_cap_and_the_stamp(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve(real_sol="0.5", mayhem=True))
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        rig.clock.advance(seconds=20)
        rig.lane.on_item(sell(leader, mint, at=rig.clock.now))
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        out, entry = bet["exit"], bet["entry"]
        assert out["sell_cap_model"] == SELL_CAP_MODEL
        assert Decimal(out["sell_cap_sol"]) == Decimal("0.5") + Decimal(entry["curve_cost_sol"])


@pytest.mark.asyncio
async def test_the_time_cap_and_the_safety_stop_are_our_own_exits(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, capped, stopped = addr("A"), mint_address(), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        for mint in (capped, stopped):
            rig.chain.set(mint, Curve())
            rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        rig.clock.advance(seconds=5)
        rig.chain.set(stopped, Curve(vsol="10", vtok="3200000000", real_sol="0.1"))
        assert await rig.lane.mark_once() == 2  # both marked live
        await rig.settle()
        rig.clock.advance(seconds=700)  # past time_cap_s = 600
        await rig.lane.sweep_once()
        await rig.settle()
        by_mint = {b["mint"]: b for b in await bets(db_session_factory, spec)}
        assert by_mint[stopped]["exit"]["reason"] == "safety_stop"
        assert by_mint[capped]["exit"]["reason"] == "time_cap"
        for bet in by_mint.values():
            assert bet["status"] == "closed" and bet["exit"]["copy"]["trigger"] == "copy_own"
            assert bet["exit"]["copy"]["leader_signature"] is None


@pytest.mark.asyncio
async def test_a_restart_recovers_open_copies_and_never_copies_a_pair_twice(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint, fresh = addr("A"), mint_address(), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as first:
        first.chain.set(mint, Curve())
        first.lane.on_item(buy(leader, mint, at=T0, position_after=2_000_000))
        await first.settle()
    async with running(spec, db_session_factory, recover=True) as rig:
        assert rig.lane.book.open_count == 1
        rig.chain.set(mint, Curve())
        rig.chain.set(fresh, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0 + timedelta(seconds=5)))  # same pair: no 2nd copy
        assert rig.lane.stats.skipped_by_reason["already_observed"] == 1
        rig.lane.on_item(buy(leader, fresh, at=T0 + timedelta(seconds=6)))  # a new pair is fine
        await rig.settle()  # priced inside its own window, before the clock moves on
        rig.clock.advance(seconds=30)
        rig.lane.on_item(sell(leader, mint, at=rig.clock.now))  # blind across the restart
        await rig.settle()
        by_mint = {b["mint"]: b for b in await bets(db_session_factory, spec)}
        assert by_mint[mint]["outcome_quality_reason"] == "worker_restart_gap"
        assert by_mint[fresh]["status"] == "open"


@pytest.mark.asyncio
async def test_load_copy_specs_reads_every_active_copy_set_not_one_hard_coded_name(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await retire_copy_sets(db_engine)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        assert await load_copy_specs(session) == []  # inert until a copy set is active
    regra = {**PARAMS, "leaders": [{"wallet": addr("A"), "stratum": "regra"}]}
    everton = {**PARAMS, "leaders": [{"wallet": addr("B"), "stratum": "escolha_everton"}]}
    async with db_engine.begin() as connection:
        for name, params in (("copy_v0", regra), ("copy_everton_v0", everton)):
            await connection.execute(
                text(
                    "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref) "
                    "VALUES (:id, :name, :v, 'research_only', CAST(:p AS jsonb), 'test', 'EXP-M28')"
                ),
                {"id": str(uuid4()), "name": name, "v": uuid4().hex[:8], "p": json.dumps(params)},
            )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        specs = await load_copy_specs(session)
    assert [s.name for s in specs] == ["copy_everton_v0", "copy_v0"]
    by_name = {s.name: s for s in specs}
    assert by_name["copy_v0"].is_primary and not by_name["copy_everton_v0"].is_primary
    await retire_copy_sets(db_engine)  # leave the shared database as it was found
