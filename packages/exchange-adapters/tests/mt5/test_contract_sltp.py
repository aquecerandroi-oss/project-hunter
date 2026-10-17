"""Contract: `TRADE_ACTION_SLTP` - the exit by bracket and the stop at the server (no live variant:
they need to drive the market)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_exchanges.mt5.constants import DealReason, Retcode, TradeAction
from hunter_exchanges.mt5.errors import Mt5NotSent
from hunter_exchanges.mt5.retcodes import Action, Verdict

from .conftest import Env
from .factories import MAGIC
from .helpers import open_long, sltp_request, touch

pytestmark = pytest.mark.unit
D = Decimal


async def test_a_tightening_sltp_is_applied_and_sends_only_the_bracket_fields(
    fake_env: Env,
) -> None:
    position = await open_long(fake_env)  # sl 129500
    request = sltp_request(fake_env, position, D("129900"), tp=D("130500"))
    outcome = await fake_env.port.send_sltp(request)

    assert outcome.verdict is Verdict.DONE and outcome.action is Action.SLTP
    assert outcome.sltp_request_id == request.sltp_request_id  # correlation (contract §4.3)
    assert outcome.request_position_ticket == position.position_ticket
    (after,) = await fake_env.port.positions()
    assert (after.sl, after.tp) == (D("129900"), D("130500"))
    body = fake_env.fake.sent_requests[-1]
    assert set(body) == {"action", "symbol", "position", "sl", "tp", "magic"}  # §5.1, nothing else
    assert body["action"] == int(TradeAction.SLTP) and body["position"] == position.position_ticket
    assert all(
        isinstance(body[k], float) for k in ("sl", "tp")
    )  # floats exist only at the boundary


async def test_the_same_levels_conclude_with_no_changes(fake_env: Env) -> None:
    position = await open_long(fake_env)
    outcome = await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl))
    assert outcome.verdict is Verdict.DONE and outcome.retcode == int(Retcode.NO_CHANGES)


async def test_the_bracket_at_the_touch_closes_the_position_by_the_server_stop(
    fake_env: Env,
) -> None:
    position = await open_long(fake_env)
    bid, ask = await touch(fake_env)
    request = sltp_request(fake_env, position, bid, tp=ask)  # sl on the bid, tp on the ask (§5.1)
    assert (await fake_env.port.send_sltp(request)).verdict is Verdict.DONE

    fake_env.fake.trade(float(bid))  # the first trade at the bid fires the stop
    assert await fake_env.port.positions() == []
    deals = await fake_env.port.deals_of_position(position.position_id)
    assert [(d.entry, d.reason) for d in deals] == [
        (0, int(DealReason.EXPERT)),
        (1, int(DealReason.SL)),
    ]
    assert {d.magic for d in deals} == {MAGIC}  # the server's stop deal keeps the position's magic


async def test_a_stop_fills_through_a_gap_at_the_printed_price(fake_env: Env) -> None:
    position = await open_long(fake_env)
    fake_env.fake.trade(float(position.sl - 100))  # gap below the stop
    (_, out) = await fake_env.port.deals_of_position(position.position_id)
    assert out.price == position.sl - 100 and out.reason == int(DealReason.SL)


async def test_a_partial_stop_fill_leaves_the_stop_on_the_rest(fake_env: Env) -> None:
    position = await open_long(fake_env, volume=3)
    fake_env.fake.broker.stop_fill_cap = 1
    fake_env.fake.trade(float(position.sl))
    (rest,) = await fake_env.port.positions()
    assert rest.volume == 2 and rest.sl == position.sl  # netting: the partial close keeps sl/tp


async def test_a_stop_the_exchange_refuses_fires_again_on_the_next_trade(fake_env: Env) -> None:
    position = await open_long(fake_env)
    broker = fake_env.fake.broker
    broker.exchange_rejects_stops = True
    fake_env.fake.trade(float(position.sl))
    assert len(await fake_env.port.positions()) == 1  # `sl` present is not an executed exit
    broker.exchange_rejects_stops = False
    fake_env.fake.trade(float(position.sl))
    assert await fake_env.port.positions() == []


async def test_a_server_rejection_of_the_levels_is_terminal_and_changes_nothing(
    fake_env: Env,
) -> None:
    position = await open_long(fake_env)
    fake_env.fake.plan_fault("reject", action=TradeAction.SLTP, retcode=Retcode.INVALID_STOPS)
    outcome = await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl + 100))
    assert outcome.verdict is Verdict.REJECTED and outcome.retcode_name == "INVALID_STOPS"
    (after,) = await fake_env.port.positions()
    assert after.sl == position.sl  # never works around a rejection by removing the stop


async def test_the_brokers_minimum_distance_is_enforced_before_the_terminal(fake_env: Env) -> None:
    position = await open_long(fake_env)
    fake_env.fake.broker.stops_level = 10  # the broker demands 10 points from the touch
    bid, _ = await touch(fake_env)
    sent = len(fake_env.fake.sent_requests)
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_sltp(sltp_request(fake_env, position, bid))
    assert caught.value.reason == "sl_wrong_side_of_touch"
    assert len(fake_env.fake.sent_requests) == sent


async def test_an_uncertain_sltp_result_is_reported_as_uncertain(fake_env: Env) -> None:
    position = await open_long(fake_env)
    fake_env.fake.plan_fault("none_after_effect", action=TradeAction.SLTP)
    request = sltp_request(fake_env, position, D("129900"))
    outcome = await fake_env.port.send_sltp(request)
    assert (
        outcome.verdict is Verdict.UNCERTAIN and outcome.sltp_request_id == request.sltp_request_id
    )
    (after,) = await fake_env.port.positions()
    assert after.sl == D("129900")  # it had taken effect; reading the level proves nothing (§4.3)


async def test_sltp_placed_and_partial_do_not_conclude(fake_env: Env) -> None:
    position = await open_long(fake_env)
    for code in (Retcode.PLACED, Retcode.DONE_PARTIAL):
        fake_env.fake.plan_fault("reject", action=TradeAction.SLTP, retcode=code)
        outcome = await fake_env.port.send_sltp(sltp_request(fake_env, position, D("129900")))
        assert outcome.verdict is Verdict.UNCERTAIN


# ---------------------------------------------------------------- refusals before the terminal


async def test_sl_zero_never_reaches_the_terminal(fake_env: Env) -> None:
    position = await open_long(fake_env)
    sent = len(fake_env.fake.sent_requests)
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_sltp(sltp_request(fake_env, position, D(0)))
    assert caught.value.reason == "sl_missing"
    assert len(fake_env.fake.sent_requests) == sent


async def test_a_looser_stop_is_refused(fake_env: Env) -> None:
    position = await open_long(fake_env)
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl - 100))
    assert caught.value.reason == "sl_looser_than_confirmed"
    with pytest.raises(Mt5NotSent) as floor:
        await fake_env.port.send_sltp(
            sltp_request(fake_env, position, position.sl + 50, floor_sl=position.sl + 100)
        )
    assert floor.value.reason == "sl_looser_than_floor"


async def test_a_stale_ticket_is_refused_and_the_new_ticket_works(fake_env: Env) -> None:
    position = await open_long(fake_env)
    fake_env.fake.service_change_ticket()  # F38: same position_id, new address
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl + 100))
    assert caught.value.reason == "position_ticket_mismatch"
    (moved,) = await fake_env.port.positions()
    assert (
        moved.position_id == position.position_id
        and moved.position_ticket != position.position_ticket
    )
    done = await fake_env.port.send_sltp(sltp_request(fake_env, moved, moved.sl + 100))
    assert done.verdict is Verdict.DONE and done.request_position_ticket == moved.position_ticket


async def test_a_closed_position_is_not_found(fake_env: Env) -> None:
    position = await open_long(fake_env)
    fake_env.fake.trade(float(position.sl))
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl + 100))
    assert caught.value.reason == "position_not_found"


async def test_the_everton_s_manual_position_is_never_touched(fake_env: Env) -> None:
    _, ask = await touch(fake_env)
    fake_env.fake.manual_trade(0, 1.0, float(ask), sl=float(ask - 500))
    (manual,) = await fake_env.port.positions()
    assert manual.magic == 0
    sent = len(fake_env.fake.sent_requests)
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_sltp(sltp_request(fake_env, manual, manual.sl + 100))
    assert caught.value.reason == "position_magic_mismatch"
    assert len(fake_env.fake.sent_requests) == sent


async def test_a_stop_above_the_bid_after_a_gap_never_reaches_the_terminal(fake_env: Env) -> None:
    """floor_unplaceable (contract §4.2, I-SL-6): the level would be on the wrong side of the touch."""
    position = await open_long(fake_env)  # sl 129500
    fake_env.fake.set_quote(129000.0, 129005.0, 129000.0)  # gapped below the stop; no trade yet
    sent = len(fake_env.fake.sent_requests)
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl + 100))
    assert caught.value.reason == "sl_wrong_side_of_touch"
    assert len(fake_env.fake.sent_requests) == sent
    (still,) = await fake_env.port.positions()
    assert still.sl == position.sl  # nothing moved; the server stop is what is left


async def test_an_unreadable_or_invalid_quote_blocks_the_sltp(fake_env: Env) -> None:
    position = await open_long(fake_env)
    fake_env.fake.malform("symbol_info_tick", "nan", "bid")
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl + 100))
    assert caught.value.reason == "quote_unreadable"
    fake_env.fake.malform("symbol_info_tick", None)
    fake_env.fake.set_quote(0.0, 0.0)  # e.g. before the open
    with pytest.raises(Mt5NotSent) as invalid:
        await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl + 100))
    assert invalid.value.reason == "quote_invalid"


async def test_the_session_rollover_erases_the_server_stop_and_the_repair_is_a_new_sltp(
    fake_env: Env,
) -> None:
    position = await open_long(fake_env)
    fake_env.fake.end_of_day()  # the server zeroes sl/tp at the turn of the session (§4.4)
    (carried,) = await fake_env.port.positions()
    assert carried.position_id == position.position_id and not carried.has_stop
    repair = sltp_request(fake_env, carried, position.sl, floor_sl=position.sl)
    assert (await fake_env.port.send_sltp(repair)).verdict is Verdict.DONE
    (back,) = await fake_env.port.positions()
    assert back.sl == position.sl
