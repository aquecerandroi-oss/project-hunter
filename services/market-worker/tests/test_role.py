"""``hunter_market_worker.main._run_spot_process`` — the whole process body
for ``MARKET_ROLE=spot`` (T3.0f). Wiring only (readiness checks, status
details, cleanup on cancellation) — the spot data path itself is already
covered end to end by ``test_spot_ingest.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import MarketType
from hunter_core.runtime import WorkerRuntime
from hunter_core.settings import Settings
from hunter_market_worker import main as market_main
from hunter_market_worker.coverage import CoverageTracker

from . import builders
from .fakes import FakeAdapter

pytestmark = pytest.mark.integration


class _FakeEngine:
    healthy = True


def _stub_build_spot_adapter(adapter: FakeAdapter) -> Any:
    """A typed stand-in for ``config.build_spot_adapter`` -- avoids the bare
    ``lambda code, settings, redis: ...`` pyright otherwise reports as
    ``reportUnknownLambdaType``/``reportUnknownArgumentType``."""

    def _build(code: str, settings: Settings, redis: object) -> FakeAdapter:
        del code, settings, redis
        return adapter

    return _build


async def test_run_spot_process_registers_its_own_status_and_readiness(
    monkeypatch: pytest.MonkeyPatch, redis_client: Any, db_session_factory: Any
) -> None:
    """``MARKET_SPOT_ENABLED=false`` under ``MARKET_ROLE=spot`` (the brief's
    explicit non-ambiguous case): the process still starts, registers its own
    ``spot``/``rest_gate`` status details and ``partitions``/``outbox``
    readiness checks, and reports ``spot: "absent"`` -- idling, never
    crash-looping."""
    monkeypatch.setattr(
        market_main, "build_spot_adapter", _stub_build_spot_adapter(FakeAdapter(code="binance"))
    )
    settings = Settings(market_role="spot", market_spot_enabled=False)
    runtime = WorkerRuntime(
        "market",
        settings,
        instance="test-spot:1",
        engine=_FakeEngine(),  # type: ignore[arg-type]
        redis_client=redis_client,
    )

    task = asyncio.ensure_future(
        market_main._run_spot_process(runtime, db_session_factory)  # pyright: ignore[reportPrivateUsage]
    )
    await asyncio.sleep(0.5)

    assert "spot" in runtime.status_details
    assert runtime.status_details["spot"]() == "absent"
    assert "rest_gate" in runtime.status_details
    names = {check.__name__ for check in runtime.readiness_checks}
    assert {"partitions", "outbox"} <= names

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # Cleanup: this process's own contributions are gone, and nothing of a
    # perpetual worker's was ever registered (no "health"/"queues"/"fx" here).
    assert "spot" not in runtime.status_details
    assert "rest_gate" not in runtime.status_details
    remaining = {check.__name__ for check in runtime.readiness_checks}
    assert not ({"partitions", "outbox"} & remaining)


async def test_run_spot_process_actually_collects_when_the_switch_is_on(
    monkeypatch: pytest.MonkeyPatch, redis_client: Any, db_session_factory: Any
) -> None:
    """The flip side: ``MARKET_SPOT_ENABLED=true`` under ``MARKET_ROLE=spot``
    reaches ``spot.run_spot``'s real collection branch (``status.enabled``
    becomes ``True``) even though this process never built a perpetual
    adapter at all."""
    adapter = FakeAdapter(code="binance")
    adapter.markets = [
        builders.market("BTCUSDT", "BTC", exchange="binance", market_type=MarketType.SPOT)
    ]
    adapter.tickers = {
        "BTCUSDT": builders.ticker(
            "BTCUSDT", "50000", exchange="binance", quote_volume_24h=Decimal("100000000")
        )
    }
    monkeypatch.setattr(market_main, "build_spot_adapter", _stub_build_spot_adapter(adapter))
    settings = Settings(market_role="spot", market_spot_enabled=True)
    runtime = WorkerRuntime(
        "market",
        settings,
        instance="test-spot:2",
        engine=_FakeEngine(),  # type: ignore[arg-type]
        redis_client=redis_client,
    )

    task = asyncio.ensure_future(
        market_main._run_spot_process(runtime, db_session_factory)  # pyright: ignore[reportPrivateUsage]
    )
    try:
        await asyncio.wait_for(adapter.stream_started.wait(), timeout=15.0)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert adapter.stream_started.is_set()


async def test_run_spot_process_flush_ticks_stamps_through_the_dict_run_ingest_registered(
    monkeypatch: pytest.MonkeyPatch, redis_client: Any, db_session_factory: Any
) -> None:
    """T3.46g review, reservation 1: ``run_market``/``_run_spot_process`` build
    one ``coverage_stamps`` dict and pass the *same object* to ``run_ingest``
    and ``coalesce_loop`` -- a wiring bug (two separate dicts) would leave
    ``flush_ticks``'s own ``coverage_stamps.get(market_type)`` lookup empty,
    silently dropping its stamp call. Nothing here mocks ``run_ingest`` or
    ``coalesce_loop``: only the exchange adapter is fake, exactly like the
    tests above.

    ``CoverageTracker.due`` gates the *other* caller (the periodic
    housekeeping tick inside ``consume_once``, ``streaming.py``) -- disabled
    here so every observed call to ``stamp`` can only have come from
    ``flush_ticks``, the one call site that depends on the shared dict. A
    bug that split the dict into two would leave ``calls`` empty forever.
    """
    calls: list[int] = []
    original_stamp = CoverageTracker.stamp

    async def _counting_stamp(self: CoverageTracker, *args: Any, **kwargs: Any) -> bool:
        calls.append(id(self))
        return await original_stamp(self, *args, **kwargs)

    monkeypatch.setattr(CoverageTracker, "stamp", _counting_stamp)
    monkeypatch.setattr(CoverageTracker, "due", lambda self, *a, **k: False)  # type: ignore[method-assign]

    adapter = FakeAdapter(code="binance")
    adapter.markets = [
        builders.market("BTCUSDT", "BTC", exchange="binance", market_type=MarketType.SPOT)
    ]
    adapter.tickers = {
        "BTCUSDT": builders.ticker(
            "BTCUSDT", "50000", exchange="binance", quote_volume_24h=Decimal("100000000")
        )
    }
    monkeypatch.setattr(market_main, "build_spot_adapter", _stub_build_spot_adapter(adapter))
    settings = Settings(market_role="spot", market_spot_enabled=True)
    runtime = WorkerRuntime(
        "market",
        settings,
        instance="test-spot:stamp",
        engine=_FakeEngine(),  # type: ignore[arg-type]
        redis_client=redis_client,
    )

    task = asyncio.ensure_future(
        market_main._run_spot_process(runtime, db_session_factory)  # pyright: ignore[reportPrivateUsage]
    )
    try:
        await asyncio.wait_for(adapter.stream_started.wait(), timeout=15.0)
        await adapter.push_event(
            builders.ticker_ws("BTCUSDT", "50001", exchange="binance", market_type=MarketType.SPOT)
        )
        deadline = asyncio.get_event_loop().time() + 10.0
        while not calls and asyncio.get_event_loop().time() < deadline:  # noqa: ASYNC110 — polling a plain list, not an Event
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert calls, (
        "flush_ticks never reached the stamp run_ingest registered -- "
        "coverage_stamps dicts diverged"
    )
    # A single CoverageTracker instance runs this whole process's spot path;
    # every counted call landing on it (never a second, unrelated tracker) is
    # the identity the reservation asked for.
    assert len(set(calls)) == 1
