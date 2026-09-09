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

Since T3.52 eligibility has a **second** term, and it is the version's, not the
market's: the gates of its ``eligibility_policy``
(:mod:`hunter_strategy_worker.gate_policy`) — the regime it is allowed to decide
in (T3.52) and, since T3.59, the hours of the day it is allowed to decide at.
They are applied *after* the market checks and never before them — a market that
is not in the universe is not eligible whatever the regime says, and reporting
the regime as the reason would name the wrong cause.

Between themselves the order is: **hours first, regime second**, and both must
pass. The hours gate reads nothing at all, so refusing there costs no query and
saves the regime gate's; the visible consequence is that a bar failing both
rules is reported as ``hours_gate:HH``.
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
from hunter_strategy_worker.hours_gate import evaluate_hours_gate
from hunter_strategy_worker.record import Provenance
from hunter_strategy_worker.regime_gate import load_gate
from hunter_strategy_worker.repo import load_candles, newest_received_at

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.domain.market import NormalizedCandle
    from hunter_strategy_worker.config import ShadowConfig
    from hunter_strategy_worker.gate_policy import GatePolicy
    from hunter_strategy_worker.hours_gate import HoursGate
    from hunter_strategy_worker.regime_gate import RegimeGate
    from hunter_strategy_worker.repo import MarketRow

    CandleReader = Callable[..., Awaitable[list[NormalizedCandle]]]
    """The signature of :func:`hunter_strategy_worker.repo.load_candles`.

    Injectable for one reason and one only: a replay evaluates thousands of
    consecutive bars of the same market, and consecutive bars share all but a
    handful of the 1560 minutes behind them. Re-reading (and re-validating) that
    window per bar is the dominant cost of a historical run, so the replay
    passes a reader that loaded the slice once and slices it
    (``replay/candles.py``). It must return **exactly** what ``load_candles``
    would — same filter, same order, same objects — and the equivalence is a
    test, not a claim (``test_replay_candle_cache``).
    """

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
    candles_reader: CandleReader | None = None,
    policy: GatePolicy | None = None,
    context_minutes: int | None = None,
) -> tuple[StrategyContext, Provenance]:
    """The context for one market as of ``source_bar_close``, plus its provenance.

    ``policy`` is the deciding version's own ``eligibility_policy`` (already
    parsed by the catalogue, which refuses a version whose policy it cannot
    read). ``None`` — every version before T3.52 — is no gate at all: not one
    extra query is issued and the eligibility answer is byte for byte what it
    was. A policy carrying only the hours rule issues no query either.

    ``context_minutes`` is how much 1m history this evaluation loads, which is a
    property of the *version* since T3.54b and no longer of the process: the
    caller passes ``ActiveVersion.context_minutes(config)``. ``None`` keeps the
    old behaviour exactly — ``config.context_minutes``, the shared floor — for
    the callers that have no version in hand (the derivatives tests).

    Either way the number is recorded in the provenance and reaches the
    envelope: two versions in the same pass now read different windows, so
    "which window did this decision see" stops being answerable only by reading
    the deployment's environment.
    """
    minutes = config.context_minutes if context_minutes is None else context_minutes
    start = source_bar_close - timedelta(minutes=minutes)
    read = candles_reader or load_candles
    durable = await read(session, market=market, start=start, end=source_bar_close)
    tail = await hot_state.read_tail(
        redis,
        exchange=market.exchange,
        symbol=market.symbol,
        count=config.hot_state_tail,
        cut=source_bar_close,
        market_type=market.market_type,
    )
    merged: dict[datetime, NormalizedCandle] = {
        c.open_time: c for c in tail if c.open_time >= start
    }
    merged.update({c.open_time: c for c in durable})
    candles = [merged[key] for key in sorted(merged)]
    eligible, reason = _eligibility(market)
    observed_at = utcnow()
    gate: RegimeGate | None = None
    hours: HoursGate | None = None
    if eligible and policy is not None and policy.hours is not None:
        hours = evaluate_hours_gate(policy.hours, cut=source_bar_close)
        eligible, reason = hours.eligible, (None if hours.eligible else hours.reason)
    if eligible and policy is not None and policy.regime is not None:
        gate = await load_gate(session, policy.regime, cut=source_bar_close)
        eligible, reason = gate.eligible, (None if gate.eligible else gate.reason)
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
        context_minutes=minutes,
        eligibility_observed_at=observed_at,
        producer=PRODUCER,
        code_ref=code_ref,
        funding_ts=deriv.funding_ts,
        funding_source=deriv.funding_source,
        funding_reason=deriv.funding_reason,
        open_interest_ts=deriv.open_interest_ts,
        open_interest_source=deriv.open_interest_source,
        open_interest_reason=deriv.open_interest_reason,
        regime_gate=gate,
        hours_gate=hours,
    )
    return context, provenance
