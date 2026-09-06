"""Building one ``MarketContext`` from the hot state, with the coverage proof.

``hunter_indicators.features.hotstate.load_context`` does almost all of this
already; what it cannot do is fill ``SourceEntry.covered_until``, because only
the collector knows whether it stayed connected (notes-T2.2 section 13). So the
scanner decodes the four keys itself, stamps the trades entry with the interval
the market-worker published, and hands the parts to the public
``build_context``. No formula changes and no fork of the loader: the decoders
are the same ones, imported.

**The cut is the proof, not the clock.** ``trades_between`` needs
``covered_until >= as_of``, and a proof is always slightly behind the clock, so
evaluating at ``utcnow()`` would make every trade window unprovable forever.
The evaluation therefore happens at ``as_of = covered_until`` whenever a live
proof exists -- "the market as it was observable at ``as_of``" is what the type
means -- and falls back to the clock when there is none, in which case the trade
features come out ``insufficient_coverage``, which is the honest answer.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_indicators.features import (
    DerivObservation,
    MarketContext,
    build_context,
    read_hot_state,
)
from hunter_indicators.features.context import (
    INPUT_DERIV_HISTORY,
    SourceEntry,
    missing,
)
from hunter_indicators.features.hotstate import (
    decode_book,
    decode_candles,
    decode_deriv,
    decode_trades,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    import redis.asyncio as redis_asyncio

    from hunter_scanner_worker.coverage import TapeCoverage

logger = get_logger(__name__)

MAX_CUT_LAG_S = 5.0
"""How far behind the clock the cut may fall before the proof is ignored.

A collector that stopped stamping must not drag the whole evaluation into the
past: past this budget the scanner evaluates at ``utcnow()`` and every trade
window says ``insufficient_coverage`` -- late and honest beats current and
made up.
"""

__all__ = ["ContextBuild", "MAX_CUT_LAG_S", "build_market_context", "evaluation_cut"]


@dataclass(frozen=True, slots=True)
class ContextBuild:
    """One context and the two facts about it a caller has to report."""

    context: MarketContext
    covered: bool
    """Whether the trade tape carries a live coverage proof for this market."""

    lagged_s: float
    """How far the cut is behind the clock, in seconds."""


def evaluation_cut(
    coverage: TapeCoverage,
    symbol: str,
    *,
    now: datetime | None = None,
    max_lag_s: float = MAX_CUT_LAG_S,
) -> tuple[datetime, datetime | None, datetime | None]:
    """``(as_of, covers_from, covered_until)`` for one market."""
    moment = now or utcnow()
    covers_from, covered_until = coverage.for_symbol(symbol)
    if covered_until is None or covers_from is None:
        return (moment, None, None)
    if moment - covered_until > timedelta(seconds=max_lag_s):
        # The proof is too old to move the cut onto it; keep the clock and let
        # the windows refuse themselves.
        return (moment, None, None)
    return (covered_until, covers_from, covered_until)


async def build_market_context(
    redis: redis_asyncio.Redis,
    *,
    exchange: str,
    symbol: str,
    coverage: TapeCoverage,
    deriv_history: Sequence[DerivObservation] = (),
    now: datetime | None = None,
    btc: MarketContext | None = None,
) -> ContextBuild:
    """Read the four hot-state keys of one market and cut them coherently."""
    moment = now or utcnow()
    as_of, covers_from, covered_until = evaluation_cut(coverage, symbol, now=moment)
    raw = await read_hot_state(redis, exchange, symbol)
    candles = decode_candles(raw.candles, raw.candles_limit)
    trades = decode_trades(raw.trades, as_of, raw.trades_limit)
    if covered_until is not None and covers_from is not None:
        # What the *session* proves and what the *tape* can show are two
        # different floors, and which one binds depends on truncation:
        #
        # - not truncated: the list holds every trade since the session began,
        #   so the absence of older ones means there were none. The session
        #   start is the honest ``covers_from`` -- and it is the only thing that
        #   lets a quiet minute produce a real zero instead of a refusal;
        # - truncated: the ring buffer dropped the beginning, so the oldest
        #   trade still present is the floor, however long the session ran
        #   (Astra, T2.5 design review: coverage may not outrun what was
        #   retained).
        proven_from = covers_from
        oldest = trades.covers_from
        if trades.truncated and oldest is not None:
            proven_from = max(covers_from, oldest)
        trades = dataclasses.replace(trades, covers_from=proven_from, covered_until=covered_until)
    context = build_context(
        exchange=exchange,
        symbol=symbol,
        as_of=as_of,
        candles=candles.value or (),
        candles_truncated=candles.truncated,
        book=decode_book(raw.book, as_of),
        trades=trades,
        deriv=decode_deriv(raw.deriv, as_of),
        deriv_history=_history_entry(deriv_history, as_of),
        btc=btc,
    )
    return ContextBuild(
        context=context,
        covered=covered_until is not None,
        lagged_s=max(0.0, (moment - as_of).total_seconds()),
    )


def _history_entry(
    observations: Sequence[DerivObservation], as_of: datetime
) -> SourceEntry[tuple[DerivObservation, ...]]:
    """The ``deriv_history`` source entry, cut at ``as_of``."""
    kept = tuple(sorted((o for o in observations if o.ts <= as_of), key=lambda o: o.ts))
    if not kept:
        return missing(INPUT_DERIV_HISTORY)
    return SourceEntry(value=kept, ts=kept[-1].ts, covers_from=kept[0].ts)
