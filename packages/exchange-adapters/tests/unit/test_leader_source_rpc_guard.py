"""Copy-trade pilot (H-037): the one cool-down every RPC call of the leader source goes through."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from structlog.testing import capture_logs

from hunter_exchanges.base import ExchangeUnavailable, RateLimited
from hunter_exchanges.pumpfun.leader_source_rpc_guard import RpcGuard, RpcRefused

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)


class Rpc:
    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls: list[str] = []

    async def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append(method)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


async def test_calls_pass_through_untouched() -> None:
    rpc = Rpc({"ok": 1})
    assert await RpcGuard(rpc).call("getBalance", ["w"]) == {"ok": 1}
    assert rpc.calls == ["getBalance"]


async def test_a_429_trips_the_guard_and_no_call_leaves_while_it_is_tripped() -> None:
    clock = Clock()
    rpc = Rpc(RateLimited("429", exchange="pumpfun", retry_after_s=10.0), {"ok": 1})
    guard = RpcGuard(rpc, wall=clock)
    with capture_logs() as logs, pytest.raises(RpcRefused) as err:
        await guard.call("getTransaction", [])
    assert err.value.reason == "rate_limited"
    assert [e for e in logs if e["event"] == "system_event"]
    for method in ("getBalance", "getSignaturesForAddress", "getTransaction"):
        with pytest.raises(RpcRefused):
            await guard.call(method, [])
    assert rpc.calls == ["getTransaction"]  # every other path (seed, listing, fetch) was held back
    clock.now = T0 + timedelta(seconds=11)
    assert await guard.call("getBalance", []) == {"ok": 1}


@pytest.mark.parametrize("status", [401, 403, 418])
async def test_a_refusal_status_trips_it_for_the_cooldown(status: int) -> None:
    clock = Clock()
    rpc = Rpc(ExchangeUnavailable(f"Solana RPC HTTP {status}", exchange="pumpfun"), {"ok": 1})
    guard = RpcGuard(rpc, wall=clock, cooldown_s=30.0)
    with pytest.raises(RpcRefused) as err:
        await guard.call("getTransaction", [])
    assert err.value.reason == f"refused_{status}"
    clock.now = T0 + timedelta(seconds=29)
    with pytest.raises(RpcRefused):
        await guard.call("getTransaction", [])
    clock.now = T0 + timedelta(seconds=31)
    assert await guard.call("getTransaction", []) == {"ok": 1}


async def test_other_errors_pass_through_and_do_not_trip() -> None:
    rpc = Rpc(ExchangeUnavailable("Solana RPC transport failure", exchange="pumpfun"), {"ok": 1})
    guard = RpcGuard(rpc)
    with pytest.raises(ExchangeUnavailable):
        await guard.call("getTransaction", [])
    assert await guard.call("getTransaction", []) == {"ok": 1}
