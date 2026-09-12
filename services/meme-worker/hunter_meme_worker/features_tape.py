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

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

NO_SELLS = "no_sells"
"""A buy/sell ratio over a minute with buys and no sells is not a number; the
row says so instead of writing an infinity or a zero (``0023``)."""
NO_TRADE_FEED = "no_trade_feed"
NO_SOL_QUOTE = "no_sol_quote"
"""The batch route counted the window in USD and the worker held no SOL/USD
quote young enough to turn it into SOL (``0032``): the tape columns stay
``NULL`` with this reason rather than carry a guessed conversion."""
SWAP_API_TRADES = "swap_api_trades"
ACTIVITY_1M = "activity_1m"
"""``tape_source`` (``0032``): the per-mint tape folded over the minute, or
the batch route's ``1m`` window ending at ``tape_as_of``."""

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
    source: str = SWAP_API_TRADES
    window_s: int = 60
    as_of: datetime | None = None
    """Where the numbers came from and the instant their window ends
    (``0032``): ``end_time`` for the per-mint tape; the batch response's stamp
    for ``activity_1m``, which may sit up to a minute before the instant judged."""


@dataclass(frozen=True, slots=True)
class ActivityReading:
    """One coin's ``1m`` window from the batch route (T4.2g), as the fold reads
    it: the counts and USD volumes the route said, the quote the worker held,
    and the two clocks non-anticipation is judged on."""

    mint: str
    end_time: datetime
    received_at: datetime
    window_s: int
    buys: int
    sells: int
    unique_buyers: int
    buy_volume_usd: Decimal
    sell_volume_usd: Decimal
    sol_usd: Decimal | None
    sol_usd_observed_at: datetime | None
    empty: bool = False
    """The route answered ``null`` for the window in a cycle that filled it
    for another coin: a stated zero, not an unknown."""


def activity_for(
    readings: Sequence[ActivityReading], *, at: datetime, max_age_s: float
) -> ActivityReading | None:
    """The newest reading that had reached us by ``at`` and whose window ended
    less than ``max_age_s`` before it, or ``None``."""
    usable = [
        r
        for r in readings
        if r.received_at <= at and at - r.end_time < timedelta(seconds=max_age_s)
    ]
    if not usable:
        return None
    return max(usable, key=lambda r: (r.received_at, r.end_time))


def activity_minute(reading: ActivityReading) -> TapeMinute | None:
    """The batch's window as a tape minute: SOL volumes derived with the quote
    beside the reading, ``creator_*`` unknown (the route does not say who
    traded). ``None`` without a positive quote — the caller writes
    ``no_sol_quote``."""
    if reading.sol_usd is None or reading.sol_usd <= 0:
        return None
    bought = (reading.buy_volume_usd / reading.sol_usd).quantize(_MONEY, ROUND_HALF_EVEN)
    sold = (reading.sell_volume_usd / reading.sol_usd).quantize(_MONEY, ROUND_HALF_EVEN)
    return TapeMinute(
        buys=reading.buys,
        sells=reading.sells,
        unique_buyers=reading.unique_buyers,
        net_sol_flow=bought - sold,
        volume_sol=bought + sold,
        creator_sold=None,
        creator_net_seller=None,
        source=ACTIVITY_1M,
        window_s=reading.window_s,
        as_of=reading.end_time,
    )


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
        as_of=end_time,
    )


def tape_columns(tape: TapeMinute | None, absence: str) -> dict[str, object]:
    """The tape columns of a ``meme_features_1m`` row: the reasons when there
    is no tape; the numbers, the source that named them (``0032``) and the
    creator columns — ``no_trade_feed`` when the source does not say who —
    when there is one."""
    if tape is None:
        return {
            "unique_buyers_reason": absence,
            "buy_sell_ratio_reason": absence,
            "creator_sold_reason": absence,
            "tape_reason": absence,
            "creator_net_seller_reason": absence,
        }
    ratio = buy_sell_ratio(tape.buys, tape.sells)
    named = tape.as_of is not None  # a minute that names its window names its source
    return {
        "unique_buyers": tape.unique_buyers,
        "unique_buyers_reason": None,
        "buy_sell_ratio": ratio,
        "buy_sell_ratio_reason": None if ratio is not None else NO_SELLS,
        "buys_1m": tape.buys,
        "sells_1m": tape.sells,
        "net_sol_flow_1m": tape.net_sol_flow,
        "curve_volume_1m_sol": tape.volume_sol,
        "tape_reason": None,
        "tape_source": tape.source if named else None,
        "tape_window_s": tape.window_s if named else None,
        "tape_as_of": tape.as_of,
        "creator_sold": tape.creator_sold,
        "creator_sold_reason": None if tape.creator_sold is not None else NO_TRADE_FEED,
        "creator_net_seller": tape.creator_net_seller,
        "creator_net_seller_reason": None if tape.creator_net_seller is not None else NO_TRADE_FEED,
    }


def buy_sell_ratio(buys: int, sells: int) -> Decimal | None:
    """Counts, not notional (T4-MEME-RADAR.md §5); ``None`` with no sells."""
    if sells == 0:
        return None
    return (Decimal(buys) / Decimal(sells)).quantize(_RATIO, ROUND_HALF_EVEN)


def fraction(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(_FRACTION, ROUND_HALF_EVEN)
