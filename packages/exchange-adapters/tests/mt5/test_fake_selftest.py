"""Self-test of the FAKE MT5 (it is test code; a lying fake would make every contract test lie)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_exchanges.mt5.constants import Filling, OrderState, Retcode, TimeMode
from hunter_exchanges.mt5.models import EntryKind, Side
from hunter_exchanges.mt5.retcodes import Verdict

from .conftest import Env
from .helpers import comment_for, entry_request, open_long, touch

pytestmark = pytest.mark.unit
D = Decimal


async def _rest_far_limit(env: Env, **over: object) -> int:
    bid, _ = await touch(env)
    price = bid - 500 * env.tick_size
    outcome = await env.port.send_entry(
        entry_request(env, price, price - 100 * env.tick_size, **over)
    )
    assert outcome.order_ticket is not None
    return outcome.order_ticket


async def test_a_resting_limit_fills_when_the_market_comes_to_it(fake_env: Env) -> None:
    ticket = await _rest_far_limit(fake_env)
    fake_env.fake.set_quote(127500.0, 127500.0)  # ask reaches the limit price
    (position,) = await fake_env.port.positions()
    assert position.price_open == D("127500") and position.has_stop
    order = await fake_env.port.history_order(ticket)
    assert order is not None and order.state == int(OrderState.FILLED)


async def test_a_resting_limit_with_return_fills_in_parts(fake_env: Env) -> None:
    ticket = await _rest_far_limit(fake_env, volume=D(3), filling=Filling.RETURN)
    fake_env.fake.broker.liquidity = 1
    fake_env.fake.set_quote(127500.0, 127500.0)
    (position,) = await fake_env.port.positions()
    assert position.volume == 1
    (resting,) = await fake_env.port.orders()
    assert resting.ticket == ticket and resting.volume_current == 2
    assert resting.state == int(OrderState.PARTIAL)


async def test_fill_or_kill_is_all_or_nothing(fake_env: Env) -> None:
    fake_env.fake.broker.liquidity = 1
    _, ask = await touch(fake_env)
    request = entry_request(fake_env, ask, ask - 500, volume=D(3), filling=Filling.FOK)
    outcome = await fake_env.port.send_entry(request)
    assert outcome.verdict is Verdict.REJECTED and outcome.retcode_name == "CANCEL"
    assert await fake_env.port.positions() == []


async def test_a_day_order_expires_at_the_close_and_a_dated_one_at_its_time(fake_env: Env) -> None:
    day = await _rest_far_limit(fake_env, comment=comment_for(2))
    dated = await _rest_far_limit(
        fake_env,
        comment=comment_for(3),
        time_in_force=TimeMode.SPECIFIED,
        expiration=fake_env.now() + timedelta(seconds=30),
    )
    fake_env.fake.advance(31)
    assert [o.ticket for o in await fake_env.port.orders()] == [day]
    fake_env.fake.end_of_day()
    assert await fake_env.port.orders() == []
    for ticket in (day, dated):
        order = await fake_env.port.history_order(ticket)
        assert order is not None and order.state == int(OrderState.EXPIRED)


async def test_a_market_deal_outside_the_deviation_is_requoted(fake_env: Env) -> None:
    _, ask = await touch(fake_env)
    request = entry_request(
        fake_env, ask - 5 * fake_env.tick_size, ask - 600, kind=EntryKind.MARKET, deviation_points=1
    )
    outcome = await fake_env.port.send_entry(request)
    assert outcome.verdict is Verdict.REJECTED and outcome.retcode_name == "REQUOTE"


async def test_the_balance_reconciles_with_the_deals_profit_and_commission(
    fake_env: Env,
) -> None:
    before = await fake_env.port.account_info()
    position = await open_long(fake_env)
    during = await fake_env.port.account_info()
    assert during.margin == D("150.00") and during.margin_free < during.equity
    fake_env.fake.manual_sltp(float(position.price_open + 50), 0.0)  # the Everton moves the stop
    fake_env.fake.trade(float(position.price_open + 50))  # stopped at +50 points = 10 ticks
    after = await fake_env.port.account_info()
    deals = await fake_env.port.deals_of_position(position.position_id)
    booked = sum((d.profit + d.commission for d in deals), D(0))
    assert after.balance - before.balance == booked == D("8.00")  # +10.00 profit, 2 x -1.00
    assert after.margin == 0 and after.equity == after.balance


async def test_orders_know_their_position_after_the_fill(fake_env: Env) -> None:
    position = await open_long(fake_env)
    now = fake_env.now()
    (order,) = await fake_env.port.history_orders(now - timedelta(hours=1), now)
    assert order.position_id == position.position_id


async def test_the_session_rollover_zeroes_stops_and_targets(fake_env: Env) -> None:
    await open_long(fake_env)
    fake_env.fake.end_of_day()
    (carried,) = await fake_env.port.positions()
    assert carried.sl == 0 and carried.tp == 0


async def test_order_check_reports_no_money_when_the_margin_does_not_fit(fake_env: Env) -> None:
    fake_env.fake.broker.margin_per_contract = 1_000_000.0
    _, ask = await touch(fake_env)
    result = await fake_env.port.check_entry(entry_request(fake_env, ask, ask - 500))
    assert not result.ok and result.retcode == int(Retcode.NO_MONEY)


REVERSAL = {
    "action": 1, "symbol": "WINZ26", "volume": 2.0, "type": 1, "deviation": 5, "tp": 0.0,
    "magic": 7_000_001, "comment": "raw", "type_filling": 1, "type_time": 1,
}  # fmt: skip


async def test_a_reversal_keeps_the_identifier_and_changes_the_ticket_in_one_inout_deal(
    fake_env: Env,
) -> None:
    old = await open_long(fake_env)
    bid, _ = await touch(fake_env)
    fake_env.fake.order_send({**REVERSAL, "price": float(bid), "sl": float(bid + 500)})
    (new,) = await fake_env.port.positions()
    assert new.side is Side.SELL and new.volume == 1 and new.sl == bid + 500
    assert new.position_id == old.position_id and new.position_ticket != old.position_ticket
    deals = await fake_env.port.deals_of_position(old.position_id)
    assert [d.entry for d in deals] == [0, 2]  # DEAL_ENTRY_IN, then DEAL_ENTRY_INOUT
    assert deals[-1].volume == 2


async def test_the_other_reversal_model_is_available_as_a_hook(fake_env: Env) -> None:
    fake_env.fake.hooks.reversal_new_identifier = True
    old = await open_long(fake_env)
    bid, _ = await touch(fake_env)
    fake_env.fake.order_send({**REVERSAL, "price": float(bid), "sl": float(bid + 500)})
    (new,) = await fake_env.port.positions()
    assert new.position_id != old.position_id
    assert len(await fake_env.port.deals_of_position(old.position_id)) == 2
