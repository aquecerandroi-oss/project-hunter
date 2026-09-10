"""One candle read per family, not per version, for one bar — T3.74b, item 2.

Design: ``docs/plans/T3.74b-CONTEXT-CACHE.md`` (approved, Astra's review folded in).
Measured problem: `handle_candle` (`consumer.py`) evaluates every due version of
a family (same ``strategy_key``, different frozen parameters) against the same
market at the same ``bar_close``, and each one re-reads the whole 1m candle
history behind it (`context.build_market_context`) — up to 8 identical-shape
reads for the same market/instant when a family has 8 live versions
(notes-T3.74.md §2c).

Reuses :class:`hunter_strategy_worker.replay.candles.WindowCache` — already
proven byte-identical to :func:`hunter_strategy_worker.repo.load_candles`
(``test_replay_engine.py::TestTheCandleCache``) — for a *different* axis of
reuse: instead of one market across many consecutive bars (the replay), one
market across many versions of the same bar. ``window_start == window_end ==
bar_close`` makes :func:`~hunter_strategy_worker.replay.candles.load_window`
preload exactly ``[bar_close - ceiling, bar_close)``, where ``ceiling`` is the
*widest* ``context_minutes`` any due member of the family needs — the same
number :meth:`hunter_strategy_worker.roster.ActiveVersion.context_minutes`
already derives per version, never a new one.

**What never changes.** Every member still gets exactly the
``context_minutes`` it always got (recorded in its own ``Provenance``, never
the family's); eligibility/hours/regime gates stay per version (they read the
version's own ``eligibility_policy`` inside ``build_market_context``, untouched
here); no strategy code (``packages/core/hunter_core/strategies/``) is read or
imported by this module.

**What does change, on purpose, documented (Astra, design review, must-fix 1).**
The cache is a snapshot as of the moment it is built — the same property
``WindowCache`` already carries for the replay ("a snapshot of the series as
of the run's start ... a property, not a bug"). A backfill landing on an
already-closed minute *during* one ``handle_candle`` call would be seen by a
version that queries the database directly and missed by a version served
from this cache — the window that matters is the lifetime of one bar's
evaluation (sub-second to a few seconds), and the candles in question are
already ``is_final`` history, not the forming minute. Two versions of the same
family evaluating the same bar could already disagree on this in the old,
uncached code if a backfill landed between their two independent reads; this
cache narrows that already-existing race window rather than inventing one.

**Failure isolation (Astra, design review, must-fix 2).** A family whose
pre-load query fails (timeout, connection) is logged and simply gets no
reader — its members fall back to :data:`None`, the exact behaviour of every
bar before this module existed (one query per version). One family's cache
failing never blocks another family, and never keeps the bar from being
acknowledged the way a version-level failure already does not
(`consumer.handle_candle`'s per-version ``try``/``except``).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_strategy_worker.replay.candles import load_window

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_strategy_worker.catalogue import ActiveVersion
    from hunter_strategy_worker.config import ShadowConfig
    from hunter_strategy_worker.context import CandleReader
    from hunter_strategy_worker.repo import MarketRow

logger = get_logger(__name__)

_MIN_SHARED_GROUP = 2
"""A family of one has nothing to share; building a cache to serve only itself
adds an indirection without removing a single read."""

__all__ = ["build_family_readers", "load_family_readers"]


def _group_by_family(versions: list[ActiveVersion]) -> dict[str, list[ActiveVersion]]:
    groups: dict[str, list[ActiveVersion]] = {}
    for version in versions:
        groups.setdefault(version.strategy_key, []).append(version)
    return groups


async def build_family_readers(
    session: AsyncSession,
    versions: list[ActiveVersion],
    *,
    market: MarketRow,
    bar_close: datetime,
    config: ShadowConfig,
) -> dict[str, CandleReader]:
    """One shared :class:`WindowCache` per ``strategy_key`` with 2+ ``versions``
    due this bar, keyed by ``strategy_key`` so ``handle_candle`` can look its
    version up by the same field.

    ``versions`` is the ``due`` list ``handle_candle`` already computed for
    this ``bar_close`` — not the whole roster, so a family with only one member
    due this particular timeframe close correctly gets no cache even if the
    strategy has other, not-due, siblings.
    """
    readers: dict[str, CandleReader] = {}
    for key, members in _group_by_family(versions).items():
        if len(members) < _MIN_SHARED_GROUP:
            continue
        ceiling = max(member.context_minutes(config) for member in members)
        try:
            readers[key] = await load_window(
                session,
                market=market,
                window_start=bar_close,
                window_end=bar_close,
                context_minutes=ceiling,
            )
        except Exception:
            logger.warning(
                "shadow_family_context_cache_failed",
                strategy_key=key,
                members=len(members),
                ceiling=ceiling,
            )
            continue
    return readers


async def load_family_readers(
    factory: async_sessionmaker[AsyncSession],
    versions: list[ActiveVersion],
    *,
    market: MarketRow,
    bar_close: datetime,
    config: ShadowConfig,
) -> dict[str, CandleReader]:
    """:func:`build_family_readers`, with its own session and never raising.

    ``handle_candle`` already holds a session for ``load_market``; a short,
    separate one is opened here so the preload's lifetime is exactly the
    preload's. This is the *outer* isolation layer — a failure to even open a
    session, as opposed to one family's own preload failing (already isolated
    inside :func:`build_family_readers`) — still must not take the bar down.
    A family of fewer than two due members is skipped before any session is
    opened at all.
    """
    if len(versions) < _MIN_SHARED_GROUP:
        return {}
    try:
        async with role_session(factory, db_role="hunter_worker") as session:
            return await build_family_readers(
                session, versions, market=market, bar_close=bar_close, config=config
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        # ``getattr`` with a fallback, not ``market.exchange`` directly: this is
        # already the exception handler, and a log call that itself raises
        # (e.g. a test double standing in for ``MarketRow``) must never replace
        # the original failure with a worse, unhandled one.
        logger.warning(
            "shadow_family_context_cache_unavailable",
            market=f"{getattr(market, 'exchange', '?')}:{getattr(market, 'symbol', '?')}",
            bar_close=bar_close.isoformat(),
        )
        return {}
