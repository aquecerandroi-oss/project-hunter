"""Does the collector know about this missing minute, and is it still trying?

Censorship used to be a stopwatch: a needed 1m bar absent for ``censor_after_s``
became ``censored`` whatever the reason. The S2 operational proof recovered 786
gaps in about ten minutes; a worse window — a longer outage, a slower exchange —
would have censored follow-ups the recovery was about to fill, and the loss
would correlate with collector instability. That is the worst possible bias for
a research log: the trades that get dropped are exactly the ones taken in the
conditions that matter (risk-engine-guardian, S2 review, MUST-FIX 2).

``ingestion_gaps`` is the market-worker's own record of what it is doing
(``services/market-worker/hunter_market_worker/recovery.py``), so this module
asks it instead of guessing:

- ``open`` covering the minute — the collector registered the hole and is
  retrying it. Wait, unless the row itself has gone stale (below);
- ``failed`` covering the minute — it asked ``MAX_ATTEMPTS`` times and did not
  get the candle. That is **not** abandonment: ``_reopen_stale_failed`` puts the
  row back to ``open`` after ``FAILED_RETRY_AFTER_S`` (3600 s) with the attempts
  reset, so censoring on sight would drop outcomes over five transient errors
  (Astra, S2 fixes diff review, HIGH c). ``failed`` is a *cooldown*: censor only
  once the ordinary budget is spent, which at 7200 s covers a full reopen and
  retry round;
- nothing covering the minute — nobody registered the hole, so nobody is going
  to fill it. Censor once the ordinary budget is spent;
- ``recovered`` and the candle still absent — the backfill ran and the exchange
  had nothing for that minute (Binance omits empty minutes). Treated as *not
  covered*: the budget applies and the outcome is censored, never invented.

The stale ``open`` branch is the bound the literal rule lacks. An ``open`` row
only becomes ``failed`` because the recovery loop moves it, so a market-worker
that is simply *not running* would leave the tracking — and the
``tracking_hold`` behind it — open forever, which is precisely what
``notes-S2.md`` §6 refused.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from hunter_core.db.models.market_data import IngestionGap
from hunter_core.domain.enums import Timeframe

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_strategy_worker.config import ShadowConfig

OPEN = "open"
FAILED = "failed"
_CONSIDERED = (OPEN, FAILED)

__all__ = ["CoveringGap", "censor_reason", "covering_gap"]


@dataclass(frozen=True, slots=True)
class CoveringGap:
    """The ``ingestion_gaps`` row that speaks for one missing minute."""

    status: str
    detected_at: datetime


async def covering_gap(
    session: AsyncSession, *, market_id: uuid.UUID, minute: datetime
) -> CoveringGap | None:
    """The gap row covering ``minute``, preferring an ``open`` one.

    ``open`` wins over ``failed`` when both cover the minute: a reopened gap
    (``_reopen_stale_failed``) is the collector saying it will try again, and
    the newest word is the one that counts.
    """
    rows = (
        await session.execute(
            select(IngestionGap.status, IngestionGap.detected_at).where(
                IngestionGap.market_id == market_id,
                IngestionGap.timeframe == Timeframe.M1,
                IngestionGap.gap_start <= minute,
                IngestionGap.gap_end >= minute,
                IngestionGap.status.in_(_CONSIDERED),
            )
        )
    ).all()
    if not rows:
        return None
    ordered = sorted(rows, key=lambda r: (r.status != OPEN, -r.detected_at.timestamp()))
    chosen = ordered[0]
    return CoveringGap(status=chosen.status, detected_at=chosen.detected_at)


def censor_reason(
    gap: CoveringGap | None,
    *,
    waited_s: float,
    gap_age_s: float | None,
    config: ShadowConfig,
) -> str | None:
    """Why this minute should be censored now, or ``None`` to keep waiting.

    Pure, so the three branches are testable without a database. The suffix is
    part of the censored reason on purpose: S3 has to count ``failed``,
    ``unregistered`` and ``stalled`` as three different populations
    (``notes-S2.md`` §14).

    ``waited_s`` is measured from ``meta.gap_wait.since`` — when *this* missing
    minute was first noticed, durable across restarts — and ``gap_age_s`` from
    the gap row's ``detected_at``, which recovery never refreshes, so it means
    "registered this long ago and still not filled", retries included.
    """
    if gap is None:
        return "unregistered" if waited_s >= config.censor_after_s else None
    if gap.status == FAILED:
        return FAILED if waited_s >= config.censor_after_s else None
    if gap_age_s is not None and gap_age_s >= config.gap_recovery_max_s:
        return "stalled"
    return None
