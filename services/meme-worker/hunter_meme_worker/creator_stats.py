"""The ``creator_watch_*`` fields of ``hb:meme:radar`` — the watch's own
liveness and the one number that says whether it is fast enough (T4.2h-b).

Its own module because ``sources.py`` is at the repo's 350-line ceiling and
because this loop's numbers are not a *source*'s: they are a watch over the
creator's token account, and its health question is different — how many mints
it covers, how many of those carry **real money**, how many calls it spends,
how many sales it saw in the hour, how many creators it cannot measure at all,
and how long a seen sale takes to become an exit.

**The latency is measured from the rows, never from memory.**
:func:`sale_to_exit_samples` reads ``exit_at − creator_sold_seen_at`` off the
closed paper bets (and the closed real positions) that carry a seen sale, so a
restarted process reports the same p50/p95 as the one that ran all day, and no
counter in a loop can drift from the ledger. An empty sample is ``None``, never
``0`` — an unmeasured latency is not a fast one (the rule of
``lab_heartbeat.percentile``, reused here rather than re-implemented).

**``creator_watch_missing`` is not "the dev did not sell".** It counts the
mints whose creator holds no token account at all (``creator_ata_missing``):
unmeasured, and the heartbeat says so by name so nobody reads silence as
safety.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_meme_worker.lab_heartbeat import percentile
from hunter_meme_worker.source_stats import RollingCounter, iso_or_none

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.creator_watch import CreatorWatchReport

__all__ = ["HEARTBEAT_PREFIX", "CreatorWatchStats", "sale_to_exit_samples"]

HEARTBEAT_PREFIX = "creator_watch_"
LATENCY_SAMPLE = 200
"""The newest closes the p50/p95 are taken over: enough to be a distribution,
small enough that yesterday's slow loop does not hide today's fast one."""

_SALE_TO_EXIT = text(
    "SELECT seconds FROM ("
    "  SELECT extract(epoch FROM (exit_at - creator_sold_seen_at)) AS seconds, exit_at "
    "    FROM meme_paper_bets "
    "   WHERE creator_sold_seen_at IS NOT NULL AND exit_at IS NOT NULL "
    "     AND exit_at >= creator_sold_seen_at "
    "  UNION ALL "
    "  SELECT extract(epoch FROM (exit_at - creator_sold_seen_at)) AS seconds, exit_at "
    "    FROM meme_live_positions "
    "   WHERE creator_sold_seen_at IS NOT NULL AND exit_at IS NOT NULL "
    "     AND exit_at >= creator_sold_seen_at"
    ") s ORDER BY exit_at DESC LIMIT :limit"
)
"""Both ledgers, because the question ("how long after the dev sold did we get
out?") is the same question for paper and for money. A close **before** the
sale was seen is not a negative latency, it is a different exit: excluded by
the ``exit_at >= creator_sold_seen_at`` predicate rather than clamped to zero."""


async def sale_to_exit_samples(session: AsyncSession, *, limit: int = LATENCY_SAMPLE) -> list[int]:
    """Whole seconds between the creator's sale being seen and the exit, newest
    first; an empty list when nothing has closed on a seen sale yet."""
    rows = (await session.execute(_SALE_TO_EXIT, {"limit": limit})).scalars().all()
    return [int(round(float(value))) for value in rows if value is not None]


@dataclass
class CreatorWatchStats:
    """One watch loop's own liveness. Gauges are the **last** cycle's; the two
    counters are sliding windows (``source_stats.RollingCounter``)."""

    mints: int | None = None
    live_mints: int | None = None
    missing: int | None = None
    cycle_s: float | None = None
    last_cycle_at: datetime | None = None
    calls_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    drops_1h: RollingCounter = field(default_factory=lambda: RollingCounter(3600))
    sale_to_exit: list[int] = field(default_factory=lambda: list[int]())

    def record_cycle(self, at: datetime, report: CreatorWatchReport) -> None:
        self.mints = report.mints
        self.live_mints = report.live_mints
        self.missing = report.missing
        self.cycle_s = report.duration_s
        self.last_cycle_at = at
        self.calls_60s.add(at, report.calls)
        self.drops_1h.add(at, report.drops)

    def record_latency(self, samples: list[int]) -> None:
        """The rows' own answer, replacing the last one wholesale — this is a
        measurement, not an accumulator."""
        self.sale_to_exit = samples

    def heartbeat_fields(self, now: datetime, *, enabled: bool = True) -> dict[str, str]:
        """``creator_watch_*``, strings like every heartbeat field of the repo;
        an absent number is ``""``, never a ``0`` that reads as a measurement.

        ``enabled`` is the **config's** answer, read at write time by the caller
        (``wiring.heartbeat_once``): a switched-off watch must be visibly off,
        not indistinguishable from one whose counters never moved."""
        p50, p95 = percentile(self.sale_to_exit, 0.50), percentile(self.sale_to_exit, 0.95)
        fields: dict[str, object] = {
            "enabled": "true" if enabled else "false",
            "mints": self.mints,
            "live_mints": self.live_mints,
            "missing": self.missing,
            "calls_60s": self.calls_60s.total(now),
            "drops_1h": self.drops_1h.total(now),
            "cycle_s": self.cycle_s,
            "last_cycle_at": iso_or_none(self.last_cycle_at),
            "sale_to_exit_s_p50": p50,
            "sale_to_exit_s_p95": p95,
            "sale_to_exit_n": len(self.sale_to_exit),
        }
        return {
            HEARTBEAT_PREFIX + key: "" if value is None else str(value)
            for key, value in fields.items()
        }
