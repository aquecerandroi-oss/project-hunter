"""T4.74-3 — from a Lab signal to the engine's ``SpotSignalInputs`` (design §2, §4).

Pure in the middle: :func:`parity_ratio` and :func:`geometry` are arithmetic in
``Decimal`` with a reason for every missing number (never a zero, never a
default); :func:`latest_final_close` is the one bounded read — the last
**final** 1 m close of a market — used twice per decision (``bin_usd`` for
the signal's market, ``sol_usd`` for ``SOLUSDT`` on the same exchange).

``jup_usd = ticket_sol × sol_usd ÷ (out_amount ÷ 10^decimals) × units_per_binance_unit``
(what one Binance unit of the token costs us on Jupiter), and the check
``parity`` refuses ``|jup_usd ÷ bin_usd − 1| > SPOT1_MAX_PARITY_PCT`` — the
filter that separated 54 false homonyms in R63.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_risk_meme import SpotSignalInputs

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_executor.spot_repo import SpotCandidate

__all__ = [
    "SOL_SYMBOL",
    "FinalClose",
    "Geometry",
    "Parity",
    "geometry",
    "latest_final_close",
    "parity_ratio",
    "signal_inputs",
]

SOL_SYMBOL = "SOLUSDT"
_CANDLE = timedelta(minutes=1)
_ZERO = Decimal(0)
_TEN = Decimal(10)

_LATEST_CLOSE = text(
    "SELECT c.close, c.open_time FROM candles c JOIN markets m ON m.id = c.market_id "
    "WHERE m.symbol = :symbol AND m.exchange_id = :exchange_id "
    "  AND m.market_type = CAST(:market_type AS market_type) "
    "  AND c.timeframe = '1m' AND c.is_final AND c.open_time >= :since "
    "  AND c.open_time <= :until "
    "ORDER BY c.open_time DESC LIMIT 1"
)


@dataclass(frozen=True, slots=True)
class FinalClose:
    close: Decimal
    close_time: datetime
    """``open_time + 1 min`` — the instant the bar closed on the exchange."""


@dataclass(frozen=True, slots=True)
class Parity:
    ratio: Decimal | None
    reason: str | None = None
    jup_usd: Decimal | None = None
    bin_usd: Decimal | None = None
    sol_usd: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Geometry:
    stop_frac: Decimal | None
    target_frac: Decimal | None
    horizon_s: int | None
    reason: str | None = None


async def latest_final_close(
    session: AsyncSession,
    *,
    symbol: str,
    exchange_id: str,
    market_type: str,
    now: datetime,
    max_age_s: int,
) -> FinalClose | None:
    """The last final 1 m close with ``now − max_age_s <= close_time <= now``; ``None``
    when the tape is older than that (the caller names ``*_unavailable``). The upper
    bound (Astra) is what keeps a replay from reading a bar that closed after ``now``."""
    since = now - timedelta(seconds=max_age_s) - _CANDLE
    until = now - _CANDLE
    r = (
        (
            await session.execute(
                _LATEST_CLOSE,
                {
                    "symbol": symbol,
                    "exchange_id": exchange_id,
                    "market_type": market_type,
                    "since": since,
                    "until": until,
                },
            )
        )
        .mappings()
        .first()
    )
    if r is None or r["close"] is None:
        return None
    close_time = r["open_time"] + _CANDLE
    if close_time < now - timedelta(seconds=max_age_s) or close_time > now:
        return None
    return FinalClose(close=Decimal(str(r["close"])), close_time=close_time)


def parity_ratio(
    *,
    ticket_sol: Decimal,
    sol_usd: Decimal | None,
    out_amount_atoms: int | None,
    decimals: int | None,
    units_per_binance_unit: Decimal,
    bin_usd: Decimal | None,
) -> Parity:
    """``jup_usd ÷ bin_usd`` for the buy quote of the whole ticket; a missing or
    non-positive input is a named reason, never a ratio."""
    if bin_usd is None or bin_usd <= _ZERO:
        return Parity(None, "market_price_unavailable")
    if sol_usd is None or sol_usd <= _ZERO:
        return Parity(None, "sol_usd_unavailable", bin_usd=bin_usd)
    if decimals is None:
        return Parity(None, "decimals_unavailable", bin_usd=bin_usd, sol_usd=sol_usd)
    if out_amount_atoms is None or out_amount_atoms <= 0:
        return Parity(None, "quote_unavailable", bin_usd=bin_usd, sol_usd=sol_usd)
    tokens = Decimal(out_amount_atoms) / (_TEN**decimals)
    jup_usd = ticket_sol * sol_usd / tokens * units_per_binance_unit
    return Parity(jup_usd / bin_usd, None, jup_usd=jup_usd, bin_usd=bin_usd, sol_usd=sol_usd)


def geometry(
    *,
    reference_price: Decimal | None,
    stop: Decimal | None,
    target1: Decimal | None,
    expected_holding_s: int | None,
    max_hold_s: int,
) -> Geometry:
    """The signal's own rule as fractions of its reference (design §4). A
    non-positive fraction is **returned**: the profile names ``geometry_invalid``;
    only a missing number is a reason here."""
    if reference_price is None or reference_price <= _ZERO:
        return Geometry(None, None, None, "reference_unavailable")
    if stop is None or stop <= _ZERO:
        return Geometry(None, None, None, "stop_unavailable")
    if target1 is None or target1 <= _ZERO:
        return Geometry(None, None, None, "target_unavailable")
    horizon = max_hold_s if expected_holding_s is None else min(expected_holding_s, max_hold_s)
    return Geometry(
        stop_frac=(reference_price - stop) / reference_price,
        target_frac=(target1 - reference_price) / reference_price,
        horizon_s=horizon,
    )


def signal_inputs(
    candidate: SpotCandidate,
    *,
    parity: Parity,
    quote_impact_pct: Decimal | None,
    priority_fee_sol: Decimal,
    open_spot_markets: tuple[str, ...],
    pending_spot_markets: tuple[str, ...],
) -> SpotSignalInputs | None:
    """What ``evaluate_spot_entry`` receives; ``None`` when the signal has no
    complete geometry (the caller refuses ``geometry_unavailable``)."""
    ref, stop, target = candidate.reference_price, candidate.stop, candidate.target1
    if ref is None or stop is None or target is None or min(ref, stop, target) <= _ZERO:
        return None
    return SpotSignalInputs(
        signal_id=candidate.signal_id,
        market_symbol=candidate.market_symbol,
        mint=candidate.mint,
        reference_price=ref,
        stop_price=stop,
        target1_price=target,
        emitted_at=candidate.emitted_at,
        expires_at=candidate.expires_at,
        parity_ratio=parity.ratio,
        parity_reason=parity.reason,
        quote_impact_pct=quote_impact_pct,
        priority_fee_sol=priority_fee_sol,
        open_spot_markets=open_spot_markets,
        pending_spot_markets=pending_spot_markets,
    )
