"""Universe ranking, allow/blocklist and delisting — docs/plans/M1.md T1.3 item 1."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import event, select

from hunter_core.db.models.markets import Market
from hunter_core.db.session import role_session
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.streams import Streams
from hunter_core.settings import Settings
from hunter_market_worker import universe as universe_mod

from . import builders
from .fakes import FakeAdapter, FakeRuntime
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration

PRODUCER = "market-worker@test:1"


def _adapter_with(exchange_code: str, symbols_and_volumes: dict[str, str]) -> FakeAdapter:
    adapter = FakeAdapter(code=exchange_code)
    for symbol, volume in symbols_and_volumes.items():
        base = symbol.removesuffix("USDT")
        adapter.markets.append(builders.market(symbol, base, exchange=exchange_code))
        adapter.tickers[symbol] = builders.ticker(
            symbol, "100", quote_volume_24h=volume, exchange=exchange_code
        )
    return adapter


async def _monitored_rows(session_factory: Any, exchange_code: str) -> list[Market]:
    async with role_session(session_factory, db_role="hunter_worker") as session:
        from hunter_core.db.models.markets import Exchange

        rows = (
            await session.scalars(
                select(Market)
                .join(Exchange, Exchange.id == Market.exchange_id)
                .where(Exchange.code == exchange_code)
                .order_by(Market.monitor_rank)
            )
        ).all()
        return list(rows)


async def test_refresh_universe_ranks_by_volume_and_caps_monitored_at_universe_size(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    adapter = _adapter_with(exchange_code, {"AUSDT": "300", "BUSDT": "100", "CUSDT": "200"})
    settings = Settings(market_universe_size=2)

    monitored = await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )

    assert monitored == ["AUSDT", "CUSDT"]
    rows = {row.symbol: row for row in await _monitored_rows(db_session_factory, exchange_code)}
    assert rows["AUSDT"].monitor_rank == 1
    assert rows["CUSDT"].monitor_rank == 2
    assert rows["BUSDT"].monitor_rank == 3
    assert rows["BUSDT"].is_monitored is False
    assert rows["AUSDT"].volume_24h_usd == 300
    assert (
        await redis_client.hget(f"mkt:{exchange_code}:AUSDT:ticker", "quote_volume_24h") == b"300"
    )


async def test_refresh_universe_allowlist_forces_monitoring_outside_top_n(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    adapter = _adapter_with(exchange_code, {"AUSDT": "300", "BUSDT": "100", "CUSDT": "200"})
    settings = Settings(market_universe_size=1, market_universe_allowlist=["BUSDT"])

    monitored = await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )

    assert set(monitored) == {"AUSDT", "BUSDT"}


async def test_refresh_universe_blocklist_excludes_even_top_ranked(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    adapter = _adapter_with(exchange_code, {"AUSDT": "300", "BUSDT": "100"})
    settings = Settings(market_universe_size=2, market_universe_blocklist=["AUSDT"])

    monitored = await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )

    assert monitored == ["BUSDT"]


async def test_refresh_universe_marks_delisted_when_symbol_disappears(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    adapter = _adapter_with(exchange_code, {"AUSDT": "300", "BUSDT": "100"})
    settings = Settings(market_universe_size=10)
    await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )

    adapter.markets = [m for m in adapter.markets if m.symbol != "BUSDT"]
    del adapter.tickers["BUSDT"]
    await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )

    rows = {row.symbol: row for row in await _monitored_rows(db_session_factory, exchange_code)}
    assert rows["BUSDT"].status.value == "delisted"
    assert rows["BUSDT"].delisted_at is not None
    assert rows["BUSDT"].is_monitored is False


async def test_refresh_universe_publishes_universe_changed_only_when_it_changes(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    adapter = _adapter_with(exchange_code, {"AUSDT": "300", "BUSDT": "100"})
    settings = Settings(market_universe_size=10)

    await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )
    length_after_first = await redis_client.xlen(Streams.MARKET_UNIVERSE_CHANGED)
    assert length_after_first == 1

    await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )
    length_after_second = await redis_client.xlen(Streams.MARKET_UNIVERSE_CHANGED)
    assert length_after_second == 1  # unchanged monitored set -> no second publish

    entries = await redis_client.xrange(Streams.MARKET_UNIVERSE_CHANGED, "-", "+")
    envelope = EventEnvelope.from_bytes(entries[-1][1][b"data"])
    assert envelope.payload["added"] == ["AUSDT", "BUSDT"]
    assert envelope.payload["removed"] == []
    assert envelope.payload["total"] == 2
    assert envelope.producer == PRODUCER


async def test_blocked_volume_leader_does_not_take_a_slot(
    db_session_factory: Any, redis_client: Any
) -> None:
    adapter = _adapter_with(unique_code(), {"AUSDT": "300", "BUSDT": "100"})
    monitored = await universe_mod.refresh_universe(
        db_session_factory,
        adapter,
        redis_client,
        Settings(market_universe_size=1, market_universe_blocklist=["AUSDT"]),
        producer=PRODUCER,
    )
    assert monitored == ["BUSDT"]


async def test_inactive_market_exits_even_when_allowlisted(
    db_session_factory: Any, redis_client: Any
) -> None:
    from hunter_core.domain.enums import MarketStatus

    adapter = _adapter_with(unique_code(), {"AUSDT": "300", "BUSDT": "100"})
    settings = Settings(market_universe_size=2, market_universe_allowlist=["AUSDT"])
    await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )
    adapter.markets[0] = adapter.markets[0].model_copy(update={"status": MarketStatus.DELISTED})
    monitored = await universe_mod.refresh_universe(
        db_session_factory, adapter, redis_client, settings, producer=PRODUCER
    )
    assert monitored == ["BUSDT"]
    rows = await redis_client.xrange(Streams.MARKET_UNIVERSE_CHANGED)
    changed = EventEnvelope.from_bytes(rows[-1][1][b"data"])
    assert changed.payload["removed"] == ["AUSDT"]


# ---- HIGH-4: ranking writes ranks back with one statement, not one per row -


async def test_rank_and_monitor_issues_a_single_update_statement(
    db_session_factory: Any, redis_client: Any
) -> None:
    exchange_code = unique_code()
    adapter = _adapter_with(exchange_code, {f"SYM{i}USDT": str(1000 - i) for i in range(30)})
    settings = Settings(market_universe_size=10)

    statements: list[str] = []
    engine = db_session_factory.kw["bind"].sync_engine

    def _listener(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        if statement.strip().upper().startswith("UPDATE"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        await universe_mod.refresh_universe(
            db_session_factory, adapter, redis_client, settings, producer=PRODUCER
        )
    finally:
        event.remove(engine, "before_cursor_execute", _listener)

    # one UPDATE for the "reset all ranks" step, one for the bulk rank write
    # -- never one per market (~30, if the old per-row loop were still there)
    assert len(statements) <= 2


# ---- HIGH-3: a failed refresh retries fast, not on the full success interval -


async def test_run_universe_retries_fast_after_failure_and_resets_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduces the 900s blindness window: two failed refreshes must sleep
    on a short, capped backoff (never anywhere near
    ``market_universe_refresh_s``), and the delay must return to the full
    interval the moment a refresh succeeds again."""
    calls = 0

    async def fake_refresh(*_args: Any, **_kwargs: Any) -> list[str]:
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise RuntimeError("simulated postgres outage")
        return ["BTCUSDT"]

    monkeypatch.setattr(universe_mod, "refresh_universe", fake_refresh)

    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        if len(sleeps) >= 3:
            raise asyncio.CancelledError

    settings = Settings(market_universe_refresh_s=900)
    universe = universe_mod.MonitoredUniverse()
    runtime = FakeRuntime()

    with pytest.raises(asyncio.CancelledError):
        await universe_mod.run_universe(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            settings,
            universe,
            runtime,  # type: ignore[arg-type]
            sleep=fake_sleep,
            rand=lambda: 0.0,
        )

    assert calls == 3
    # Two failures: short, capped, non-decreasing backoff -- nowhere near the
    # 900s success interval.
    assert sleeps[0] < 30
    assert sleeps[1] < 60
    assert sleeps[0] <= sleeps[1]
    # The third refresh succeeded: back to the full configured interval.
    assert sleeps[2] == 900
    assert runtime.error_count == 2
    assert runtime.success_count == 1
