"""The copy lane against a real Postgres (H-037), the refusing half: the durable funnel (every first
observation that is not admitted is a ``rejected`` row with the design's reason), an admitted attempt
that never fills (``unfilled`` with a name), a slot floor, an exit across a gap, and an unconfirmed
event acted on and later confirmed — or never confirmed and invalidated by name while it STAYS in the
primary. Every refusal is a row with a named reason, never a guessed fill."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from .copy_fakes import Curve
from .copy_rig import addr, bets, mint_address, proposals, rule_set, running
from .copy_support import T0, buy, gap, sell

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_a_buy_inside_a_gap_is_a_rejected_funnel_row_named_lacuna(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(gap(T0 - timedelta(seconds=30), T0 + timedelta(seconds=30), wallet=leader))
        rig.lane.on_item(buy(leader, mint, at=T0 + timedelta(seconds=5), block_time=T0))
        await rig.settle()
        assert await bets(db_session_factory, spec) == []
        [proposal] = await proposals(db_session_factory, spec)
        assert proposal["status"] == "rejected" and proposal["refusal"] is None
        assert proposal["decision"]["reason"] == "lacuna" and proposal["decided_by"] == "rules:copy"
        assert proposal["quote"]["leader_wallet"] == leader
        assert json.loads(rig.lane.fields()["copy_rejected_by_reason"]) == {"lacuna": 1}


@pytest.mark.asyncio
async def test_a_buy_below_the_floor_and_a_second_look_leave_exactly_one_funnel_row(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0, spent_sol="0.05"))
        rig.lane.on_item(buy(leader, mint, at=T0 + timedelta(seconds=3), spent_sol="0.9"))
        await rig.settle()
        [proposal] = await proposals(db_session_factory, spec)
        assert (
            proposal["status"] == "rejected" and proposal["decision"]["reason"] == "abaixo_do_piso"
        )
        assert await bets(db_session_factory, spec) == []
        assert rig.lane.stats.skipped_by_reason["already_observed"] == 1


@pytest.mark.asyncio
async def test_an_exit_after_a_gap_is_closed_indeterminate_and_prices_nothing(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        rig.clock.advance(seconds=30)
        rig.lane.on_item(gap(rig.clock.now, rig.clock.now + timedelta(seconds=20), wallet=leader))
        rig.clock.advance(seconds=40)
        rig.lane.on_item(sell(leader, mint, at=rig.clock.now))
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["status"] == "closed" and bet["outcome_quality"] == "indeterminate"
        assert bet["outcome_quality_reason"] == "leader_gap_exit"
        assert bet["exit"]["sol_received"] == "0" and bet["exit"]["snapshot"] is None
        assert rig.lane.stats.exits == 0


@pytest.mark.asyncio
async def test_a_buy_of_a_migrated_mint_is_a_rejected_row_outside_the_venue_and_costs_no_attempt(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, other, mint = addr("A"), addr("B"), mint_address()
    spec = await rule_set(db_engine, leader, other, max_attempts_per_leader_day=1)
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve(complete=True))
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        [proposal] = await proposals(db_session_factory, spec)
        assert proposal["status"] == "rejected"
        assert proposal["decision"]["reason"] == "venue_fora_do_escopo"
        assert await bets(db_session_factory, spec) == []
        assert rig.lane.book.open_count == 0
        # the attempt was refunded (a day ceiling of 1 is still free) and the mint is now known as pool
        rig.lane.on_item(buy(other, mint, at=T0 + timedelta(seconds=9)))
        fresh = mint_address()
        rig.chain.set(fresh, Curve())
        rig.lane.on_item(buy(leader, fresh, at=T0 + timedelta(seconds=10)))
        await rig.settle()
        reasons = sorted(
            p["decision"].get("reason") or p["refusal"]
            for p in await proposals(db_session_factory, spec)
            if p["status"] == "rejected"
        )
        assert reasons == ["venue_fora_do_escopo", "venue_fora_do_escopo"]
        assert len(await bets(db_session_factory, spec)) == 1  # the next, on the curve, is copied


@pytest.mark.asyncio
async def test_no_eligible_state_inside_the_window_is_unfilled_sem_estado(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.lane.on_item(buy(leader, mint, at=T0))  # the chain knows nothing about this mint
        await rig.settle()
        [proposal] = await proposals(db_session_factory, spec)
        assert proposal["status"] == "unfilled" and proposal["refusal"] == "sem_estado"


@pytest.mark.asyncio
async def test_a_state_served_at_or_before_the_leaders_slot_is_never_a_price(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        event = buy(leader, mint, at=T0)
        rig.chain.slot_override[mint] = event.slot  # a state from the leader's own slot: too early
        rig.lane.on_item(event)
        await rig.settle()
        [proposal] = await proposals(db_session_factory, spec)
        assert proposal["status"] == "unfilled" and proposal["refusal"] == "sem_estado"
        assert await bets(db_session_factory, spec) == []


@pytest.mark.asyncio
async def test_an_unconfirmed_event_is_acted_on_and_its_confirmation_delay_recorded(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        first = buy(leader, mint, at=T0, confirmed=False, signature="SIG-C1")
        rig.lane.on_item(first)
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["status"] == "open"  # acted on before confirmation
        assert bet["entry"]["copy"]["leader"]["confirmed_at_decision"] is False
        rig.lane.on_item(
            buy(
                leader,
                mint,
                at=T0 + timedelta(milliseconds=830),
                confirmed=True,
                signature="SIG-C1",
                slot=first.slot,
            )
        )
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["entry"]["copy"]["confirmation_delay_ms"] == 830
        assert bet["outcome_quality"] == "measured"
        assert rig.lane.stats.confirm_delay_ms[0] == 830


@pytest.mark.asyncio
async def test_an_event_that_never_confirms_invalidates_the_copy_but_it_stays_in_the_primary(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0, confirmed=False, signature="SIG-C2"))
        await rig.settle()
        rig.clock.advance(seconds=31)  # confirm_timeout_s = 30
        await rig.lane.sweep_once()
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        # sold at market by the same selector, with the economic result it has, flagged by name
        assert bet["status"] == "closed" and bet["outcome_quality"] == "measured"
        assert bet["exit"]["reason"] == "invalidated" and bet["exit"]["sol_received"] != "0"
        assert bet["entry"]["copy"]["invalid_reason"] == "not_found"
        assert rig.lane.stats.invalidated == 1 and rig.lane.book.open_count == 0


@pytest.mark.asyncio
async def test_a_closed_copy_whose_exit_never_confirms_is_only_annotated(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        rig.clock.advance(seconds=10)
        rig.lane.on_item(sell(leader, mint, at=rig.clock.now, confirmed=False, signature="SIG-X"))
        await rig.settle()
        [before] = await bets(db_session_factory, spec)
        assert before["status"] == "closed" and before["outcome_quality"] == "measured"
        rig.clock.advance(seconds=31)
        await rig.lane.sweep_once()
        await rig.settle()
        [after] = await bets(db_session_factory, spec)
        assert after["outcome_quality"] == "measured" and after["pnl_sol"] == before["pnl_sol"]
        assert after["entry"]["copy"]["invalid_reason"] == "not_found"
        assert after["entry"]["copy"]["invalid_event"] == "exit"
