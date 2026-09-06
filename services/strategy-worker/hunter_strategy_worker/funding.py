"""Funding cost of one hypothetical long, per unit — SHADOW-LAB.md §3.

    R_net = ((P_exit - P_entry) - fee*P_entry - fee*P_exit - funding) / (P_entry - stop)

``funding`` is signed and per unit: positive means the long **paid** it. It is
charged for every settlement in ``(entry_ts, exit_ts]`` — the settlement that
lands exactly on the entry is not paid, because the position is taken at that
instant.

The hard part is not the sum, it is knowing when a settlement was *due*. The
cadence is read from the market's own observed history (two consecutive
settlements are enough, and the most common gap wins), never from a hardcoded
eight hours: not every perpetual settles on the same schedule, and a wrong
schedule would either invent a charge or hide one.

When funding is applicable but cannot be established — the schedule is unknown,
a due settlement is missing, or a settlement has no price to value it — the
reading is ``None`` with a reason. The caller then persists ``r_multiple = NULL``
plus ``meta.r_net_reason`` and keeps ``meta.r_ex_funding`` as the separate,
lower-coverage metric. A zero would be an invented number.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.numeric import CONTEXT

__all__ = ["FundingReading", "Settlement", "resolve_funding"]


@dataclass(frozen=True, slots=True)
class Settlement:
    """One realized funding settlement — a row of ``funding_rates``."""

    funding_time: datetime
    rate: Decimal
    mark_price: Decimal | None


@dataclass(frozen=True, slots=True)
class FundingReading:
    """What funding cost this trade, or why that cannot be said."""

    per_unit: Decimal | None
    reason: str | None
    settlements: int
    interval_s: int | None

    @property
    def available(self) -> bool:
        return self.per_unit is not None

    def to_jsonable(self) -> dict[str, object]:
        return {
            "per_unit": None if self.per_unit is None else format(self.per_unit, "f"),
            "reason": self.reason,
            "settlements": self.settlements,
            "interval_s": self.interval_s,
        }


def _cadence(times: Sequence[datetime]) -> int | None:
    """The market's settlement interval, in seconds, or ``None`` if unknowable."""
    if len(times) < 2:
        return None
    gaps = Counter(
        int((later - earlier).total_seconds())
        for earlier, later in zip(times, times[1:], strict=False)
        if later > earlier
    )
    if not gaps:
        return None
    interval, _count = gaps.most_common(1)[0]
    return interval or None


def _due_times(
    anchor: datetime, interval_s: int, entry_ts: datetime, exit_ts: datetime
) -> list[datetime]:
    """Every settlement instant the cadence puts inside ``(entry_ts, exit_ts]``."""
    step = timedelta(seconds=interval_s)
    cursor = anchor
    while cursor <= entry_ts:
        cursor += step
    due: list[datetime] = []
    while cursor <= exit_ts:
        due.append(cursor)
        cursor += step
    return due


def resolve_funding(
    history: Sequence[Settlement],
    *,
    entry_ts: datetime,
    exit_ts: datetime,
    ambiguous_from: datetime | None = None,
) -> FundingReading:
    """Funding per unit over ``(entry_ts, exit_ts]``, or the reason it is unknown.

    ``ambiguous_from`` is the open of a bar the exit is only known to be
    *somewhere inside* (an intrabar touch). A settlement landing in that window
    may or may not have been paid — the position may already have been out — so
    it makes the reading unestablishable instead of being charged as if the
    conservative barrier were the real exit instant (Astra, S2 diff review,
    must-fix 5).
    """
    entry, exit_ = ensure_utc(entry_ts), ensure_utc(exit_ts)
    known = {ensure_utc(s.funding_time): s for s in history}
    times = sorted(known)
    interval_s = _cadence(times)
    if interval_s is None:
        return FundingReading(None, "funding_schedule_unknown", 0, None)
    before = [t for t in times if t <= entry]
    anchor = before[-1] if before else times[0]
    # The union, not just the grid: a settlement the exchange actually recorded
    # inside the window is charged even when the observed cadence does not
    # predict it. An off-grid settlement is data, and dropping it would hide a
    # real cost (must-fix 5).
    scheduled = _due_times(anchor, interval_s, entry, exit_)
    observed = [t for t in times if entry < t <= exit_]
    due = sorted(set(scheduled) | set(observed))
    if not due:
        return FundingReading(Decimal(0), None, 0, interval_s)
    with localcontext(CONTEXT):
        total = Decimal(0)
        for instant in due:
            if ambiguous_from is not None and instant > ensure_utc(ambiguous_from):
                return FundingReading(None, "funding_ambiguous_exit", 0, interval_s)
            settlement = known.get(instant)
            if settlement is None:
                return FundingReading(
                    None, f"funding_missing:{instant.isoformat()}"[:64], 0, interval_s
                )
            if settlement.mark_price is None:
                return FundingReading(None, "funding_price_missing", 0, interval_s)
            total += settlement.rate * settlement.mark_price
    return FundingReading(total, None, len(due), interval_s)
