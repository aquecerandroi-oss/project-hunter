"""Shadow-side setup for the T3.14 bridge suites: a perpetual, a version, a signal.

``builders.py`` already gives a tenant with the **spot** market the wallet
executes on. What the bridge needs on top of it is the other half of D1: the
**perpetual** the Lab decided on, the frozen strategy version behind it, the
agent that runs that version inside the wallet, and one ``agent_signals`` row
written exactly as ``hunter_strategy_worker.persist`` writes it — envelope in
``supporting_features``, entry plan in ``signal_outcomes.meta``.

Everything here is labelled test setup. Nothing fabricates a decision: the rows
are the ones the real writer produces, and the bridge reads them the same way in
production.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import uuid7
from hunter_core.strategies.envelope import PURPOSE_PAPER, PURPOSE_RESEARCH_ONLY

from .builders import COSTS, MIN_NOTIONAL, TICK, filters_metadata

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from .builders import Tenant

__all__ = ["PURPOSE_PAPER", "PURPOSE_RESEARCH_ONLY"]

# ``PURPOSE_PAPER`` is the only purpose that may reach the wallet
# (``admission.sources`` admits ``paper`` and refuses ``live`` by name — D10).


def _costs_json() -> dict[str, Any]:
    return {
        "spread_bps": str(COSTS.spread_bps),
        "slippage_bps": str(COSTS.slippage_bps),
        "fee_bps": str(COSTS.fee_bps),
        "max_entry_delay_s": COSTS.max_entry_delay_s,
    }


async def ensure_candle_partitions(engine: AsyncEngine, around: datetime) -> None:
    """The monthly ``candles_1m`` leaves the volume window falls into.

    DDL, so it runs as the owner — in production this is
    ``infra/scripts/create_partitions.py``'s job, never a worker's.
    """
    months = {(around.year, around.month)}
    earlier = around - timedelta(days=40)
    months.add((earlier.year, earlier.month))
    async with engine.begin() as connection:
        for year, month in sorted(months):
            start = datetime(year, month, 1, tzinfo=UTC)
            end = datetime(year + (month // 12), (month % 12) + 1, 1, tzinfo=UTC)
            name = f"candles_1m_{year}_{month:02d}"
            await connection.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF candles_1m "
                    f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
                )
            )


async def add_perp_market(engine: AsyncEngine, tenant: Tenant) -> uuid.UUID:
    """The perpetual of the same ``base/quote`` — where the Lab decides (D1)."""
    return await add_perp_market_for(engine, tenant, tenant.market_id)


async def add_perp_market_for(
    engine: AsyncEngine, tenant: Tenant, spot_market_id: uuid.UUID
) -> uuid.UUID:
    """The perpetual twin of an existing spot market, by its own ``base/quote``."""
    async with engine.begin() as connection:
        row = (
            await connection.execute(
                text("SELECT symbol, base_asset_id, quote_asset_id FROM markets WHERE id = :id"),
                {"id": spot_market_id},
            )
        ).one()
        market_id = uuid7()
        await connection.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type, base_asset_id, "
                "quote_asset_id, tick_size, step_size, min_notional, is_monitored, metadata) "
                "VALUES (:id, :ex, :symbol, 'perpetual', :base, :quote, :tick, :step, "
                ":min_notional, true, CAST(:meta AS jsonb))"
            ),
            {
                "id": market_id,
                "ex": tenant.exchange_id,
                "symbol": row.symbol,
                "base": row.base_asset_id,
                "quote": row.quote_asset_id,
                "tick": TICK,
                "step": tenant.step,
                "min_notional": MIN_NOTIONAL,
                "meta": filters_metadata(),
            },
        )
    return market_id


async def add_scaled_perp_market(
    engine: AsyncEngine, tenant: Tenant, *, scale: int = 1000
) -> uuid.UUID:
    """A perpetual quoted at ``scale``x the spot price, Binance's own naming:
    ``1000SHIBUSDT`` is a distinct ``assets`` row (``1000SHIB``) from spot's own
    ``SHIB`` — never the same asset id at a different price (T3.14b review item
    4, ``bridge_universe._scaled_spot_pair``).
    """
    base_id = uuid7()
    base_symbol = f"{scale}{tenant.base_symbol}"
    symbol = f"{scale}{tenant.symbol}"
    market_id = uuid7()
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO assets (id, symbol) VALUES (:id, :symbol)"),
            {"id": base_id, "symbol": base_symbol},
        )
        await connection.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type, base_asset_id, "
                "quote_asset_id, tick_size, step_size, min_notional, is_monitored, metadata) "
                "VALUES (:id, :ex, :symbol, 'perpetual', :base, :quote, :tick, :step, "
                ":min_notional, true, CAST(:meta AS jsonb))"
            ),
            {
                "id": market_id,
                "ex": tenant.exchange_id,
                "symbol": symbol,
                "base": base_id,
                "quote": tenant.quote_asset_id,
                "tick": TICK,
                "step": tenant.step,
                "min_notional": MIN_NOTIONAL,
                "meta": filters_metadata(),
            },
        )
    return market_id


async def set_spot_volume(
    engine: AsyncEngine,
    market_id: uuid.UUID,
    *,
    volume: Decimal | None,
    monitored: bool = True,
) -> None:
    """What T3.0c's spot universe refresh writes on the row: the 24h figure."""
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE markets SET volume_24h_usd = :v, is_monitored = :m WHERE id = :id"),
            {"v": volume, "m": monitored, "id": market_id},
        )


async def seed_minute_volumes(
    engine: AsyncEngine,
    market_id: uuid.UUID,
    *,
    now: datetime,
    quote_volume: Decimal = Decimal(4_000_000),
    minutes: int = 31,
    skip: int = 0,
) -> None:
    """``candles`` 1m rows for the participation window, newest first.

    ``skip`` drops that many of the newest complete minutes, which is how a test
    reaches ``volume_window_complete = False`` without inventing a flag.
    """
    last_open = now.replace(second=0, microsecond=0) - timedelta(minutes=1)
    async with engine.begin() as connection:
        for index in range(skip, minutes):
            await connection.execute(
                text(
                    "INSERT INTO candles (market_id, timeframe, open_time, open, high, low, "
                    "close, volume, quote_volume, is_final, source) VALUES (:market, '1m', "
                    ":open_time, :price, :price, :price, :price, :volume, :quote_volume, true, "
                    "'test') ON CONFLICT DO NOTHING"
                ),
                {
                    "market": market_id,
                    "open_time": last_open - timedelta(minutes=index),
                    "price": Decimal(100),
                    "volume": quote_volume / Decimal(100),
                    "quote_volume": quote_volume,
                },
            )


async def open_ingestion_gap(engine: AsyncEngine, market_id: uuid.UUID, *, at: datetime) -> None:
    """One unrecovered hole in the 1m series — R-OPS-3's ``open_gap``."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO ingestion_gaps (id, market_id, timeframe, gap_start, gap_end, "
                "status) VALUES (:id, :market, '1m', :start, :end, 'open')"
            ),
            {
                "id": uuid7(),
                "market": market_id,
                "start": at - timedelta(minutes=5),
                "end": at - timedelta(minutes=4),
            },
        )


async def create_version(
    engine: AsyncEngine, *, active: bool = True, at: datetime | None = None
) -> uuid.UUID:
    """A strategy and one of its versions, active or still ``draft``."""
    strategy_id, version_id = uuid7(), uuid7()
    key = f"bridge_probe_{uuid.uuid4().hex[:8]}"
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO strategies (id, key, name) VALUES (:id, :key, :key)"),
            {"id": strategy_id, "key": key},
        )
        await connection.execute(
            text(
                "INSERT INTO strategy_versions (id, strategy_id, version, status, activated_at) "
                "VALUES (:id, :strategy, 'v1', CAST(:status AS strategy_version_status), "
                ":activated)"
            ),
            {
                "id": version_id,
                "strategy": strategy_id,
                "status": "active" if active else "draft",
                "activated": at if active else None,
            },
        )
    return version_id


async def create_agent(
    engine: AsyncEngine,
    *,
    organization_id: uuid.UUID,
    workspace_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    version_id: uuid.UUID,
    status: str = "enabled",
) -> uuid.UUID:
    """The version running **inside this wallet** — what ``agent_id`` names."""
    agent_id = uuid7()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO agents (id, organization_id, workspace_id, portfolio_id, name, "
                "strategy_version_id, status) VALUES (:id, :org, :ws, :pf, 'bridge probe', "
                ":version, CAST(:status AS agent_status))"
            ),
            {
                "id": agent_id,
                "org": organization_id,
                "ws": workspace_id,
                "pf": portfolio_id,
                "version": version_id,
                "status": status,
            },
        )
    return agent_id


def envelope(*, source_bar_close: datetime, purpose: str) -> str:
    """``agent_signals.supporting_features`` in the shape S1/S2 persist it."""
    return json.dumps(
        {
            "observation_ts": source_bar_close.isoformat().replace("+00:00", "Z"),
            "timeframe": "15m",
            "strategy_key": "bridge_probe",
            "strategy_version": "v1",
            "features": [],
            "atr": None,
            "assumed_costs": _costs_json(),
            "confidence_method": "constant_uncalibrated_v1",
            "eligible": True,
            "eligibility_reason": None,
            "purpose": purpose,
            "params_format": 1,
        }
    )


async def emit_signal(
    engine: AsyncEngine,
    *,
    version_id: uuid.UUID,
    market_id: uuid.UUID,
    source_bar_close: datetime,
    emitted_at: datetime | None = None,
    entry_ref: Decimal = Decimal(100),
    stop: Decimal = Decimal("97.5"),
    target: Decimal = Decimal("105"),
    purpose: str = PURPOSE_RESEARCH_ONLY,
) -> uuid.UUID:
    """One shadow decision, both rows, exactly as ``persist_decision`` writes them."""
    signal_id = uuid7()
    decision_at = emitted_at or (source_bar_close + timedelta(seconds=2))
    meta = json.dumps(
        {
            "reference_price": str(entry_ref),
            "purpose": purpose,
            "assumed_costs": _costs_json(),
        }
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO agent_signals (id, strategy_version_id, market_id, params_hash, "
                "direction, confidence, entry_zone, stop, targets, supporting_features, "
                "emitted_at, status) VALUES (:id, :version, :market, 'probe', 'long', 0.5, "
                "CAST('{}' AS jsonb), :stop, CAST(:targets AS jsonb), CAST(:envelope AS jsonb), "
                ":emitted, 'active')"
            ),
            {
                "id": signal_id,
                "version": version_id,
                "market": market_id,
                "stop": stop,
                "targets": json.dumps([str(target)]),
                "envelope": envelope(source_bar_close=source_bar_close, purpose=purpose),
                "emitted": decision_at,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO signal_outcomes (signal_id, virtual_stop, result, tracking_state, "
                "meta) VALUES (:id, :stop, 'open', 'pending_entry', CAST(:meta AS jsonb))"
            ),
            {"id": signal_id, "stop": stop, "meta": meta},
        )
    return signal_id


async def set_beta(
    engine: AsyncEngine,
    market_id: uuid.UUID,
    *,
    as_of: datetime,
    value: Decimal = Decimal("1.0"),
    valid_for: timedelta = timedelta(hours=6),
) -> None:
    """One current, valid ``market_betas`` revision for the spot market."""
    window_end = as_of - timedelta(minutes=1)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO market_betas (id, market_id, reference_market_id, as_of, "
                "window_start, window_end, input_start, valid_until, available_at, "
                "beta_version, estimator, beta, n, contiguous_bars, valid, input_digest) "
                "VALUES (:id, :market, :market, :as_of, :window_start, :window_end, "
                ":input_start, :valid_until, :available, 'beta_v1_test', 'definition', "
                ":beta, 720, 720, true, :digest) ON CONFLICT DO NOTHING"
            ),
            {
                "id": uuid7(),
                "market": market_id,
                "as_of": as_of,
                "window_start": window_end - timedelta(days=30),
                "window_end": window_end,
                "input_start": window_end - timedelta(days=31),
                "valid_until": window_end + valid_for,
                "available": as_of - timedelta(minutes=1),
                "beta": value,
                "digest": uuid.uuid4().hex,
            },
        )


async def set_opportunity(
    engine: AsyncEngine,
    market_id: uuid.UUID,
    *,
    score: Decimal,
    last_updated_at: datetime,
) -> None:
    """The Radar row of the **perpetual** — D3's first ordering key."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO opportunities (id, market_id, direction, score, confidence, "
                "first_seen_at, last_updated_at) VALUES (:id, :market, 'long', :score, 0.7, "
                ":seen, :updated)"
            ),
            {
                "id": uuid7(),
                "market": market_id,
                "score": score,
                "seen": last_updated_at - timedelta(minutes=5),
                "updated": last_updated_at,
            },
        )
