"""I1 (EXP-M26, ``docs/design/exp-m26-grafico-moedas-maduras.md`` §1.6): the
pure rule that decides which mature mints the tracker keeps past the cap, in
a budget of its own that never takes a slot from a young mint.

Split out of ``tracker.py`` (which sat at the 350-line budget already, its
own docstring says so) — pure, no IO, no clock of its own; ``prune`` only
calls it.

**Why keeping matters.** ``docs/design`` §1.1 measured that the tracked set's
cap evicts by *newest*, so a mint older than ~13 min is gone in minutes,
alive or not: 73 of 32 287 mints created on 24/09 still had a 1-minute line
past 30 min, and almost all of those were pinned by an open bet or proposal
of the desk's own 1–4 min portes — never an unselected population. Retaining
the ``k`` largest-by-``mcap_sol`` mints aged 5–120 min, quoted in SOL,
unfinished and without an active Mayhem agent is what lets ``fold_minute``
keep dobrando the 1-minute line past that point for a mint nobody bet on.

**Causal, by construction.** :func:`select_mature` reads only ``mcap_sol``
and ``mcap_observed_at`` already on the candidate at the instant ``now`` is
passed in — never a reading that arrives after ``prune`` ran. A mint whose
last market-cap reading is older than :data:`MATURE_MCAP_FRESHNESS_S` is not
eligible at all (``stale_mcap`` in :class:`MatureReport`): ranking a mint on
a market cap nobody has re-confirmed in two minutes would rank it on stale
information, not on "what already arrived".

**Not the tracker's ``pinned`` mints.** Eligibility is evaluated only over
mints ``prune`` has already excluded from ``self._pinned``/``self._pinned_exp_m26``
(an open bet, a live position, a pending proposal) — those are never
optional inventory for reasons of their own, and mixing them into this
budget would double-count against the ceiling the design's §1.6 draws.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_meme_worker.tracker_types import ACTIVE_MAYHEM_STATES, TrackedMint

__all__ = [
    "MATURE_MAX_AGE_S",
    "MATURE_MCAP_FRESHNESS_S",
    "MATURE_MIN_AGE_S",
    "MatureReport",
    "PinnedMints",
    "is_mature_eligible",
    "mature_heartbeat_fields",
    "mature_report",
    "select_mature",
]


@dataclass
class PinnedMints:
    """I2 (EXP-M26): the tracker's two pinned sets. ``ordinary`` (another
    set's bet, a live position, another set's proposal) narrows
    :meth:`MintTracker.prune`'s young cap; ``exp_m26`` (an EXP-M26 rule set's
    ``approved``-without-bet proposal, open bet or re-entry) never does — it
    spends the mature budget instead (design §1.6). A mint in both counts
    once, as ordinary, since :attr:`all` is a plain union."""

    ordinary: set[str] = field(default_factory=set[str])
    exp_m26: set[str] = field(default_factory=set[str])

    @property
    def all(self) -> frozenset[str]:
        return frozenset(self.ordinary | self.exp_m26)

    def pin(self, mints: Iterable[str]) -> None:
        self.ordinary.update(mints)

    def unpin(self, mints: Iterable[str]) -> None:
        self.ordinary.difference_update(mints)

    def set_pinned(self, mints: Iterable[str]) -> None:
        wanted = frozenset(mints)
        self.unpin(self.ordinary - wanted)
        self.pin(wanted)

    def pin_exp_m26(self, mints: Iterable[str]) -> None:
        self.exp_m26.update(mints)

    def unpin_exp_m26(self, mints: Iterable[str]) -> None:
        self.exp_m26.difference_update(mints)

    def set_pinned_exp_m26(self, mints: Iterable[str]) -> None:
        wanted = frozenset(mints)
        self.unpin_exp_m26(self.exp_m26 - wanted)
        self.pin_exp_m26(wanted)


MATURE_MIN_AGE_S = 300
"""5 minutes (design §2.1's ``min_age_s``): below this the desk's own 1–4 min
portes already cover the mint, and a mint podada before 5 min never comes
back — retention is not a rescue for it (§1.6's "população" note)."""

MATURE_MAX_AGE_S = 7200
"""120 minutes (design §2.1's ``max_age_s``): past this the population is
almost all graduated already (§1.5), and the brief bounds the window there."""

MATURE_MCAP_FRESHNESS_S = 120
"""A reading older than this is not "already arrived" for this tick's
ranking — it is stale, and the mint is not eligible at all (design §1.6)."""


def is_mature_eligible(tracked: TrackedMint, now: datetime) -> bool:
    """Age 5–120 min (known ``created_at``), not finished, quoted in SOL, no
    active Mayhem agent, and a market cap read within the last
    :data:`MATURE_MCAP_FRESHNESS_S` — every clause the design's §1.6 names."""
    if not _age_and_state_eligible(tracked, now):
        return False
    return _mcap_fresh(tracked, now)


def _age_and_state_eligible(tracked: TrackedMint, now: datetime) -> bool:
    """Every clause of :func:`is_mature_eligible` except market-cap freshness
    — the "would qualify if the mint had a fresher reading" half, which
    :func:`mature_report` uses to name ``stale_mcap`` apart from "not aged
    into the window at all"."""
    if tracked.created_at is None or tracked.quote_unsupported or tracked.finished:
        return False
    if tracked.mayhem_state in ACTIVE_MAYHEM_STATES:
        return False
    age = now - tracked.created_at
    return timedelta(seconds=MATURE_MIN_AGE_S) <= age <= timedelta(seconds=MATURE_MAX_AGE_S)


def _mcap_fresh(tracked: TrackedMint, now: datetime) -> bool:
    if tracked.mcap_sol is None or tracked.mcap_observed_at is None:
        return False
    return now - tracked.mcap_observed_at <= timedelta(seconds=MATURE_MCAP_FRESHNESS_S)


def select_mature(candidates: Iterable[TrackedMint], now: datetime, k: int) -> tuple[str, ...]:
    """The ``k`` largest-by-``mcap_sol`` eligible mints, ties broken by mint —
    deterministic and, because eligibility already required a fresh reading,
    causal: nothing that arrives after this call can move the choice."""
    if k <= 0:
        return ()
    eligible = [t for t in candidates if is_mature_eligible(t, now)]
    ranked = sorted(eligible, key=lambda t: (-(t.mcap_sol or Decimal(0)), t.mint))
    return tuple(t.mint for t in ranked[:k])


@dataclass(frozen=True, slots=True)
class MatureReport:
    """One prune's worth of the mature budget, for the heartbeat."""

    kept: tuple[str, ...]
    """The ``k`` mints retained this tick (``tracked_mature_kept``)."""
    eligible: tuple[str, ...]
    """Every mint that qualified, kept or not."""
    ranked_out: tuple[str, ...]
    """Eligible, but not among the ``k`` largest right now
    (``tracked_mature_ranked_out_60s``)."""
    stale_mcap: tuple[str, ...]
    """Would qualify by age/finished/Mayhem, but the last market-cap reading
    is older than :data:`MATURE_MCAP_FRESHNESS_S` (``tracked_mature_stale_mcap``)."""


def mature_report(candidates: Iterable[TrackedMint], now: datetime, k: int) -> MatureReport:
    """The eligibility/selection breakdown a heartbeat renders — never IO."""
    pool = tuple(candidates)
    eligible = tuple(sorted(t.mint for t in pool if is_mature_eligible(t, now)))
    kept = select_mature(pool, now, k)
    kept_set = frozenset(kept)
    ranked_out = tuple(sorted(mint for mint in eligible if mint not in kept_set))
    stale_mcap = tuple(
        sorted(t.mint for t in pool if _age_and_state_eligible(t, now) and not _mcap_fresh(t, now))
    )
    return MatureReport(kept=kept, eligible=eligible, ranked_out=ranked_out, stale_mcap=stale_mcap)


def mature_heartbeat_fields(report: MatureReport) -> dict[str, str]:
    """``hb:meme:radar``'s own fields for this budget (``wiring.heartbeat_once``,
    the same ``dict.update`` pattern every other subsystem's own stats use)."""
    return {
        "tracked_mature_kept": str(len(report.kept)),
        "tracked_mature_eligible": str(len(report.eligible)),
        "tracked_mature_ranked_out_60s": str(len(report.ranked_out)),
        "tracked_mature_stale_mcap": str(len(report.stale_mcap)),
    }
