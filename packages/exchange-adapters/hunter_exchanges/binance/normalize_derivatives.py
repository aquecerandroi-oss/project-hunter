"""REST parsers for the USDS-M **derivative** endpoints: ``premiumIndex``,
``fundingRate`` and ``openInterest``.

Split out of :mod:`.normalize` (T3.0b, 350-line budget) along the line the spot
adapter drew: these three endpoints exist only for perpetuals — the spot API
has no funding, no mark price and no open interest — while everything left in
``normalize.py`` (klines, tickers, depth, exchangeInfo) has a byte-compatible
spot counterpart. ``normalize`` re-exports all three, so importers do not move.
"""

from __future__ import annotations

from typing import Any

from hunter_core.domain.market import NormalizedFunding, NormalizedOpenInterest
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.binance.parse import (
    EXCHANGE,
    ms_to_datetime,
    require_field,
    to_decimal,
    to_decimal_or_none,
)

__all__ = ["parse_funding", "parse_open_interest", "parse_realized_funding"]


def parse_funding(premium: dict[str, Any], *, symbol: str) -> NormalizedFunding:
    """``GET /fapi/v1/premiumIndex`` -> the *estimated*, not-yet-settled
    :class:`NormalizedFunding` (``funding_kind="estimated"``, explicit — F1).
    Realized/settled funding comes only from :func:`parse_realized_funding`
    — mixing the two mislabels a stale, settled rate as a fresh estimate.
    """
    try:
        funding_rate = to_decimal(premium["lastFundingRate"], field="lastFundingRate")
        next_funding_time = (
            ms_to_datetime(premium["nextFundingTime"], field="nextFundingTime")
            if premium.get("nextFundingTime")
            else None
        )
        metadata: dict[str, Any] = {}
        for extra in ("estimatedSettlePrice", "interestRate"):
            if extra in premium:
                metadata[extra] = premium[extra]
        return NormalizedFunding(
            exchange=EXCHANGE,
            symbol=symbol,
            ts=ms_to_datetime(premium["time"], field="time"),
            funding_rate=funding_rate,
            next_funding_time=next_funding_time,
            mark_price=to_decimal(premium["markPrice"], field="markPrice"),
            index_price=to_decimal_or_none(premium.get("indexPrice"), field="indexPrice"),
            funding_kind="estimated",
            metadata=metadata,
        )
    except (KeyError, IndexError) as exc:
        raise MalformedMessage(
            f"malformed funding payload {premium!r}: {exc}", exchange=EXCHANGE
        ) from exc


def parse_realized_funding(raw: dict[str, Any]) -> NormalizedFunding:
    """One ``GET /fapi/v1/fundingRate`` row -> settled :class:`NormalizedFunding`.

    ``ts`` is the settlement's own ``fundingTime`` (never ``time.time()`` /
    the request's own clock — Astra review, T1.2 resume finding 4: reusing
    ``premiumIndex``'s ``time`` here would make the same settlement look
    newly timestamped on every repeated fetch). ``mark_price`` is required
    by the domain model; current Binance responses always include it, and a
    row without one is treated as malformed rather than inventing a value
    (CLAUDE.md: "no fake anything").
    """
    try:
        return NormalizedFunding(
            exchange=EXCHANGE,
            symbol=require_field(raw, "symbol"),
            ts=ms_to_datetime(raw["fundingTime"], field="fundingTime"),
            funding_rate=to_decimal(raw["fundingRate"], field="fundingRate"),
            mark_price=to_decimal(require_field(raw, "markPrice"), field="markPrice"),
            funding_kind="realized",
        )
    except KeyError as exc:
        raise MalformedMessage(
            f"missing field {exc} in funding rate history row {raw!r}", exchange=EXCHANGE
        ) from exc


def parse_open_interest(raw: dict[str, Any], *, symbol: str) -> NormalizedOpenInterest:
    """``GET /fapi/v1/openInterest`` -> :class:`NormalizedOpenInterest`."""
    try:
        return NormalizedOpenInterest(
            exchange=EXCHANGE,
            symbol=symbol,
            ts=ms_to_datetime(raw["time"], field="time"),
            open_interest=to_decimal(raw["openInterest"], field="openInterest"),
            open_interest_value=None,
        )
    except KeyError as exc:
        raise MalformedMessage(
            f"missing field {exc} in open interest {raw!r}", exchange=EXCHANGE
        ) from exc
