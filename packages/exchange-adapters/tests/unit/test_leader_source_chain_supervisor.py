"""Copy-trade pilot (H-037), code review R2: the on-chain fallback's tasks are supervised.

An exception in a child task (or in handling one notification) must be a named ``chain_*`` gap and a
restart with backoff — never a fallback that dies silently while the stream looks alive."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from hunter_exchanges.pumpfun import leader_source_chain_run as run_module
from hunter_exchanges.pumpfun.leader_events import LeaderEvent, LeaderGap
from hunter_exchanges.pumpfun.rpc_ws_models import LogsNotification

from .test_leader_source_chain import (
    BUY_TX,
    BUYER,
    FakeFeed,
    Rpc,
    make,
    notif,
    take,
)

pytestmark = pytest.mark.unit


class FlakyFeed(FakeFeed):
    """``listen`` raises once, as a broken transport layer could, then behaves."""

    def __init__(self) -> None:
        super().__init__()
        self.listens = 0

    async def listen(self) -> AsyncIterator[LogsNotification]:
        self.listens += 1
        if self.listens == 1:
            raise RuntimeError("transport layer bug")
        async for note in super().listen():
            yield note


async def test_a_crashed_listener_is_a_named_gap_and_restarts_with_backoff() -> None:
    feed, rpc = FlakyFeed(), Rpc({"SIG-B": BUY_TX})
    sleeps: list[float] = []
    agen = make(feed, rpc, sleeps=sleeps).stream([BUYER])
    got = await take(agen, 3)
    reasons = [g.reason for g in got if isinstance(g, LeaderGap)]
    assert "chain_listen_crashed" in reasons
    await asyncio.sleep(0.05)
    assert feed.listens >= 2 and sleeps and 1.0 <= sleeps[0] <= 30.0
    feed.inbox.put_nowait(notif(1, "SIG-B"))
    for _ in range(10):
        item = (await take(agen, 1))[0]
        if isinstance(item, LeaderEvent):
            break
    else:
        raise AssertionError("the restarted fallback never delivered the trade")
    await agen.aclose()  # type: ignore[attr-defined]


async def test_an_exception_while_handling_one_notification_is_a_gap_and_a_recovery_not_a_dead_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed, rpc = FakeFeed(), Rpc({"S-LOST": BUY_TX, "S-NEXT": BUY_TX})
    rpc.chain[BUYER] = ["A"]
    real = run_module.ChainRun.on_notification
    calls = {"n": 0}

    def flaky(self: run_module.ChainRun, note: LogsNotification, wallet: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("bug in handling")
        real(self, note, wallet)

    monkeypatch.setattr(run_module.ChainRun, "on_notification", flaky)
    agen = make(feed, rpc).stream([BUYER])
    await take(agen, 2)  # chain_connect open/close
    rpc.chain[BUYER] = ["S-LOST", "A"]
    feed.inbox.put_nowait(notif(1, "S-LOST"))  # blows up inside the handler
    items: list[Any] = []
    for _ in range(8):
        items.append((await take(agen, 1))[0])
        if any(isinstance(i, LeaderEvent) for i in items):
            break
    reasons = [i.reason for i in items if isinstance(i, LeaderGap)]
    assert "chain_notification_error" in reasons  # named, for that wallet
    assert [i.signature for i in items if isinstance(i, LeaderEvent)] == [
        "S-LOST"
    ]  # recovered by REST
    feed.inbox.put_nowait(notif(1, "S-NEXT"))  # and the fallback keeps working
    nxt = await take(agen, 1)
    assert isinstance(nxt[0], LeaderEvent) or isinstance(nxt[0], LeaderGap)
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_crashed_monitor_restarts_instead_of_ending_recovery_for_good(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed, rpc = FakeFeed(), Rpc({})
    rpc.chain[BUYER] = ["A"]
    real = run_module.ChainRun.recover_all
    calls = {"n": 0}

    async def flaky(self: run_module.ChainRun) -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("bug in recovery")
        return await real(self)

    monkeypatch.setattr(run_module.ChainRun, "recover_all", flaky)
    agen = make(feed, rpc).stream([BUYER])
    await take(agen, 2)
    feed.state.reconnects += 1
    got: list[object] = []
    for _ in range(12):
        got.append((await take(agen, 1))[0])
        if (
            sum(
                isinstance(g, LeaderGap) and g.reason == "chain_ws_down" and g.end is not None
                for g in got
            )
            >= 1
        ):
            break
    reasons = [g.reason for g in got if isinstance(g, LeaderGap)]
    assert "chain_monitor_crashed" in reasons and calls["n"] >= 2
    assert (
        reasons.count("chain_ws_down") >= 2
    )  # opened, and closed only after a recovery that finished
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_listener_that_simply_ends_is_treated_as_a_crash_too() -> None:
    class Ending(FakeFeed):
        def __init__(self) -> None:
            super().__init__()
            self.listens = 0

        async def listen(self) -> AsyncIterator[LogsNotification]:
            self.listens += 1
            if self.listens == 1:
                return
            async for note in super().listen():
                yield note

    feed = Ending()
    agen = make(feed, Rpc({})).stream([BUYER])
    got = await take(agen, 3)
    assert "chain_listen_crashed" in [g.reason for g in got if isinstance(g, LeaderGap)]
    await asyncio.sleep(0.05)
    assert feed.listens >= 2
    await agen.aclose()  # type: ignore[attr-defined]
