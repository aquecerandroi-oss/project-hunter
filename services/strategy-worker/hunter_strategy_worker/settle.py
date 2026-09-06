"""Closing the books on a finished tracking: exit price, funding, net R.

SHADOW-LAB.md §3 and §9. Two numbers are produced, not one:

- ``r_multiple`` — the net R **including** funding. It is ``NULL`` whenever
  funding was applicable but could not be established, with the reason in
  ``meta.r_net_reason``;
- ``meta.r_ex_funding`` — the same R with funding excluded. A separate metric
  with its own, wider coverage, never a substitute presented as the real thing.

A zero funding charge is only ever written when the market's own settlement
cadence puts no settlement inside the trade.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_strategy_worker.funding import MATCH_TOLERANCE, resolve_funding
from hunter_strategy_worker.pricing import exit_price, r_net
from hunter_strategy_worker.repo import load_funding

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_strategy_worker.walker import Progress, TrackingPlan

_CADENCE_LOOKBACK = timedelta(days=3)
"""How far before the entry funding history is read, so the market's own
settlement interval can be measured instead of assumed."""

__all__ = ["Settlement", "settle"]


@dataclass(frozen=True, slots=True)
class Settlement:
    """What a finished tracking is worth, and what could not be established."""

    exit_price: Decimal | None
    r_multiple: Decimal | None
    meta: dict[str, Any]


async def settle(
    session: AsyncSession,
    *,
    market_id: uuid.UUID,
    plan: TrackingPlan,
    progress: Progress,
) -> Settlement:
    """Price the exit and compute both R readings for a terminal tracking."""
    if progress.exit_base is None or progress.entry is None or progress.entry_ts is None:
        return Settlement(None, None, {"funding": None, "r_ex_funding": None})
    exit_ts = progress.exit_ts or progress.entry_ts
    price = exit_price(progress.exit_base, plan.costs)
    history = await load_funding(
        session,
        market_id=market_id,
        since=progress.entry_ts - _CADENCE_LOOKBACK,
        # A real row a few ms *after* exit_ts can be the other half of a
        # cluster whose sibling is inside the window — resolve_funding needs
        # to see it to tell "boundary uncertain" from "resolved" (Astra,
        # S2-funding review, round 4 must-fix 1). It is never charged on its
        # own: resolve_funding's own (entry_ts, exit_ts] filter still excludes
        # a cluster with no member inside the window.
        until=exit_ts + MATCH_TOLERANCE,
    )
    # An intrabar exit is only known to be somewhere inside its bar; the close
    # is a conservative *barrier*, not the financial instant. A settlement in
    # that window makes funding unestablishable rather than charged.
    ambiguous_from = None if progress.exit_at_open else progress.exit_bar_open
    reading = resolve_funding(
        history,
        entry_ts=progress.entry_ts,
        exit_ts=exit_ts,
        ambiguous_from=ambiguous_from,
    )
    ex_funding = r_net(
        entry=progress.entry,
        exit_=price,
        stop=plan.stop,
        costs=plan.costs,
        funding_per_unit=Decimal(0),
    )
    r_multiple = (
        None
        if reading.per_unit is None
        else r_net(
            entry=progress.entry,
            exit_=price,
            stop=plan.stop,
            costs=plan.costs,
            funding_per_unit=reading.per_unit,
        )
    )
    return Settlement(
        exit_price=price,
        r_multiple=r_multiple,
        meta={
            "funding": reading.to_jsonable(),
            "r_ex_funding": format(ex_funding, "f"),
            "r_net_reason": reading.reason,
        },
    )
