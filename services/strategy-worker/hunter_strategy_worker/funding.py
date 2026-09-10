"""Funding cost of one hypothetical long, per unit — SHADOW-LAB.md §3.

    R_net = ((P_exit - P_entry) - fee*P_entry - fee*P_exit - funding) / (P_entry - stop)

``funding`` is signed and per unit: positive means the long **paid** it. It is
charged for every settlement in ``(entry_ts, exit_ts]`` — the settlement that
lands exactly on the entry is not paid, because the position is taken at that
instant.

The hard part is not the sum, it is knowing when a settlement was *due*. The
cadence is read from the market's own observed history — the most common gap
among the most *recent* few, never the mode of the whole window nor a
hardcoded eight hours (T3.65, see ``_cadence()``): a wrong schedule invents or hides a charge.

When funding is applicable but cannot be established — the schedule is unknown,
a due settlement is missing, its rows disagree, or a settlement has no price to
value it — the reading is ``None`` with a reason. The caller then persists
``r_multiple = NULL`` plus ``meta.r_net_reason`` and keeps ``meta.r_ex_funding``
as the separate, lower-coverage metric. A zero would be an invented number.

Identity, not proximity (S2-funding, EXP-0001-momentum-v1.md H2): 69 of 73
``R_net = null`` outcomes had a real row less than 2 s from the "missing" instant
(the exchange's grid is not round), and a blanket ``±2s`` lookup on the old
nominal-plus-observed union would have counted one settlement twice.

Three designs were tried and rejected before this one, all by Astra's review
(``.claude/state/astra-review-S2-funding.md``, three rounds): an epoch-anchored
slot grid (killed by second-truncated cadences and by two due settlements in one
bucket), nearest-within-tolerance matching against the nominal schedule only
(killed by the ambiguous-exit guard comparing the nominal instant, by silently
resolving conflicting rows, and by never deduplicating off-schedule duplicates),
and clustering restricted to rows inside the window with the first member as
the instant (killed by clusters straddling ``ambiguous_from`` or ``entry_ts``).

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
identifies gaps, it never manufactures or merges a charge. A nominal instant
that *any* real row of the history answers — including one that landed just
outside ``(entry_ts, exit_ts]`` — is not a gap either (``_fulfilled``, T3.65b):
the settlement exists, it simply was not paid by this position.

The tolerance (``MATCH_TOLERANCE``, 2 s) is a documented limit, not a proof: it
must stay far smaller than half the shortest real gap between two distinct
settlements of one market (every cadence read so far — 1h/4h/8h — clears it by
three orders of magnitude), and chaining is sequential, not transitive-safe.
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

_CADENCE_RECENT_GAPS = 3
"""Gaps ``_cadence()`` reads the mode over: 2 new settlements outvote a retired cadence; 1 stray gap does not (T3.65)."""


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
    """The market's *current* settlement interval, in seconds, or ``None``.

    Rounded to the nearest second, not truncated: a jittered pair such as
    ``00:00:00.010`` -> ``08:00:00.005`` is a 28799.995 s gap, and truncating it
    (the previous behaviour) reads back as 28799 — one second short of the real
    8h grid, which compounds every time the schedule steps (Astra, S2-funding
    review, round 1 must-fix 2).

    Mode over only the last ``_CADENCE_RECENT_GAPS`` gaps, not the whole
    window (T3.65) — a schedule change else reads as retired. Ties by recency.
    """
    distinct = _distinct_instants(times)
    if len(distinct) < 2:
        return None
    gaps = [
        round((later - earlier).total_seconds())
        for earlier, later in zip(distinct, distinct[1:], strict=False)
        if later > earlier
    ]
    if not gaps:
        return None
    recent = gaps[-_CADENCE_RECENT_GAPS:]
    counts = Counter(recent)
    interval = max(reversed(recent), key=lambda gap: counts[gap])
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


def _fulfilled(instant: datetime, times: Sequence[datetime]) -> bool:
    """``True`` if some real row of the history is this nominal instant.

    Identity, not proximity — but identity does not care which side of a
    boundary the real row landed on. A nominal instant within
    ``MATCH_TOLERANCE`` of a real settlement **is** that settlement, and a
    settlement that exists is not missing: if it fell outside
    ``(entry_ts, exit_ts]`` it simply was not paid (T3.65b).

    Measured on the real series: PROMUSDT settles at ``20:00:00.000`` and again
    at ``00:00:00.003``. A trade exiting exactly at ``00:00:00`` anchors its
    nominal grid on the ms-zero row, so the grid predicts ``00:00:00.000`` —
    inside the window — while the real row is 3 ms outside it. Without this
    check the window is refused as ``funding_missing`` even though nothing was
    due and nothing is absent: 3 376 of 175 416 windows swept over the real
    90 days of PROM/SAHARA/TAO (``.claude/state/notes-T3.65b.md`` §3).

    It can never hide a genuine absence: a nominal instant is only silenced
    when a real row for it exists. Inside the window that row is charged by the
    cluster loop; outside it, the position was not holding when it settled.
    """
    return any(abs(t - instant) <= MATCH_TOLERANCE for t in times)


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
    items.extend(
        (instant, None)
        for instant in nominal
        if instant not in claimed and not _fulfilled(instant, times)
    )
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
