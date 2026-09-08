"""Step 3 of the bridge cycle: screen the pending signals and order them by D3.

Split out of :mod:`hunter_execution_worker.bridge` along the seam its own
docstring already draws — that module runs the cycle and submits **one**
candidate, this one answers *which* candidate that is. The split follows the
same rule as ``bridge_repo``/``bridge_screen``/``bridge_universe``: one
responsibility per module, so the file that commits capital stays short enough
to read in one sitting (CLAUDE.md's file-size gate).

**D3, in order:** the Radar score of the *perpetual* at the source bar (higher
first, no score last), then the estimated entry cost in R (lower first), then
arrival, then the signal id — the last key is what makes the order **total**, so
two workers ranking the same cycle cannot disagree about who goes first.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_execution_worker import metrics
from hunter_execution_worker.bridge_repo import pending_signals
from hunter_execution_worker.bridge_screen import screen_signal
from hunter_execution_worker.reference import load_market

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_execution_worker.bridge_screen import Screened
    from hunter_execution_worker.market_data import SpotMarketData, SpotSnapshot
    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["Ranked", "count_outcome", "entry_cost_r", "rank_candidates"]

_BPS = Decimal(10_000)
_TWO = Decimal(2)


@dataclass(frozen=True, slots=True)
class Ranked:
    """A candidate with everything the ordering and the submission need."""

    screened: Screened
    market: MarketReference
    snapshot: SpotSnapshot
    cost_r: Decimal | None


def count_outcome(outcome: str) -> None:
    metrics.bridge_candidates_total.labels(outcome=outcome).inc()


def entry_cost_r(screened: Screened, snapshot: SpotSnapshot) -> Decimal | None:
    """D3's second key: what entering costs, measured in R.

    Half the observed spread of the **spot** book (the part the market is telling
    us right now) plus the experiment's own declared slippage and fee hypothesis
    (the part no book can answer without a size), over the distance to the stop.
    ``None`` when the book was not observed — a candidate without a cost sorts
    after the ones with one, exactly like a candidate without a score.
    """
    book = snapshot.book
    entry_ref, stop, costs = screened.entry_ref, screened.stop, screened.assumed_costs
    if book is None or not book.asks or not book.bids or entry_ref is None or stop is None:
        return None
    if costs is None or entry_ref <= stop:
        return None
    mid = (book.bids[0].price + book.asks[0].price) / _TWO
    half_spread = max(Decimal(0), book.asks[0].price - mid)
    hypothesis = entry_ref * (costs.slippage_bps + costs.fee_bps) / _BPS
    return (half_spread + hypothesis) / (entry_ref - stop)


def _priority(item: Ranked) -> tuple[int, Decimal, int, Decimal, datetime, str]:
    """D3, as a total order. Ties are broken by the signal id so two workers
    ranking the same cycle cannot disagree about who goes first."""
    score = item.screened.score
    cost = item.cost_r
    return (
        0 if score is not None else 1,
        -(score if score is not None else Decimal(0)),
        0 if cost is not None else 1,
        cost if cost is not None else Decimal(0),
        item.screened.signal.emitted_at,
        str(item.screened.signal_id),
    )


async def rank_candidates(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    data: SpotMarketData,
    now: datetime,
    refusals: list[str],
    reported: dict[uuid.UUID, str] | None = None,
) -> list[Ranked]:
    """Screen every pending signal and order the survivors by D3.

    ``reported`` is the once-per-(signal, reason) map item 1 asks for, forgotten
    once a signal stops appearing so it cannot grow without bound. ``refusals``
    is the cycle's own list, appended in place — the caller owns the outcome.
    """
    signals = await pending_signals(session, wallet=wallet, now=now)
    if reported is not None:
        current = {signal.signal_id for signal in signals}
        for stale in set(reported) - current:
            del reported[stale]
    ranked: list[Ranked] = []
    for signal in signals:
        screened = await screen_signal(
            session, wallet=wallet, signal=signal, now=now, reported=reported
        )
        if not screened.eligible or screened.spot_market_id is None:
            reason = screened.refused or "spot_pair_unavailable"
            refusals.append(reason)
            if screened.freshly_refused:
                count_outcome(reason)
            continue
        market = await load_market(session, screened.spot_market_id)
        if market is None:  # pragma: no cover - the pair was just read from markets
            refusals.append("spot_market_unknown")
            count_outcome("spot_market_unknown")
            continue
        snapshot = await data.snapshot(market.identity)
        ranked.append(
            Ranked(
                screened=screened,
                market=market,
                snapshot=snapshot,
                cost_r=entry_cost_r(screened, snapshot),
            )
        )
    ranked.sort(key=_priority)
    return ranked
