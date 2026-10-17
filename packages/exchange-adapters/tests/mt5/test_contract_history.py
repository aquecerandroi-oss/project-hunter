"""Contract: history deals (magic, reason, comment), duplicates, gaps, reconnects, malformed answers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.mt5.constants import DealEntry, DealReason, OrderState
from hunter_exchanges.mt5.errors import Mt5ReadError
from hunter_exchanges.mt5.models import Side

from .conftest import Env
from .factories import MAGIC
from .helpers import comment_for, entry_request, open_long, touch

pytestmark = pytest.mark.unit
D = Decimal


# ---------------------------------------------------------------- attribution inputs (§4.5)


async def test_deals_of_a_position_carry_magic_reason_and_comment(fake_env: Env) -> None:
    position = await open_long(fake_env)
    fake_env.fake.trade(float(position.sl))
    entry, stop = await fake_env.port.deals_of_position(position.position_id)
    assert (entry.entry, entry.reason, entry.magic) == (
        int(DealEntry.IN),
        int(DealReason.EXPERT),
        MAGIC,
    )
    assert (stop.entry, stop.reason, stop.magic) == (int(DealEntry.OUT), int(DealReason.SL), MAGIC)
    assert entry.comment == comment_for(1) and entry.symbol == fake_env.symbol
    assert entry.time.tzinfo is not None and entry.time <= stop.time
    assert isinstance(entry.price, Decimal) and isinstance(entry.commission, Decimal)


async def test_a_manual_deal_is_visible_as_client_with_magic_zero(fake_env: Env) -> None:
    position = await open_long(fake_env, volume=2)
    bid, _ = await touch(fake_env)
    fake_env.fake.manual_trade(1, 1.0, float(bid))  # the Everton sells one by hand
    deals = await fake_env.port.deals_of_position(position.position_id)
    assert [d.reason for d in deals] == [int(DealReason.EXPERT), int(DealReason.CLIENT)]
    assert deals[-1].magic == 0 and deals[-1].comment == ""


async def test_when_the_broker_drops_comment_and_magic_the_adapter_reports_what_it_sees(
    fake_env: Env,
) -> None:
    fake_env.fake.hooks.drop_comment = True
    fake_env.fake.hooks.drop_magic = True
    position = await open_long(fake_env)
    assert position.comment == "" and position.magic == 0  # T8 would fail; the data is honest
    (deal,) = await fake_env.port.deals_of_position(position.position_id)
    assert deal.magic == 0 and deal.comment == ""


async def test_history_orders_expose_the_stop_the_order_asked_for(fake_env: Env) -> None:
    position = await open_long(fake_env)
    now = fake_env.now()
    history = await fake_env.port.history_orders(now - timedelta(hours=1), now + timedelta(hours=1))
    (order,) = history
    assert order.state == int(OrderState.FILLED) and order.sl == position.sl  # `ORDER_SL` (§4.4)
    assert order.volume_current == 0


async def test_a_duplicated_deal_in_the_answer_is_counted_once(fake_env: Env) -> None:
    position = await open_long(fake_env)
    fake_env.fake.hooks.duplicate_deals = True
    deals = await fake_env.port.deals_of_position(position.position_id)
    assert len(deals) == 1
    now = fake_env.now()
    assert len(await fake_env.port.history_deals(now - timedelta(hours=1), now)) == 1


async def test_two_different_deals_with_the_same_ticket_are_corrupt_data(fake_env: Env) -> None:
    position = await open_long(fake_env)
    fake = fake_env.fake
    original = fake.history_deals_get

    def corrupt(*args: Any, **kwargs: Any) -> Any:
        rows = original(*args, **kwargs)
        return (*rows, rows[0]._replace(volume=9.0))

    fake.history_deals_get = corrupt
    with pytest.raises(Mt5ReadError) as caught:
        await fake_env.port.deals_of_position(position.position_id)
    assert caught.value.reason.startswith("malformed:duplicate_ticket")


async def test_history_before_the_floor_is_missing_not_invented(fake_env: Env) -> None:
    position = await open_long(fake_env)
    fake_env.fake.hooks.history_floor_ms = fake_env.fake.broker.now_ms + 1  # a gap in the history
    assert await fake_env.port.deals_of_position(position.position_id) == []


async def test_history_unavailable_is_an_error_not_an_empty_list(fake_env: Env) -> None:
    fake_env.fake.hooks.history_unavailable = True
    now = fake_env.now()
    with pytest.raises(Mt5ReadError) as caught:
        await fake_env.port.history_deals(now - timedelta(hours=1), now)
    assert caught.value.reason == "none_result" and caught.value.last_error is not None


# ---------------------------------------------------------------- reconnect with a gap


async def test_a_stop_fired_while_disconnected_is_found_after_the_reconnect(fake_env: Env) -> None:
    position = await open_long(fake_env)
    fake = fake_env.fake
    fake.disconnect()
    fake.trade(float(position.sl))  # the SERVER executes the stop while the terminal is off
    for read in (fake_env.port.positions, fake_env.port.terminal_info, fake_env.port.account_info):
        with pytest.raises(Mt5ReadError) as caught:
            await read()
        assert caught.value.last_error == (-10004, "No IPC connection")
    fake.reconnect()
    assert await fake_env.port.positions() == []
    deals = await fake_env.port.deals_of_position(position.position_id)
    assert [d.reason for d in deals][-1] == int(DealReason.SL)


async def test_a_disconnect_between_the_check_and_the_send_is_an_uncertain_outcome(
    fake_env: Env,
) -> None:
    _, ask = await touch(fake_env)
    request = entry_request(fake_env, ask, ask - 500)
    fake_env.fake.plan_fault("none_no_effect")
    outcome = await fake_env.port.send_entry(request)
    assert outcome.error == "none_result" and outcome.last_error == (-10001, "Send failed")


# ---------------------------------------------------------------- malformed answers


READS: dict[str, Callable[[Env], Awaitable[Any]]] = {
    "positions_get": lambda e: e.port.positions(),
    "account_info": lambda e: e.port.account_info(),
    "terminal_info": lambda e: e.port.terminal_info(),
    "symbol_info": lambda e: e.port.symbol_spec(e.symbol),
    "symbol_info_tick": lambda e: e.port.tick(e.symbol),
    "history_deals_get": lambda e: e.port.deals_of_position(1001),
    "orders_get": lambda e: e.port.orders(),
}


@pytest.mark.parametrize(
    ("function", "mode", "field"),
    [
        ("positions_get", "missing", "sl"),
        ("positions_get", "missing", "symbol"),
        ("positions_get", "nan", "price_open"),
        ("positions_get", "wrong_type", "magic"),
        ("account_info", "nan", "equity"),
        ("account_info", "missing", "currency_digits"),
        ("terminal_info", "missing", "connected"),
        ("symbol_info", "missing", "trade_tick_size"),
        ("symbol_info", "nan", "volume_step"),
        ("symbol_info_tick", "wrong_type", "bid"),
        ("history_deals_get", "missing", "reason"),
        ("orders_get", "nan", "volume_current"),
    ],
)
async def test_a_malformed_answer_is_a_read_error_naming_the_field(
    fake_env: Env, function: str, mode: str, field: str
) -> None:
    if function == "orders_get":  # needs a resting order, on a flat account
        bid, _ = await touch(fake_env)
        price = bid - 500 * fake_env.tick_size
        await fake_env.port.send_entry(entry_request(fake_env, price, price - 100, comment="HB1"))
    else:
        await open_long(fake_env)  # a position and a deal to be malformed
    fake_env.fake.malform(function, mode, field)
    with pytest.raises(Mt5ReadError) as caught:
        await READS[function](fake_env)
    assert caught.value.reason == f"malformed:{field}"


async def test_float_noise_from_the_terminal_snaps_back_to_the_grid(fake_env: Env) -> None:
    fake_env.fake.hooks.float_noise = True
    position = await open_long(fake_env)
    assert position.price_open == D("130005") and position.sl == D("129500")
    tick = await fake_env.port.tick(fake_env.symbol)
    assert (tick.bid, tick.ask) == (D("130000"), D("130005"))
    assert position.volume == 1 and position.side is Side.BUY
