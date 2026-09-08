"""Gap lifecycle additions for T3.7d — kept apart from ``recovery_queries.py``
for the same 350-line budget that module's own docstring already lives under.

Three pieces, all from the same incident (`.claude/state/notes-T3.7b-diag.md`,
2026-09-08): BTCUSDT and UNIUSDT sat at ``attempts=0`` for 8h30 while
`MARSCOINUSDT` — listed mid-request, with four pre-listing windows the
exchange can never fill — monopolized every one of the shard's six per-cycle
history slots, reopened every hour, forever.

1. :func:`earliest` — the cheapest signal for "this window is entirely before
   the market's listing" (T3.7d item 1), used by
   :func:`hunter_market_worker.recovery_drain.recover_registered`.
2. :func:`history_candidates` — the history tier's fair share, one
   round-robin slot per market instead of a single global ``gap_end DESC``
   (T3.7d item 2), used by ``recovery_queries.pending_gaps``.
3. :func:`reopen_stale_failed` — a `failed` gap earns only
   :data:`MAX_REOPEN_ATTEMPTS` more lives, with doubling backoff, before it
   becomes ``unrecoverable`` (``reason=exhausted``) instead of reopening
   forever (T3.7d item 3).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.domain.enums import Timeframe
from hunter_core.logging import get_logger
from hunter_market_worker import backfill_priority as priority

logger = get_logger(__name__)

MAX_REOPEN_ATTEMPTS = 3
"""A `failed` gap earns this many more lives before the retry loop must stop
admitting it silently. Backoff between reopens doubles each life
(``FAILED_RETRY_AFTER_S * 2 ** (life_count - 1)``); past the cap the gap
becomes ``unrecoverable`` (``reason=exhausted``) instead of reopening again —
the exact failure mode the incident exposed: a gap that could never actually
succeed was reopened every hour, forever, with nothing ever saying so."""


async def earliest(session: Any, market_ids: list[Any]) -> dict[Any, datetime | None]:
    """The first final candle ever persisted, per market — mirrors
    ``recovery_queries.watermarks`` (last candle) with ``min`` instead of
    ``max``.

    This is the cheapest reliable "before this market's listing" signal
    available without a REST probe or an ``onboardDate``/schema change (that
    field is not parsed by any adapter today and ``markets`` has no column for
    it — either is a schema change, out of this task's scope). A market's live
    collection starts persisting candles within one detection cycle of its
    listing, so by the time a *historical* gap for it has ever been attempted
    even once, this column already anchors the true start — exactly what the
    incident's own evidence shows: `MARSCOINUSDT`'s earliest persisted candle
    (2026-09-01 09:45Z) was its real listing minute, hours before its four
    pre-listing gaps were even planned. Costs zero REST weight and reuses data
    already being collected for an unrelated reason. `None` only for a market
    with no live candle yet — then ``recover_registered`` cannot use this
    signal, and the ordinary ``attempts``/``failed``/``exhausted`` path below
    is the backstop that still bounds the retry loop.
    """
    result: dict[Any, datetime | None] = dict.fromkeys(market_ids)
    if not market_ids:
        return result
    rows = (
        await session.execute(
            select(Candle.market_id, func.min(Candle.open_time))
            .where(
                Candle.market_id.in_(market_ids),
                Candle.timeframe == Timeframe.M1,
                Candle.is_final.is_(True),
            )
            .group_by(Candle.market_id)
        )
    ).all()
    result.update({row[0]: row[1] for row in rows})
    return result


async def history_candidates(
    session: Any, market_ids: list[Any], live_from: datetime, limit: int
) -> list[tuple[Any, Any]]:
    """The history tier's fair share: one round-robin slot per market instead
    of a single global ``ORDER BY gap_end DESC LIMIT`` (the exact query shape
    that let `MARSCOINUSDT` win every slot in the incident).

    A window function fetches at most ``limit`` rows **per market** — a single
    market can never need more than the whole shared budget, so capping its
    own candidate set there loses nothing, and it bounds the round trip to at
    most ``len(market_ids) * limit`` rows regardless of how large one market's
    backlog is. :func:`hunter_market_worker.backfill_priority.interleave` then
    picks the final ``limit`` rows one-per-market per round.
    """
    if not market_ids or limit <= 0:
        return []
    ranked = (
        select(
            IngestionGap.id,
            IngestionGap.market_id,
            func.row_number()
            .over(partition_by=IngestionGap.market_id, order_by=IngestionGap.gap_end.desc())
            .label("rn"),
        )
        .where(
            IngestionGap.market_id.in_(market_ids),
            IngestionGap.status == "open",
            IngestionGap.gap_end < live_from,
        )
        .subquery()
    )
    rows = (
        await session.execute(
            select(ranked.c.id, ranked.c.market_id)
            .where(ranked.c.rn <= limit)
            .order_by(ranked.c.market_id, ranked.c.rn)
        )
    ).all()
    grouped: dict[Any, list[tuple[Any, Any]]] = {}
    for gap_id, market_id in rows:
        grouped.setdefault(market_id, []).append((gap_id, market_id))
    return priority.interleave(grouped, limit)


def reopen_stale_failed(
    gaps_by_market: dict[Any, list[IngestionGap]],
    now: datetime,
    max_reopen_per_cycle: int,
    *,
    retry_after_s: float,
    max_attempts: int,
    max_reopens: int | None = None,
) -> tuple[int, list[IngestionGap]]:
    """A `failed` gap gets one more try after a cooldown that doubles with
    every life, capped at ``max_reopens`` lives — past that the gap becomes
    ``unrecoverable`` (``reason=exhausted``) instead, visibly (the caller logs
    it and writes a ``system_events`` row) rather than silently.

    **``attempts`` is never reset across a reopen.** Before this task a reopen
    zeroed it, which is exactly why the incident's 148 impossible rows showed
    ``attempts=0`` — indistinguishable from a gap nobody had ever touched.
    ``life_count = gap.attempts // max_attempts`` is therefore both "how many
    lives this gap has already exhausted" and the true, honest total of every
    fetch it has ever spent — an operator reading the row sees the real
    number instead of one that keeps resetting to zero.

    Bounded per cycle by ``max_reopen_per_cycle``, exactly as before: this
    cannot flood the recovery loop with a whole backlog reopening in one pass.

    ``max_reopens`` defaults to ``None`` and is resolved to
    :data:`MAX_REOPEN_ATTEMPTS` **here**, not bound as a default at import
    time (the same reason ``recovery.history_deadline`` reads its module
    constants inside the function body): a test that monkeypatches the module
    attribute must actually change this function's behaviour.
    """
    if max_reopens is None:
        max_reopens = MAX_REOPEN_ATTEMPTS
    reopened = 0
    exhausted: list[IngestionGap] = []
    for gaps in gaps_by_market.values():
        for gap in gaps:
            if gap.status != "failed":
                continue
            if reopened + len(exhausted) >= max_reopen_per_cycle:
                return reopened, exhausted
            life_count = max(1, gap.attempts // max_attempts)
            if life_count > max_reopens:
                gap.status = "unrecoverable"
                exhausted.append(gap)
                logger.warning(
                    "market_gap_unrecoverable",
                    reason="exhausted",
                    market_id=gap.market_id,
                    gap_start=gap.gap_start,
                    gap_end=gap.gap_end,
                    attempts=gap.attempts,
                    lives=life_count,
                )
                continue
            backoff = timedelta(seconds=retry_after_s * (2 ** (life_count - 1)))
            if gap.detected_at <= now - backoff:
                gap.status = "open"
                reopened += 1
                logger.info(
                    "market_gap_reopened",
                    market_id=gap.market_id,
                    gap_start=gap.gap_start,
                    gap_end=gap.gap_end,
                    life=life_count + 1,
                )
    return reopened, exhausted
