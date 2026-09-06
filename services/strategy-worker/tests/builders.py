"""Fixtures for the shadow integration tests: a market, an activated version,
and a 1-minute candle series that makes ``volume_anomaly_v1`` fire.

Everything here is labelled test data and lives only in tests (CLAUDE.md: no
fake data outside them). The series is built the way the strategy reads it —
288 quiet 5m bars and one bar with four times the volume closing above its own
midpoint — so the decision under test is a real decision of the real frozen
strategy, not a hand-written ``Decision`` that could drift from it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hunter_core.db.models.agents import Strategy as StrategyRow
from hunter_core.db.models.agents import StrategyVersion
from hunter_core.db.models.market_data import Candle
from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.domain.enums import (
    MarketStatus,
    MarketType,
    StrategyVersionStatus,
    Timeframe,
)
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.registry import StrategyRegistry
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_strategy_worker.code_ref import version_code_ref

MINUTE = timedelta(minutes=1)
EXCHANGE = "binance"
SYMBOL = "BTCUSDT"
SERIES_MINUTES = 1600
"""Enough 1m history for the 289 5m bars *and* the 97 15m ATR bars."""

_RUNNING_CODE_REF = version_code_ref("volume_anomaly_v1")
"""The per-version digest of the code this process is running (every fixture
here carries the real ``volume_anomaly_v1`` contract): the worker refuses an
activated version whose frozen ``code_ref`` is anything else."""


@dataclass(frozen=True, slots=True)
class Fixture:
    """Ids of everything one integration test needs."""

    exchange_id: uuid.UUID
    market_id: uuid.UUID
    strategy_id: uuid.UUID
    version_id: uuid.UUID
    params: dict[str, Any]
    cut: datetime


def canonical_params() -> dict[str, Any]:
    """``default_parameters`` in the exact JSONB shape the activation writes."""
    import json

    parsed: dict[str, Any] = json.loads(canonical_json(dict(VOLUME_ANOMALY_V1.default_parameters)))
    return parsed


async def ensure_partitions(session: AsyncSession, around: datetime) -> None:
    """The monthly ``candles_1m`` partitions the series falls into.

    Must run as the *owner*, not as ``hunter_worker``: creating a partition is
    DDL, and the worker role deliberately has no ``CREATE`` on ``public``. In
    production this is ``infra/scripts/create_partitions.py``'s job.
    """
    months = {(around.year, around.month)}
    earlier = around - timedelta(days=40)
    months.add((earlier.year, earlier.month))
    later = around + timedelta(days=40)
    months.add((later.year, later.month))
    for year, month in sorted(months):
        start = datetime(year, month, 1, tzinfo=UTC)
        end = datetime(year + (month // 12), (month % 12) + 1, 1, tzinfo=UTC)
        name = f"candles_1m_{year}_{month:02d}"
        await session.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF candles_1m "
                f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
            )
        )


async def seed_market(
    session: AsyncSession, *, monitored: bool = True
) -> tuple[uuid.UUID, uuid.UUID]:
    """An exchange and one active, monitored perpetual."""
    exchange_id = uuid7()
    await session.execute(
        text(
            "INSERT INTO exchanges (id, code, name, status) "
            "VALUES (:id, :code, :name, 'active') ON CONFLICT (code) DO NOTHING"
        ),
        {"id": exchange_id, "code": EXCHANGE, "name": "Binance"},
    )
    exchange_id = await session.scalar(
        text("SELECT id FROM exchanges WHERE code = :code"), {"code": EXCHANGE}
    )
    base, quote = uuid7(), uuid7()
    for asset_id, symbol in ((base, "BTC"), (quote, "USDT")):
        await session.execute(
            text(
                "INSERT INTO assets (id, symbol) VALUES (:id, :symbol) "
                "ON CONFLICT (symbol) DO NOTHING"
            ),
            {"id": asset_id, "symbol": symbol},
        )
    market_id = uuid7()
    await session.execute(
        text(
            "INSERT INTO markets (id, exchange_id, symbol, market_type, status, "
            "is_monitored, monitor_rank, volume_24h_usd, last_seen_at) "
            "VALUES (:id, :exchange_id, :symbol, 'perpetual', 'active', :monitored, 1, "
            "1000000, now()) "
            "ON CONFLICT (exchange_id, symbol, market_type) DO NOTHING"
        ),
        {
            "id": market_id,
            "exchange_id": exchange_id,
            "symbol": SYMBOL,
            "monitored": monitored,
        },
    )
    market_id = await session.scalar(
        text(
            "SELECT id FROM markets WHERE exchange_id = :exchange_id AND symbol = :symbol "
            "AND market_type = 'perpetual'"
        ),
        {"exchange_id": exchange_id, "symbol": SYMBOL},
    )
    return exchange_id, market_id


async def activate_version(
    session: AsyncSession,
    *,
    key: str = "volume_anomaly",
    version: str = "v1",
    code_ref: str | None = _RUNNING_CODE_REF,
    active: bool = True,
) -> tuple[uuid.UUID, uuid.UUID]:
    """A ``strategy`` and an already-activated ``strategy_version``.

    Inserted activated rather than updated into activation: the freeze trigger
    fires on ``UPDATE``/``DELETE`` of an already-activated row, which is exactly
    what the ops script has to respect and what this fixture must not fight.
    """
    strategy_id, version_id = uuid7(), uuid7()
    await session.execute(
        text(
            "INSERT INTO strategies (id, key, name) VALUES (:id, :key, :name) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {"id": strategy_id, "key": key, "name": key},
    )
    strategy_id = await session.scalar(
        text("SELECT id FROM strategies WHERE key = :key"), {"key": key}
    )
    existing = await session.scalar(
        text(
            "SELECT id FROM strategy_versions WHERE strategy_id = :strategy_id "
            "AND version = :version"
        ),
        {"strategy_id": strategy_id, "version": version},
    )
    if existing is not None:
        # Reused on purpose: the freeze trigger refuses to delete an activated
        # version (that is the point of it), so tests share one frozen row.
        return strategy_id, existing
    import json

    await session.execute(
        text(
            "INSERT INTO strategy_versions (id, strategy_id, version, status, "
            "parameters_schema, default_parameters, code_ref, params_format, activated_at) "
            "VALUES (:id, :strategy_id, :version, :status, CAST(:schema AS jsonb), "
            "CAST(:params AS jsonb), :code_ref, 1, :activated_at)"
        ),
        {
            "id": version_id,
            "strategy_id": strategy_id,
            "version": version,
            "status": (
                StrategyVersionStatus.ACTIVE.value if active else StrategyVersionStatus.DRAFT.value
            ),
            "schema": json.dumps(dict(VOLUME_ANOMALY_V1.parameters_schema)),
            "params": canonical_json(dict(VOLUME_ANOMALY_V1.default_parameters)).decode(),
            "code_ref": code_ref,
            "activated_at": utcnow() if active else None,
        },
    )
    return strategy_id, version_id


class NamedStrategy:
    """A registry entry under a test-only key, carrying the real v1 contract.

    Labelled test data (CLAUDE.md): the registry is keyed by
    ``strategies.key + "_" + version``, and every real key is a frozen row that
    the migration's trigger will not let a later test delete. Giving each
    scenario its own key is what keeps them independent; the *schema*, the
    *parameters* and the *module* are the genuine frozen ones, so what is being
    validated is real — in particular ``__module__``, because that is the name
    the per-version ``code_ref`` carries and the name a superseded row is bound
    back to code by.
    """

    __module__ = "hunter_core.strategies.volume_anomaly_v1"

    def __init__(self, key: str) -> None:
        self.key = key
        self.version = "v1"
        self.timeframe = VOLUME_ANOMALY_V1.timeframe
        self.parameters_schema = VOLUME_ANOMALY_V1.parameters_schema
        self.default_parameters = VOLUME_ANOMALY_V1.default_parameters

    def evaluate(self, ctx: Any, params: Any) -> Any:
        return VOLUME_ANOMALY_V1.evaluate(ctx, params)

    def explain(self, ctx: Any, params: Any) -> Any:
        return VOLUME_ANOMALY_V1.explain(ctx, params)


def registry_for(db_key: str) -> StrategyRegistry:
    """A one-entry registry binding ``<db_key>_v1`` to the real v1 contract."""
    return StrategyRegistry([NamedStrategy(f"{db_key}_v1")])


def series(cut: datetime, *, trigger: bool = True) -> list[dict[str, Any]]:
    """``SERIES_MINUTES`` quiet 1m candles ending at ``cut``, optionally with a
    volume anomaly in the last five minutes."""
    rows: list[dict[str, Any]] = []
    for index in range(SERIES_MINUTES):
        open_time = cut - MINUTE * (SERIES_MINUTES - index)
        spike = trigger and index >= SERIES_MINUTES - 5
        rows.append(
            {
                "open_time": open_time,
                "open": Decimal("100"),
                "high": Decimal("100.4") if spike else Decimal("100.2"),
                "low": Decimal("100.0") if spike else Decimal("99.8"),
                "close": Decimal("100.3") if spike else Decimal("100"),
                "volume": Decimal("60") if spike else Decimal("10"),
            }
        )
    return rows


async def insert_candles(
    session: AsyncSession,
    market_id: uuid.UUID,
    rows: list[dict[str, Any]],
    *,
    skip: set[datetime] | None = None,
) -> None:
    """Persist 1m candles, optionally leaving holes (``skip``) for gap tests."""
    skip = skip or set()
    for row in rows:
        if row["open_time"] in skip:
            continue
        session.add(
            Candle(
                market_id=market_id,
                timeframe=Timeframe.M1,
                open_time=row["open_time"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                is_final=True,
                source="test",
            )
        )
    await session.flush()


__all__ = [
    "EXCHANGE",
    "MINUTE",
    "SERIES_MINUTES",
    "SYMBOL",
    "Asset",
    "Exchange",
    "Fixture",
    "Market",
    "MarketStatus",
    "MarketType",
    "StrategyRow",
    "StrategyVersion",
    "activate_version",
    "canonical_params",
    "ensure_partitions",
    "NamedStrategy",
    "insert_candles",
    "insert_funding_rate",
    "insert_open_interest",
    "insert_regime",
    "isolate_catalogue",
    "only_version",
    "register_gap",
    "registry_for",
    "seed_market",
    "series",
]


def only_version(versions: list[Any], key: str = "volume_anomaly") -> Any:
    """The one active version under ``key``.

    Tests share one database and one catalogue, so ``versions[0]`` silently
    depends on which other test activated something first. Naming the version
    keeps each scenario independent of the file order.
    """
    matching = [v for v in versions if v.strategy_key == key]
    assert len(matching) == 1, (
        f"expected one {key} version, got {[v.strategy_key for v in versions]}"
    )
    return matching[0]


async def register_gap(
    session: AsyncSession,
    market_id: uuid.UUID,
    *,
    start: datetime,
    end: datetime,
    status: str = "open",
    detected_at: datetime | None = None,
) -> None:
    """An ``ingestion_gaps`` row like the market-worker's detector writes."""
    await session.execute(
        text(
            "INSERT INTO ingestion_gaps (id, market_id, timeframe, gap_start, gap_end, "
            "status, attempts, detected_at) VALUES (:id, :market_id, '1m', :start, :end, "
            ":status, 0, :detected_at)"
        ),
        {
            "id": uuid7(),
            "market_id": market_id,
            "start": start,
            "end": end,
            "status": status,
            "detected_at": detected_at or utcnow(),
        },
    )


async def insert_funding_rate(
    session: AsyncSession,
    market_id: uuid.UUID,
    *,
    funding_time: datetime,
    rate: Decimal,
    mark_price: Decimal | None,
) -> None:
    """One durable ``funding_rates`` settlement row."""
    await session.execute(
        text(
            "INSERT INTO funding_rates (market_id, funding_time, rate, mark_price) "
            "VALUES (:market_id, :funding_time, :rate, :mark_price)"
        ),
        {
            "market_id": market_id,
            "funding_time": funding_time,
            "rate": rate,
            "mark_price": mark_price,
        },
    )
    await session.flush()


async def insert_open_interest(
    session: AsyncSession,
    market_id: uuid.UUID,
    *,
    ts: datetime,
    open_interest: Decimal | None,
    open_interest_value: Decimal | None = None,
) -> None:
    """One durable ``open_interest_history`` sample row."""
    await session.execute(
        text(
            "INSERT INTO open_interest_history (market_id, ts, open_interest, open_interest_value) "
            "VALUES (:market_id, :ts, :open_interest, :open_interest_value)"
        ),
        {
            "market_id": market_id,
            "ts": ts,
            "open_interest": open_interest,
            "open_interest_value": open_interest_value,
        },
    )
    await session.flush()


async def insert_regime(
    session: AsyncSession,
    *,
    start_time: datetime,
    end_time: datetime | None = None,
    regime: str = "SIDEWAYS",
    scope: str = "global",
) -> uuid.UUID:
    """One ``market_regimes`` row, like ``hunter_scanner_worker.writers.write_regime``."""
    regime_id = uuid7()
    await session.execute(
        text(
            "INSERT INTO market_regimes (id, scope, regime, start_time, end_time) "
            "VALUES (:id, :scope, :regime, :start_time, :end_time)"
        ),
        {
            "id": regime_id,
            "scope": scope,
            "regime": regime,
            "start_time": start_time,
            "end_time": end_time,
        },
    )
    await session.flush()
    return regime_id


async def isolate_catalogue(session: AsyncSession, *, keep: str = "volume_anomaly") -> None:
    """Leave exactly one strategy key ``active`` in the shared catalogue.

    The tests share one database and the freeze trigger refuses to delete an
    activated version — on purpose — so every scenario that activates something
    leaves it behind for the next one. Scenarios that assert *how many* versions
    ran have to state which catalogue they expect instead of inheriting it.
    ``status`` is the one lifecycle field the trigger leaves mutable
    (DATABASE.md §16.1), which is exactly what makes this possible.
    """
    await session.execute(
        text(
            "UPDATE strategy_versions v SET status = 'deprecated' FROM strategies s "
            "WHERE s.id = v.strategy_id AND v.status = 'active' AND s.key <> :keep"
        ),
        {"keep": keep},
    )
    await session.execute(
        text(
            "UPDATE strategy_versions v SET status = 'active' FROM strategies s "
            "WHERE s.id = v.strategy_id AND s.key = :keep AND v.activated_at IS NOT NULL"
        ),
        {"keep": keep},
    )
