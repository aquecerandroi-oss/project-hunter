"""The columns ``0023`` added to the minute: holders from the site's boards
(or its risk read) and the tape of ``swap-api`` — pure, and honest about what
it cannot compute.

**Non-anticipation is decided here and nowhere later.** Every input carries
``received_at``; a reading that reached us after ``end_time`` is not an input
of that minute, however early the source stamps it. ``holders_for`` picks the
newest reading with ``received_at <= end_time``; ``tape_for`` counts only
trades with ``received_at <= end_time`` and ``block_time`` inside the minute.
``test_features.py`` proves the look-ahead case: a holders reading or a trade
stamped inside the minute but received one second after it closes changes
nothing in the row.

Two "creator" booleans, because the gate and the diary ask two questions:
``creator_sold`` (F-B3's ``creator_sold_any``: any sell by the creator in the
tape covered so far) and ``creator_net_seller`` (``Σ sells − Σ buys > 0`` in
SOL, the EXP-M1 input). Both need ``meme_tokens.creator``; without it they are
``NULL`` with ``no_trade_feed``… no — with ``no_holders_reader``? Neither:
the creator is identity, and the honest reason is the tape's own (``no_trade_feed``
when no tape, else the creator is unknown and the row says so through the token
row's ``creator IS NULL`` — the §19.3 argument against a second copy). The
vocabulary is the frozen one plus ``no_sells`` (``0023``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

NO_SELLS = "no_sells"
"""A buy/sell ratio over a minute with buys and no sells is not a number; the
row says so instead of writing an infinity or a zero (``0023``)."""

_FRACTION = Decimal("0.000001")
_MONEY = Decimal("0.0000000001")
_RATIO = Decimal("0.00000001")
LAMPORTS_PER_SOL = Decimal(1_000_000_000)


@dataclass(frozen=True, slots=True)
class HoldersObservation:
    """One reading of holders/top-10/dev/snipers, from a board entry or the
    risk read, with the two clocks that make it usable in a closed minute."""

    observed_at: datetime
    received_at: datetime
    source: str
    holders: int | None
    top10_share: Decimal | None
    dev_share: Decimal | None
    snipers: int | None


@dataclass(frozen=True, slots=True)
class TapeTrade:
    """The part of a ``meme_trades`` row the fold reads."""

    block_time: datetime
    received_at: datetime
    trader: str
    side: str
    sol_lamports: int


@dataclass(frozen=True, slots=True)
class TapeMinute:
    """What the tape said about one mint at ``end_time`` — a **pulled** tape,
    even when nothing traded, so a zero here is a zero the source stated."""

    buys: int
    sells: int
    unique_buyers: int
    net_sol_flow: Decimal
    volume_sol: Decimal
    creator_sold: bool | None
    creator_net_seller: bool | None


def holders_for(
    readings: list[HoldersObservation], *, end_time: datetime
) -> HoldersObservation | None:
    """The newest reading that had reached us by ``end_time``, or ``None``."""
    usable = [r for r in readings if r.received_at <= end_time]
    if not usable:
        return None
    return max(usable, key=lambda r: (r.received_at, r.observed_at))


def tape_for(
    trades: list[TapeTrade],
    *,
    end_time: datetime,
    creator: str | None,
    covered_since: datetime | None,
) -> TapeMinute | None:
    """Fold the tape of one mint at ``end_time``.

    ``covered_since`` is when the first successful pull of this mint's tape was
    received; ``None`` (never pulled) or later than ``end_time`` means the minute
    had no tape and the result is ``None`` — the caller writes ``no_trade_feed``.
    ``creator`` is ``meme_tokens.creator``; unknown means the two creator
    booleans are ``None``.
    """
    if covered_since is None or covered_since > end_time:
        return None
    start = end_time - timedelta(minutes=1)
    known = [t for t in trades if t.received_at <= end_time]
    minute = [t for t in known if start < t.block_time <= end_time]
    buys = sum(1 for t in minute if t.side == "buy")
    sells = sum(1 for t in minute if t.side == "sell")
    buyers = {t.trader for t in minute if t.side == "buy" and t.trader != creator}
    inflow = sum((t.sol_lamports for t in minute if t.side == "buy"), 0)
    outflow = sum((t.sol_lamports for t in minute if t.side == "sell"), 0)
    volume = (Decimal(inflow + outflow) / LAMPORTS_PER_SOL).quantize(_MONEY, ROUND_HALF_EVEN)
    net = (Decimal(inflow - outflow) / LAMPORTS_PER_SOL).quantize(_MONEY, ROUND_HALF_EVEN)
    creator_sold: bool | None = None
    creator_net_seller: bool | None = None
    if creator is not None:
        creator_trades = [t for t in known if t.trader == creator and t.block_time <= end_time]
        sold = sum(t.sol_lamports for t in creator_trades if t.side == "sell")
        bought = sum(t.sol_lamports for t in creator_trades if t.side == "buy")
        creator_sold = sold > 0
        creator_net_seller = sold > bought
    return TapeMinute(
        buys=buys,
        sells=sells,
        unique_buyers=len(buyers),
        net_sol_flow=net,
        volume_sol=volume,
        creator_sold=creator_sold,
        creator_net_seller=creator_net_seller,
    )


def buy_sell_ratio(buys: int, sells: int) -> Decimal | None:
    """Counts, not notional (T4-MEME-RADAR.md §5); ``None`` with no sells."""
    if sells == 0:
        return None
    return (Decimal(buys) / Decimal(sells)).quantize(_RATIO, ROUND_HALF_EVEN)


def fraction(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(_FRACTION, ROUND_HALF_EVEN)
