"""Copy-trade pilot (H-037), security R1 LOW-2: a call already queued in the RPC client's own bucket must
not be sent while an RPC pause is on (the guard checked before the queue, not after it)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hunter_exchanges.base import RateLimited
from hunter_exchanges.pumpfun.leader_source_rpc_guard import RpcGuard, RpcRefused
from hunter_exchanges.pumpfun.leader_source_wiring import attach_guard
from hunter_exchanges.pumpfun.rpc import SolanaRpcClient
from hunter_exchanges.rate_limit import TokenBucketRateLimiter

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)


class GateLimiter(TokenBucketRateLimiter):
    """A bucket whose ``acquire`` waits for a test-controlled event (a queued call)."""

    def __init__(self) -> None:
        super().__init__("test", capacity=1000, refill_period_s=1.0)
        self.gate = asyncio.Event()
        self.gate.set()

    async def acquire(self, *args: Any, **kwargs: Any) -> Any:
        await self.gate.wait()
        return await super().acquire(*args, **kwargs)


def client(handler: Any, limiter: GateLimiter) -> SolanaRpcClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SolanaRpcClient(rpc_url="https://rpc.invalid/", http_client=http, rate_limiter=limiter)


async def test_a_call_queued_in_the_client_bucket_does_not_send_during_a_pause() -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.content))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": 1})

    limiter = GateLimiter()
    rpc = client(handler, limiter)
    now = {"t": T0}
    guard = RpcGuard(rpc, wall=lambda: now["t"])
    attach_guard(guard, rpc)
    limiter.gate.clear()
    queued = asyncio.create_task(
        guard.call("getBalance", ["w"])
    )  # passes the guard, waits in the bucket
    await asyncio.sleep(0.02)
    guard.trip("refused_403", 30.0)  # another call got the 403 meanwhile
    limiter.gate.set()
    with pytest.raises(RpcRefused):
        await queued
    assert sent == []  # the queued call never reached the node
    now["t"] += timedelta(seconds=31)
    assert await guard.call("getBalance", ["w"]) == 1 and len(sent) == 1


async def test_without_a_hook_the_client_behaves_exactly_as_before() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": 7})

    rpc = client(handler, GateLimiter())
    assert await rpc.call("getBalance", ["w"]) == 7


async def test_a_429_through_the_hooked_client_still_trips_the_guard() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "5"})

    rpc = client(handler, GateLimiter())
    guard = RpcGuard(rpc)
    attach_guard(guard, rpc)
    with pytest.raises((RpcRefused, RateLimited)):
        await guard.call("getBalance", ["w"])
    with pytest.raises(RpcRefused):
        await guard.call("getBalance", ["w"])
