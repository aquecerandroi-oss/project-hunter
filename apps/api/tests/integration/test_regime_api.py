"""Integration tests for ``GET /api/v1/regime`` and ``/regime/history``.

``is_stale`` also depends on an ``hb:scanner:*`` heartbeat reading ``alive``
(Astra, T2.6 diff review, must-fix 3: a crashed scanner must not leave an
open regime looking "fresh" forever) — every test asserting ``is_stale`` on
an otherwise-open row writes one first, exactly like the market-worker
heartbeat helpers in ``test_system_workers_api.py``.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio

from hunter_core.domain.enums import MarketRegime, RegimeScope
from hunter_core.redis import keys

from . import analysis_fixtures as fx
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


@contextlib.asynccontextmanager
async def _scanner_heartbeat(redis_client: redis_asyncio.Redis) -> AsyncGenerator[None]:
    """A fresh ``hb:scanner:*`` heartbeat, deleted on exit.

    A hand-written hash carries no TTL (unlike the real 30s TTL
    ``WorkerRuntime`` writes) — left behind, it reads ``alive`` for up to
    ``ALIVE_AFTER_S`` (15s) after the test that wrote it returns, which is
    long enough to pollute a *later* test in this same session-scoped Redis
    that specifically asserts no scanner heartbeat exists.
    """
    key = keys.heartbeat("scanner", f"scanner-{uuid.uuid4().hex[:8]}")
    await redis_client.hset(key, mapping={"ts": datetime.now(UTC).isoformat(), "errors": "0"})
    try:
        yield
    finally:
        await redis_client.delete(key)


async def test_get_current_regime_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/regime")
    assert response.status_code == 401


async def test_get_current_regime_returns_the_open_row_not_stale(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    async with _scanner_heartbeat(redis_client):
        regime_id = await fx.seed_regime(
            session_factory, scope=RegimeScope.BTC, regime=MarketRegime.BTC_BULL, end_time=None
        )
        actor: Actor = make_actor("regime-current-open")

        response = await client.get("/api/v1/regime", headers=actor.headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    row = next(i for i in items if i["id"] == str(regime_id))
    assert row["scope"] == "btc"
    assert row["regime"] == "BTC_BULL"
    assert row["is_stale"] is False
    assert row["is_stale"] is False


async def test_get_current_regime_unknown_carries_a_reason(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    reason = {"reason": "warmup: 12/30 days of 1m candles"}
    regime_id = await fx.seed_regime(
        session_factory,
        scope=RegimeScope.GLOBAL,
        regime=MarketRegime.UNKNOWN,
        confidence=None,
        supporting_features=reason,
    )
    actor: Actor = make_actor("regime-unknown-reason")

    response = await client.get("/api/v1/regime", headers=actor.headers)

    assert response.status_code == 200, response.text
    row = next(i for i in response.json()["items"] if i["id"] == str(regime_id))
    assert row["regime"] == "UNKNOWN"
    assert row["supporting_features"] == reason


async def test_get_current_regime_marks_a_closed_last_row_as_stale(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """A scope whose most recent row is already closed (``end_time`` set) is
    shown for continuity but stamped ``is_stale`` — never presented as
    current without the flag.

    ``start_time`` is pushed ten years out: ``current_per_scope()`` picks the
    row with the latest ``start_time`` for the scope, and this integration
    database is shared (session-scoped) across the whole file/suite, so a
    "recent" timestamp could still lose to another test's open BTC row
    created moments earlier in wall-clock time.
    """
    far_future = datetime.now(UTC) + timedelta(days=3650)
    regime_id = await fx.seed_regime(
        session_factory,
        scope=RegimeScope.BTC,
        regime=MarketRegime.SIDEWAYS,
        start_time=far_future,
        end_time=far_future + timedelta(hours=1),
    )
    actor: Actor = make_actor("regime-stale")

    response = await client.get("/api/v1/regime", headers=actor.headers)

    assert response.status_code == 200, response.text
    row = next(i for i in response.json()["items"] if i["id"] == str(regime_id))
    assert row["is_stale"] is True


async def test_get_current_regime_open_row_reads_stale_when_the_scanner_is_not_confirmed_alive(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """The bug Astra's diff review caught: a scanner that crashes right after
    opening a regime row must not leave it reading "fresh" forever just
    because nothing ever closed it. No ``hb:scanner:*`` heartbeat is written
    here — the row is open (``end_time IS NULL``) but still ``is_stale``.
    """
    far_future = datetime.now(UTC) + timedelta(days=7300)
    regime_id = await fx.seed_regime(
        session_factory,
        scope=RegimeScope.BTC,
        regime=MarketRegime.BTC_BEAR,
        start_time=far_future,
        end_time=None,
    )
    actor: Actor = make_actor("regime-open-no-scanner")

    response = await client.get("/api/v1/regime", headers=actor.headers)

    assert response.status_code == 200, response.text
    row = next(i for i in response.json()["items"] if i["id"] == str(regime_id))
    assert row["end_time"] is None
    assert row["is_stale"] is True


async def test_regime_history_pagination_round_trip(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    base = datetime.now(UTC) - timedelta(days=10)
    ids: list[str] = []
    for offset, confidence in enumerate(("0.6000", "0.7000", "0.8000")):
        row_id = await fx.seed_regime(
            session_factory,
            scope=RegimeScope.GLOBAL,
            regime=MarketRegime.HIGH_VOLATILITY,
            confidence=Decimal(confidence),
            start_time=base + timedelta(hours=offset),
            end_time=base + timedelta(hours=offset + 1),
        )
        ids.append(str(row_id))
    actor: Actor = make_actor("regime-history-pagination")

    # Walk every page (the shared, session-scoped test database may hold
    # other GLOBAL rows from earlier tests in this file/suite, more recent
    # than this test's ten-days-ago fixture, so the three target rows are not
    # guaranteed to land on the first couple of pages) — collecting the full,
    # duplicate-free id set is what actually proves the keyset cursor works.
    seen: set[str] = set()
    cursor: str | None = None
    for _ in range(50):
        params = "scope=global&limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = await client.get(f"/api/v1/regime/history?{params}", headers=actor.headers)
        assert page.status_code == 200, page.text
        body = page.json()
        page_ids = {item["id"] for item in body["items"]}
        assert not (page_ids & seen), "pagination must never repeat a row"
        seen |= page_ids
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert set(ids).issubset(seen)


async def _find_in_regime_history(
    client: httpx.AsyncClient, headers: dict[str, str], *, scope: RegimeScope, regime_id: str
) -> dict[str, Any]:
    """Walks ``/regime/history?scope=...`` page by page until ``regime_id`` is
    found — never ``GET /regime`` (``current_per_scope`` returns only the
    single newest ``start_time`` per scope, and this shared, session-scoped
    test database already holds far-future ``BTC`` rows from the
    ``is_stale``-on-``regime_v0`` tests above, which would always outrank a
    realistic "a few hours ago" hourly row). ``is_stale`` is computed by the
    exact same ``services/regime.py::_to_out`` for both endpoints, so history
    proves the rule identically.
    """
    cursor: str | None = None
    for _ in range(50):
        params = f"scope={scope.value}&limit=25" + (f"&cursor={cursor}" if cursor else "")
        page = await client.get(f"/api/v1/regime/history?{params}", headers=headers)
        assert page.status_code == 200, page.text
        body = page.json()
        for item in body["items"]:
            if item["id"] == regime_id:
                return item
        cursor = body["next_cursor"]
        if cursor is None:
            break
    raise AssertionError(f"regime {regime_id} not found in history")


@contextlib.asynccontextmanager
async def _regime_last_ts_heartbeat(
    redis_client: redis_asyncio.Redis, *, ts: datetime
) -> AsyncGenerator[None]:
    """A fresh ``hb:scanner:*`` heartbeat carrying ``regime_last_ts`` — the
    scanner-only field the T3.43b staleness rule reads raw
    (``routers/regime.py::_newest_regime_last_ts``), not exposed by
    ``WorkerHeartbeatOut``. Also carries ``ts`` so the same heartbeat can
    stand in for :func:`_scanner_heartbeat` where a test needs both signals.
    """
    key = keys.heartbeat("scanner", f"scanner-{uuid.uuid4().hex[:8]}")
    await redis_client.hset(
        key,
        mapping={
            "ts": datetime.now(UTC).isoformat(),
            "errors": "0",
            "regime_last_ts": ts.isoformat(),
        },
    )
    try:
        yield
    finally:
        await redis_client.delete(key)


async def test_get_current_regime_hourly_row_is_not_stale_with_a_fresh_heartbeat(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """T3.43b: an hourly (``regime_hourly_v1``) row is *always* closed by
    construction (``end_time = start_time + 1h``) — the ``regime_v0`` rule
    (closed => stale) would mark it stale forever. A recent hour with a fresh
    ``regime_last_ts`` heartbeat must read ``is_stale: false``.
    """
    now = datetime.now(UTC)
    end_time = now - timedelta(minutes=10)
    async with _regime_last_ts_heartbeat(redis_client, ts=now - timedelta(minutes=1)):
        regime_id = await fx.seed_regime(
            session_factory,
            scope=RegimeScope.BTC,
            regime=MarketRegime.BTC_BULL,
            confidence=Decimal("0.8000"),
            start_time=end_time - timedelta(hours=1),
            end_time=end_time,
            supporting_features=fx.hourly_regime_features(),
            classifier_version="regime_hourly_v1",
        )
        actor: Actor = make_actor("regime-hourly-fresh")

        row = await _find_in_regime_history(
            client, actor.headers, scope=RegimeScope.BTC, regime_id=str(regime_id)
        )

    assert row["is_stale"] is False
    assert row["identity"] == "regime_hourly_v1"
    assert row["score"] == "62.00"
    assert row["as_of"] is not None
    names = [c["name"] for c in row["components"]]
    assert names == ["trend", "breadth", "volatility", "drawdown", "funding"]
    funding = next(c for c in row["components"] if c["name"] == "funding")
    assert funding["normalized"] is None
    assert funding["weight"] == "0.10"


async def test_get_current_regime_hourly_row_is_stale_when_the_hour_is_old(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """An hourly row more than two hours past its own ``end_time`` reads
    stale even with a heartbeat confirmed fresh right now — the row itself
    has aged out, and a live producer today does not revive an old hour."""
    now = datetime.now(UTC)
    end_time = now - timedelta(hours=3)
    async with _regime_last_ts_heartbeat(redis_client, ts=now - timedelta(minutes=1)):
        regime_id = await fx.seed_regime(
            session_factory,
            scope=RegimeScope.BTC,
            regime=MarketRegime.BTC_BULL,
            start_time=end_time - timedelta(hours=1),
            end_time=end_time,
            supporting_features=fx.hourly_regime_features(),
            classifier_version="regime_hourly_v1",
        )
        actor: Actor = make_actor("regime-hourly-old-hour")

        row = await _find_in_regime_history(
            client, actor.headers, scope=RegimeScope.BTC, regime_id=str(regime_id)
        )

    assert row["is_stale"] is True


async def test_get_current_regime_hourly_row_is_stale_without_a_regime_heartbeat(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """A recent hour with **no** ``regime_last_ts`` heartbeat at all (the
    producer's own liveness signal, distinct from the generic scanner
    ``ts``) reads stale — the row's own recency is not, by itself, proof the
    pipeline is still writing.
    """
    now = datetime.now(UTC)
    end_time = now - timedelta(minutes=5)
    regime_id = await fx.seed_regime(
        session_factory,
        scope=RegimeScope.BTC,
        regime=MarketRegime.BTC_BULL,
        start_time=end_time - timedelta(hours=1),
        end_time=end_time,
        supporting_features=fx.hourly_regime_features(),
        classifier_version="regime_hourly_v1",
    )
    actor: Actor = make_actor("regime-hourly-no-heartbeat")

    row = await _find_in_regime_history(
        client, actor.headers, scope=RegimeScope.BTC, regime_id=str(regime_id)
    )

    assert row["is_stale"] is True


async def test_get_current_regime_v0_row_carries_none_for_the_hourly_fields(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """A ``regime_v0`` row (no ``classifier_version``, the default the T2.6
    classifier writes) never fabricates the hourly-only fields."""
    regime_id = await fx.seed_regime(
        session_factory,
        scope=RegimeScope.GLOBAL,
        regime=MarketRegime.SIDEWAYS,
    )
    actor: Actor = make_actor("regime-v0-additive-fields")

    response = await client.get("/api/v1/regime", headers=actor.headers)

    assert response.status_code == 200, response.text
    row = next(i for i in response.json()["items"] if i["id"] == str(regime_id))
    assert row["as_of"] is None
    assert row["score"] is None
    assert row["components"] == []
    assert row["identity"] is None


async def test_regime_history_garbage_cursor_returns_422(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("regime-history-garbage-cursor")

    response = await client.get(
        "/api/v1/regime/history?cursor=!!!not-a-valid-cursor!!!", headers=actor.headers
    )

    assert response.status_code == 422, response.text
    assert response.json()["type"].endswith("invalid-cursor")
