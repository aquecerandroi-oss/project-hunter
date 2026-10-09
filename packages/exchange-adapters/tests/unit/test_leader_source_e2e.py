"""Copy-trade pilot (H-037): NATS source + chain source + combinator wired together, all fakes.

The chain side is the real mainnet buy of ``AsRQ...`` (fixture of T4.12); the NATS legs are built from
that transaction's own balances, so the preview and the chain read the same trade. No network.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_core.domain.types import utcnow
from hunter_exchanges.pumpfun.leader_events import LeaderConfirmation, LeaderEvent, LeaderGap
from hunter_exchanges.pumpfun.leader_source import CombinedLeaderSource
from hunter_exchanges.pumpfun.leader_source_chain import ChainLeaderSource
from hunter_exchanges.pumpfun.leader_source_nats import NatsLeaderSource, WalletSnapshot
from hunter_exchanges.pumpfun.leader_source_nats_wire import NatsAuthError, NatsConfig
from hunter_exchanges.pumpfun.leader_source_stats import LeaderSourceStats
from hunter_exchanges.pumpfun.leader_source_wiring import build_leader_source
from hunter_exchanges.pumpfun.rpc_ws_models import ConnectionState, LogsNotification

pytestmark = pytest.mark.unit

FX = Path(__file__).parents[1] / "fixtures/pumpfun"
BUYER = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
BUY_TX = cast("dict[str, Any]", json.loads((FX / "rpc_tx_buy_raw.json").read_text())["result"])
CFG = NatsConfig("wss://core.nats.invalid", "subscriber", "TEST-ONLY-NOT-A-REAL-PASSWORD")
Item = LeaderEvent | LeaderGap | LeaderConfirmation


def _held(label: str) -> int:
    return sum(
        int(b["uiTokenAmount"]["amount"])
        for b in BUY_TX["meta"][label]
        if b.get("owner") == BUYER and b["mint"] == MINT
    )


def _ui(atoms: int, decimals: int) -> str:
    whole, frac = divmod(atoms, 10**decimals)
    return f"{whole}.{frac:0{decimals}d}"


def _frame(mint: str, balance: str, sig: str) -> bytes:
    body = json.dumps(
        {
            "walletAddress": BUYER,
            "tokenMint": mint,
            "balance": balance,
            "slot": 446369982,
            "timestamp": "2026-10-09T12:00:00.000Z",
            "txSignature": sig,
            "txIndex": "3",
        }
    ).encode()
    return b"MSG account_balance_change.%s.%s 1 %d\r\n%s\r\n" % (
        BUYER.encode(),
        mint.encode(),
        len(body),
        body,
    )


class FakeWs:
    def __init__(self) -> None:
        self.inbox: asyncio.Queue[bytes] = asyncio.Queue()
        self.inbox.put_nowait(b"INFO {}\r\n")

    async def recv(self) -> bytes:
        return await self.inbox.get()

    async def send(self, message: str) -> None:
        if message.startswith("CONNECT"):
            self.inbox.put_nowait(b"PONG\r\n")


class FakeFeed:
    def __init__(self) -> None:
        self.state = ConnectionState(ws_state="connected")
        self.inbox: asyncio.Queue[LogsNotification] = asyncio.Queue()

    async def subscribe_logs(
        self, *, mentions: Sequence[str], commitment: str = "confirmed"
    ) -> int:
        return 1

    async def listen(self) -> AsyncIterator[LogsNotification]:
        while True:
            yield await self.inbox.get()

    async def aclose(self) -> None:
        return None


class FakeRpc:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append(method)
        if method == "getTransaction":
            return BUY_TX
        if method == "getSignaturesForAddress":
            return []
        raise AssertionError(method)


async def read(agen: AsyncGenerator[Item], n: int) -> list[Item]:
    out: list[Item] = []
    for _ in range(n):
        out.append(await asyncio.wait_for(agen.__anext__(), 3))
    return out


async def collect(
    agen: AsyncGenerator[Item], want: tuple[type, ...], limit: int = 40
) -> list[Item]:
    """Read until every wanted type was seen (gaps in between are part of the story)."""
    seen: list[Item] = []
    while not all(any(isinstance(i, t) for i in seen) for t in want):
        if len(seen) >= limit:
            raise AssertionError(f"not all of {want} arrived: {seen}")
        seen += await read(agen, 1)
    return seen


async def test_nats_event_then_chain_confirmation_with_the_latency_distributions() -> None:
    ws, feed, rpc, stats = FakeWs(), FakeFeed(), FakeRpc(), LeaderSourceStats()

    async def fetch() -> NatsConfig:
        return CFG

    @asynccontextmanager
    async def connect(url: str) -> AsyncGenerator[FakeWs]:
        yield ws

    async def seeder(wallet: str) -> WalletSnapshot:
        pre = _held("preTokenBalances")
        return WalletSnapshot(
            sol_lamports=10**10, sol_slot=1, tokens={MINT: (pre, 1)} if pre else {}, tokens_slot=1
        )

    nats = NatsLeaderSource(fetch_config=fetch, connect=connect, seeder=seeder, stats=stats)
    chain = ChainLeaderSource(
        feed=feed,
        fetch_tx=lambda sig: rpc.call("getTransaction", [sig]),
        list_signatures=None,
        stats=stats,
    )
    combined = CombinedLeaderSource(nats=nats, chain=chain, stats=stats)
    agen = cast("AsyncGenerator[Item]", combined.stream([BUYER]))
    try:
        seen: list[Item] = []
        while not (
            seen
            and isinstance(seen[-1], LeaderGap)
            and seen[-1].reason == "nats_unseeded"
            and seen[-1].end
        ):
            seen += await read(agen, 1)  # until the wallet is seeded: the lane may now act on NATS
        post = _held("postTokenBalances")
        ws.inbox.put_nowait(_frame("SOL", "9.9", "SIG-B") + _frame(MINT, _ui(post, 6), "SIG-B"))
        items = await collect(agen, (LeaderEvent, LeaderConfirmation))
    finally:
        await agen.aclose()
    event = next(i for i in items if isinstance(i, LeaderEvent))
    confirmation = next(i for i in items if isinstance(i, LeaderConfirmation))
    assert items.index(event) < items.index(confirmation)  # the event never waited for the chain
    assert (event.source, event.confirmed, event.kind) == ("nats", False, "unknown")
    assert (
        event.token_delta_atoms == 22_628_881_309_131 and event.sol_delta_lamports == -100_000_000
    )
    assert confirmation.status == "confirmed" and confirmation.reason is None
    assert (confirmation.wallet, confirmation.signature, confirmation.mint) == (
        event.wallet,
        event.signature,
        event.mint,
    )
    assert confirmation.post_reserves is not None and confirmation.post_reserves.venue == "curve"
    assert confirmation.chain_token_delta_atoms == event.token_delta_atoms
    snap = stats.snapshot()
    assert snap["receive_to_emit"]["n"] == 1 and snap["nats_to_confirm"]["n"] == 1
    assert snap["first_seen_to_deliver"]["n"] == 1
    assert snap["receive_to_emit"]["p99_ms"] < 50  # parse + emit, in-process: milliseconds
    assert rpc.calls.count("getTransaction") == 1


async def test_with_nats_refused_the_chain_alone_still_delivers_a_confirmed_event() -> None:
    feed, rpc, stats = FakeFeed(), FakeRpc(), LeaderSourceStats()

    async def fetch() -> NatsConfig:
        raise NatsAuthError("gone")

    nats = NatsLeaderSource(fetch_config=fetch, stats=stats, sleep=lambda _: asyncio.sleep(0.05))
    chain = ChainLeaderSource(
        feed=feed,
        fetch_tx=lambda sig: rpc.call("getTransaction", [sig]),
        list_signatures=None,
        stats=stats,
    )
    agen = cast(
        "AsyncGenerator[Item]",
        CombinedLeaderSource(nats=nats, chain=chain, stats=stats).stream([BUYER]),
    )
    try:
        await asyncio.sleep(0.1)  # NATS is failing; the chain is up and covering
        feed.inbox.put_nowait(LogsNotification(1, "logs", 446369982, "SIG-B", None, (), utcnow()))
        seen = await collect(agen, (LeaderEvent,))
    finally:
        await agen.aclose()
    event = next(i for i in seen if isinstance(i, LeaderEvent))
    assert (event.source, event.confirmed, event.kind) == ("chain", True, "swap")
    reasons = {i.reason for i in seen if isinstance(i, LeaderGap)}
    assert "nats_auth" in reasons  # the fast path being down is named, even though the chain covers
    assert stats.counters["chain_only"] == 1


def test_build_leader_source_shares_one_stats_object() -> None:
    combined = build_leader_source(FakeRpc(), FakeFeed())
    assert combined.stats is not None
