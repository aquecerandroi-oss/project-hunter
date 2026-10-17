"""The late facts of a copy against a real Postgres (H-037, R2 fix B5/B6 and the sensitivities): an
`rpc_error` that never became a verdict flags the copy `unverified` and keeps it; the chain's post-trade
reserves (`ideal`) and a second read at decision + 3.9 s (`p90`) are persisted as secondary fields; an
exit's confirmation lands on the exit even when it overtakes its own close. Paper only."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.leader_events import PostReserves
from hunter_meme_worker import copy_exec

from .copy_fakes import Curve
from .copy_rig import WORKER, addr, bets, mint_address, rule_set, running
from .copy_support import T0, buy, confirmation, sell

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("fast_retries")]


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(copy_exec, "RETRY_BASE_S", 0.0)
    monkeypatch.setattr(copy_exec, "WAIT_S", 0.0)


@pytest.mark.asyncio
async def test_an_rpc_error_that_never_became_a_verdict_flags_the_copy_unverified_and_keeps_it(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        event = buy(leader, mint, at=T0, confirmed=False, signature="RPC-ONLY")
        rig.lane.on_item(event)
        await rig.settle()
        rig.lane.on_item(confirmation(event, "rpc_error"))
        rig.clock.advance(seconds=31)  # confirm_timeout_s = 30
        await rig.lane.sweep_once()
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["status"] == "open" and bet["outcome_quality"] == "measured"  # NOT liquidated
        assert bet["entry"]["copy"]["unverified"] is True
        assert bet["entry"]["copy"]["invalid_reason"] is None  # nothing invalidated it
        assert rig.lane.stats.unverified == 1 and rig.lane.stats.invalidated == 0


@pytest.mark.asyncio
async def test_the_ideal_post_trade_reserves_and_the_p90_read_are_persisted_as_secondary_fields(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve(vsol="30", vtok="1073000000"))
        # the market moves 2 s after the decision: the nominal fill (decision + 250 ms) sees the old
        # state, the p90 read (decision + 3.9 s) must see THIS one
        rig.chain.set(
            mint, Curve(vsol="31", vtok="1036000000"), at=rig.clock.now + timedelta(seconds=2)
        )
        event = buy(leader, mint, at=T0, confirmed=False, signature="IDEAL")
        rig.lane.on_item(event)
        await rig.settle()
        reserves = PostReserves("curve", 31_000_000_000, 1_036_000_000_000, None, 1_000_000_000)
        rig.lane.on_item(confirmation(event, post_reserves=reserves))
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        copy = bet["entry"]["copy"]
        assert copy["ideal_post_reserves"] == {
            "venue": "curve",
            "sol_reserves": 31_000_000_000,
            "token_reserves": 1_036_000_000_000,
            "virtual_quote_reserves": None,
            "real_sol_reserves": 1_000_000_000,
        }
        p90 = copy["sensitivity_p90"]
        assert p90["latency_s"] == "3.9" and "unavailable" not in p90
        assert p90["priced_at"] >= (T0 + timedelta(milliseconds=3900)).isoformat(
            timespec="milliseconds"
        )
        assert p90["tokens"] != bet["entry"]["tokens"]  # another state, another fill
        assert bet["status"] == "open"  # secondary: the primary fill is untouched


@pytest.mark.asyncio
async def test_the_p90_exit_is_priced_from_the_p90_entry_when_causal_order_allows(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        rig.clock.advance(seconds=60)
        rig.lane.on_item(sell(leader, mint, at=rig.clock.now))
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        p90 = bet["exit"]["copy"]["sensitivity_p90"]
        assert "sol_received" in p90 and "pnl_sol" in p90 and "unavailable" not in p90


@pytest.mark.asyncio
async def test_an_exit_confirmation_that_overtakes_its_close_is_written_after_it_landed(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        rig.lane.on_item(buy(leader, mint, at=T0))
        await rig.settle()
        rig.clock.advance(seconds=30)
        sale = sell(leader, mint, at=rig.clock.now, confirmed=False, signature="EXIT-CONF")
        rig.lane.on_item(sale)
        rig.lane.on_item(confirmation(sale, at=rig.clock.now + timedelta(milliseconds=500)))
        await rig.settle()
        [bet] = await bets(db_session_factory, spec)
        assert bet["status"] == "closed"
        assert bet["exit"]["copy"]["confirmation_delay_ms"] == 500  # on the exit, not lost
        assert rig.lane.stats.annotation_lost == 0 and rig.lane.stats.confirm_delay_ms[0] == 500
        async with role_session(db_session_factory, db_role=WORKER) as session:
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM meme_paper_bets WHERE rule_set_id = CAST(:r AS uuid)"
                    ),
                    {"r": spec.id},
                )
            ) == 1


@pytest.mark.asyncio
async def test_an_unverified_copy_is_not_resurrected_as_a_pending_confirmation_after_a_restart(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    leader, mint = addr("A"), mint_address()
    spec = await rule_set(db_engine, leader, addr("B"))
    async with running(spec, db_session_factory) as rig:
        rig.chain.set(mint, Curve())
        event = buy(leader, mint, at=T0, confirmed=False, signature="UNV-RESTART")
        rig.lane.on_item(event)
        await rig.settle()
        rig.lane.on_item(confirmation(event, "rpc_error"))
        rig.clock.advance(seconds=31)
        await rig.lane.sweep_once()
        await rig.settle()
    async with running(spec, db_session_factory, recover=True) as again:
        assert again.lane.book.open_count == 1  # the copy is still there ...
        assert (
            again.lane.book.expired_confirmations(T0 + timedelta(hours=1)) == []
        )  # ... owes nothing
