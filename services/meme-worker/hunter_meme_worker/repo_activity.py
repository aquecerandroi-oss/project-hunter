"""The batch tape's rows (T4.2g): ``meme_market_activity_1m`` from what the
``swap-api`` batch route said — as ``hunter_worker``, never as owner
(``repo.py``'s discipline). Pure conversion here, one ``INSERT`` there.

**What a row claims, and what it does not.** A reading the route returned as
an object becomes a row of its numbers. A window the route returned as
``null`` becomes a row of zeros with ``empty = true`` **only** when the same
cycle's responses filled that window for at least one coin
(``ActivityBatch.windows_live``): that is the proof the route computes the
window, and then ``null`` is its way of saying "no trade". A ``null`` under a
window nobody filled is written nowhere — it is counted as *dark* and the
heartbeat says so (the ``1m`` window was accepted by the validator but not
yet seen non-null on a trading coin; ``market_activity.py``). The SOL
columns are derived with the quote the worker held, which sits beside them;
without one they are ``NULL`` together (``sol_figures_name_their_quote``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_exchanges.pumpfun.market_activity import ACTIVITY_SOURCE, WINDOW_SECONDS
from hunter_meme_worker.features_tape import ActivityReading

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_exchanges.pumpfun.market_activity import ActivityBatch, NormalizedMarketActivity

__all__ = ["ActivityRow", "SolQuote", "TAPE_WINDOW", "activity_rows", "insert_activity"]

TAPE_WINDOW = "1m"
"""The window the features read as the minute's tape; the rest is the record."""
_MONEY = Decimal("0.0000000001")


@dataclass(frozen=True, slots=True)
class SolQuote:
    """The SOL/USD quote the worker held when it derived the SOL columns."""

    price_usd: Decimal
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ActivityRow:
    """One row of ``meme_market_activity_1m``."""

    end_time: datetime
    mint: str
    window_name: str
    window_s: int
    received_at: datetime
    empty: bool
    num_txs: int
    buys: int
    sells: int
    unique_users: int
    unique_buyers: int
    unique_sellers: int
    volume_usd: Decimal
    buy_volume_usd: Decimal
    sell_volume_usd: Decimal
    price_change_pct: Decimal | None
    sol_usd: Decimal | None
    sol_usd_observed_at: datetime | None
    buy_volume_sol: Decimal | None
    sell_volume_sol: Decimal | None
    source: str = ACTIVITY_SOURCE

    def as_reading(self) -> ActivityReading:
        return ActivityReading(
            mint=self.mint,
            end_time=self.end_time,
            received_at=self.received_at,
            window_s=self.window_s,
            buys=self.buys,
            sells=self.sells,
            unique_buyers=self.unique_buyers,
            buy_volume_usd=self.buy_volume_usd,
            sell_volume_usd=self.sell_volume_usd,
            sol_usd=self.sol_usd,
            sol_usd_observed_at=self.sol_usd_observed_at,
            empty=self.empty,
        )


def _sol(usd: Decimal, quote: SolQuote | None) -> Decimal | None:
    if quote is None or quote.price_usd <= 0:
        return None
    return (usd / quote.price_usd).quantize(_MONEY, ROUND_HALF_EVEN)


def _row_from_reading(reading: NormalizedMarketActivity, quote: SolQuote | None) -> ActivityRow:
    return ActivityRow(
        end_time=reading.observed_at,
        mint=reading.mint,
        window_name=reading.window,
        window_s=reading.window_s,
        received_at=reading.received_at,
        empty=False,
        num_txs=reading.num_txs,
        buys=reading.buys,
        sells=reading.sells,
        unique_users=reading.unique_users,
        unique_buyers=reading.unique_buyers,
        unique_sellers=reading.unique_sellers,
        volume_usd=reading.volume_usd,
        buy_volume_usd=reading.buy_volume_usd,
        sell_volume_usd=reading.sell_volume_usd,
        price_change_pct=reading.price_change_pct,
        sol_usd=None if quote is None else quote.price_usd,
        sol_usd_observed_at=None if quote is None else quote.observed_at,
        buy_volume_sol=_sol(reading.buy_volume_usd, quote),
        sell_volume_sol=_sol(reading.sell_volume_usd, quote),
        source=reading.source,
    )


def _empty_row(
    mint: str, window: str, *, end_time: datetime, received_at: datetime, quote: SolQuote | None
) -> ActivityRow:
    zero = Decimal(0)
    return ActivityRow(
        end_time=end_time,
        mint=mint,
        window_name=window,
        window_s=WINDOW_SECONDS[window],
        received_at=received_at,
        empty=True,
        num_txs=0,
        buys=0,
        sells=0,
        unique_users=0,
        unique_buyers=0,
        unique_sellers=0,
        volume_usd=zero,
        buy_volume_usd=zero,
        sell_volume_usd=zero,
        price_change_pct=None,
        sol_usd=None if quote is None else quote.price_usd,
        sol_usd_observed_at=None if quote is None else quote.observed_at,
        buy_volume_sol=None if quote is None else zero,
        sell_volume_sol=None if quote is None else zero,
    )


def activity_rows(
    batches: Sequence[ActivityBatch], *, quote: SolQuote | None
) -> tuple[list[ActivityRow], dict[str, int]]:
    """Every batch of one cycle into rows: numbers as delivered, stated zeros
    for the windows the cycle proved live, nothing for the dark ones — and
    how many ``(window → coins)`` were left dark, for the heartbeat."""
    live: set[str] = set()
    for batch in batches:
        live |= batch.windows_live
    rows: list[ActivityRow] = []
    dark: dict[str, int] = {}
    for batch in batches:
        rows.extend(_row_from_reading(reading, quote) for reading in batch.readings)
        for window, mints in batch.empty.items():
            if window in live:
                rows.extend(
                    _empty_row(
                        mint,
                        window,
                        end_time=batch.observed_at,
                        received_at=batch.received_at,
                        quote=quote,
                    )
                    for mint in mints
                )
            elif mints:
                dark[window] = dark.get(window, 0) + len(mints)
    return rows, dark


_COLUMNS = tuple(ActivityRow.__dataclass_fields__)
_INSERT = text(
    f"INSERT INTO meme_market_activity_1m ({', '.join(_COLUMNS)}) "  # noqa: S608
    f"VALUES ({', '.join(':' + column for column in _COLUMNS)}) "
    "ON CONFLICT (end_time, mint, window_name) DO NOTHING"
)


async def insert_activity(session: AsyncSession, rows: Sequence[ActivityRow]) -> int:
    """One statement per cycle's worth of rows; returns how many were offered."""
    if not rows:
        return 0
    await session.execute(_INSERT, [asdict(row) for row in rows])
    return len(rows)
