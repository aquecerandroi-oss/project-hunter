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
a due settlement is missing, its rows disagree, or a settlement has no price to
value it — the reading is ``None`` with a reason. The caller then persists
``r_multiple = NULL`` plus ``meta.r_net_reason`` and keeps ``meta.r_ex_funding``
as the separate, lower-coverage metric. A zero would be an invented number.

Identity, not proximity (S2-funding, EXP-0001-momentum-v1.md H2). 69 of 73
outcomes with ``R_net = null`` for a "missing" settlement had a real row in
``funding_rates`` less than 2 s away — the exchange's real grid is not round
(851 of 1883 rows have a non-zero second) and the old code matched by *exact*
timestamp equality. A blanket ``±2s`` tolerance is forbidden on its own: the old
code unioned the schedule's nominal instant with the observed one for the same
real settlement, so a naive tolerant lookup on that union would count a single
settlement twice.

Three designs were tried and rejected here before this one, all by Astra's
review (``.claude/state/astra-review-S2-funding.md``, three rounds):

1. An epoch-anchored slot grid (``floor(epoch_seconds / interval_s)``) so an
   observed row always falls in the same bucket as its nominal instant. Killed
   by: ``_cadence()`` truncating the gap to whole seconds (a jittered
   ``00:00:00.010``/``08:00:00.005`` pair read as 28799 s, not 28800, and an
   epoch-anchored bucket then lands nowhere near the real grid); and a market
   that briefly settles hourly after its usual 8h settlement (a real Binance
   mechanism) putting two distinct, both-due real settlements in the same 8h
   bucket, with "the oldest wins" silently dropping the second payment.
2. Nearest-within-tolerance matching *against the nominal schedule only*,
   leaving unmatched real rows to stand alone. Killed by three more concrete
   failures: (a) the ambiguous-exit guard compared the *nominal* instant to
   the exit bar's open instead of the *real* one, so a settlement recorded a
   few ms after the bar open (genuinely uncertain) passed as fine; (b) two
   rows within tolerance of the same nominal but with *conflicting* rate or
   mark price were silently resolved by picking the nearer one, when
   disagreement is evidence they are not the same event; (c) two rows that are
   duplicates of each other but land off-schedule (no nearby nominal instant)
   were never deduplicated, since matching only ever looked at the schedule.
3. Clustering restricted to rows already inside ``(entry_ts, exit_ts]``, with
   the cluster's *first* member as the instant compared to every boundary.
   Killed by: a cluster whose members straddle ``ambiguous_from`` (one before,
   one after) reported the earlier, convenient one and skipped the guard; and
   a cluster whose members straddle ``entry_ts`` itself — one exactly at entry
   (rightly excluded) and one a few ms later (included) — was seen only from
   the included side, so a duplicate recording of the very settlement that
   should not be charged was charged anyway. Agreement that two rows are one
   event never proves *which* timestamp is the true one.

What is here instead: **all** of ``history`` is first grouped into clusters
purely by mutual time proximity (``MATCH_TOLERANCE``), with no reference to
the schedule or the window at all — two rows close to *each other* are one
event, on-grid or not, inside the trade or not. A cluster entirely outside
``(entry_ts, exit_ts]`` is simply not due. A cluster whose members disagree
about being inside that window, or about being before/after
``ambiguous_from``, is unestablishable (``funding_boundary_uncertain`` /
``funding_ambiguous_exit``) — incidence itself is uncertain, not just the
choice of representative. Only a cluster fully and unanimously inside the
window is charged: its rows must agree on rate and mark price or the reading
is unestablishable (``funding_conflicting_rows``); a multi-row cluster that
agrees is one charge (``duplicate_settlement_row``), never two. Only then is
it matched to the nearest *unclaimed* nominal instant within tolerance, purely
to say which nominal instants remain genuinely missing — the schedule
identifies gaps, it never manufactures or merges a charge.

The tolerance (``MATCH_TOLERANCE``, 2 s) is a documented limit, not a proof:
it must stay far smaller than half the shortest real gap between two distinct
settlements of the same market, and every cadence read back so far (1h/4h/8h)
clears that by three orders of magnitude. A market whose genuine, distinct
settlements are legitimately less than a few seconds apart would be
misclassified; none has been observed. Chaining is also sequential, not
transitive-safe: three real settlements each ~1.5 s from the next (A-B and B-C
within tolerance, A-C not) would cluster as one. Real funding settlements are
hours apart, so this has not been observed either.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.numeric import CONTEXT

__all__ = ["MATCH_TOLERANCE", "FundingReading", "Settlement", "resolve_funding"]

MATCH_TOLERANCE = timedelta(seconds=2)
"""See the module docstring: far smaller than half the shortest real cadence."""


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
    notes: tuple[str, ...] = field(default_factory=tuple)
    charged_at: tuple[datetime, ...] = field(default_factory=tuple)
    """The real settlement instants actually charged, oldest first — empty
    whenever ``per_unit`` is ``None``. Lets a caller (the recompute script)
    report *which* liquidation an outcome was matched to without recomputing."""

    @property
    def available(self) -> bool:
        return self.per_unit is not None

    def to_jsonable(self) -> dict[str, object]:
        return {
            "per_unit": None if self.per_unit is None else format(self.per_unit, "f"),
            "reason": self.reason,
            "settlements": self.settlements,
            "interval_s": self.interval_s,
            "notes": list(self.notes),
            "charged_at": list(self.charged_at),
        }


def _cluster(rows: Sequence[Settlement]) -> list[list[Settlement]]:
    """Group ``rows`` (already sorted by ``funding_time``) by mutual proximity.

    Purely temporal, with no reference to any schedule: two rows within
    ``MATCH_TOLERANCE`` of each other are one real-world event, whether or not
    a nominal instant is anywhere near them.
    """
    clusters: list[list[Settlement]] = []
    for row in rows:
        ts = ensure_utc(row.funding_time)
        if clusters and ts - ensure_utc(clusters[-1][-1].funding_time) <= MATCH_TOLERANCE:
            clusters[-1].append(row)
        else:
            clusters.append([row])
    return clusters


def _distinct_instants(times: Sequence[datetime]) -> list[datetime]:
    """``times`` (sorted) with near-duplicates collapsed before reading cadence.

    Two ``funding_rates`` rows for the same real settlement a few ms apart
    would otherwise show up as a near-zero gap and pollute the mode."""
    out: list[datetime] = []
    for t in times:
        if out and t - out[-1] <= MATCH_TOLERANCE:
            continue
        out.append(t)
    return out


def _cadence(times: Sequence[datetime]) -> int | None:
    """The market's settlement interval, in seconds, or ``None`` if unknowable.

    Rounded to the nearest second, not truncated: a jittered pair such as
    ``00:00:00.010`` -> ``08:00:00.005`` is a 28799.995 s gap, and truncating it
    (the previous behaviour) reads back as 28799 — one second short of the real
    8h grid, which compounds every time the schedule steps (Astra, S2-funding
    review, round 1 must-fix 2).
    """
    distinct = _distinct_instants(times)
    if len(distinct) < 2:
        return None
    gaps = Counter(
        round((later - earlier).total_seconds())
        for earlier, later in zip(distinct, distinct[1:], strict=False)
        if later > earlier
    )
    if not gaps:
        return None
    interval, _count = gaps.most_common(1)[0]
    return interval or None


def _due_times(
    anchor: datetime, interval_s: int, entry_ts: datetime, exit_ts: datetime
) -> list[datetime]:
    """The nominal schedule's instants inside ``(entry_ts, exit_ts]``.

    This is a *prediction*, not a fact: it says what the market's own cadence
    suggests should be due, so a missing real settlement can be reported. It
    never decides, on its own, what gets charged or merges two real rows.
    """
    step = timedelta(seconds=interval_s)
    cursor = anchor
    while cursor <= entry_ts:
        cursor += step
    due: list[datetime] = []
    while cursor <= exit_ts:
        due.append(cursor)
        cursor += step
    return due


def _conflict_reason(cluster: Sequence[Settlement]) -> str | None:
    """``None`` if every row of a multi-row cluster agrees, else why not.

    Agreement, not proximity, is what makes two close rows *the same event
    recorded twice*. Rows this close that disagree are evidence of a data
    problem, not license to pick one arbitrarily (Astra, S2-funding review,
    round 2 must-fix 2)."""
    if len(cluster) < 2:
        return None
    first = cluster[0]
    if any((row.rate, row.mark_price) != (first.rate, first.mark_price) for row in cluster[1:]):
        instant = ensure_utc(first.funding_time).isoformat()
        return f"funding_conflicting_rows:{instant}"[:64]
    return None


def _claim_nominal(
    anchor: datetime, nominal: Sequence[datetime], claimed: set[datetime]
) -> datetime | None:
    """The nearest not-yet-claimed nominal instant within tolerance of ``anchor``.

    Bookkeeping only — it says which nominal instants are genuinely unfulfilled
    (missing), it never changes what a cluster is charged."""
    candidates = [n for n in nominal if n not in claimed and abs(n - anchor) <= MATCH_TOLERANCE]
    if not candidates:
        return None
    return min(candidates, key=lambda n: abs(n - anchor))


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
    must-fix 5). The check always compares against a cluster's own real
    instant, never a nominal one (Astra, S2-funding review, round 2 must-fix 1).

    Clustering runs over *every* row of ``history``, not just the ones already
    inside ``(entry_ts, exit_ts]``: a cluster whose members disagree about
    which side of ``entry_ts``, ``exit_ts`` or ``ambiguous_from`` they fall on
    is the same uncertainty as disagreeing on rate — agreement that two close
    rows are one event does not establish *which* of their timestamps is the
    true one, so a boundary that only one representation crosses is
    unestablishable, not resolved by picking the representation that happens to
    land on the convenient side (Astra, S2-funding review, round 3 must-fix 1).
    """
    entry, exit_ = ensure_utc(entry_ts), ensure_utc(exit_ts)
    times = sorted({ensure_utc(s.funding_time) for s in history})
    interval_s = _cadence(times)
    if interval_s is None:
        return FundingReading(None, "funding_schedule_unknown", 0, None)

    before = [t for t in times if t <= entry]
    anchor = before[-1] if before else times[0]
    nominal = _due_times(anchor, interval_s, entry, exit_)
    ambiguous_at = None if ambiguous_from is None else ensure_utc(ambiguous_from)

    all_rows = sorted(history, key=lambda s: ensure_utc(s.funding_time))
    clusters = _cluster(all_rows)

    notes: list[str] = []
    claimed: set[datetime] = set()
    items: list[tuple[datetime, Settlement | str | None]] = []
    for cluster in clusters:
        cluster_ts = [ensure_utc(row.funding_time) for row in cluster]
        in_window = [t for t in cluster_ts if entry < t <= exit_]
        if not in_window:
            continue  # entirely outside the trade; not due, whatever it is
        if len(in_window) != len(cluster_ts):
            anchor_ts = in_window[0]
            reason = f"funding_boundary_uncertain:{anchor_ts.isoformat()}"[:64]
            items.append((anchor_ts, reason))
            continue
        anchor_ts = cluster_ts[0]
        # Claimed as soon as the cluster is known to be in the window, whatever
        # happens next: a nominal instant a blocked cluster accounts for is not
        # also "missing" (that would emit a redundant, order-dependent item).
        matched = _claim_nominal(anchor_ts, nominal, claimed)
        if matched is not None:
            claimed.add(matched)
        if ambiguous_at is not None:
            after = [t for t in cluster_ts if t > ambiguous_at]
            if after and len(after) != len(cluster_ts):
                items.append((anchor_ts, "funding_ambiguous_exit"))
                continue
        conflict = _conflict_reason(cluster)
        if conflict is not None:
            items.append((anchor_ts, conflict))
            continue
        if len(cluster) > 1:
            label = matched if matched is not None else anchor_ts
            notes.append(f"duplicate_settlement_row:{label.isoformat()}"[:64])
        items.append((anchor_ts, cluster[0]))
    items.extend((instant, None) for instant in nominal if instant not in claimed)
    items.sort(key=lambda pair: pair[0])

    if not items:
        return FundingReading(Decimal(0), None, 0, interval_s)

    with localcontext(CONTEXT):
        total = Decimal(0)
        charged_at: list[datetime] = []
        for instant, payload in items:
            if isinstance(payload, str):
                return FundingReading(None, payload, 0, interval_s)
            if ambiguous_at is not None and instant > ambiguous_at:
                return FundingReading(None, "funding_ambiguous_exit", 0, interval_s)
            if payload is None:
                return FundingReading(
                    None, f"funding_missing:{instant.isoformat()}"[:64], 0, interval_s
                )
            if payload.mark_price is None:
                return FundingReading(None, "funding_price_missing", 0, interval_s)
            total += payload.rate * payload.mark_price
            charged_at.append(instant)
    return FundingReading(
        total, None, len(charged_at), interval_s, notes=tuple(notes), charged_at=tuple(charged_at)
    )
