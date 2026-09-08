"""Whether the SPOT picture is complete enough for an entry to be attempted.

Split out of :mod:`hunter_execution_worker.entry` along the line the cycle
already draws: this module answers *is the input ready*, ``entry`` answers *what
to do about it*. The same answer serves both branches — deferring a live
proposal and naming, on the expiry of a dead one, the input that never arrived
(review of ``7ecafd2``, item 1 and suggestion 7).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_core.domain.enums import OrderSide
from hunter_core.execution.pricing import eligible_for
from hunter_execution_worker.avg_price import AVG_PRICE_MAX_AGE_S

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_core.execution.pricing import ExecutionPolicy
    from hunter_execution_worker.market_data import SpotSnapshot
    from hunter_execution_worker.reference import MarketReference

__all__ = ["missing_inputs", "needs_average", "stale_average"]


def missing_inputs(
    snapshot: SpotSnapshot,
    market: MarketReference,
    *,
    policy: ExecutionPolicy,
    decision_at: datetime,
    now: datetime,
) -> str:
    """Why this snapshot cannot be attempted against — or an empty string.

    **An entry is attempted only against an *eligible* book**, and the reason is
    the whole point of the "one attempt is terminal" rule: the attempt is spent
    on what the market answered, never on what we had not observed yet. The
    30-minute proof of 2026-09-07 caught this — a decision taken at 06:48:23,857
    met a book received at 06:48:22 (the snapshot before it), and
    ``book_before_latency`` burned the decision on a snapshot that was simply not
    the one the contract names. A snapshot that is too old, too new, empty or
    corrupt is the same class of fact: the input is not ready, so nothing is
    written and nothing is spent, and if it never becomes ready the 30 s
    reservation expires and is released with its reason.
    """
    if "hot_state_unreachable" in snapshot.unavailable:
        # "Unread" is not "empty" (V6 step 4). Both defer, but only one of them
        # is an infrastructure incident, and an operator reading
        # ``entry_deferred reason=no_book`` for a Redis outage would go looking
        # at the exchange feed instead of at Redis.
        return "hot_state_unreachable"
    if snapshot.book is None:
        return "no_book"
    if snapshot.last_trade is None:
        return "no_trade"
    verdict = eligible_for(
        policy,
        snapshot.book,
        decision_at=decision_at,
        now=now,
        side=OrderSide.BUY,
        market=(market.identity.exchange, market.identity.symbol),
    )
    if not verdict.eligible:
        return verdict.reason
    if needs_average(market):
        return stale_average(snapshot, now=now)
    return ""


def stale_average(snapshot: SpotSnapshot, *, now: datetime) -> str:
    """Why this snapshot's ``NOTIONAL`` reference cannot judge the filter.

    The ``NOTIONAL`` filter of a MARKET order is judged against the exchange's
    ``avgPrice`` over ``avgPriceMins`` minutes, and never against the last trade
    — which moves with the very book under suspicion (T3.0a §5). Without it the
    order cannot be judged, so it is not attempted: the reservation expires and
    is released with its reason, and no absence ever produces a fill.

    **The age is measured here, against the cycle's own ``now``.** The reader
    already refuses a quote past its bound on its own clock
    (:mod:`hunter_execution_worker.avg_price`); this second measurement is the
    one the *decision* can be held to, and it is the one that catches a snapshot
    assembled before a stall and used after it. A reference with a price and no
    stamp is not a reference at all (§7, R-OPS-2) — ``avg_price_undated`` — and a
    stamp in the future is refused exactly like an expired one.
    """
    if snapshot.avg_price is None:
        return f"avg_price_{snapshot.avg_price_source}"
    if snapshot.avg_price_ts is None:
        return "avg_price_undated"
    age = (now - snapshot.avg_price_ts).total_seconds()
    if age < 0 or age > AVG_PRICE_MAX_AGE_S:
        return "avg_price_stale"
    return ""


def needs_average(market: MarketReference) -> bool:
    """Does this market's ``NOTIONAL`` filter actually need an ``avgPrice``?

    ``avgPriceMins == 0`` is Binance's own "use the last price" case, and a
    market that declares no notional floor for MARKET orders needs no reference
    at all. Deferring those would be refusing an order the exchange would take.
    """
    filters = market.filters
    applies = (filters.min_notional is not None and filters.apply_min_to_market) or (
        filters.max_notional is not None and filters.apply_max_to_market
    )
    return applies and filters.avg_price_mins != 0
