"""``<symbol>@forceOrder`` parsing (Binance USDS-M liquidations).

Split out of ``streams.py`` for the 350-line budget; ``streams`` re-exports
:func:`parse_force_order` so callers keep one import. Semantics decided in
``.claude/state/notes-liquidations.md`` (KB-0017).
"""

from __future__ import annotations

from typing import Any

from hunter_core.domain.enums import OrderSide
from hunter_core.domain.market import NormalizedLiquidation
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.binance.normalize import (
    EXCHANGE,
    ms_to_datetime,
    require_field,
    to_decimal,
    to_decimal_or_none,
)


def parse_force_order(raw: dict[str, Any]) -> NormalizedLiquidation:
    """``<symbol>@forceOrder`` -> :class:`NormalizedLiquidation`.

    KB-0017 / ``.claude/state/notes-liquidations.md``: ``o.q`` is the
    liquidation order's *original* quantity, not what actually traded.
    ``qty`` must be the **executed accumulated quantity** (``o.z``) so it
    never overstates forced flow when the order doesn't fill in full:

    - ``o.X == "FILLED"``: ``o.z`` already equals ``o.q`` — same value, no
      special case needed.
    - partial fill: ``o.z`` is the executed slice; ``o.q`` would overstate it.
    - nothing executed yet (``o.z == "0"``, status not ``FILLED``): ``qty``
      comes out an explicit ``0`` — never falls back to ``o.q``, because an
      order that hasn't traded isn't forced flow yet.

    ``price`` prefers the average fill price (``o.ap``) — it can differ from
    the order price ``o.p`` even on a full fill — and only falls back to
    ``o.p`` when ``o.ap`` is absent or ``"0"`` (nothing to average yet).

    ``notional`` is set explicitly (its model_validator default skips
    ``model_construct``).
    """
    try:
        order = require_field(raw, "o")
        side_raw = order["S"]
        side = OrderSide.SELL if side_raw == "SELL" else OrderSide.BUY
        qty = to_decimal(order["z"], field="o.z")
        avg_price = to_decimal_or_none(order.get("ap"), field="o.ap")
        price = (
            avg_price
            if avg_price is not None and avg_price != 0
            else to_decimal(order["p"], field="o.p")
        )
        return NormalizedLiquidation.model_construct(
            exchange=EXCHANGE,
            symbol=require_field(order, "s"),
            ts=ms_to_datetime(order["T"], field="o.T"),
            side=side,
            qty=qty,
            price=price,
            notional=qty * price,
        )
    except KeyError as exc:
        raise MalformedMessage(
            f"missing field {exc} in forceOrder {raw!r}", exchange=EXCHANGE
        ) from exc
