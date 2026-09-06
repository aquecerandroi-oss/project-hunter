"""The market data one shadow evaluation reads: markets, candles, funding.

Which *versions* to run is :mod:`.catalogue`; this module is what to run them
on. Everything goes through ``role_session(..., db_role="hunter_worker")`` at
the call sites. Nothing here is tenant data — shadow research is global
(DATABASE.md §1.1), so there is no ``organization_id`` and no
``app.current_org`` to set; the worker role is used because it is the only role
allowed to write the tables these reads feed.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import or_, select

from hunter_core.db.models.analysis import MarketRegimeRow
from hunter_core.db.models.market_data import Candle, FundingRate, OpenInterestHistory
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.domain.enums import MarketStatus, RegimeScope, Timeframe
from hunter_core.domain.market import NormalizedCandle
from hunter_strategy_worker.funding import Settlement

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "FundingRow",
    "MarketRow",
    "OpenInterestRow",
    "load_candles",
    "load_funding",
    "load_latest_funding_row",
    "load_latest_open_interest_row",
    "load_market",
    "load_regime_asof",
    "newest_received_at",
]

_MINUTE = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class MarketRow:
    """Identity and current universe standing of one market."""

    id: uuid.UUID
    symbol: str
    exchange: str
    is_monitored: bool
    status: MarketStatus


async def load_market(session: AsyncSession, exchange: str, symbol: str) -> MarketRow | None:
    """The market row for ``exchange:symbol``, or ``None`` if it is unknown."""
    row = (
        await session.execute(
            select(Market.id, Market.symbol, Market.is_monitored, Market.status, Exchange.code)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .where(Exchange.code == exchange, Market.symbol == symbol)
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    return MarketRow(
        id=row.id,
        symbol=row.symbol,
        exchange=row.code,
        is_monitored=bool(row.is_monitored),
        status=row.status,
    )


async def load_candles(
    session: AsyncSession,
    *,
    market: MarketRow,
    start: datetime,
    end: datetime,
) -> list[NormalizedCandle]:
    """Final 1m candles with ``start <= open_time < end``, oldest first.

    ``end`` is exclusive and is the caller's cut: a candle that closes after the
    reference bar can never reach a decision (``build_context`` refuses it).
    """
    rows = (
        await session.execute(
            select(
                Candle.open_time,
                Candle.open,
                Candle.high,
                Candle.low,
                Candle.close,
                Candle.volume,
                Candle.quote_volume,
                Candle.trade_count,
                Candle.taker_buy_volume,
                Candle.received_at,
            )
            .where(
                Candle.market_id == market.id,
                Candle.timeframe == Timeframe.M1,
                Candle.open_time >= start,
                Candle.open_time < end,
                Candle.is_final.is_(True),
            )
            .order_by(Candle.open_time)
        )
    ).all()
    return [
        NormalizedCandle(
            exchange=market.exchange,
            symbol=market.symbol,
            timeframe=Timeframe.M1,
            open_time=row.open_time,
            close_time=row.open_time + _MINUTE,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            quote_volume=row.quote_volume,
            trade_count=row.trade_count,
            taker_buy_volume=row.taker_buy_volume,
            is_final=True,
            received_at=row.received_at,
        )
        for row in rows
    ]


async def load_funding(
    session: AsyncSession, *, market_id: uuid.UUID, since: datetime, until: datetime
) -> list[Settlement]:
    """Realized funding settlements in ``[since, until]``, oldest first.

    The window must be wide enough for the caller to read the market's own
    cadence (:func:`hunter_strategy_worker.funding.resolve_funding`), so callers
    ask for a few settlements before the entry, not just the crossed ones.
    """
    rows = (
        await session.execute(
            select(FundingRate.funding_time, FundingRate.rate, FundingRate.mark_price)
            .where(
                FundingRate.market_id == market_id,
                FundingRate.funding_time >= since,
                FundingRate.funding_time <= until,
            )
            .order_by(FundingRate.funding_time)
        )
    ).all()
    return [
        Settlement(
            funding_time=row.funding_time,
            rate=Decimal(row.rate),
            mark_price=None if row.mark_price is None else Decimal(row.mark_price),
        )
        for row in rows
    ]


@dataclass(frozen=True, slots=True)
class FundingRow:
    """One durable ``funding_rates`` settlement, as read for a context cut."""

    ts: datetime
    rate: Decimal
    mark_price: Decimal | None


async def load_latest_funding_row(
    session: AsyncSession, *, market_id: uuid.UUID, until: datetime
) -> FundingRow | None:
    """The most recent settlement with ``funding_time <= until``, or ``None``.

    ``funding_time`` is the settlement instant, not a publication time, so this
    can never return a row from after ``until`` (the primary key is
    ``(market_id, funding_time)``; ordering by it descending is the same index
    the primary key already gives).
    """
    row = (
        await session.execute(
            select(FundingRate.funding_time, FundingRate.rate, FundingRate.mark_price)
            .where(FundingRate.market_id == market_id, FundingRate.funding_time <= until)
            .order_by(FundingRate.funding_time.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    return FundingRow(
        ts=row.funding_time,
        rate=Decimal(row.rate),
        mark_price=None if row.mark_price is None else Decimal(row.mark_price),
    )


@dataclass(frozen=True, slots=True)
class OpenInterestRow:
    """One durable ``open_interest_history`` sample, as read for a context cut."""

    ts: datetime
    open_interest: Decimal | None
    open_interest_value: Decimal | None


async def load_latest_open_interest_row(
    session: AsyncSession, *, market_id: uuid.UUID, until: datetime
) -> OpenInterestRow | None:
    """The most recent sample with ``ts <= until``, or ``None``."""
    row = (
        await session.execute(
            select(
                OpenInterestHistory.ts,
                OpenInterestHistory.open_interest,
                OpenInterestHistory.open_interest_value,
            )
            .where(OpenInterestHistory.market_id == market_id, OpenInterestHistory.ts <= until)
            .order_by(OpenInterestHistory.ts.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    return OpenInterestRow(
        ts=row.ts,
        open_interest=None if row.open_interest is None else Decimal(row.open_interest),
        open_interest_value=(
            None if row.open_interest_value is None else Decimal(row.open_interest_value)
        ),
    )


async def load_regime_asof(
    session: AsyncSession, *, cut: datetime
) -> tuple[uuid.UUID | None, str | None]:
    """The global regime in force at ``cut``, or ``None`` with why.

    Only ``RegimeScope.GLOBAL`` exists in v0 (the scanner classifies one regime
    for the whole universe, ``hunter_scanner_worker/scanner.py``); there is no
    per-market regime to look up. The classifier's own ``UNKNOWN`` state during
    its 20-30 day warm-up is still a *row* (``market_regimes.regime =
    'unknown'``) and is returned like any other — it is a classification, not a
    missing value (``hunter_core.domain.enums.MarketRegime`` docstring). Only
    the *absence* of any eligible row returns ``None``, with
    ``"no_regime_asof"``: before the classifier's very first row this is
    exactly the expected warm-up state, but this function does not itself know
    which case it is in and does not guess (Astra, S2-context review,
    must-fix 3) — it reports an empty result honestly either way.

    ``end_time IS NULL OR cut < end_time`` guards the half-open
    ``[start_time, end_time)`` the model documents: regimes are expected to be
    contiguous (one row's insert closes the previous one,
    ``hunter_scanner_worker/writers.py::write_regime``), so picking the newest
    row with ``start_time <= cut`` should already land on the one in force —
    but this makes that not merely assumed (Astra, S2-context review,
    nice-to-have).
    """
    row = (
        await session.execute(
            select(MarketRegimeRow.id)
            .where(
                MarketRegimeRow.scope == RegimeScope.GLOBAL,
                MarketRegimeRow.start_time <= cut,
                or_(MarketRegimeRow.end_time.is_(None), MarketRegimeRow.end_time > cut),
            )
            .order_by(MarketRegimeRow.start_time.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None, "no_regime_asof"
    return row.id, None


def newest_received_at(candles: Sequence[NormalizedCandle]) -> datetime | None:
    """The most recent ``received_at`` among ``candles`` — decision provenance.

    The cut at ``source_bar_close`` controls *market* time, not availability: a
    late backfilled candle passes the cut. Recording what had actually been
    received when the decision was taken is what makes it reproducible
    (notes-S1.md §12).
    """
    stamps = [c.received_at for c in candles]
    return max(stamps) if stamps else None
