"""``MarketContext`` — everything a feature may look at, cut at ``as_of``.

The cut is the anti-look-ahead guarantee and it is enforced by the type, not by
discipline (the shape ``hunter_core.strategies.base`` uses for the shadow lab):
a final candle is admitted only when it had already **closed** at ``as_of``
(admitting it by ``open_time`` would reveal the next 60 seconds), the candle
still forming must straddle the cut *and* have been last updated before it, and
every other source carries the exchange timestamp of the observation, which must
not be in the future either.

Two ways in, on purpose:

- :class:`MarketContext` is strict and raises — a scanner bug surfaces as an
  error instead of a quietly biased score;
- :func:`build_context` filters **the candle list, and only it**: choosing among
  candles is selection (the list legitimately holds the forming minute), while a
  book stamped after the cut is a broken clock — ``hotstate.decode_*`` turns
  that into an ``after_cut`` entry, so one that reaches here still raises.

Availability is part of the contract: a source is a :class:`SourceEntry` with
its own timestamp, coverage and reason, so "the book is missing" and "the book
is 40 s old" are different facts and neither becomes an invented zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import OrderSide, Timeframe
from hunter_core.domain.market import NormalizedCandle
from hunter_core.domain.types import ensure_utc
from hunter_indicators.features.vector import seconds_between

INPUT_CANDLES = "candles:1m"
"""Final 1-minute candles — the only input a non-``_live`` bar feature may read."""
INPUT_FORMING = "candles:1m:forming"
"""The candle still being printed. ``_live`` features only."""
INPUT_BOOK = "book:20"
"""Top-20 order book snapshot (`docs/plans/M2.md` §"Universo/book": book features are ``_20``)."""
INPUT_TRADES = "trades"
INPUT_FUNDING = "deriv:funding"
INPUT_MARK = "deriv:mark"
INPUT_OI = "deriv:oi"
INPUT_ATR_STATE = "state:atr_15m"
"""The anchored ATR checkpoint. An input like any other: its staleness must
reach every feature that reads it, not only ``atr_14_pct`` (Astra, diff review,
must-fix 2)."""

INPUT_DERIV_HISTORY = "deriv:history"
"""Past derivative observations. The hot state holds only the current one, so a
change over 1 h needs a reference the caller supplies (Postgres
``open_interest_history`` / ``funding_rates``); without it the feature is
``unavailable``, never "change since the first reading after the restart"."""

MISSING_INPUT = "missing_input"
_MINUTE = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class SourceEntry[T]:
    """One source of the context: its value, when it was observed, why not."""

    value: T | None = None
    ts: datetime | None = None
    reason: str | None = None
    covers_from: datetime | None = None
    """Oldest instant this entry is known to cover (trades tape, history series)."""
    covered_until: datetime | None = None
    """Newest instant the *collector* proves it was still listening.

    Not the newest observation: a tape whose last trade is 10 min old may be a
    quiet market or an outage, and only the collector tells them apart (Astra,
    diff review, must-fix 3). ``None`` means unproven, and a window with no
    events inside it is then ``insufficient_coverage``, never a zero."""
    truncated: bool = False
    """The source was capped by a ring buffer, so it may not reach ``covers_from``."""

    @property
    def available(self) -> bool:
        return self.value is not None and self.reason is None

    def age_s(self, as_of: datetime) -> Decimal | None:
        if self.ts is None:
            return None
        return seconds_between(self.ts, as_of)


def missing(input_name: str) -> SourceEntry[Any]:
    """The entry for a source the hot state did not have."""
    del input_name  # the name is documentation at the call site, not data
    return SourceEntry[Any](value=None, ts=None, reason=MISSING_INPUT)


@dataclass(frozen=True, slots=True)
class BookSnapshot:
    ts: datetime
    depth: int
    bids: tuple[tuple[Decimal, Decimal], ...]
    """Descending by price, exactly as the exchange published it."""
    asks: tuple[tuple[Decimal, Decimal], ...]


@dataclass(frozen=True, slots=True)
class TapeTrade:
    ts: datetime
    price: Decimal
    qty: Decimal
    side: OrderSide
    trade_id: str


@dataclass(frozen=True, slots=True)
class DerivSnapshot:
    """The ``deriv`` hash, keeping the three timestamps the writer keeps apart.

    Collapsing them into one would let a fresh mark price make a 20-minute-old
    open interest look current (Astra, T2.2 design review, must-fix 1c).
    """

    funding_rate: Decimal | None = None
    funding_kind: str | None = None
    funding_ts: datetime | None = None
    next_funding_time: datetime | None = None
    """When the current rate settles — an **appointment**, not an observation.

    Hence kept out of :meth:`timestamps`: it is supposed to be in the future.
    T2.3 needs it to read a funding rate at all (the same rate means different
    things eight hours and two minutes before settlement)."""
    mark_price: Decimal | None = None
    index_price: Decimal | None = None
    mark_ts: datetime | None = None
    open_interest: Decimal | None = None
    open_interest_value: Decimal | None = None
    oi_ts: datetime | None = None

    def timestamps(self) -> tuple[datetime, ...]:
        return tuple(ts for ts in (self.funding_ts, self.mark_ts, self.oi_ts) if ts is not None)


@dataclass(frozen=True, slots=True)
class DerivObservation:
    """A past reading of the derivative fields, for changes over a lookback."""

    ts: datetime
    open_interest: Decimal | None = None
    funding_rate: Decimal | None = None


def _check_candles(
    candles: Sequence[NormalizedCandle], exchange: str, symbol: str, as_of: datetime
) -> None:
    previous: datetime | None = None
    for item in candles:
        if item.exchange != exchange or item.symbol != symbol:
            raise ValueError(f"candle of {item.exchange}:{item.symbol} in {exchange}:{symbol}")
        if item.timeframe is not Timeframe.M1:
            raise ValueError(f"MarketContext takes 1m candles, got {item.timeframe}")
        if not item.is_final:
            raise ValueError(f"final_candles takes is_final candles only ({item.open_time})")
        if item.close_time > as_of:
            raise ValueError(f"candle close_time {item.close_time} is after the cut {as_of}")
        if previous is not None and item.open_time <= previous:
            raise ValueError("final_candles must be strictly increasing by open_time")
        previous = item.open_time


def _check_forming(forming: NormalizedCandle, exchange: str, symbol: str, as_of: datetime) -> None:
    if forming.exchange != exchange or forming.symbol != symbol:
        raise ValueError(f"forming candle of {forming.exchange}:{forming.symbol}")
    if forming.is_final:
        raise ValueError("forming must be a non-final candle")
    if not (forming.open_time <= as_of < forming.close_time):
        raise ValueError(f"forming candle {forming.open_time} does not straddle the cut {as_of}")
    if forming.event_ts is None:
        # the market-worker refuses to store a partial without the exchange push
        # time (hot_state_candles.push_candle), so one without it can only hide a
        # later update: 12:00:50 data inside a 12:00:20 evaluation.
        raise ValueError("a forming candle without event_ts cannot be proven causal")
    if forming.event_ts > as_of:
        raise ValueError(f"forming candle event_ts {forming.event_ts} is after the cut {as_of}")


@dataclass(frozen=True, slots=True)
class MarketContext:
    """One market, as it was observable at ``as_of``."""

    exchange: str
    symbol: str
    as_of: datetime
    final_candles: tuple[NormalizedCandle, ...] = ()
    forming: NormalizedCandle | None = None
    book: SourceEntry[BookSnapshot] = field(default_factory=lambda: missing(INPUT_BOOK))
    trades: SourceEntry[tuple[TapeTrade, ...]] = field(
        default_factory=lambda: missing(INPUT_TRADES)
    )
    deriv: SourceEntry[DerivSnapshot] = field(default_factory=lambda: missing(INPUT_OI))
    deriv_history: SourceEntry[tuple[DerivObservation, ...]] = field(
        default_factory=lambda: missing(INPUT_DERIV_HISTORY)
    )
    candles_truncated: bool = False
    """The minute history came back as long as it was asked for, so it may have
    been capped: the buffer holds 1500 minutes and the deepest window asks for
    1440. Travels to the provenance of ``candles:1m`` (nice-to-have b)."""
    btc: MarketContext | None = None
    """The reference market, cut at the same instant. Never nested twice."""

    def __post_init__(self) -> None:
        as_of = ensure_utc(self.as_of)
        object.__setattr__(self, "as_of", as_of)
        _check_candles(self.final_candles, self.exchange, self.symbol, as_of)
        if self.forming is not None:
            _check_forming(self.forming, self.exchange, self.symbol, as_of)
        for entry, label in (
            (self.book, "book"),
            (self.trades, "trades"),
            (self.deriv, "deriv"),
            (self.deriv_history, "deriv_history"),
        ):
            if entry.ts is not None and entry.ts > as_of:
                raise ValueError(f"{label} observed at {entry.ts}, after the cut as_of={as_of}")
        book = self.book.value
        if book is not None and book.ts > as_of:
            raise ValueError(f"book snapshot {book.ts} is after the cut as_of={as_of}")
        deriv = self.deriv.value
        if deriv is not None and any(ts > as_of for ts in deriv.timestamps()):
            raise ValueError(f"deriv field observed after the cut as_of={as_of}")
        for trade in self.trades.value or ():
            if trade.ts > as_of:
                raise ValueError(f"trade {trade.trade_id} at {trade.ts} is after the cut {as_of}")
        for observation in self.deriv_history.value or ():
            if observation.ts > as_of:
                raise ValueError(f"deriv history at {observation.ts} is after the cut {as_of}")
        if self.btc is not None:
            if self.btc.as_of != as_of:
                raise ValueError("the btc reference must share the same as_of cut")
            if self.btc.btc is not None:
                raise ValueError("the btc reference must not nest another reference")

    @property
    def last_final(self) -> NormalizedCandle | None:
        return self.final_candles[-1] if self.final_candles else None


def build_context(
    *,
    exchange: str,
    symbol: str,
    as_of: datetime,
    candles: Iterable[NormalizedCandle] = (),
    book: SourceEntry[BookSnapshot] | None = None,
    trades: SourceEntry[tuple[TapeTrade, ...]] | None = None,
    deriv: SourceEntry[DerivSnapshot] | None = None,
    deriv_history: SourceEntry[tuple[DerivObservation, ...]] | None = None,
    candles_truncated: bool = False,
    btc: MarketContext | None = None,
) -> MarketContext:
    """A context that respects the cut, filtering the **candles** handed over.

    Drops foreign markets, non-1m candles, candles that had not closed at
    ``as_of``, and a forming candle whose last update is newer than the cut or
    that carries no update timestamp at all.

    It does **not** filter ``book``/``trades``/``deriv``/``deriv_history``: those
    arrive as entries someone already decided about (``hotstate.decode_*`` drops
    what it saw after the cut, with a reason), so one still stamped after
    ``as_of`` is a bug in that decision and raises instead of being emptied.
    """
    as_of = ensure_utc(as_of)
    final: list[NormalizedCandle] = []
    forming: NormalizedCandle | None = None
    for item in candles:
        if item.exchange != exchange or item.symbol != symbol or item.timeframe is not Timeframe.M1:
            continue
        if item.is_final:
            if item.close_time <= as_of:
                final.append(item)
            continue
        if (
            item.open_time <= as_of < item.close_time
            and item.event_ts is not None
            and item.event_ts <= as_of
        ):
            if forming is None or item.open_time > forming.open_time:
                forming = item
    final.sort(key=lambda c: c.open_time)
    deduped: list[NormalizedCandle] = []
    for item in final:
        if deduped and deduped[-1].open_time == item.open_time:
            deduped[-1] = item
            continue
        deduped.append(item)
    return MarketContext(
        exchange=exchange,
        symbol=symbol,
        as_of=as_of,
        final_candles=tuple(deduped),
        forming=forming,
        book=book if book is not None else missing(INPUT_BOOK),
        trades=trades if trades is not None else missing(INPUT_TRADES),
        deriv=deriv if deriv is not None else missing(INPUT_OI),
        deriv_history=deriv_history if deriv_history is not None else missing(INPUT_DERIV_HISTORY),
        candles_truncated=candles_truncated,
        btc=btc,
    )


def expected_last_close(as_of: datetime) -> datetime:
    """The minute close a healthy feed would already have printed at ``as_of``."""
    return as_of.replace(second=0, microsecond=0)


__all__ = [
    "INPUT_ATR_STATE",
    "INPUT_BOOK",
    "INPUT_CANDLES",
    "INPUT_DERIV_HISTORY",
    "INPUT_FORMING",
    "INPUT_FUNDING",
    "INPUT_MARK",
    "INPUT_OI",
    "INPUT_TRADES",
    "MISSING_INPUT",
    "BookSnapshot",
    "DerivObservation",
    "DerivSnapshot",
    "MarketContext",
    "SourceEntry",
    "TapeTrade",
    "build_context",
    "expected_last_close",
    "missing",
    "seconds_between",
]
