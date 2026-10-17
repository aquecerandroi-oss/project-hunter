"""The IPC lane (deadline, latch, late results) and the secret rules (I-S-1)."""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import inspect
import json
import threading
import time
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
import structlog

from hunter_exchanges.mt5.adapter import Mt5Adapter, Mt5Config
from hunter_exchanges.mt5.errors import Mt5IpcTimeout, Mt5NotSent, Mt5ReadError
from hunter_exchanges.mt5.ipc import IpcExecutor, LateResult
from hunter_exchanges.mt5.models import SendOutcome
from hunter_exchanges.mt5.retcodes import Action, Verdict

from .conftest import Env, load_fakes
from .helpers import entry_request, open_long, sltp_request, touch

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------- the lane


async def test_a_call_past_the_deadline_latches_and_every_later_call_is_refused_at_once() -> None:
    release = threading.Event()
    lane = IpcExecutor(timeout_s=0.1, error_probe=lambda: (1, "Success"))
    started = time.monotonic()
    with pytest.raises(Mt5IpcTimeout):
        await lane.call(
            "stuck",
            lambda: (release.wait(5), "late value")[1],
            on_late=lambda result, _err: result,
        )
    assert time.monotonic() - started < 1.0
    assert lane.hung and lane.hung_call == "stuck"

    started = time.monotonic()
    with pytest.raises(Mt5ReadError) as caught:
        await lane.call("next", lambda: "never runs")
    assert caught.value.reason == "ipc_hung:stuck" and time.monotonic() - started < 0.5

    release.set()
    late: list[LateResult] = []
    for _ in range(100):
        late = lane.drain_late_results()
        if late:
            break
        await asyncio.sleep(0.02)
    assert late[0].name == "stuck" and late[0].value == "late value"
    assert lane.hung  # the latch falls only with a restart of the process
    lane.close()


async def test_a_fast_call_returns_its_result_and_the_error_only_when_the_result_is_none() -> None:
    lane = IpcExecutor(timeout_s=1.0, error_probe=lambda: (-4, "Terminal: Not found"))
    assert await lane.call("ok", lambda: 42) == (42, None)
    assert await lane.call("none", lambda: None) == (None, (-4, "Terminal: Not found"))
    lane.close()


async def test_shutdown_after_a_hang_does_not_wait_for_the_stuck_thread(fake_env: Env) -> None:
    fake_env.fake.plan_fault("hang")
    _, ask = await touch(fake_env)
    await fake_env.port.send_entry(entry_request(fake_env, ask, ask - 500))
    started = time.monotonic()
    await fake_env.port.shutdown()
    assert time.monotonic() - started < 1.0


async def test_work_queued_behind_a_hung_call_never_starts_once_the_lane_is_latched() -> None:
    """F4/G5: a mutation still waiting when the lane latches must not run when the stuck call returns."""
    release = threading.Event()
    ran: list[str] = []
    lane = IpcExecutor(timeout_s=0.1, error_probe=lambda: (1, "Success"))

    def stuck() -> bool:
        return release.wait(5)

    a = asyncio.create_task(lane.call("A", stuck))  # submitted first; latches the lane at 0.1 s
    await asyncio.sleep(0.02)  # A has started
    queued = asyncio.create_task(
        lane.call(
            "B", lambda: ran.append("B"), mutation=True, timeout_s=5.0
        )  # outlives A's deadline
    )
    with pytest.raises(Mt5IpcTimeout) as stuck_call:
        await a
    assert stuck_call.value.started is True and lane.hung
    release.set()  # A returns; the worker now reaches B
    with pytest.raises(Mt5IpcTimeout) as skipped:
        await queued
    assert skipped.value.started is False
    assert ran == []  # B never started
    lane.close()


async def test_a_call_that_times_out_in_the_queue_is_abandoned_and_does_not_latch() -> None:
    release = threading.Event()
    ran: list[str] = []
    lane = IpcExecutor(timeout_s=0.1, error_probe=lambda: (1, "Success"))
    slow = asyncio.create_task(lane.call("slow", lambda: release.wait(5), timeout_s=5.0))
    await asyncio.sleep(0.05)  # `slow` has started
    with pytest.raises(Mt5IpcTimeout) as queued:
        await lane.call("B", lambda: ran.append("B"), mutation=True)  # waits 0.1 s, never starts
    assert queued.value.started is False
    assert not lane.hung and not lane.unresolved  # a legitimately slow call is not a hang
    release.set()
    await slow
    await asyncio.sleep(0.2)
    assert ran == []  # abandoned means abandoned
    lane.close()


async def test_a_send_that_never_left_the_queue_is_not_sent_rather_than_uncertain() -> None:
    fake = load_fakes().FakeMt5()
    release = threading.Event()
    real = fake.account_info

    def slow() -> Any:
        release.wait(5)
        return real()

    fake.account_info = slow
    port = Mt5Adapter(fake, config=Mt5Config(ipc_call_timeout_s=0.2))
    await port.attach()
    stuck_read = asyncio.create_task(port.account_info())
    await asyncio.sleep(0.05)  # the read is inside the terminal call
    body = {"action": 6, "symbol": "WINZ26", "position": 1, "sl": 1.0, "tp": 0.0, "magic": 1}
    with pytest.raises(Mt5NotSent) as caught:
        await port._send(Action.SLTP, body)  # pyright: ignore[reportPrivateUsage]
    assert caught.value.reason == "guard_ipc_hung"
    with pytest.raises(Mt5ReadError):
        await stuck_read
    release.set()
    await asyncio.sleep(0.2)
    assert fake.sent_requests == []  # nothing ever reached order_send
    await port.shutdown()


async def test_a_concurrent_second_entry_behind_a_hung_send_is_never_sent(fake_env: Env) -> None:
    fake = fake_env.fake
    fake.plan_fault("hang")
    _, ask = await touch(fake_env)
    request = entry_request(fake_env, ask, ask - 500)
    first, second = await asyncio.gather(
        fake_env.port.send_entry(request),
        fake_env.port.send_entry(request),
        return_exceptions=True,
    )
    assert getattr(first, "verdict", None) is Verdict.UNCERTAIN or isinstance(first, Mt5NotSent)
    assert isinstance(second, Mt5NotSent) or getattr(second, "verdict", None) is Verdict.UNCERTAIN
    assert fake_env.port.ipc_hung
    fake.release_hang()
    await asyncio.sleep(0.4)
    assert len(fake.sent_requests) == 1  # only the first request ever reached the terminal
    assert len(fake.broker.positions) <= 1


async def test_cancelling_a_send_leaves_an_unresolved_send_that_blocks_new_mutations(
    fake_env: Env,
) -> None:
    fake = fake_env.fake
    fake.plan_fault("hang")
    _, ask = await touch(fake_env)
    request = entry_request(fake_env, ask, ask - 500)
    task = asyncio.create_task(fake_env.port.send_entry(request))
    for _ in range(200):  # wait until the terminal call is in progress
        if fake.hang_entered.is_set():
            break
        await asyncio.sleep(0.01)
    assert fake.hang_entered.is_set()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    with pytest.raises(Mt5NotSent) as caught:  # the first send may have executed: no new mutation
        await fake_env.port.send_entry(request)
    assert caught.value.reason == "guard_unresolved_send"
    assert len(fake.sent_requests) == 1

    fake.release_hang()  # it did execute; its result is kept, normalized, for the caller
    late: list[LateResult] = []
    for _ in range(200):
        late = fake_env.port.drain_late_results()
        if late:
            break
        await asyncio.sleep(0.02)
    assert late and isinstance(late[0].value, SendOutcome)
    assert late[0].value.verdict is Verdict.DONE and late[0].value.error == "late_result"
    assert len(fake.broker.positions) == 1
    # once the caller has collected it, mutations are allowed again
    (position,) = await fake_env.port.positions()
    done = await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl + 100))
    assert done.verdict is Verdict.DONE


async def test_a_late_read_result_never_exposes_the_raw_object() -> None:
    """`account_info` returned late would carry `login` and `server` (I-S-1)."""
    fake = load_fakes().FakeMt5()
    release = threading.Event()
    real = fake.account_info

    def slow() -> Any:
        release.wait(5)
        return real()

    fake.account_info = slow
    port = Mt5Adapter(fake, config=Mt5Config(ipc_call_timeout_s=0.1))
    with pytest.raises(Mt5ReadError):
        await port.account_info()
    release.set()
    late: list[LateResult] = []
    for _ in range(100):
        late = port.drain_late_results()
        if late:
            break
        await asyncio.sleep(0.02)
    assert late and late[0].name == "account_info" and late[0].value is None
    haystack = repr(late) + repr(dataclasses.asdict(late[0]))
    assert str(fake.LOGIN) not in haystack and fake.SERVER not in haystack
    await port.shutdown()


# ---------------------------------------------------------------- credentials never pass through us


def test_the_api_has_no_place_to_put_a_credential() -> None:
    forbidden = {"login", "password", "pass", "server", "secret", "token", "api_key"}
    config_fields = {f.name for f in dataclasses.fields(Mt5Config)}
    assert not (config_fields & forbidden), config_fields
    for method in (Mt5Adapter.attach, Mt5Adapter.for_real_terminal, Mt5Adapter.__init__):
        assert not (set(inspect.signature(method).parameters) & forbidden), method


async def test_attach_passes_only_the_terminal_path_and_timeout() -> None:
    fake = load_fakes().FakeMt5()
    port = Mt5Adapter(fake, config=Mt5Config(terminal_path="C:/Fake/terminal64.exe"))
    await port.attach()
    assert fake.initialize_kwargs == [{"path": "C:/Fake/terminal64.exe", "timeout": 60_000}]
    await port.shutdown()


async def test_a_failed_attach_is_an_error_with_the_terminal_s_last_error() -> None:
    fake = load_fakes().FakeMt5()

    def refuse(**_kw: Any) -> bool:
        return False

    fake.initialize = refuse
    fake._err = (-10003, "IPC initialize failed")
    port = Mt5Adapter(fake)
    with pytest.raises(Mt5ReadError) as caught:
        await port.attach()
    assert caught.value.reason == "initialize_failed"
    assert caught.value.last_error == (-10003, "IPC initialize failed")
    await port.shutdown()


async def test_a_whole_session_leaks_neither_login_nor_server_anywhere(fake_env: Env) -> None:
    fake = fake_env.fake
    secrets = {str(fake.LOGIN), fake.SERVER}
    seen: list[Any] = []
    with structlog.testing.capture_logs() as logs:
        seen.append(await fake_env.port.terminal_info())
        seen.append(account := await fake_env.port.account_info())
        seen.append(await fake_env.port.symbol_spec(fake_env.symbol))
        seen.append(await fake_env.port.read_spec_snapshot(fake_env.symbol))
        position = await open_long(fake_env)
        seen.append(position)
        seen.append(
            await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl + 100))
        )
        fake.trade(float(position.sl + 100))
        now = fake_env.now()
        seen.extend(await fake_env.port.history_deals(now - timedelta(hours=1), now))
        seen.extend(await fake_env.port.history_orders(now - timedelta(hours=1), now))
        with pytest.raises(Mt5NotSent):  # the refusal path must not leak either
            await fake_env.port.send_sltp(sltp_request(fake_env, position, Decimal(0)))

    haystacks = [repr(m) for m in seen] + [m.model_dump_json() for m in seen]
    haystacks.append(json.dumps(fake.sent_requests))
    haystacks.append(json.dumps(logs, default=str))
    for haystack in haystacks:
        for secret in secrets:
            assert secret not in haystack, secret
    expected = hashlib.sha256(f"{fake.LOGIN}|{fake.SERVER}".encode()).hexdigest()
    assert account.account_hash == expected
    assert fake.login_calls == 0
    assert {k for _, kw in fake.calls for k in kw}.isdisjoint({"login", "password", "server"})


async def test_no_request_for_an_open_position_is_anything_but_sltp_unless_it_is_an_entry(
    fake_env: Env,
) -> None:
    """The adapter has exactly three senders; the only DEAL/PENDING one is `send_entry`."""
    position = await open_long(fake_env)
    before = len(fake_env.fake.sent_requests)
    await fake_env.port.send_sltp(sltp_request(fake_env, position, position.sl + 100))
    bodies = fake_env.fake.sent_requests[before:]
    assert [b["action"] for b in bodies] == [6]  # TRADE_ACTION_SLTP only
