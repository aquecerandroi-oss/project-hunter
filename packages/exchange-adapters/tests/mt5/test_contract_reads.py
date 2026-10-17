"""Contract: reads. Runs against the fake, and against a demo terminal when marked live."""

from __future__ import annotations

from datetime import UTC, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.mt5.errors import Mt5NotSent, Mt5ReadError
from hunter_exchanges.mt5.models import AccountMode, EntryKind, Side

from .conftest import Env
from .helpers import entry_request, touch

pytestmark = pytest.mark.unit


async def test_the_terminal_reports_its_state(env: Env) -> None:
    info = await env.port.terminal_info()
    assert info.connected is True
    assert isinstance(info.trade_allowed, bool)
    assert info.read_at.tzinfo is UTC


async def test_the_account_is_identified_by_a_hash_and_is_demo(env: Env) -> None:
    account = await env.port.account_info()
    assert len(account.account_hash) == 64
    assert account.trade_mode is AccountMode.DEMO
    for money in (account.balance, account.equity, account.margin, account.margin_free):
        assert isinstance(money, Decimal)
    assert account.currency_digits >= 0


async def test_the_spec_is_decimal_and_consistent(env: Env) -> None:
    spec = await env.port.symbol_spec(env.symbol)
    assert spec.symbol == env.symbol
    assert spec.trade_tick_size > 0 and spec.volume_step > 0
    assert spec.volume_min <= spec.volume_max
    assert isinstance(spec.trade_tick_size, Decimal)


async def test_the_tick_is_on_the_grid_and_timestamps_are_utc(env: Env) -> None:
    tick = await env.port.tick(env.symbol)
    assert 0 < tick.bid <= tick.ask
    assert tick.bid % env.tick_size == 0 and tick.ask % env.tick_size == 0
    assert tick.server_time.tzinfo is UTC and tick.received_at.tzinfo is UTC


async def test_a_flat_account_has_no_positions_and_no_orders(env: Env) -> None:
    assert await env.port.positions() == []
    assert await env.port.positions(env.symbol) == []
    assert await env.port.orders() == []


async def test_history_windows_return_lists(env: Env) -> None:
    now = env.now()
    since, until = now - timedelta(days=1), now + timedelta(minutes=1)
    assert isinstance(await env.port.history_deals(since, until), list)
    assert isinstance(await env.port.history_orders(since, until), list)
    assert await env.port.history_order(2_000_000_000) is None


async def test_calc_margin_is_a_positive_decimal(env: Env) -> None:
    _, ask = await touch(env)
    margin = await env.port.calc_margin(Side.BUY, env.symbol, Decimal(1), ask)
    assert isinstance(margin, Decimal) and margin > 0


async def test_order_check_accepts_a_sane_far_limit(env: Env) -> None:
    bid, _ = await touch(env)
    request = entry_request(
        env, bid - 500 * env.tick_size, bid - 600 * env.tick_size, kind=EntryKind.LIMIT
    )
    result = await env.port.check_entry(request)
    assert result.ok, result
    assert isinstance(result.margin, Decimal)


async def test_order_check_refuses_a_volume_above_the_maximum_before_the_terminal(
    env: Env,
) -> None:
    spec = await env.port.symbol_spec(env.symbol)
    bid, _ = await touch(env)
    request = entry_request(
        env, bid - 500 * env.tick_size, bid - 600 * env.tick_size, volume=spec.volume_max + 1
    )
    with pytest.raises(Mt5NotSent) as caught:
        await env.port.check_entry(request)
    assert caught.value.reason == "volume_out_of_range"


async def test_an_unknown_symbol_is_an_error_never_an_empty_spec(env: Env) -> None:
    with pytest.raises(Mt5ReadError) as caught:
        await env.port.symbol_spec("NOSUCHSYMBOL")
    assert caught.value.reason == "none_result"
    assert caught.value.last_error is not None


async def test_the_spec_snapshot_covers_the_pinned_fields(env: Env) -> None:
    snapshot = await env.port.read_spec_snapshot(env.symbol)
    assert snapshot.symbol == env.symbol
    assert snapshot.package_version and snapshot.terminal_version
    assert snapshot.account_margin_mode in {"netting", "exchange", "hedging"}


async def test_every_decimal_field_is_a_decimal_never_a_float(env: Env) -> None:
    models: list[Any] = [
        await env.port.account_info(),
        await env.port.symbol_spec(env.symbol),
        await env.port.tick(env.symbol),
    ]
    for model in models:
        for name, value in model:
            assert not isinstance(value, float), f"{type(model).__name__}.{name}"


@pytest.mark.parametrize("bad", [True, False, float("nan"), "12", float("inf")])
async def test_a_malformed_margin_is_a_read_error_never_a_number(
    fake_env: Env, bad: object
) -> None:
    def broken(*_args: Any, **_kw: Any) -> object:
        return bad

    fake_env.fake.order_calc_margin = broken
    _, ask = await touch(fake_env)
    with pytest.raises(Mt5ReadError) as caught:
        await fake_env.port.calc_margin(Side.BUY, fake_env.symbol, Decimal(1), ask)
    assert caught.value.reason == "malformed:margin"


@pytest.mark.parametrize(("mode", "field"), [("wrong_type", "margin"), ("nan", "margin_free")])
async def test_a_malformed_order_check_is_a_read_error(
    fake_env: Env, mode: str, field: str
) -> None:
    fake_env.fake.malform("order_check", mode, field)
    bid, _ = await touch(fake_env)
    request = entry_request(
        fake_env, bid - 500 * fake_env.tick_size, bid - 600 * fake_env.tick_size
    )
    with pytest.raises(Mt5ReadError) as caught:
        await fake_env.port.check_entry(request)
    assert caught.value.reason == f"malformed:{field}"
