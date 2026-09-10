"""One read, one validated context per (market, bar) — T3.74g.

**The measured problem.** T3.74f split the universe across four processes and a
15-minute boundary still took 37-43 s to drain: the cost is proportional to the
number of ``(market, version)`` evaluations a shard owns (~50 markets x ~10 live
versions ~ 500 per boundary), so the wall is the cost of *one* evaluation, not
the number of processes. Profiled locally (``.claude/state/notes-T3.74g.md``
§1), one evaluation paid, on top of the strategy's own arithmetic:

- a full ``StrategyContext`` construction — and pydantic re-runs every nested
  ``NormalizedCandle``'s model validator, so a 3165-minute window costs 3165
  re-validations *per version*: 59 % of the whole CPU profile of a boundary,
  for candles that were validated once when they were read;
- its own ``load_candles`` round trip (or its family's, since T3.74b), its own
  ``hot_state.read_tail``, its own ``load_derivatives`` (two queries plus a
  Redis read) and its own ``role_session`` — with ten due versions that is ten
  sessions and ~30 round trips per market per bar where one of each would do.

**What this module does, and what it deliberately does not.** It reads the
widest window any due version needs **once** per ``(market, bar)``, builds the
``StrategyContext`` for that ceiling **once** — through the real
:func:`hunter_core.strategies.base.build_context`, so the anti-look-ahead filter
and the strict invariants are enforced exactly as before — and then serves each
version a *view*: its own window, obtained by slicing the validated tuple, and
its own eligibility, applied with ``model_copy`` (which pydantic documents as
not re-validating). Nothing in ``packages/core/hunter_core/strategies/`` is
read, imported or changed, so every live version's ``code_ref`` digest is
untouched; the strategies still receive raw 1m candles and still compute their
own windows.

**Why slicing is not an approximation.** ``build_context`` keeps the final
candles closing at or before the cut, sorted by ``open_time``. A version's
window is ``[cut - context_minutes, cut)`` — a *suffix* of the ceiling's window,
because both end at the same cut. A suffix of a sorted, filtered, strictly
increasing series is the same series the shorter query would have produced: same
filter, same order, the same objects. That is the same argument
:class:`hunter_strategy_worker.replay.candles.WindowCache` has always made for
the replay, applied to the context instead of to the rows, and it is a test
(``test_bar_context.py``), not a claim: every view must compare ``==`` to the
context built the old way.

**The property this shares with T3.74b, stated plainly.** The bundle is a
snapshot of the instant it was built. Ten versions of one bar now see the same
funding/open-interest observation and the same candles, where before each read
its own a few milliseconds apart; a backfill or a funding settlement landing
*during* one bar's evaluation used to be visible to some versions and not
others. This narrows a race that already existed — it never invents one — and it
is the same trade-off ``context_cache.py`` documented for candles.

**Failure isolation.** A bundle that cannot be built is ``None``, and the caller
falls back to the pre-T3.74g path (per-family readers, per-version reads)
unchanged. A bar is never lost because a preload failed.
"""

from __future__ import annotations

import asyncio
from bisect import bisect_left
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_core.strategies.base import build_context
from hunter_strategy_worker import hot_state
from hunter_strategy_worker.derivatives import load_derivatives
from hunter_strategy_worker.repo import load_candles

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.domain.market import NormalizedCandle
    from hunter_core.strategies.base import StrategyContext
    from hunter_strategy_worker.catalogue import ActiveVersion
    from hunter_strategy_worker.config import ShadowConfig
    from hunter_strategy_worker.derivatives import DerivativesObservation
    from hunter_strategy_worker.repo import MarketRow

logger = get_logger(__name__)

__all__ = ["BarBundle", "BarView", "build_bar_bundle", "load_bar_bundle"]


@dataclass(frozen=True, slots=True)
class BarView:
    """One version's share of a bundle: exactly what its own reads produced."""

    context: StrategyContext
    """This version's window, with the bundle's neutral eligibility. The gates
    are read *after* the candles in ``build_market_context`` and always per
    version, so the answer they produce is stamped on afterwards by
    :meth:`with_eligibility` instead of being guessed here."""
    durable: tuple[NormalizedCandle, ...]
    """The **durable** rows of this version's window, in ``load_candles`` order.
    Kept apart from the merged series because ``Provenance.available_through`` is
    ``newest_received_at(durable)`` — the hot-state tail carries a decode time,
    not a persistence time, and mixing them would change a recorded number."""
    newest_bar_open: datetime | None
    """``open_time`` of the last merged candle, which is what the provenance
    records — the merged series, not the filtered context (they coincide today;
    recording the same one keeps that an observation and not an assumption)."""
    deriv: DerivativesObservation
    """Funding and open interest as of the bar, read once for every version —
    the same object the bundle's own context was built with, so the observation
    the provenance names and the one the strategy saw can never disagree."""

    def with_eligibility(
        self, *, eligible: bool, eligibility_reason: str | None
    ) -> StrategyContext:
        """The same context carrying this version's own eligibility verdict."""
        update: dict[str, object] = {}
        if eligible is not self.context.eligible:
            update["eligible"] = eligible
        if eligibility_reason != self.context.eligibility_reason:
            update["eligibility_reason"] = eligibility_reason
        return self.context if not update else self.context.model_copy(update=update)


class BarBundle:
    """Everything the due versions of one ``(market, bar)`` read, read once."""

    __slots__ = (
        "_base",
        "_context_opens",
        "_durable",
        "_durable_opens",
        "_merged",
        "_merged_opens",
        "bar_close",
        "ceiling_minutes",
        "deriv",
        "market_id",
    )

    def __init__(
        self,
        *,
        market_id: uuid.UUID,
        bar_close: datetime,
        ceiling_minutes: int,
        durable: list[NormalizedCandle],
        merged: list[NormalizedCandle],
        base: StrategyContext,
        deriv: DerivativesObservation,
    ) -> None:
        self.market_id = market_id
        self.bar_close = bar_close
        self.ceiling_minutes = ceiling_minutes
        self.deriv = deriv
        self._durable = tuple(durable)
        self._durable_opens = [candle.open_time for candle in durable]
        self._merged = tuple(merged)
        self._merged_opens = [candle.open_time for candle in merged]
        self._base = base
        self._context_opens = [candle.open_time for candle in base.candles_1m]

    def covers(self, market: MarketRow, bar_close: datetime, minutes: int) -> bool:
        """Whether this bundle can answer for ``minutes`` of that market's bar.

        A window wider than the ceiling, another market or another bar is
        **refused**, never served short: the caller falls back to its own reads,
        exactly as it did before this module existed.
        """
        return (
            market.id == self.market_id
            and bar_close == self.bar_close
            and minutes <= self.ceiling_minutes
        )

    def view(self, minutes: int) -> BarView:
        """This version's window, without re-reading it or re-validating it."""
        start = self.bar_close - timedelta(minutes=minutes)
        durable = self._durable[bisect_left(self._durable_opens, start) :]
        merged = self._merged[bisect_left(self._merged_opens, start) :]
        candles = self._base.candles_1m[bisect_left(self._context_opens, start) :]
        # ``model_copy`` does not re-validate (pydantic v2), which is the whole
        # point: the candles it is handed are the *same objects* the strict
        # constructor already accepted above, in the same order, and a suffix of
        # a series that satisfied the invariants satisfies them too. Equality
        # with a freshly built context is asserted in ``test_bar_context.py``.
        context = (
            self._base
            if len(candles) == len(self._base.candles_1m)
            else self._base.model_copy(update={"candles_1m": candles})
        )
        return BarView(
            context=context,
            durable=durable,
            newest_bar_open=merged[-1].open_time if merged else None,
            deriv=self.deriv,
        )


def ceiling_minutes(versions: list[ActiveVersion], config: ShadowConfig) -> int:
    """The widest window any due version needs — the only one actually read."""
    return max(version.context_minutes(config) for version in versions)


async def build_bar_bundle(
    session: AsyncSession,
    redis: redis_asyncio.Redis,
    versions: list[ActiveVersion],
    *,
    market: MarketRow,
    bar_close: datetime,
    config: ShadowConfig,
) -> BarBundle:
    """Read the ceiling window, the tail and the derivatives once, and validate once.

    The merge is byte for byte the one :func:`~hunter_strategy_worker.context.
    build_market_context` performs per version — durable and hot-state rows keyed
    by ``open_time`` with **Postgres winning** — so a view of it is the list that
    version would have merged for itself.
    """
    minutes = ceiling_minutes(versions, config)
    start = bar_close - timedelta(minutes=minutes)
    durable = await load_candles(session, market=market, start=start, end=bar_close)
    tail = await hot_state.read_tail(
        redis,
        exchange=market.exchange,
        symbol=market.symbol,
        count=config.hot_state_tail,
        cut=bar_close,
        market_type=market.market_type,
    )
    merged_by_open = {c.open_time: c for c in tail if c.open_time >= start}
    merged_by_open.update({c.open_time: c for c in durable})
    merged = [merged_by_open[key] for key in sorted(merged_by_open)]
    deriv = await load_derivatives(session, redis, market=market, cut=bar_close)
    base = build_context(
        merged,
        exchange=market.exchange,
        symbol=market.symbol,
        source_bar_close=bar_close,
        funding=deriv.funding,
        open_interest=deriv.open_interest,
    )
    return BarBundle(
        market_id=market.id,
        bar_close=bar_close,
        ceiling_minutes=minutes,
        durable=durable,
        merged=merged,
        base=base,
        deriv=deriv,
    )


async def load_bar_bundle(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    versions: list[ActiveVersion],
    *,
    market: MarketRow,
    bar_close: datetime,
    config: ShadowConfig,
) -> BarBundle | None:
    """:func:`build_bar_bundle` with its own short session, and never raising.

    ``None`` means "read it the old way": the caller keeps the T3.74b family
    readers and every version does its own reads, which is the behaviour of every
    bar before this module existed. A bar is never dropped because a preload
    failed, and one market's failure never touches another's.
    """
    if not versions:
        return None
    try:
        async with role_session(factory, db_role="hunter_worker") as session:
            return await build_bar_bundle(
                session, redis, versions, market=market, bar_close=bar_close, config=config
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning(
            "shadow_bar_bundle_unavailable",
            market=f"{getattr(market, 'exchange', '?')}:{getattr(market, 'symbol', '?')}",
            bar_close=bar_close.isoformat(),
        )
        return None
