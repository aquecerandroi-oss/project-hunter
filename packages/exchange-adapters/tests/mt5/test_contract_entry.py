"""Contract: entries, cancellation and the order lifecycle. `fake_env` tests drive the broker."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from hunter_exchanges.mt5.adapter import Mt5Adapter
from hunter_exchanges.mt5.constants import OrderState, Retcode, TradeAction
from hunter_exchanges.mt5.errors import Mt5NotSent, Mt5ReadError
from hunter_exchanges.mt5.ipc import LateResult
from hunter_exchanges.mt5.models import EntryKind, SendOutcome, Side
from hunter_exchanges.mt5.retcodes import Action, Verdict

from .conftest import Env, load_fakes
from .factories import MAGIC, entry
from .helpers import comment_for, entry_request, open_long, sltp_request, touch

pytestmark = pytest.mark.unit
D = Decimal


# ---------------------------------------------------------------- the lifecycle (fake and live)


async def test_a_far_limit_rests_is_visible_with_magic_and_comment_then_cancels_with_proof(
    env: Env,
) -> None:
    bid, _ = await touch(env)
    price = bid - 500 * env.tick_size
    request = entry_request(env, price, price - 100 * env.tick_size, comment=comment_for(7))
    outcome = await env.port.send_entry(request)
    assert outcome.verdict is Verdict.PLACED and outcome.action is Action.ENTRY
    assert outcome.order_ticket is not None

    resting = await env.port.orders(env.symbol)
    assert [o.ticket for o in resting] == [outcome.order_ticket]
    assert resting[0].magic == MAGIC
    assert resting[0].comment == comment_for(7)  # T8: `comment_preserved`
    assert resting[0].sl == request.sl and resting[0].volume_current == 1

    cancel = await env.port.cancel_order(outcome.order_ticket, magic=MAGIC)
    assert cancel.verdict is Verdict.DONE and cancel.action is Action.CANCEL
    # Accepted is not cancelled: the order must be read in a final state in the history.
    final = await env.port.history_order(outcome.order_ticket)
    assert final is not None and final.state == int(OrderState.CANCELED)
    assert await env.port.orders(env.symbol) == []


async def test_cancelling_an_order_that_is_not_ours_is_refused_before_the_terminal(
    env: Env,
) -> None:
    bid, _ = await touch(env)
    price = bid - 500 * env.tick_size
    other = await env.port.send_entry(
        entry_request(env, price, price - 100 * env.tick_size, magic=1)
    )
    assert other.order_ticket is not None
    with pytest.raises(Mt5NotSent) as caught:
        await env.port.cancel_order(other.order_ticket, magic=MAGIC)
    assert caught.value.reason == "order_magic_mismatch"
    with pytest.raises(Mt5NotSent) as missing:
        await env.port.cancel_order(999_999_999, magic=MAGIC)
    assert missing.value.reason == "order_not_found"
    await env.port.cancel_order(other.order_ticket, magic=1)  # clean up


# ---------------------------------------------------------------- fills (fake)


async def test_a_marketable_limit_fills_and_the_position_is_born_with_its_stop(
    fake_env: Env,
) -> None:
    position = await open_long(fake_env)
    assert position.side is Side.BUY and position.volume == 1
    assert position.sl == D("129500") and position.magic == MAGIC and position.has_stop
    assert position.comment == comment_for(1)
    assert position.position_id == position.position_ticket


async def test_a_market_deal_with_deviation_fills_at_the_touch(fake_env: Env) -> None:
    _, ask = await touch(fake_env)
    request = entry_request(
        fake_env, ask, ask - 100 * fake_env.tick_size, kind=EntryKind.MARKET, deviation_points=5
    )
    outcome = await fake_env.port.send_entry(request)
    assert outcome.verdict is Verdict.DONE and outcome.price == ask
    assert fake_env.fake.sent_requests[-1]["action"] == int(TradeAction.DEAL)
    assert fake_env.fake.sent_requests[-1]["deviation"] == 5


async def test_the_outcome_snaps_the_fill_price_to_the_grid_and_zero_means_none(
    fake_env: Env,
) -> None:
    fake_env.fake.hooks.float_noise = True
    _, ask = await touch(fake_env)
    request = entry_request(
        fake_env, ask, ask - 100 * fake_env.tick_size, kind=EntryKind.MARKET, deviation_points=5
    )
    outcome = await fake_env.port.send_entry(request)
    assert outcome.price == ask and outcome.volume == 1  # not 130005.00000000001
    (position,) = await fake_env.port.positions()
    done = await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl + 100))
    assert done.price is None and done.volume is None  # a SLTP result has no fill


async def test_a_partial_fill_is_reported_with_the_filled_volume(fake_env: Env) -> None:
    fake_env.fake.broker.liquidity = 1
    _, ask = await touch(fake_env)
    request = entry_request(fake_env, ask, ask - 100 * fake_env.tick_size, volume=D(3))
    outcome = await fake_env.port.send_entry(request)
    assert outcome.verdict is Verdict.PARTIAL and outcome.volume == 1
    (position,) = await fake_env.port.positions()
    assert position.volume == 1 and position.has_stop


async def test_a_broker_reject_is_terminal_without_effect(fake_env: Env) -> None:
    fake_env.fake.plan_fault("reject", retcode=Retcode.INVALID_STOPS)
    _, ask = await touch(fake_env)
    outcome = await fake_env.port.send_entry(entry_request(fake_env, ask, ask - 500))
    assert outcome.verdict is Verdict.REJECTED and outcome.retcode_name == "INVALID_STOPS"
    assert await fake_env.port.positions() == []


async def test_algo_trading_off_is_a_rejection_not_an_exception(fake_env: Env) -> None:
    fake_env.fake.algo_trading = False
    assert (await fake_env.port.terminal_info()).trade_allowed is False
    _, ask = await touch(fake_env)
    outcome = await fake_env.port.send_entry(entry_request(fake_env, ask, ask - 500))
    assert outcome.verdict is Verdict.REJECTED and outcome.retcode_name == "CLIENT_DISABLES_AT"


# ---------------------------------------------------------------- uncertain results: never resend


async def test_no_result_after_the_effect_is_uncertain_and_the_position_exists(
    fake_env: Env,
) -> None:
    fake_env.fake.plan_fault("none_after_effect")
    _, ask = await touch(fake_env)
    outcome = await fake_env.port.send_entry(entry_request(fake_env, ask, ask - 500))
    assert outcome.verdict is Verdict.UNCERTAIN and outcome.error == "none_result"
    assert outcome.retcode is None and outcome.last_error is not None
    assert len(await fake_env.port.positions()) == 1  # the order DID execute


async def test_no_result_without_effect_is_just_as_uncertain(fake_env: Env) -> None:
    fake_env.fake.plan_fault("none_no_effect")
    _, ask = await touch(fake_env)
    outcome = await fake_env.port.send_entry(entry_request(fake_env, ask, ask - 500))
    assert outcome.verdict is Verdict.UNCERTAIN  # the adapter cannot tell the two apart
    assert await fake_env.port.positions() == []


async def test_an_exception_during_the_call_is_an_uncertain_outcome_not_a_raise(
    fake_env: Env,
) -> None:
    fake_env.fake.plan_fault("raise")
    _, ask = await touch(fake_env)
    outcome = await fake_env.port.send_entry(entry_request(fake_env, ask, ask - 500))
    assert outcome.verdict is Verdict.UNCERTAIN and outcome.error == "exception:RuntimeError"


async def test_a_hung_call_latches_the_lane_and_the_late_result_is_kept(fake_env: Env) -> None:
    fake = fake_env.fake
    fake.plan_fault("hang")
    _, ask = await touch(fake_env)
    outcome = await fake_env.port.send_entry(entry_request(fake_env, ask, ask - 500))
    assert outcome.verdict is Verdict.UNCERTAIN and outcome.error == "ipc_timeout"
    assert fake_env.port.ipc_hung is True
    sent = len(fake.sent_requests)

    with pytest.raises(Mt5ReadError) as refused_read:  # reads are refused too
        await fake_env.port.tick(fake_env.symbol)
    assert refused_read.value.reason.startswith("ipc_hung")
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_entry(entry_request(fake_env, ask, ask - 500))
    assert caught.value.reason == "guard_ipc_hung"
    assert len(fake.sent_requests) == sent  # nothing else reached the terminal

    fake.release_hang()  # the stuck call finally returns: its real outcome is not lost
    late: list[LateResult] = []
    for _ in range(100):
        late = fake_env.port.drain_late_results()
        if late:
            break
        await asyncio.sleep(0.02)
    assert late and late[0].name == "order_send"
    assert isinstance(late[0].value, SendOutcome) and late[0].value.retcode == int(Retcode.DONE)
    assert len(fake.broker.positions) == 1


# ---------------------------------------------------------------- refusals before the terminal


async def test_off_grid_numbers_are_refused_not_rounded(fake_env: Env) -> None:
    fake = fake_env.fake
    _, ask = await touch(fake_env)
    cases = {
        "price_off_tick": entry_request(fake_env, ask + 1, ask - 500),
        "sl_off_tick": entry_request(fake_env, ask, ask - 501),
        "volume_off_step": entry_request(fake_env, ask, ask - 500, volume=D("1.5")),
    }
    for reason, request in cases.items():
        with pytest.raises(Mt5NotSent) as caught:
            await fake_env.port.send_entry(request)
        assert caught.value.reason == reason
    assert fake.sent_requests == []


async def test_without_a_pinned_spec_there_are_no_entries() -> None:
    fake = load_fakes().FakeMt5()
    port = Mt5Adapter(fake)
    await port.attach()
    with pytest.raises(Mt5NotSent) as caught:
        await port.send_entry(entry(price=D("130005"), sl=D("129500")))
    assert caught.value.reason == "spec_not_pinned"
    assert fake.sent_requests == []
    await port.shutdown()


async def test_a_changed_tick_size_refuses_entries_but_not_exits(fake_env: Env) -> None:
    position = await open_long(fake_env)
    fake = fake_env.fake
    sent = len(fake.sent_requests)
    fake.broker.tick_size = 10.0  # the exchange redefined the contract
    _, ask = await touch(fake_env)
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_entry(entry_request(fake_env, ask, ask - 500))
    assert caught.value.reason == "spec_changed" and "trade_tick_size" in caught.value.detail
    assert len(fake.sent_requests) == sent
    # A good read afterwards does not clear it (latched), and exits keep working.
    fake.broker.tick_size = 5.0
    with pytest.raises(Mt5NotSent):
        await fake_env.port.send_entry(entry_request(fake_env, ask, ask - 500))
    done = await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl + 100))
    assert done.verdict is Verdict.DONE


async def test_a_delisted_symbol_is_unreadable_and_blocks_entries(fake_env: Env) -> None:
    _, ask = await touch(fake_env)
    request = entry_request(fake_env, ask, ask - 500)
    fake_env.fake.delist()
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_entry(request)
    assert caught.value.reason == "spec_unreadable"
    assert fake_env.fake.sent_requests == []
    assert (await fake_env.port.refresh_spec(fake_env.symbol)).value == "ok"  # 1 failure of 3


# ---------------------------------------------------------------- would_delete_stop (I-X-2)


async def test_an_increase_with_sl_zero_never_reaches_the_terminal(fake_env: Env) -> None:
    position = await open_long(fake_env)
    sent = len(fake_env.fake.sent_requests)
    _, ask = await touch(fake_env)
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_entry(entry_request(fake_env, ask, D(0)))
    assert caught.value.reason == "would_delete_stop"
    assert len(fake_env.fake.sent_requests) == sent
    (still,) = await fake_env.port.positions()
    assert still.sl == position.sl


async def test_an_increase_that_loosens_the_stop_is_refused_and_a_tighter_one_replaces_it(
    fake_env: Env,
) -> None:
    position = await open_long(fake_env)
    _, ask = await touch(fake_env)
    with pytest.raises(Mt5NotSent) as caught:
        await fake_env.port.send_entry(entry_request(fake_env, ask, position.sl - 100))
    assert caught.value.reason == "would_loosen_stop"
    tighter = position.sl + 100
    await fake_env.port.send_entry(entry_request(fake_env, ask, tighter))
    (grown,) = await fake_env.port.positions()
    assert grown.volume == 2 and grown.sl == tighter  # netting inheritance: replaced


async def test_reduce_and_close_are_never_refused_for_the_stop(fake_env: Env) -> None:
    await open_long(fake_env, volume=2)
    bid, _ = await touch(fake_env)
    reduce_ = entry_request(fake_env, bid, D(0), side=Side.SELL, kind=EntryKind.MARKET)
    sl_before = (await fake_env.port.positions())[0].sl
    assert (await fake_env.port.send_entry(reduce_)).verdict is Verdict.DONE
    (left,) = await fake_env.port.positions()
    assert left.volume == 1 and left.sl == sl_before  # a partial close leaves the stop alone
    close = entry_request(fake_env, bid, D(0), side=Side.SELL, kind=EntryKind.MARKET)
    assert (await fake_env.port.send_entry(close)).verdict is Verdict.DONE
    assert await fake_env.port.positions() == []


async def test_the_fake_reproduces_the_trap_the_guard_exists_for(fake_env: Env) -> None:
    """Sending the same increase straight to the terminal erases the stop: the guard is not theatre."""
    position = await open_long(fake_env)
    _, ask = await touch(fake_env)
    body = {
        "action": int(TradeAction.PENDING), "symbol": fake_env.symbol, "volume": 1.0,
        "type": 2, "price": float(ask), "sl": 0.0, "tp": 0.0, "magic": MAGIC,
        "comment": "raw", "type_filling": 1, "type_time": 1,
    }  # fmt: skip
    fake_env.fake.order_send(body)
    (after,) = await fake_env.port.positions()
    assert position.has_stop and after.volume == 2 and not after.has_stop
