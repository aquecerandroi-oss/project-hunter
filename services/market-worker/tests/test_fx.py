"""T3.11a — the ``fx_observations`` collector: idempotent, never fabricates.

``httpx.MockTransport`` stands in for Binance spot, as
``packages/exchange-adapters/tests/unit/test_spot_rest_client.py`` already
does for the REST client itself; the mandatory cases from
``docs/EXCHANGE_INTEGRATION.md`` §6 that apply to a single-endpoint REST
poller (malformed message, and the two ways a poll may not produce a row:
rate limit and transport failure) are covered here, plus the FX-specific
ones the T3.11a brief names explicitly: idempotency and the plausibility
band.
"""

from __future__ import annotations

import asyncio
import copy
import itertools
import json
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from sqlalchemy import select

from hunter_core.db.models.fx import FxObservation
from hunter_core.db.models.system import SystemEvent
from hunter_core.db.session import role_session
from hunter_core.settings import Settings
from hunter_exchanges.binance_spot.http import SpotHttp
from hunter_market_worker.fx import (
    FX_SOURCE,
    FX_SYMBOL,
    FxCollectorHealth,
    fx_implausible_total,
    fx_observations_total,
    run_fx_collector,
)
from hunter_market_worker.fx import collect_once as fx_collect_once

from .fakes import FakeRuntime

pytestmark = pytest.mark.integration

FIXTURE = (Path(__file__).parent / "fixtures" / "fx_usdtbrl_ticker_24hr.json").read_text(
    encoding="utf-8"
)
_BASE_RAW: dict[str, Any] = json.loads(FIXTURE)
# ``observed_at <= available_at`` is a CHECK (§18.2): every closeTime this
# module invents must stay in the past relative to the real clock the insert
# stamps ``available_at`` with, so the base is "now, minus a safety margin"
# rather than an arbitrary fixed constant.
_close_times = itertools.count(int(time.time() * 1000) - 60_000)

Handler = Callable[[httpx.Request], httpx.Response]


def _raw_ticker(*, rate: str | None = None, close_time_ms: int | None = None) -> dict[str, Any]:
    """A fresh copy of the recorded fixture, with a unique ``closeTime`` unless
    the caller wants a repeat (the idempotency test)."""
    raw = copy.deepcopy(_BASE_RAW)
    raw["closeTime"] = close_time_ms if close_time_ms is not None else next(_close_times)
    if rate is not None:
        raw["lastPrice"] = rate
    return raw


class _FakeLimiter:
    """The minimal surface ``SpotHttp`` needs from a rate limiter — never
    waits, so these tests are fast and offline (Redis plays no part in them;
    the token bucket's own Redis contract is ``test_rate_limit.py``'s job)."""

    def __init__(self) -> None:
        self.acquired: list[tuple[str, int]] = []
        self.cooldowns: list[tuple[str, float]] = []
        self.ip_gate: Any = None

    async def acquire(self, bucket: str, weight: int = 1) -> None:
        self.acquired.append((bucket, weight))

    async def cooldown(self, bucket: str, *, retry_after_s: float) -> None:
        self.cooldowns.append((bucket, retry_after_s))

    async def record_used_weight(self, bucket: str, used: int) -> None:
        return None


class _FastSleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _spot_http(
    handler: Handler, *, sleep: Callable[[float], Awaitable[None]] | None = None
) -> SpotHttp:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.binance.com"
    )
    return SpotHttp(
        http_client=http_client,
        rate_limiter=_FakeLimiter(),  # type: ignore[arg-type]
        sleep=sleep or _FastSleeper(),
        backoff_base_s=0.01,
        backoff_max_s=0.02,
    )


def _always(
    status: int = 200, *, body: Any = None, headers: dict[str, str] | None = None
) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body, headers=headers)

    return handler


async def _observations(factory: Any, *, observed_at: Any) -> list[FxObservation]:
    async with role_session(factory, db_role="hunter_worker") as session:
        rows = await session.scalars(
            select(FxObservation).where(
                FxObservation.pair == FX_SYMBOL,
                FxObservation.source == FX_SOURCE,
                FxObservation.observed_at == observed_at,
            )
        )
        return list(rows)


def _ms_to_dt(ms: int) -> Any:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ms / 1000, tz=UTC)


# ---- persistence, the declared source/pair, causality ---------------------


async def test_collect_once_persists_the_declared_pair_and_source(db_session_factory: Any) -> None:
    raw = _raw_ticker(rate="5.43210000")
    http = _spot_http(_always(body=raw))

    outcome = await fx_collect_once(http, db_session_factory)

    assert outcome == "ok"
    rows = await _observations(db_session_factory, observed_at=_ms_to_dt(raw["closeTime"]))
    assert len(rows) == 1
    row = rows[0]
    assert row.pair == FX_SYMBOL == "USDTBRL"
    assert row.source == FX_SOURCE == "binance.spot.ticker"
    assert row.rate == Decimal("5.43210000")
    assert row.raw == raw
    assert row.observed_at <= row.available_at
    await http.aclose()


# ---- idempotency: the unique key is (pair, source, observed_at) -----------


async def test_collect_once_is_idempotent_for_the_same_observed_at(db_session_factory: Any) -> None:
    close_time_ms = next(_close_times)
    raw = _raw_ticker(close_time_ms=close_time_ms)
    http = _spot_http(_always(body=raw))

    first = await fx_collect_once(http, db_session_factory)
    second = await fx_collect_once(http, db_session_factory)

    assert first == "ok"
    assert second == "duplicate"
    rows = await _observations(db_session_factory, observed_at=_ms_to_dt(close_time_ms))
    assert len(rows) == 1
    await http.aclose()


# ---- malformed message: never a fabricated ticker --------------------------


async def test_collect_once_writes_nothing_on_a_malformed_body(db_session_factory: Any) -> None:
    raw = _raw_ticker()
    del raw["bidPrice"]  # required by parse_ticker_24h
    http = _spot_http(_always(body=raw))

    outcome = await fx_collect_once(http, db_session_factory)

    assert outcome == "malformed"
    rows = await _observations(db_session_factory, observed_at=_ms_to_dt(raw["closeTime"]))
    assert rows == []
    await http.aclose()


# ---- plausibility band: recorded, flagged, never refused here -------------


async def test_collect_once_persists_an_implausible_rate_but_flags_it(
    db_session_factory: Any,
) -> None:
    raw = _raw_ticker(rate="0.0000005432")  # a scale error: outside [1, 100]
    http = _spot_http(_always(body=raw))
    before = fx_implausible_total._value.get()  # type: ignore[attr-defined]

    outcome = await fx_collect_once(http, db_session_factory)

    assert outcome == "ok"
    rows = await _observations(db_session_factory, observed_at=_ms_to_dt(raw["closeTime"]))
    assert len(rows) == 1
    assert rows[0].rate == Decimal("0.0000005432")
    after = fx_implausible_total._value.get()  # type: ignore[attr-defined]
    assert after == before + 1
    await http.aclose()


# ---- 429/418: a system_event, never a silently retried loop ---------------


async def test_collect_once_reports_rate_limited_and_writes_no_row(db_session_factory: Any) -> None:
    raw = _raw_ticker()
    http = _spot_http(_always(429, body={"code": -1003}, headers={"Retry-After": "7"}))
    before = fx_observations_total.labels(outcome="rate_limited")._value.get()  # type: ignore[attr-defined]

    outcome = await fx_collect_once(http, db_session_factory)

    assert outcome == "rate_limited"
    after = fx_observations_total.labels(outcome="rate_limited")._value.get()  # type: ignore[attr-defined]
    assert after == before + 1
    rows = await _observations(db_session_factory, observed_at=_ms_to_dt(raw["closeTime"]))
    assert rows == []
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        events = await session.scalars(
            select(SystemEvent).where(SystemEvent.event == "fx_collector_rate_limited")
        )
        assert any(events)
    await http.aclose()


# ---- transport failure after SpotHttp's own retries -----------------------


async def test_collect_once_reports_network_error_and_writes_no_row(
    db_session_factory: Any,
) -> None:
    raw = _raw_ticker()
    http = _spot_http(_always(503))

    outcome = await fx_collect_once(http, db_session_factory)

    assert outcome == "network_error"
    rows = await _observations(db_session_factory, observed_at=_ms_to_dt(raw["closeTime"]))
    assert rows == []
    await http.aclose()


# ---- FxCollectorHealth: the /ready status detail, no I/O -------------------


def test_fx_collector_health_is_unknown_then_ok_then_stale() -> None:
    now = [1_000.0]
    health = FxCollectorHealth(clock=lambda: now[0])

    assert health.status() == "unknown"

    health.record_success()
    assert health.status() == "ok"

    now[0] += 301  # past FxPolicy.availability_max_age_s (300s)
    assert health.status() == "stale"


# ---- shard/venue guard: one collector per venue, never N -------------------


async def test_run_fx_collector_idles_forever_off_shard_zero() -> None:
    runtime: Any = FakeRuntime(settings=Settings(market_shard="1/2"))
    runtime.status_details = cast("dict[str, Any]", {})

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            run_fx_collector(cast(Any, object()), cast(Any, object()), "binance", runtime),
            timeout=0.05,
        )

    assert "fx" not in runtime.status_details


async def test_run_fx_collector_idles_forever_off_the_declared_venue() -> None:
    runtime: Any = FakeRuntime(settings=Settings())
    runtime.status_details = cast("dict[str, Any]", {})

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            run_fx_collector(cast(Any, object()), cast(Any, object()), "bybit", runtime),
            timeout=0.05,
        )

    assert "fx" not in runtime.status_details
