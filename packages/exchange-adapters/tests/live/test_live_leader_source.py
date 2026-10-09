"""Copy-trade pilot (H-037) — the leader source against the real pump.fun NATS and Solana RPC (``live``).

Opt-in, read-only, anonymous, at most ~50 s, one connection per instance, 1-2 wallets: the same access an
anonymous visitor of pump.fun has (decision 2026-10-06). The credential is read from the public home page
into memory by the code under test; this test never prints, stores or asserts on it.

Never in CI (``live`` marker + opt-in env var). Run:
``HUNTER_LIVE_TESTS=1 uv run pytest packages/exchange-adapters/tests/live/test_live_leader_source.py -m live -q -s``

Wallets: ``HUNTER_LIVE_LEADER_WALLETS`` (comma separated; required by the chain and seed tests) or, for the
NATS-only test, by default pump.fun's own protocol fee recipient — a public, always-busy account, so balance legs flow within seconds without following any
trader. What it proves: the credential is still readable from the home page, the socket reaches ``ready``
(the ``nats_connect`` gap closes), legs are parsed (no ``malformed`` flood), the chain feed connects, and
the receive->emit distribution is published. It does not prove a trade was copied: that needs a leader to
trade during the window.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from hunter_exchanges.pumpfun.leader_events import LeaderEvent, LeaderGap, LeaderItem
from hunter_exchanges.pumpfun.leader_source_nats import NatsLeaderSource
from hunter_exchanges.pumpfun.leader_source_stats import LeaderSourceStats
from hunter_exchanges.pumpfun.leader_source_wiring import build_leader_source, rpc_wallet_seeder
from hunter_exchanges.pumpfun.rpc import SolanaRpcClient
from hunter_exchanges.pumpfun.rpc_ws import SolanaWsClient

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("HUNTER_LIVE_TESTS") != "1",
        reason="set HUNTER_LIVE_TESTS=1 to hit the real pump.fun NATS and the Solana public RPC",
    ),
]

DEFAULT_WALLET = "62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV"  # pump.fun protocol fee recipient
WALLETS = [
    w.strip()
    for w in os.environ.get("HUNTER_LIVE_LEADER_WALLETS", DEFAULT_WALLET).split(",")
    if w.strip()
][:2]
WINDOW_S = 40.0
EXPLICIT = bool(os.environ.get("HUNTER_LIVE_LEADER_WALLETS", "").strip())
needs_wallets = pytest.mark.skipif(
    not EXPLICIT,
    reason="set HUNTER_LIVE_LEADER_WALLETS to a quiet wallet: the default (the busy fee recipient) would "
    "stream the whole protocol over logsSubscribe and read a huge token list",
)


async def test_nats_leg_flow_and_latency_distribution_live() -> None:
    stats = LeaderSourceStats()
    source = NatsLeaderSource(stats=stats)  # default: credential from the home page, real socket
    agen = source.stream(WALLETS)
    gaps: list[LeaderGap] = []
    events: list[LeaderEvent] = []
    others: list[object] = []

    async def drain() -> None:
        async for item in agen:
            if isinstance(item, LeaderGap):
                gaps.append(item)
            elif isinstance(item, LeaderEvent):
                events.append(item)
            else:
                others.append(item)

    task = asyncio.create_task(drain())
    try:
        await asyncio.sleep(WINDOW_S)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await agen.aclose()  # type: ignore[attr-defined]
    snap = stats.snapshot()
    print(json.dumps({"wallets": len(WALLETS), "events": len(events), "stats": snap}, indent=1))
    reasons = sorted({g.reason for g in gaps})
    assert not any(r.startswith("nats_auth") for r in reasons), f"credential refused: {reasons}"
    assert not any(r.startswith("nats_refused") for r in reasons), (
        f"rate-limited/blocked: {reasons}"
    )
    closed = [g for g in gaps if g.reason == "nats_connect" and g.end is not None]
    assert closed, f"the socket never became ready: {reasons}"
    counters = snap["counters"]
    assert counters.get("malformed", 0) <= max(1, sum(counters.values()) // 20)
    for event in events:
        assert (event.source, event.confirmed) == ("nats", False)
        assert event.observed_at.tzinfo is not None


@needs_wallets
async def test_combined_source_chain_confirmation_live() -> None:
    rpc = SolanaRpcClient()
    ws = SolanaWsClient()
    stats = LeaderSourceStats()
    combined = build_leader_source(rpc, ws, stats=stats)
    agen = combined.stream(WALLETS[:1])
    seen: list[LeaderItem] = []

    async def drain() -> None:
        async for item in agen:
            seen.append(item)

    task = asyncio.create_task(drain())
    try:
        await asyncio.sleep(WINDOW_S)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await agen.aclose()  # type: ignore[attr-defined]
        await rpc.aclose()
    snap = stats.snapshot()
    print(json.dumps({"items": len(seen), "stats": snap}, indent=1))
    both = [i for i in seen if isinstance(i, LeaderGap) and i.reason.startswith("no_coverage")]
    still_open = [g for g in both if g.end is None]
    closed = [g for g in both if g.end is not None]
    # either both sources lost it for good (a real problem) or coverage came up
    assert not still_open or closed, f"no coverage the whole window: {[g.reason for g in both]}"
    for item in seen:
        if isinstance(item, LeaderEvent) and item.confirmed:
            assert item.source == "chain" and item.block_time is not None


@needs_wallets
async def test_seed_reads_a_wallet_snapshot_live() -> None:
    rpc = SolanaRpcClient()
    try:
        snap = await rpc_wallet_seeder(rpc)(WALLETS[0])
    except Exception as exc:  # the public endpoint may be over its data allowance (KB-0186)
        pytest.skip(f"public RPC refused the seed reads: {type(exc).__name__}")
    finally:
        await rpc.aclose()
    assert snap.sol_lamports > 0 and snap.sol_slot > 0
