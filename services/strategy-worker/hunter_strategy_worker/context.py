"""Building one :class:`~hunter_core.strategies.base.StrategyContext`.

Two sources, one cut. Postgres holds the durable 1m series; Redis holds the
last minutes the persistence batch has not flushed yet. They are merged by
``open_time`` with **Postgres winning**, and then handed to ``build_context``,
which drops anything non-final or closing after ``source_bar_close``. That cut
is the anti-look-ahead guarantee: a candle that arrives later, or the minute
still forming, cannot move a decision (S1, ``strategies/base.py``).

Funding and open interest go through the same cut (:mod:`.derivatives`): until
this module started passing them, ``StrategyContext.funding`` and
``.open_interest`` were always ``None`` even though ``build_context`` already
accepted and filtered both (notes-S2.md, "o que o contexto nunca recebe").
Neither v1 strategy reads them yet, so this does not change what they decide;
it unblocks a funding-gated candidate strategy from the backlog.

Eligibility is read from ``markets.is_monitored`` at that moment and the reading
instant is recorded in the envelope: the universe is overwritten in place by
every refresh, so the current flag is only evidence about *now*. The caller
refuses to evaluate a bar older than ``eligibility_max_lag_s`` for exactly that
reason (Astra, S2 design review, must-fix 4).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.domain.enums import MarketStatus
from hunter_core.domain.types import utcnow
from hunter_core.strategies.base import StrategyContext, build_context
from hunter_strategy_worker import hot_state
from hunter_strategy_worker.config import PRODUCER
from hunter_strategy_worker.derivatives import load_derivatives
from hunter_strategy_worker.record import Provenance
from hunter_strategy_worker.repo import load_candles, newest_received_at

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.domain.market import NormalizedCandle
    from hunter_strategy_worker.config import ShadowConfig
    from hunter_strategy_worker.repo import MarketRow

__all__ = ["build_market_context"]


def _eligibility(market: MarketRow) -> tuple[bool, str | None]:
    if market.status is not MarketStatus.ACTIVE:
        return False, f"market_status:{market.status.value}"
    if not market.is_monitored:
        return False, "not_in_monitored_universe"
    return True, None


async def build_market_context(
    session: AsyncSession,
    redis: redis_asyncio.Redis,
    *,
    market: MarketRow,
    source_bar_close: datetime,
    config: ShadowConfig,
    code_ref: str | None = None,
) -> tuple[StrategyContext, Provenance]:
    """The context for one market as of ``source_bar_close``, plus its provenance."""
    start = source_bar_close - timedelta(minutes=config.context_minutes)
    durable = await load_candles(session, market=market, start=start, end=source_bar_close)
    tail = await hot_state.read_tail(
        redis,
        exchange=market.exchange,
        symbol=market.symbol,
        count=config.hot_state_tail,
        cut=source_bar_close,
    )
    merged: dict[datetime, NormalizedCandle] = {
        c.open_time: c for c in tail if c.open_time >= start
    }
    merged.update({c.open_time: c for c in durable})
    candles = [merged[key] for key in sorted(merged)]
    eligible, reason = _eligibility(market)
    observed_at = utcnow()
    deriv = await load_derivatives(session, redis, market=market, cut=source_bar_close)
    context = build_context(
        candles,
        exchange=market.exchange,
        symbol=market.symbol,
        source_bar_close=source_bar_close,
        funding=deriv.funding,
        open_interest=deriv.open_interest,
        eligible=eligible,
        eligibility_reason=reason,
    )
    provenance = Provenance(
        available_through=newest_received_at(durable),
        newest_bar_open=candles[-1].open_time if candles else None,
        bars_in_context=len(context.candles_1m),
        eligibility_observed_at=observed_at,
        producer=PRODUCER,
        code_ref=code_ref,
        funding_ts=deriv.funding_ts,
        funding_source=deriv.funding_source,
        funding_reason=deriv.funding_reason,
        open_interest_ts=deriv.open_interest_ts,
        open_interest_source=deriv.open_interest_source,
        open_interest_reason=deriv.open_interest_reason,
    )
    return context, provenance
