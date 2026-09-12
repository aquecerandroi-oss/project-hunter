"""``advanced-indexer`` over HTTP: the board twin (same shape as a WS snapshot)
and the 65-field risk read, over the live captures of 2026-09-12."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from hunter_exchanges.base import MalformedMessage, RateLimited
from hunter_exchanges.pumpfun.indexer_rest import (
    REQUEST_CAPACITY,
    AdvancedIndexerClient,
    parse_risk_snapshot,
)
from hunter_exchanges.rate_limit import TokenBucketRateLimiter

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"


def _bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


async def test_the_board_twin_parses_like_a_snapshot_with_positions_and_source() -> None:
    seen: list[httpx.URL] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, content=_bytes("indexer_boards_new_raw.json"))

    async with httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(respond)
    ) as http:
        client = AdvancedIndexerClient(http_client=http)
        entries = await client.get_board("new", limit=50, offset=10)
    assert seen[0].path == "/boards/new" and seen[0].params["limit"] == "50"
    assert len(entries) == 50
    assert [e.position for e in entries] == list(range(10, 60))
    assert all(e.source == "indexer_rest:/boards" and e.board == "new" for e in entries)
    assert all(isinstance(e.market_cap_usd, Decimal) for e in entries if e.market_cap_usd)
    assert entries[0].observed_at < entries[0].received_at
    with pytest.raises(ValueError):
        await client.get_board("koth")


async def test_the_risk_read_keeps_the_raw_object_and_extracts_fractions() -> None:
    raw: dict[str, Any] = json.loads(_bytes("indexer_in_memory_coin_raw.json"))

    async with httpx.AsyncClient(
        base_url="https://test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=_bytes("indexer_in_memory_coin_raw.json"))
        ),
    ) as http:
        snapshot = await AdvancedIndexerClient(http_client=http).get_risk_snapshot(raw["mint"])
    assert snapshot.holders == raw["numHolders"] == 24
    assert snapshot.snipers == raw["sniperCount"] == 19
    assert snapshot.top10_share == Decimal("0.000001")
    assert snapshot.dev_share == Decimal(0) and snapshot.bundled_share == Decimal(0)
    assert snapshot.progress_pct is not None and snapshot.progress_pct > 99
    assert snapshot.graduated_at is None, "graduationDate 0 is not an instant"
    assert snapshot.program == "raydium_launchpad" and snapshot.quote_asset == "SOL"
    assert snapshot.is_mayhem is False and snapshot.mayhem_state is None
    assert len(snapshot.raw) == 65 and snapshot.raw["mint"] == raw["mint"]
    assert snapshot.source == "indexer_rest:/in-memory-coin"


def test_a_risk_body_with_a_bad_holders_count_is_malformed() -> None:
    raw: dict[str, Any] = json.loads(_bytes("indexer_in_memory_coin_raw.json"))
    raw["numHolders"] = "many"
    with pytest.raises(MalformedMessage):
        parse_risk_snapshot(
            raw, received_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC)
        )


async def test_a_different_mint_in_the_answer_is_refused() -> None:
    async with httpx.AsyncClient(
        base_url="https://test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=_bytes("indexer_in_memory_coin_raw.json"))
        ),
    ) as http:
        with pytest.raises(MalformedMessage, match="different mint"):
            await AdvancedIndexerClient(http_client=http).get_risk_snapshot("OTHER")


async def test_the_declared_bucket_is_sixty_a_minute_and_a_429_is_rate_limited() -> None:
    assert REQUEST_CAPACITY == 60
    now = [0.0]
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)
        now[0] += delay

    limiter = TokenBucketRateLimiter(
        "pumpfun_indexer", capacity=60, refill_period_s=60, clock=lambda: now[0], sleep=sleep
    )
    async with httpx.AsyncClient(
        base_url="https://test",
        transport=httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "3"})),
    ) as http:
        client = AdvancedIndexerClient(http_client=http, rate_limiter=limiter)
        with pytest.raises(RateLimited) as error:
            await client.get_risk_snapshot("MINT")
    assert error.value.retry_after_s == 3
