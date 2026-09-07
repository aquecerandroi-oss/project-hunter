"""The USDS-M ``markPrice`` stream frame — mark price, index price and the
estimated funding rate of one perpetual.

Split out of :mod:`.streams` (T3.0b, 350-line budget) on the same line as
:mod:`.normalize_derivatives`: this stream exists only for perpetuals (spot has
no funding and no mark price), while the four parsers left in ``streams`` all
have a spot counterpart that reuses them. ``streams`` re-exports this one, and
keeps it in ``_PARSERS``, exactly as it does ``parse_force_order``.
"""

from __future__ import annotations

from typing import Any

from hunter_core.domain.market import NormalizedFunding
from hunter_core.domain.types import utcnow
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.binance.parse import (
    EXCHANGE,
    ms_to_datetime,
    require_field,
    to_decimal,
    to_decimal_or_none,
)

__all__ = ["parse_mark_price"]


def parse_mark_price(raw: dict[str, Any]) -> NormalizedFunding:
    """``<symbol>@markPrice@1s`` -> :class:`NormalizedFunding` (always
    ``funding_kind="estimated"``); ``metadata`` labels the unmapped ``P``."""
    try:
        next_funding_time = ms_to_datetime(raw["T"], field="T") if raw.get("T") else None
        metadata: dict[str, Any] = {}
        if "P" in raw:
            metadata["estimated_settle_price"] = raw["P"]
        return NormalizedFunding.model_construct(
            exchange=EXCHANGE,
            symbol=require_field(raw, "s"),
            ts=ms_to_datetime(raw["E"], field="E"),
            funding_rate=to_decimal(raw["r"], field="r"),
            next_funding_time=next_funding_time,
            mark_price=to_decimal(raw["p"], field="p"),
            index_price=to_decimal_or_none(raw.get("i"), field="i"),
            funding_kind="estimated",
            metadata=metadata,
            kind="funding",
            received_at=utcnow(),
        )
    except KeyError as exc:
        raise MalformedMessage(
            f"missing field {exc} in markPrice {raw!r}", exchange=EXCHANGE
        ) from exc
