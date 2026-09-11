"""The market picture one bridge submission is decided against — assembled, never guessed.

``admit`` takes ``MarketLiquidity`` from its caller on purpose: a service that
fetched the price, the volume and the beta itself would be *choosing* them
silently. So the bridge declares its sources here, and each one is either read
or reported absent:

- **price and book** — the last valid SPOT print and the eligible book of the
  hot state, through the same :class:`SpotMarketData` the entry cycle uses;
- **volume, all of it** — the last complete 1m candle of the **spot** market,
  the median of the last 30 and the **24 h sum**, from one ``candles`` read of
  one venue, stamped with the close of the newest candle it found (T3.86).
  Incomplete window means ``volume_window_complete = False``, which makes the
  engine's participation reference unknown and rejects, exactly as it should: a
  median over a window with holes is a smaller denominator than the market
  really has. The 24 h figure is **not** ``markets.volume_24h_usd``: that
  column is a ticker snapshot from another instant, with no timestamp of its
  own, and the contract gives the two volumes a single ``volume_ts``;
- **continuity** — an unrecovered ``ingestion_gaps`` row is ``open_gap``
  (R-OPS-3). No row is ``ok``, and that is a claim about *the gap table*, which
  is the artefact whose whole job is to know;
- **universe membership** — ``markets.is_monitored``, written by T3.0c's spot
  refresh (R-OPS-4).

Nothing here has a default that flatters the market. Every unknown arrives at
the engine as ``None`` and the engine refuses, which is the contract's rule and
the reason a paper wallet can be believed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from sqlalchemy import text

from hunter_core.execution.tape import usable_trade
from hunter_core.logging import get_logger
from hunter_execution_worker.positions import load_open_positions
from hunter_execution_worker.reference import load_markets
from hunter_risk.inputs import BookLevel as RiskBookLevel
from hunter_risk.inputs import MarketLiquidity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.execution.tape import MarkingPolicy
    from hunter_execution_worker.bridge_universe import SpotPair
    from hunter_execution_worker.market_data import SpotMarketData, SpotSnapshot
    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = [
    "WINDOW_MINUTES",
    "MarkCoverage",
    "VolumeWindow",
    "liquidity_for",
    "marks_for_open_positions",
]

logger = get_logger(__name__)

WINDOW_MINUTES = 30
"""Complete minutes behind the participation median (RISK_ENGINE.md v2 §4)."""

DAY_MINUTES = 1440
"""Complete minutes behind the 24 h figure of check 9 (RISK_ENGINE.md §3.1)."""

_TWO = Decimal(2)
_ONE = Decimal(1)


class VolumeWindow:
    """The volume numbers of one market, all from **one** read, and how old they are.

    The 24 h figure lives here, next to the minute reference, because the
    contract gives the two a **single** stamp (§3.1, "Idade do volume"): one
    ``volume_ts`` decides whether check 9 and ``participation`` may be
    evaluated at all. Two numbers from two sources cannot honour one stamp —
    T3.86 — so both come from the same ``candles`` read of the same execution
    venue, in the same transaction, over windows that end at the same minute.
    """

    __slots__ = (
        "complete",
        "day_minutes",
        "last_minute",
        "median",
        "quote_volume_24h",
        "volume_ts",
    )

    def __init__(
        self,
        *,
        last_minute: Decimal | None,
        median: Decimal | None,
        complete: bool,
        volume_ts: datetime | None,
        quote_volume_24h: Decimal | None = None,
        day_minutes: int = 0,
    ) -> None:
        self.last_minute = last_minute
        self.median = median
        self.complete = complete
        self.volume_ts = volume_ts
        self.quote_volume_24h = quote_volume_24h
        self.day_minutes = day_minutes


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / _TWO


async def volume_window(
    session: AsyncSession, *, market_id: uuid.UUID, now: datetime
) -> VolumeWindow:
    """Every volume number of one spot market: the minute, the median of 30, the 24 h.

    **The stamp is the close of the newest candle actually observed, never the
    cycle's own clock (T3.86).** Minting ``volume_ts`` from ``now`` said "this
    is a picture of the last minute" even when the newest candle was an hour
    old; the engine then measured 60 s against ``max_volume_age_s`` and
    believed it. Read off the data, a feed that stopped ten minutes ago reports
    600 s and ``liquidity_24h``/``participation`` come back ``unavailable`` with
    the age named, which is R-OPS-2 working.

    **The 24 h figure is summed here and not read from
    ``markets.volume_24h_usd``.** That column is a ticker snapshot the spot
    universe refresh rewrites every ``market_universe_refresh_s`` (900 s by
    default, against a 120 s age budget), it has no timestamp of its own —
    ``last_seen_at`` is the upsert, and ``upsert_markets`` coalesces the old
    value onto the row when the symbol is missing from the bulk ticker, so a
    frozen number keeps a fresh-looking ``last_seen_at`` for ever — and it
    described a different instant from ``volume_ts``. Partial coverage of the
    window can only make the sum **smaller**, so it can only refuse: an
    undercount never buys anything, and an unrecovered hole is already
    ``open_gap`` (check 5).
    """
    last_open = now.replace(second=0, microsecond=0) - timedelta(minutes=1)
    first_open = last_open - timedelta(minutes=WINDOW_MINUTES - 1)
    rows = (
        await session.execute(
            text(
                "SELECT open_time, quote_volume FROM candles WHERE market_id = :market "
                "AND timeframe = '1m' AND is_final AND open_time BETWEEN :first AND :last "
                "ORDER BY open_time DESC"
            ),
            {"market": market_id, "first": first_open, "last": last_open},
        )
    ).all()
    # Aggregated in Postgres: the 24 h window is 1440 rows per market per pass,
    # and the cycle needs three numbers out of it, not the rows themselves.
    day = (
        await session.execute(
            text(
                "SELECT sum(quote_volume) AS total, count(quote_volume) AS minutes, "
                "max(open_time) AS newest FROM candles WHERE market_id = :market "
                "AND timeframe = '1m' AND is_final AND open_time BETWEEN :first AND :last"
            ),
            {
                "market": market_id,
                "first": last_open - timedelta(minutes=DAY_MINUTES - 1),
                "last": last_open,
            },
        )
    ).one()
    volumes = [row.quote_volume for row in rows]
    complete = len(rows) == WINDOW_MINUTES and all(value is not None for value in volumes)
    newest = rows[0] if rows else None
    last_minute = (
        newest.quote_volume if newest is not None and newest.open_time == last_open else None
    )
    return VolumeWindow(
        last_minute=None if last_minute is None else Decimal(str(last_minute)),
        median=(
            _median([Decimal(str(value)) for value in volumes if value is not None])
            if complete
            else None
        ),
        complete=complete,
        volume_ts=None if day.newest is None else day.newest + timedelta(minutes=1),
        quote_volume_24h=None if day.total is None else Decimal(str(day.total)),
        day_minutes=int(day.minutes or 0),
    )


async def gap_state(session: AsyncSession, *, market_id: uuid.UUID) -> Literal["ok", "open_gap"]:
    """``open_gap`` while a hole in the 1m series is unrecovered, else ``ok``."""
    found = await session.scalar(
        text(
            "SELECT 1 FROM ingestion_gaps WHERE market_id = :market AND timeframe = '1m' "
            "AND recovered_at IS NULL AND status <> 'recovered' LIMIT 1"
        ),
        {"market": market_id},
    )
    return "open_gap" if found is not None else "ok"


async def liquidity_for(
    session: AsyncSession,
    *,
    spot: SpotPair,
    market: MarketReference,
    snapshot: SpotSnapshot,
    now: datetime,
) -> MarketLiquidity | str:
    """One market's live picture, or the name of the input that is missing."""
    trade = snapshot.last_trade
    if trade is None:
        return "spot_price_unavailable"
    book = snapshot.book
    if book is None or not book.asks or not book.bids:
        return "spot_book_unavailable"
    best_bid = book.bids[0].price
    best_ask = book.asks[0].price
    volumes = await volume_window(session, market_id=spot.market_id, now=now)
    return MarketLiquidity(
        market=market.identity,
        last_price=trade.price,
        mid_price=(best_bid + best_ask) / _TWO,
        best_bid=best_bid,
        best_ask=best_ask,
        price_ts=trade.ts,
        asks=tuple(RiskBookLevel(price=level.price, qty=level.qty) for level in book.asks),
        book_ts=book.received_at,
        quote_volume_24h=volumes.quote_volume_24h,
        last_minute_quote_volume=volumes.last_minute,
        median_30m_quote_volume=volumes.median,
        volume_window_complete=volumes.complete,
        volume_ts=volumes.volume_ts,
        gap_state=await gap_state(session, market_id=spot.market_id),
        in_universe=spot.is_monitored,
    )


@dataclass(frozen=True, slots=True)
class MarkCoverage:
    """The marks of one pass, and **how good they are** (T3.29 item 4).

    ``mtm_fresh`` (``health.py``) measures the *write*: whether a curve point was
    persisted recently. That is not the same question as whether the prices in
    it were live, and Astra's review of 2026-09-08 named the scenario — a
    stopped tape, a wallet marked at the last durable price, an equity that
    looks stable and a green MTM check. :attr:`quality` is the missing number:
    the share of open positions this pass could mark with a **live** print
    inside the marking policy's own age budget.

    A wallet with no open positions has quality ``1`` by construction: there is
    nothing whose price could be stale, and reporting ``0`` would turn the
    normal, empty wallet into a permanent alarm.
    """

    marks: dict[uuid.UUID, Decimal]
    open_positions: int
    """Positions read from Postgres this pass — the denominator."""

    @property
    def marked(self) -> int:
        """How many of them got a live price — the numerator."""
        return len(self.marks)

    @property
    def quality(self) -> Decimal:
        """Share of open positions marked live, in ``[0, 1]``."""
        if self.open_positions <= 0:
            return _ONE
        return Decimal(self.marked) / Decimal(self.open_positions)

    @property
    def complete(self) -> bool:
        """Whether **every** open position is marked at a live price."""
        return self.quality >= _ONE


async def marks_for_open_positions(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    data: SpotMarketData,
    policy: MarkingPolicy,
    now: datetime,
) -> MarkCoverage:
    """A price per open market, from the **last valid SPOT trade** and nothing else.

    A market whose tape has nothing usable is simply absent from the map, and
    the ledger then falls back to the last durable mark and flags the state
    incomplete. Marking at a price we could not validate would be the invented
    number the directive forbids. Returns the marks **and** the coverage they
    achieved, so the caller can report the quality without a second query.
    """
    positions = await load_open_positions(session, wallet=wallet)
    markets = await load_markets(session, {position.market_id for position in positions})
    marks: dict[uuid.UUID, Decimal] = {}
    for market_id, market in markets.items():
        snapshot = await data.snapshot(market.identity)
        trade, _ = usable_trade(snapshot.last_trade, now=now, policy=policy)
        if trade is not None:
            marks[market_id] = trade.price
    return MarkCoverage(marks=marks, open_positions=len(positions))


def prices_with(
    marks: Mapping[uuid.UUID, Decimal], *, market_id: uuid.UUID, price: Decimal
) -> dict[uuid.UUID, Decimal]:
    """The mark map the candidate's own market is added to, without mutating it."""
    return {**marks, market_id: price}
