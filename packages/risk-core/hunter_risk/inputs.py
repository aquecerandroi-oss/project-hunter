"""Everything the engine is allowed to look at, as arguments.

``RiskEngine.evaluate`` is pure (docs/ARCHITECTURE.md §6): no Redis, no
Postgres, no clock, no HTTP. So the market identity, the market's trading rules,
the live liquidity, the beta estimate and the proposal itself are value objects
built by the caller and handed in whole.

Two things here are deliberately **not** optional conveniences:

- :class:`MarketIdentity` travels with every input, and the engine compares
  them. A proposal decided on the perpetual with a book from the spot venue
  would otherwise size against liquidity that does not exist for the order it is
  about to send (D1: spot executes, the perpetual decides);
- every observation carries its own timestamp, because the freshness of a
  decision is the freshness of its **oldest** input, not of its price
  (``R-OPS-2``). ``None`` means "not observed", never "zero".
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import Field, field_validator

from hunter_core.domain.enums import ExitReason, MarketType, TradeDirection
from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.envelope import AssumedCosts
from hunter_core.strategies.numeric import CONTEXT
from hunter_risk.base import RiskModel

DataQuality = Literal["ok", "degraded"]

_TWO = Decimal(2)


class MarketIdentity(RiskModel):
    """Which market, on which venue, in which modality. Compared, not assumed."""

    exchange: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    market_type: MarketType
    base_asset: str = Field(min_length=1)
    quote_asset: str = Field(min_length=1)


class MarketSpec(RiskModel):
    """The exchange's trading rules for one market. Static between reloads."""

    market: MarketIdentity
    step_size: Decimal = Field(gt=0)
    """Quantity increment. A size is always rounded **down** to a multiple of it."""
    min_notional: Decimal = Field(ge=0)
    """Below this the exchange refuses the order, so the engine refuses it first."""
    tick_size: Decimal | None = Field(default=None, gt=0)


class BookLevel(RiskModel):
    """One price level of the resting book."""

    price: Decimal = Field(gt=0)
    qty: Decimal = Field(gt=0)


class BetaEstimate(RiskModel):
    """The market's beta against BTC, with the marks that make it usable.

    ``validated`` is the directive's word (§4, "sem beta validado, manter o ativo
    apenas em shadow"): an estimate that exists but was not validated is not a
    beta, and the engine treats it as absent.
    """

    value: Decimal
    as_of: datetime
    validated: bool
    bars: int = Field(ge=0)

    @field_validator("as_of", mode="after")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class MarketLiquidity(RiskModel):
    """The live picture of one market: price, book, volume, and how old each is."""

    market: MarketIdentity
    data_quality: DataQuality = "ok"

    last_price: Decimal = Field(gt=0)
    mid_price: Decimal | None = Field(default=None, gt=0)
    best_bid: Decimal | None = Field(default=None, gt=0)
    best_ask: Decimal | None = Field(default=None, gt=0)
    price_ts: datetime

    asks: tuple[BookLevel, ...] = ()
    """Ask side, best first. Empty means the book was not observed - in a market
    under stress that is the normal failure, and it must reject, not skip."""
    book_ts: datetime | None = None

    quote_volume_24h: Decimal | None = Field(default=None, ge=0)
    last_minute_quote_volume: Decimal | None = Field(default=None, ge=0)
    """Quote volume of the last **complete** minute on the execution venue."""
    median_30m_quote_volume: Decimal | None = Field(default=None, ge=0)
    """Median of the last 30 complete minutes, same venue."""
    volume_window_complete: bool = False
    """False when those 30 minutes are not contiguous and complete: a median over
    a window with holes is a smaller denominator than the market really has."""
    participation_used_quote: Decimal = Field(default=Decimal(0), ge=0)
    """Notional already taken in this market inside the rolling participation
    window (v2 §4, 60 s): executed fills **and** reservations still executable,
    every agent and the manual order. Passed in, because a pure function cannot
    see the other proposals of the same cycle - and because a ceiling counted per
    order would be exactly the splitting the directive forbids."""
    volume_ts: datetime | None = None

    gap_state: Literal["ok", "open_gap"] | None = None
    """R-OPS-3. ``None`` is "not known", which rejects: 34 of 232 markets lost a
    candle in 24 h, and an unrecovered gap is not a quiet market."""
    in_universe: bool | None = None
    """R-OPS-4: the market may have left the monitored universe between the signal
    and the proposal. ``None`` rejects."""

    @field_validator("price_ts", mode="after")
    @classmethod
    def _price_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("book_ts", "volume_ts", mode="after")
    @classmethod
    def _optional_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else ensure_utc(value)

    @field_validator("asks", mode="after")
    @classmethod
    def _ascending(cls, value: tuple[BookLevel, ...]) -> tuple[BookLevel, ...]:
        prices = [level.price for level in value]
        if prices != sorted(prices):
            raise ValueError("asks must be ordered best first; an unsorted book is a bug")
        return value

    @property
    def reference_mid(self) -> Decimal | None:
        """Mid used by the book walk: the supplied mid, else bid/ask, else nothing."""
        if self.mid_price is not None:
            return self.mid_price
        if self.best_bid is not None and self.best_ask is not None:
            with localcontext(CONTEXT):
                return (self.best_bid + self.best_ask) / _TWO
        return None

    @property
    def spread_pct(self) -> Decimal | None:
        """Relative spread against the mid, or ``None`` when it was not observed."""
        mid = self.reference_mid
        if mid is None or self.best_bid is None or self.best_ask is None:
            return None
        with localcontext(CONTEXT):
            return (self.best_ask - self.best_bid) / mid

    @property
    def participation_reference(self) -> Decimal | None:
        """``min(last complete minute, median of the last 30)`` - directive §3.

        ``None`` when either leg is missing or the window is incomplete: the
        smaller of two numbers one of which is unknown is unknown.
        """
        if not self.volume_window_complete:
            return None
        if self.last_minute_quote_volume is None or self.median_30m_quote_volume is None:
            return None
        return min(self.last_minute_quote_volume, self.median_30m_quote_volume)


class EntryProposal(RiskModel):
    """What an agent wants to open. It never carries a size the engine must honour.

    ``requested_notional`` is a **ceiling the caller adds**, never a target: the
    engine may only size at or below it (directive §2, "o limite é um teto, não
    uma meta"). ``stop`` is the stop the strategy declared and the engine never
    moves it - a decision that widened a stop to fit a size would be inventing
    the protection it then reports.
    """

    proposal_id: uuid.UUID
    portfolio_id: uuid.UUID
    agent_id: uuid.UUID | None = None
    market: MarketIdentity
    direction: TradeDirection
    entry_ref: Decimal = Field(gt=0)
    """Reference price of the entry, **before** costs. The cost hypothesis is
    added once, in the sizing; folding it in here would charge it twice."""
    stop: Decimal = Field(gt=0)
    requested_notional: Decimal | None = Field(default=None, gt=0)
    assumed_costs: AssumedCosts
    agent_enabled: bool = True
    """Whether the agent behind the proposal is enabled (v2 §3.1 check 2). A DB
    fact the caller reads and passes in - the engine reads no database."""
    signal_valid: bool = True
    """Whether the signal was still active and inside its entry zone when the
    proposal was built. The zone and the expiry live in the signal envelope, not
    here; what the engine checks on its own is the stop geometry."""


class ExitProposal(RiskModel):
    """A protective exit. Bound to the position it reduces, never to a new one."""

    proposal_id: uuid.UUID
    portfolio_id: uuid.UUID
    position_id: uuid.UUID
    market: MarketIdentity
    qty: Decimal = Field(gt=0)
    reason: ExitReason
