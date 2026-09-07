"""T3.0c — the tradable SPOT universe is a **floor**, not a top-N.

D1 (``.claude/state/decisions-M3-delegated-2026-09-06.md``): the wallet executes
on Binance spot, and a pair is only tradable when it clears 50M USDT of 24h
volume **on spot itself** — never inferred from the perpetual's volume, which is
a different book on a different product.

The floor is exercised against a real recorded ``GET /api/v3/ticker/24hr``
snapshot (``spot_universe_ticker_24hr.json``, every USDT row of one call, not a
hand-picked handful): five megacaps would clear any floor, so five megacaps
prove nothing about a rule whose entire job is to say *no*.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from hunter_core.db.models.markets import Exchange, Market
from hunter_core.db.models.system import OutboxEvent
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketStatus, MarketType
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.streams import Streams
from hunter_core.settings import Settings
from hunter_exchanges.binance_spot import normalize as spot_normalize
from hunter_market_worker import spot_universe

from . import builders
from .fakes import FakeAdapter
from .universe_test_helpers import unique_code

FIXTURES = (
    Path(__file__).parents[3]
    / "packages"
    / "exchange-adapters"
    / "hunter_exchanges"
    / "testing"
    / "fixtures"
)
PRODUCER = "market-worker@test:1"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _spot_market(symbol: str, *, quote: str = "USDT", **overrides: object) -> Any:
    base = symbol.removesuffix(quote) or "X"
    return builders.market(symbol, base, quote, market_type=MarketType.SPOT, **overrides)


def _spot_ticker(symbol: str, quote_volume: str | None, **overrides: object) -> Any:
    fields: dict[str, object] = {
        "quote_volume_24h": None if quote_volume is None else Decimal(quote_volume),
        "market_type": MarketType.SPOT,
        **overrides,
    }
    return builders.ticker_rest(symbol, "100", **fields)


# --------------------------------------------------------------------------
# The floor, against the recorded snapshot
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_recorded_snapshot_admits_nineteen_of_seven_hundred_and_forty() -> None:
    """The number matters: T3.0a measured 19 live pairs above the floor while
    D1 had estimated ~50. Whoever sizes connections uses the measured number."""
    rows = _load("spot_universe_ticker_24hr.json")
    tickers = {row["symbol"]: spot_normalize.parse_ticker_24h(row) for row in rows}
    markets = [_spot_market(symbol) for symbol in tickers]

    tradable = spot_universe.tradable_symbols(markets, tickers)

    assert len(rows) == 740
    assert len(tradable) == 19
    assert {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"} <= tradable


@pytest.mark.unit
def test_a_pair_exactly_on_the_floor_is_in_and_a_cent_below_is_out() -> None:
    floor = spot_universe.SPOT_VOLUME_FLOOR_USDT
    markets = [_spot_market("ONUSDT"), _spot_market("UNDERUSDT")]
    tickers = {
        "ONUSDT": _spot_ticker("ONUSDT", str(floor)),
        "UNDERUSDT": _spot_ticker("UNDERUSDT", str(floor - Decimal("0.01"))),
    }

    assert spot_universe.tradable_symbols(markets, tickers) == {"ONUSDT"}


@pytest.mark.unit
def test_no_ticker_is_not_tradable_rather_than_assumed_liquid() -> None:
    """A pair whose volume we could not read is not a pair we may execute on."""
    markets = [_spot_market("QUIETUSDT")]

    assert spot_universe.tradable_symbols(markets, {}) == set()
    assert (
        spot_universe.tradable_symbols(markets, {"QUIETUSDT": _spot_ticker("QUIETUSDT", None)})
        == set()
    )


@pytest.mark.unit
def test_non_usdt_quote_and_inactive_and_blocklisted_are_excluded() -> None:
    big = str(spot_universe.SPOT_VOLUME_FLOOR_USDT * 10)
    markets = [
        _spot_market("ETHBTC", quote="BTC"),
        _spot_market("HALTUSDT", status=MarketStatus.SUSPENDED),
        _spot_market("BLOCKEDUSDT"),
        _spot_market("GOODUSDT"),
    ]
    tickers = {m.symbol: _spot_ticker(m.symbol, big) for m in markets}

    tradable = spot_universe.tradable_symbols(markets, tickers, blocklist={"blockedusdt"})

    assert tradable == {"GOODUSDT"}


@pytest.mark.unit
def test_a_perpetual_row_can_never_enter_the_spot_universe() -> None:
    """Belt and braces: the selection filters on ``market_type`` itself, so an
    adapter that answered ``list_markets`` with the wrong product cannot make
    the wallet execute against a perpetual listing."""
    perpetual = builders.market("BTCUSDT", "BTC", market_type=MarketType.PERPETUAL)
    tickers = {"BTCUSDT": _spot_ticker("BTCUSDT", "999999999999")}

    assert spot_universe.tradable_symbols([perpetual], tickers) == set()


# --------------------------------------------------------------------------
# The refresh, against Postgres
# --------------------------------------------------------------------------


def _spot_adapter(code: str, volumes: dict[str, str]) -> FakeAdapter:
    adapter = FakeAdapter(code=code)
    for symbol, volume in volumes.items():
        adapter.markets.append(_spot_market(symbol, exchange=code))
        adapter.tickers[symbol] = _spot_ticker(symbol, volume, exchange=code)
    return adapter


def _one_pair_adapter(
    code: str,
    symbol: str,
    volume: str | None,
    *,
    status: MarketStatus = MarketStatus.ACTIVE,
    quote: str = "USDT",
) -> FakeAdapter:
    """One refresh's worth of reading for a single already-listed pair -- a
    fresh adapter every call, exactly like a market-worker process that
    restarted would build one from scratch."""
    adapter = FakeAdapter(code=code)
    adapter.markets.append(_spot_market(symbol, exchange=code, status=status, quote=quote))
    if volume is not None:
        adapter.tickers[symbol] = _spot_ticker(symbol, volume, exchange=code)
    return adapter


async def _markets(session_factory: Any, code: str) -> dict[tuple[str, MarketType], Market]:
    async with role_session(session_factory, db_role="hunter_worker") as session:
        rows = (
            await session.scalars(
                select(Market)
                .join(Exchange, Exchange.id == Market.exchange_id)
                .where(Exchange.code == code)
            )
        ).all()
        return {(row.symbol, row.market_type): row for row in rows}


@pytest.mark.integration
async def test_refresh_writes_spot_rows_and_monitors_only_above_the_floor(
    db_session_factory: Any, redis_client: Any
) -> None:
    code = unique_code()
    floor = spot_universe.SPOT_VOLUME_FLOOR_USDT
    adapter = _spot_adapter(code, {"BIGUSDT": str(floor * 2), "SMALLUSDT": str(floor / 2)})

    monitored = await spot_universe.refresh_spot_universe(
        db_session_factory, adapter, redis_client, Settings(), producer=PRODUCER
    )

    assert monitored == ["BIGUSDT"]
    rows = await _markets(db_session_factory, code)
    assert rows[("BIGUSDT", MarketType.SPOT)].is_monitored is True
    assert rows[("SMALLUSDT", MarketType.SPOT)].is_monitored is False
    # Rank is still written, so the operator can see *where* a pair sits
    # relative to the floor rather than only that it is out.
    assert rows[("BIGUSDT", MarketType.SPOT)].monitor_rank == 1
    assert rows[("SMALLUSDT", MarketType.SPOT)].monitor_rank == 2
    assert rows[("BIGUSDT", MarketType.SPOT)].volume_24h_usd == floor * 2


@pytest.mark.integration
async def test_spot_refresh_leaves_the_perpetual_row_of_the_same_symbol_alone(
    db_session_factory: Any, redis_client: Any
) -> None:
    """The whole point of T3.0b's third identity column, proved end to end."""
    from hunter_market_worker import universe as universe_mod

    code = unique_code()
    perp = FakeAdapter(code=code)
    perp.markets.append(builders.market("BTCUSDT", "BTC", exchange=code))
    perp.tickers["BTCUSDT"] = builders.ticker(
        "BTCUSDT", "100", quote_volume_24h=Decimal("7"), exchange=code
    )
    await universe_mod.refresh_universe(
        db_session_factory, perp, redis_client, Settings(), producer=PRODUCER
    )
    before = (await _markets(db_session_factory, code))[("BTCUSDT", MarketType.PERPETUAL)]

    spot = _spot_adapter(code, {"BTCUSDT": str(spot_universe.SPOT_VOLUME_FLOOR_USDT * 3)})
    await spot_universe.refresh_spot_universe(
        db_session_factory, spot, redis_client, Settings(), producer=PRODUCER
    )

    rows = await _markets(db_session_factory, code)
    after = rows[("BTCUSDT", MarketType.PERPETUAL)]
    assert after.id == before.id
    assert after.is_monitored is True
    assert after.volume_24h_usd == Decimal("7")
    assert after.monitor_rank == 1
    assert rows[("BTCUSDT", MarketType.SPOT)].id != before.id
    assert rows[("BTCUSDT", MarketType.SPOT)].volume_24h_usd != Decimal("7")


@pytest.mark.integration
async def test_spot_market_filters_are_persisted_where_a_column_does_not_exist(
    db_session_factory: Any, redis_client: Any
) -> None:
    """``MARKET_LOT_SIZE``/``applyMinToMarket``/``avgPriceMins`` have no column
    of their own; they go to ``markets.metadata`` under the explicit
    ``spot_market_filters`` label (EXCHANGE_INTEGRATION.md §2)."""
    code = unique_code()
    adapter = FakeAdapter(code=code)
    adapter.markets.append(
        _spot_market(
            "BIGUSDT",
            exchange=code,
            metadata={"spot_market_filters": {"market_step_size": "0.001", "avg_price_mins": 5}},
        )
    )
    adapter.tickers["BIGUSDT"] = _spot_ticker(
        "BIGUSDT", str(spot_universe.SPOT_VOLUME_FLOOR_USDT * 2), exchange=code
    )

    await spot_universe.refresh_spot_universe(
        db_session_factory, adapter, redis_client, Settings(), producer=PRODUCER
    )

    row = (await _markets(db_session_factory, code))[("BIGUSDT", MarketType.SPOT)]
    assert row.meta["spot_market_filters"]["avg_price_mins"] == 5
    assert row.tick_size == Decimal("0.01")
    assert row.min_notional == Decimal("5")


@pytest.mark.integration
async def test_universe_changed_carries_market_type_and_a_distinct_event_id(
    db_session_factory: Any, redis_client: Any
) -> None:
    """A consumer that predates the field reads the payload unchanged; a spot
    change and a perpetual change of the same set never share an identity."""
    code = unique_code()
    adapter = _spot_adapter(code, {"BIGUSDT": str(spot_universe.SPOT_VOLUME_FLOOR_USDT * 2)})

    await spot_universe.refresh_spot_universe(
        db_session_factory, adapter, redis_client, Settings(), producer=PRODUCER
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = (
            await session.scalars(
                select(OutboxEvent).where(OutboxEvent.stream == Streams.MARKET_UNIVERSE_CHANGED)
            )
        ).all()
    payloads = [
        EventEnvelope.model_validate(row.payload).payload
        for row in rows
        if EventEnvelope.model_validate(row.payload).key.startswith(code)
    ]
    assert len(payloads) == 1
    assert payloads[0]["market_type"] == MarketType.SPOT.value
    assert payloads[0]["added"] == ["BIGUSDT"]

    from hunter_market_worker.durable import universe_event_id

    at = builders.utcnow()
    assert universe_event_id(code, {"BIGUSDT"}, at, MarketType.SPOT) != universe_event_id(
        code, {"BIGUSDT"}, at
    )


@pytest.mark.integration
async def test_hot_state_ticker_from_the_spot_refresh_lands_on_the_spot_key(
    db_session_factory: Any, redis_client: Any
) -> None:
    code = unique_code()
    adapter = _spot_adapter(code, {"BIGUSDT": str(spot_universe.SPOT_VOLUME_FLOOR_USDT * 2)})

    await spot_universe.refresh_spot_universe(
        db_session_factory, adapter, redis_client, Settings(), producer=PRODUCER
    )

    assert await redis_client.hget(f"mkt:{code}:spot:BIGUSDT:ticker", "last") == b"100"
    assert await redis_client.exists(f"mkt:{code}:BIGUSDT:ticker") == 0


# --------------------------------------------------------------------------
# D12 — the exit-only hysteresis band, against Postgres + Redis
# --------------------------------------------------------------------------


async def _is_monitored(session_factory: Any, code: str, symbol: str) -> bool:
    rows = await _markets(session_factory, code)
    return rows[(symbol, MarketType.SPOT)].is_monitored


@pytest.mark.integration
async def test_a_pair_oscillating_around_the_admission_floor_never_leaves(
    db_session_factory: Any, redis_client: Any
) -> None:
    """``PROMUSDT`` (notes-T3.0c.md §8, t30-proof.md §2): 49M/51M straddles
    the 50M admission floor but never touches the 40M exit floor, so it must
    never generate a removal."""
    code, symbol = unique_code(), "PROMUSDT"
    settings = Settings()
    for volume in ("51000000", "49000000", "51000000", "49000000"):
        adapter = _one_pair_adapter(code, symbol, volume)
        await spot_universe.refresh_spot_universe(
            db_session_factory, adapter, redis_client, settings, producer=PRODUCER
        )
        assert await _is_monitored(db_session_factory, code, symbol)


@pytest.mark.integration
async def test_a_pair_between_the_exit_floor_and_the_admission_floor_never_enters(
    db_session_factory: Any, redis_client: Any
) -> None:
    """D12: the band is exit-only. 45M clears the 40M exit floor by a wide
    margin but never clears the 50M admission floor, and admission does not
    relax for a pair that has never been monitored."""
    code, symbol = unique_code(), "MIDUSDT"
    settings = Settings()
    for _ in range(3):
        adapter = _one_pair_adapter(code, symbol, "45000000")
        monitored = await spot_universe.refresh_spot_universe(
            db_session_factory, adapter, redis_client, settings, producer=PRODUCER
        )
        assert monitored == []


@pytest.mark.integration
async def test_three_consecutive_readings_below_the_exit_floor_remove_the_pair(
    db_session_factory: Any, redis_client: Any
) -> None:
    code, symbol = unique_code(), "THINUSDT"
    settings = Settings()
    admit = _one_pair_adapter(code, symbol, str(spot_universe.SPOT_VOLUME_FLOOR_USDT * 2))
    await spot_universe.refresh_spot_universe(
        db_session_factory, admit, redis_client, settings, producer=PRODUCER
    )
    assert await _is_monitored(db_session_factory, code, symbol)

    below = _one_pair_adapter(code, symbol, "30000000")
    for _ in range(2):
        await spot_universe.refresh_spot_universe(
            db_session_factory, below, redis_client, settings, producer=PRODUCER
        )
        assert await _is_monitored(db_session_factory, code, symbol)

    monitored = await spot_universe.refresh_spot_universe(
        db_session_factory, below, redis_client, settings, producer=PRODUCER
    )
    assert symbol not in monitored
    assert not await _is_monitored(db_session_factory, code, symbol)


@pytest.mark.integration
async def test_two_below_readings_then_one_above_resets_the_streak(
    db_session_factory: Any, redis_client: Any
) -> None:
    code, symbol = unique_code(), "RESETUSDT"
    settings = Settings()
    admit = _one_pair_adapter(code, symbol, str(spot_universe.SPOT_VOLUME_FLOOR_USDT * 2))
    await spot_universe.refresh_spot_universe(
        db_session_factory, admit, redis_client, settings, producer=PRODUCER
    )

    below = _one_pair_adapter(code, symbol, "30000000")
    for _ in range(2):
        await spot_universe.refresh_spot_universe(
            db_session_factory, below, redis_client, settings, producer=PRODUCER
        )

    above = _one_pair_adapter(code, symbol, str(spot_universe.SPOT_VOLUME_FLOOR_USDT * 2))
    await spot_universe.refresh_spot_universe(
        db_session_factory, above, redis_client, settings, producer=PRODUCER
    )
    assert await _is_monitored(db_session_factory, code, symbol)

    # Two more "below" readings: if the streak had not truly reset to zero,
    # this second one would be the third *consecutive* one and remove the
    # pair. It must not -- the reset actually happened.
    for _ in range(2):
        await spot_universe.refresh_spot_universe(
            db_session_factory, below, redis_client, settings, producer=PRODUCER
        )
        assert await _is_monitored(db_session_factory, code, symbol)


@pytest.mark.integration
async def test_a_restart_between_the_second_and_third_reading_keeps_the_streak(
    db_session_factory: Any, redis_client: Any
) -> None:
    """The durable counter lives in Redis, never in a Python object shared
    across calls -- every adapter and every call below is independent,
    exactly as if the shard 0 process had been restarted between refreshes."""
    code, symbol = unique_code(), "SURVIVEUSDT"
    settings = Settings()
    await spot_universe.refresh_spot_universe(
        db_session_factory,
        _one_pair_adapter(code, symbol, str(spot_universe.SPOT_VOLUME_FLOOR_USDT * 2)),
        redis_client,
        settings,
        producer=PRODUCER,
    )

    await spot_universe.refresh_spot_universe(
        db_session_factory,
        _one_pair_adapter(code, symbol, "30000000"),
        redis_client,
        settings,
        producer=PRODUCER,
    )
    assert await redis_client.hget(f"mkt:{code}:spot:band_state", symbol) == b"1"

    # "Restart": nothing Python-side survives from the calls above except the
    # Redis client, which in production is a separate, already-running
    # process the market-worker container never restarts alongside itself.
    await spot_universe.refresh_spot_universe(
        db_session_factory,
        _one_pair_adapter(code, symbol, "30000000"),
        redis_client,
        settings,
        producer=PRODUCER,
    )
    assert await redis_client.hget(f"mkt:{code}:spot:band_state", symbol) == b"2"
    assert await _is_monitored(db_session_factory, code, symbol)

    monitored = await spot_universe.refresh_spot_universe(
        db_session_factory,
        _one_pair_adapter(code, symbol, "30000000"),
        redis_client,
        settings,
        producer=PRODUCER,
    )
    assert symbol not in monitored
    assert await redis_client.hget(f"mkt:{code}:spot:band_state", symbol) is None


@pytest.mark.integration
async def test_losing_trading_status_removes_immediately_with_no_band(
    db_session_factory: Any, redis_client: Any
) -> None:
    """D12: the three hard-exit conditions skip the band entirely -- one
    reading is enough, never three."""
    code, symbol = unique_code(), "HALTUSDT"
    settings = Settings()
    await spot_universe.refresh_spot_universe(
        db_session_factory,
        _one_pair_adapter(code, symbol, str(spot_universe.SPOT_VOLUME_FLOOR_USDT * 2)),
        redis_client,
        settings,
        producer=PRODUCER,
    )
    assert await _is_monitored(db_session_factory, code, symbol)

    suspended = _one_pair_adapter(
        code,
        symbol,
        str(spot_universe.SPOT_VOLUME_FLOOR_USDT * 2),
        status=MarketStatus.SUSPENDED,
    )
    monitored = await spot_universe.refresh_spot_universe(
        db_session_factory, suspended, redis_client, settings, producer=PRODUCER
    )
    assert symbol not in monitored
    assert not await _is_monitored(db_session_factory, code, symbol)


@pytest.mark.integration
async def test_the_universe_event_carries_the_removal_reason(
    db_session_factory: Any, redis_client: Any
) -> None:
    """D12: ``market.universe.changed`` names *why* a pair left."""
    code, symbol = unique_code(), "REASONUSDT"
    settings = Settings()
    await spot_universe.refresh_spot_universe(
        db_session_factory,
        _one_pair_adapter(code, symbol, str(spot_universe.SPOT_VOLUME_FLOOR_USDT * 2)),
        redis_client,
        settings,
        producer=PRODUCER,
    )

    below = _one_pair_adapter(code, symbol, "30000000")
    for _ in range(3):
        await spot_universe.refresh_spot_universe(
            db_session_factory, below, redis_client, settings, producer=PRODUCER
        )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = (
            await session.scalars(
                select(OutboxEvent).where(OutboxEvent.stream == Streams.MARKET_UNIVERSE_CHANGED)
            )
        ).all()
    payloads = [
        EventEnvelope.model_validate(row.payload).payload
        for row in rows
        if EventEnvelope.model_validate(row.payload).key.startswith(code)
    ]
    removal_payloads = [p for p in payloads if symbol in p.get("removed", [])]
    assert len(removal_payloads) == 1
    assert removal_payloads[0]["removed_reasons"] == {symbol: "below_band_3x"}
