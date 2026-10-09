"""Copy-trade pilot (H-037): one ``getTransaction`` per signature, with a deadline, a pause and no lost task."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from structlog.testing import capture_logs

from hunter_exchanges.base import ExchangeUnavailable, RateLimited
from hunter_exchanges.pumpfun import leader_source_chain_fetch as module
from hunter_exchanges.pumpfun.leader_source_chain_fetch import TxFetcher
from hunter_exchanges.pumpfun.leader_source_rpc_guard import RpcRefused
from hunter_exchanges.pumpfun.leader_source_stats import LeaderSourceStats

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
TX = {"slot": 1}


class Clock:
    def __init__(self) -> None:
        self.now = T0
        self.sleeps: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)
        await asyncio.sleep(0)


def fetcher(fetch: Any, clock: Clock, **kw: Any) -> TxFetcher:
    return TxFetcher(fetch, stats=LeaderSourceStats(), wall=clock, sleep=clock.sleep, **kw)


async def test_one_call_per_signature_and_successes_are_cached() -> None:
    clock, calls = Clock(), list[str]()

    async def fetch(sig: str) -> dict[str, Any] | None:
        calls.append(sig)
        return TX

    f = fetcher(fetch, clock)
    results = await asyncio.gather(f.get("a"), f.get("a"), f.get("a"))
    assert results == [(TX, None)] * 3 and calls == ["a"]
    assert await f.get("a") == (TX, None) and calls == ["a"]


async def test_a_failure_is_never_cached_so_a_later_ask_calls_again() -> None:
    clock, calls = Clock(), list[str]()

    async def fetch(sig: str) -> dict[str, Any] | None:
        calls.append(sig)
        return None

    f = fetcher(fetch, clock, retry_delays_s=(0.1,))
    assert await f.get("a") == (None, "not_found")
    assert await f.get("a") == (None, "not_found")
    assert len(calls) == 4  # two attempts each time


async def test_the_whole_ladder_obeys_the_thirty_second_deadline_even_when_the_rpc_is_slow() -> (
    None
):
    clock, calls = Clock(), list[str]()

    async def fetch(sig: str) -> dict[str, Any] | None:
        calls.append(sig)
        clock.now += timedelta(seconds=8)  # each answer takes 8 s of the clock
        return None

    f = fetcher(fetch, clock)
    assert await f.get("slow") == (None, "not_found")
    assert len(calls) <= 3  # the design: up to three attempts


async def test_a_refusal_pauses_a_call_already_queued_behind_the_semaphore() -> None:
    clock, calls = Clock(), list[str]()
    release = asyncio.Event()

    async def fetch(sig: str) -> dict[str, Any] | None:
        calls.append(sig)
        if sig == "A":
            await release.wait()
            raise ExchangeUnavailable("Solana RPC HTTP 403", exchange="pumpfun")
        return TX

    f = fetcher(fetch, clock, max_inflight=1)
    with capture_logs() as logs:
        a = asyncio.create_task(f.get("A"))
        await asyncio.sleep(0.01)
        b = asyncio.create_task(f.get("B"))  # queued behind A on the semaphore
        await asyncio.sleep(0.01)
        release.set()
        assert await a == (None, "refused_403")
        assert await b == (None, "refused_403")
    assert calls == ["A"]  # B never reached the node during the pause
    assert [e for e in logs if e["event"] == "system_event"]


async def test_the_pause_expires() -> None:
    clock = Clock()
    answers: list[Any] = [RateLimited("429", exchange="p", retry_after_s=5.0), TX]

    async def fetch(sig: str) -> dict[str, Any] | None:
        item = answers.pop(0)
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[no-any-return]

    f = fetcher(fetch, clock)
    assert await f.get("a") == (None, "rate_limited")
    assert await f.get("b") == (None, "rate_limited")  # inside the pause: no call
    clock.now += timedelta(seconds=6)
    assert await f.get("b") == (TX, None)


async def test_a_guarded_refusal_stops_the_ladder_at_once() -> None:
    clock, calls = Clock(), list[str]()

    async def fetch(sig: str) -> dict[str, Any] | None:
        calls.append(sig)
        raise RpcRefused("refused_403")

    assert await fetcher(fetch, clock).get("a") == (None, "refused_403")
    assert calls == ["a"]


async def test_transient_errors_retry_and_then_say_unavailable() -> None:
    clock = Clock()

    async def fetch(sig: str) -> dict[str, Any] | None:
        raise ExchangeUnavailable("Solana RPC transport failure", exchange="pumpfun")

    assert await fetcher(fetch, clock).get("a") == (None, "unavailable")


async def test_in_flight_fetches_beyond_the_cache_bound_are_not_lost_and_close_cancels_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "CACHE_MAX", 2)
    clock, gate, calls = Clock(), asyncio.Event(), list[str]()

    async def fetch(sig: str) -> dict[str, Any] | None:
        calls.append(sig)
        await gate.wait()
        return TX

    f = fetcher(fetch, clock, max_inflight=50)
    waiting = [asyncio.create_task(f.get(f"s{i}")) for i in range(6)]
    await asyncio.sleep(0.02)
    assert f.live() == 6  # nothing was evicted while pending
    gate.set()
    assert [await w for w in waiting] == [(TX, None)] * 6

    gate.clear()
    stuck = [asyncio.create_task(f.get(f"t{i}")) for i in range(6)]
    await asyncio.sleep(0.02)
    await f.aclose()
    assert f.live() == 0
    results = await asyncio.gather(*stuck, return_exceptions=True)
    assert all(isinstance(r, asyncio.CancelledError) for r in results)


async def test_the_deadline_also_bounds_a_call_that_hangs_and_a_wait_for_the_slot() -> None:
    gate = asyncio.Event()
    calls: list[str] = []

    async def fetch(sig: str) -> dict[str, Any] | None:
        calls.append(sig)
        await gate.wait()  # the node never answers
        return TX

    f = TxFetcher(fetch, stats=LeaderSourceStats(), deadline_s=0.1, max_inflight=1)
    started = asyncio.get_running_loop().time()
    first = asyncio.create_task(f.get("a"))
    queued = asyncio.create_task(f.get("b"))  # waits for the only slot, behind a hanging call
    assert await first == (None, "unavailable")
    assert await queued == (None, "unavailable")
    assert asyncio.get_running_loop().time() - started < 2.0
    assert calls[0] == "a"
    gate.set()


def test_the_default_ladder_is_the_designs_three_attempts_inside_thirty_seconds() -> None:
    from hunter_exchanges.pumpfun.leader_source_chain_fetch import DEADLINE_S, RETRY_DELAYS_S

    assert len(RETRY_DELAYS_S) + 1 == 3 and DEADLINE_S == 30.0
