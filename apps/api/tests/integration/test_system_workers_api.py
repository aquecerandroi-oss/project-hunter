"""Integration tests for ``/api/v1/system/workers`` and
``/api/v1/system/market-status`` — real Redis ``hb:*`` hashes and real
Postgres market/gap counts.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio

from hunter_api.services.system_status import anonymize_instance
from hunter_core.db.models.market_data import IngestionGap
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.redis import keys

from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[redis_asyncio.Redis]:
    client = redis_asyncio.from_url(redis_url, decode_responses=False)
    try:
        yield client
    finally:
        await client.aclose()


async def _seed_exchange(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    monitored_markets: int = 0,
    open_gaps: int = 0,
) -> str:
    code = f"testex{uuid.uuid4().hex[:10]}"
    async with session_factory() as session:
        exchange = Exchange(code=code, name=code)
        session.add(exchange)
        await session.flush()
        gap_market_id = None
        for index in range(monitored_markets):
            market = Market(
                exchange_id=exchange.id,
                symbol=f"SYM{index}USDT",
                market_type=MarketType.PERPETUAL,
                is_monitored=True,
                monitor_rank=index,
            )
            session.add(market)
            await session.flush()
            if gap_market_id is None:
                gap_market_id = market.id
        for _ in range(open_gaps):
            assert gap_market_id is not None, "open_gaps requires monitored_markets >= 1"
            session.add(
                IngestionGap(
                    market_id=gap_market_id,
                    timeframe=Timeframe.M1,
                    gap_start=datetime.now(UTC) - timedelta(hours=1),
                    gap_end=datetime.now(UTC),
                    status="open",
                )
            )
        await session.commit()
    return code


async def test_workers_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/system/workers")
    assert response.status_code == 401


async def test_market_status_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/system/market-status")
    assert response.status_code == 401


async def test_workers_reports_a_fresh_heartbeat_as_alive(
    client: httpx.AsyncClient,
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(F5) A non-``market`` role's ``instance`` (``WorkerRuntime``'s default
    ``hostname:pid``) is anonymized in the response -- this test looks the
    row up by the anonymized value, exactly as a real client would have to.
    """
    # (G2) a plain slug (no ``:``) now passes through unchanged regardless of
    # role -- use ``WorkerRuntime``'s actual default shape (``hostname:pid``)
    # so this test still exercises anonymization.
    instance = f"host-{uuid.uuid4().hex[:8]}:4242"
    await redis_client.hset(
        keys.heartbeat("api", instance),
        mapping={
            "ts": datetime.now(UTC).isoformat(),
            "last_success": datetime.now(UTC).isoformat(),
            "errors": "0",
            "version": "0.0.0",
        },
    )
    actor: Actor = make_actor("workers-reader")

    response = await client.get("/api/v1/system/workers", headers=actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert all(row["instance"] != instance for row in body)
    anonymized = anonymize_instance("api", instance)
    rows = [row for row in body if row["instance"] == anonymized]
    assert len(rows) == 1
    assert rows[0]["role"] == "api"
    assert rows[0]["status"] == "alive"
    assert rows[0]["errors"] == 0


async def test_workers_anonymizes_hostname_and_pid_for_non_market_roles(
    client: httpx.AsyncClient,
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(F5) ``hb:api:myhost:4242`` yields a 12-hex instance; the response
    body contains neither the hostname nor the PID anywhere.
    """
    suffix = uuid.uuid4().hex[:8]
    hostname = f"myhost-{suffix}"
    pid = "4242"
    await redis_client.hset(
        keys.heartbeat("api", f"{hostname}:{pid}"),
        mapping={"ts": datetime.now(UTC).isoformat(), "errors": "0"},
    )
    actor: Actor = make_actor(f"workers-anon-{suffix}")

    response = await client.get("/api/v1/system/workers", headers=actor.headers)

    assert response.status_code == 200, response.text
    raw_body = response.text
    assert hostname not in raw_body
    assert f"{hostname}:{pid}" not in raw_body
    anonymized = anonymize_instance("api", f"{hostname}:{pid}")
    assert any(row["instance"] == anonymized for row in response.json())
    assert len(anonymized) == 12


async def test_workers_keeps_market_role_instance_as_the_exchange_code(
    client: httpx.AsyncClient,
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(F5) ``hb:market:binance`` still yields ``binance`` verbatim -- the
    exchange code is meaningful, non-sensitive data the UI displays.
    """
    exchange = f"testex{uuid.uuid4().hex[:10]}"
    await redis_client.hset(
        keys.heartbeat("market", exchange),
        mapping={"ts": datetime.now(UTC).isoformat(), "errors": "0"},
    )
    actor: Actor = make_actor(f"workers-market-anon-{exchange}")

    response = await client.get("/api/v1/system/workers", headers=actor.headers)

    assert response.status_code == 200, response.text
    rows = [row for row in response.json() if row["instance"] == exchange]
    assert len(rows) == 1
    assert rows[0]["role"] == "market"


async def test_workers_hashes_market_role_instance_when_it_has_a_colon(
    client: httpx.AsyncClient,
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(G2) The exception is keyed on the *shape* of ``instance``, never on
    ``role``: the market worker entrypoint constructs
    ``WorkerRuntime(role="market")`` without an explicit ``instance``, so it
    still falls back to the generic ``hostname:pid`` default and writes it
    under ``hb:market:{hostname}:{pid}`` -- a real key the original
    role-only exception ("pass it through when role == market") would have
    leaked verbatim.
    """
    suffix = uuid.uuid4().hex[:8]
    hostname = f"myhost-{suffix}"
    pid = "4242"
    await redis_client.hset(
        keys.heartbeat("market", f"{hostname}:{pid}"),
        mapping={"ts": datetime.now(UTC).isoformat(), "errors": "0"},
    )
    actor: Actor = make_actor(f"workers-market-colon-{suffix}")

    response = await client.get("/api/v1/system/workers", headers=actor.headers)

    assert response.status_code == 200, response.text
    raw_body = response.text
    assert hostname not in raw_body
    assert f"{hostname}:{pid}" not in raw_body
    anonymized = anonymize_instance("market", f"{hostname}:{pid}")
    rows = [row for row in response.json() if row["instance"] == anonymized]
    assert len(rows) == 1
    assert rows[0]["role"] == "market"


async def test_workers_reports_market_extension_fields_when_present(
    client: httpx.AsyncClient,
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    exchange = f"testex{uuid.uuid4().hex[:10]}"
    await redis_client.hset(
        keys.heartbeat("market", exchange),
        mapping={
            "ts": datetime.now(UTC).isoformat(),
            "errors": "0",
            "last_event_at": datetime.now(UTC).isoformat(),
            "ws_state": "connected",
            "subscriptions": "42",
            "reconnects": "1",
            "markets_monitored": "42",
            "open_gaps": "0",
        },
    )
    actor: Actor = make_actor("workers-market-reader")

    response = await client.get("/api/v1/system/workers", headers=actor.headers)

    assert response.status_code == 200, response.text
    rows = [row for row in response.json() if row["instance"] == exchange]
    assert len(rows) == 1
    assert rows[0]["ws_state"] == "connected"
    assert rows[0]["subscriptions"] == 42
    assert rows[0]["reconnects"] == 1
    assert rows[0]["markets_monitored"] == 42
    assert rows[0]["open_gaps"] == 0


async def test_workers_returns_503_problem_json_when_a_heartbeat_key_has_the_wrong_redis_type(
    client: httpx.AsyncClient,
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(G4) A real ``WRONGTYPE`` against one ``hb:*`` key (set as a STRING
    instead of a HASH) aborts the ``SCAN``/``HGETALL`` read -- that is a
    genuine failure to read heartbeats, not "no worker has ever reported
    in", and must not render as the same ``200 []`` a healthy, idle cluster
    would return. The response is a ``503`` problem+json, and redis-py's
    ``WRONGTYPE`` message (which can embed the offending key) never reaches
    the response body.
    """
    bogus_key = keys.heartbeat("api", f"wrongtype-{uuid.uuid4().hex[:8]}")
    await redis_client.set(bogus_key, "not-a-hash")
    try:
        actor: Actor = make_actor("workers-wrongtype")

        response = await client.get("/api/v1/system/workers", headers=actor.headers)

        assert response.status_code == 503, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        assert "not-a-hash" not in response.text
        assert bogus_key not in response.text
        assert response.json()["type"].endswith("workers-unavailable")
    finally:
        await redis_client.delete(bogus_key)


async def test_workers_returns_200_empty_list_when_redis_is_healthy_with_no_heartbeats(
    client: httpx.AsyncClient,
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(G4) The other half of the distinction: a healthy Redis with no
    ``hb:*`` key at all is genuinely empty, not unavailable -- ``200 []``,
    never a ``503``. Deletes any ``hb:*`` key this suite itself may have left
    behind (each test uses a unique, uuid-suffixed instance, so this only
    ever removes this file's own leftovers, never a real worker's).
    """
    async for stale_key in redis_client.scan_iter(match="hb:*"):  # type: ignore[reportUnknownMemberType]
        await redis_client.delete(cast(bytes, stale_key))
    actor: Actor = make_actor("workers-empty-healthy")

    response = await client.get("/api/v1/system/workers", headers=actor.headers)

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_market_status_unavailable_with_no_heartbeat(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    code = await _seed_exchange(session_factory, monitored_markets=3, open_gaps=0)
    actor: Actor = make_actor("market-status-reader")

    response = await client.get("/api/v1/system/market-status", headers=actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    entries = [row for row in body["exchanges"] if row["exchange"] == code]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["ws_state"] == "unavailable"
    assert entry["markets_monitored"] == 3
    assert entry["open_gaps"] == 0
    assert entry["last_event_at"] is None


async def test_market_status_isolates_a_single_exchange_wrongtype_heartbeat(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(G4) A real ``WRONGTYPE`` against one exchange's own ``hb:market:*``
    hash must not take the whole response down -- every other (global,
    no-RLS) exchange row still renders normally, and the response is still
    ``200``, not a ``503``. (The global ``exchanges`` table already has other
    rows from the seed script and earlier tests in this session, so this
    exercises real per-exchange isolation, not the wholesale-failure path.)
    """
    code = await _seed_exchange(session_factory, monitored_markets=1, open_gaps=0)
    bogus_key = keys.heartbeat("market", code)
    await redis_client.set(bogus_key, "not-a-hash")
    try:
        actor: Actor = make_actor("market-status-wrongtype")

        response = await client.get("/api/v1/system/market-status", headers=actor.headers)

        assert response.status_code == 200, response.text
        assert "not-a-hash" not in response.text
        entry = next(row for row in response.json()["exchanges"] if row["exchange"] == code)
        assert entry["ws_state"] == "unavailable"
    finally:
        # (T2.6) left uncleaned, this WRONGTYPE key persists in the
        # session-scoped Redis container and 503s every later test that does
        # a full ``hb:*`` scan (``GET /api/v1/system/workers``), even though
        # this test's own target (``/market-status``) only ever reads it
        # per-exchange and is isolated from the failure by construction.
        await redis_client.delete(bogus_key)


async def test_market_status_reports_ws_state_and_open_gaps(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    code = await _seed_exchange(session_factory, monitored_markets=2, open_gaps=1)
    await redis_client.hset(
        keys.heartbeat("market", code),
        mapping={
            "ts": datetime.now(UTC).isoformat(),
            "errors": "0",
            "last_event_at": datetime.now(UTC).isoformat(),
            "ws_state": "connected",
            "reconnects": "4",
        },
    )
    actor: Actor = make_actor("market-status-reader-2")

    response = await client.get("/api/v1/system/market-status", headers=actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    entry = next(row for row in body["exchanges"] if row["exchange"] == code)
    assert entry["ws_state"] == "connected"
    assert entry["markets_monitored"] == 2
    assert entry["open_gaps"] == 1
    assert entry["last_event_at"] is not None
    assert entry["last_event_age_ms"] is not None
    assert entry["reconnects"] == 4


async def test_workers_reports_the_scanner_role_through_the_generic_hb_scan(
    client: httpx.AsyncClient,
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """T2.6: ``/system/workers`` "passes to show `scanner`" without any
    scanner-specific code (``services/system_status.py``'s ``scan_heartbeats``
    already parses role generically off the ``hb:{role}:{instance}`` key) --
    this is the contract test the brief asks for, proving it end to end
    rather than only at the unit level (``test_system_workers_status.py``).
    """
    instance = f"scanner-{uuid.uuid4().hex[:8]}"
    scanner_key = keys.heartbeat("scanner", instance)
    await redis_client.hset(
        scanner_key,
        mapping={"ts": datetime.now(UTC).isoformat(), "errors": "0", "version": "0.0.0"},
    )
    try:
        actor: Actor = make_actor("workers-reader-scanner")

        response = await client.get("/api/v1/system/workers", headers=actor.headers)

        assert response.status_code == 200, response.text
        rows = [row for row in response.json() if row["role"] == "scanner"]
        assert len(rows) == 1
        assert rows[0]["instance"] == instance
        assert rows[0]["status"] == "alive"
    finally:
        # No TTL on a hand-written hash (unlike the real 30s TTL
        # ``WorkerRuntime`` writes) — left behind, it would make the very
        # next test ("scanner absent") see a "present" scanner forever.
        await redis_client.delete(scanner_key)


async def test_workers_absent_scanner_is_simply_missing_not_reported_unavailable(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    """ "Ausente = sem verificação, distinto de indisponível" (brief): no
    ``hb:scanner:*`` key at all is a healthy ``200`` with no ``scanner`` row —
    never a fabricated "unavailable" entry, and never the ``503`` a genuine
    Redis outage gets (``test_workers_returns_503_...`` above).
    """
    actor: Actor = make_actor("workers-reader-scanner-absent")

    response = await client.get("/api/v1/system/workers", headers=actor.headers)

    assert response.status_code == 200, response.text
    assert all(row["role"] != "scanner" for row in response.json())
