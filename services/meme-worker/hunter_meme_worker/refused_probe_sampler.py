"""Who gets drawn, and at what rate — the frozen half of EXP-M23 (T4.85).

Split from :mod:`hunter_meme_worker.refused_probe`, which owns the other
question: **which instant is a legitimate opportunity** (the anti-look-ahead
guard and the one-draw-per-mint rule). Everything here is a pure function of
a mint and a list of refusal names, and every constant is frozen with the
experiment: moving one is a new arm, never an edit of a live row.

The design is the pre-registration
(``obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md``) plus its
Emenda 1 of 23/09/2026, which replaced a single 10 % rate over the whole
refused population — ~19 000 mints/day, 25 to 38 times the frozen daily
target and the declared infra budget — by two strata:

- **A**, exactly one criterion failed (the near-miss ``meme_gate_refusals_by_mint``
  already records): 10 % base, **50 %** when the reason is rare. ~60/day. The
  only stratum the eleven per-criterion non-inferiority tests may use.
- **B**, two or more: 0,1 % base, **0,5 %** when any reason is rare. ~19/day.
  Without it the global contrast would be blind to the worst coins, which are
  exactly the ones that fail several criteria at once.

**"Rare" is frozen data, not a runtime count.** :data:`CENSUS_REFUSALS` is
the eleven names of the pre-registration's own census — each over 598
refusals in six days, far past the 30 mints/week line. A name absent from
that census did not appear in it at all and is oversampled. Counting live
would make a bet's inclusion probability a function of what happened after
it, which is the very thing ``refused_probe.is_readable_at`` forbids.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from hashlib import blake2b
from typing import TYPE_CHECKING

from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = [
    "CENSUS_REFUSALS",
    "EXPERIMENT",
    "FROZEN_SEED",
    "PROBE_CLOCK",
    "PROBE_RULE_SET_ID",
    "PROBE_RULE_SET_NAME",
    "PROBE_RULE_SET_VERSION",
    "RATE_A_BASE",
    "RATE_A_RARE",
    "RATE_B_BASE",
    "RATE_B_RARE",
    "STRATUM_MULTIPLE",
    "STRATUM_NEAR_MISS",
    "STRUCTURAL_REFUSALS",
    "criteria_refusals",
    "has_rare_reason",
    "inclusion_probability",
    "is_sampled",
    "stratum_of",
    "uniform01",
]

EXPERIMENT = "EXP-M23"
PROBE_RULE_SET_NAME = "refused_probe_v0"
PROBE_RULE_SET_VERSION = "1"
PROBE_RULE_SET_ID = "01994d00-6c1a-7000-8000-00000000001c"
"""``0060``'s seeded id, frozen here too because the desk's own pedigree
query has to be able to subtract this arm's paper bets by id
(``lab_repo_fast._PEDIGREE``) without importing a migration.
``test_migration_0060`` proves the two agree against the database."""

PROBE_CLOCK = "refused"
"""This arm's own clock. **Not** ``15s``, ``1m`` or ``event``: the population
is not a series the gate reads, it is what the desk's gate rejected, so no
existing lane may select this set (``lab._gate_step`` filters ``1m``,
``lab_fast.fast_gate_step`` and ``event_gate_caches`` filter ``15s``,
``launch_lane_repo`` refuses anything that is not ``event``).
``lab_repo.load_active_rule_sets`` keeps loading it — the fill, the marks and
the exits are the Lab's own, which is the symmetry EXP-M23 requires."""

FROZEN_SEED = "EXP-M23/refused_probe_v0/1"
"""Frozen with the experiment: changing it is a new arm, never an edit."""

STRATUM_NEAR_MISS = "A"
STRATUM_MULTIPLE = "B"

RATE_A_BASE = Decimal("0.10")
RATE_A_RARE = Decimal("0.50")
RATE_B_BASE = Decimal("0.001")
RATE_B_RARE = Decimal("0.005")
"""Emenda 1's four rates. ~60 mints/day from A and ~19 from B ≈ 79/day, inside
the frozen target of 50–80 and inside the infra budget the pre-registration
set for itself (if the fast lane loses a tick to this, the experiment dies)."""

CENSUS_REFUSALS: frozenset[str] = frozenset(
    {
        "snipers_above_max",
        "progress_above_max",
        "e2b_top_buyer_unknown",
        "holders_below_min",
        "symbol_clone",
        "creator_is_net_seller",
        "sells_ratio_above_max",
        "creator_serial",
        "snipers_below_min",
        "top10_unknown",
        "creator_repeat_dumper",
    }
)
"""The eleven names of the pre-registration's census (15 290 … 598 refusals in
six days). Anything else is "under 30 mints/week" by that same census and is
oversampled — a frozen list, so the probability of a bet is knowable before
the bet and is never a function of what happened afterwards."""

STRUCTURAL_REFUSALS: frozenset[str] = frozenset({"already_open", "no_snapshot_for_quote"})
"""Neither of these is the desk judging a criterion. ``already_open`` fires
before the gate reads anything (the desk already has that mint) and
``no_snapshot_for_quote`` fires **after** every criterion passed (there was
simply no photo to price). ``lab_fast._trail_row`` excludes ``already_open``
from the refusal trail for the same reason; a mint whose only refusals are
these is not in EXP-M23's population."""

_SCALE = 1 << 64


def criteria_refusals(names: Iterable[str]) -> tuple[str, ...]:
    """Every refusal by a criterion, sorted and deduplicated — the structural
    skips of :data:`STRUCTURAL_REFUSALS` dropped. **All** of them: without
    the full set it is impossible to isolate "passed everything else and only
    tripped on this one", which is what the eleven per-criterion contrasts of
    the pre-registration are about."""
    return tuple(sorted({name for name in names if name not in STRUCTURAL_REFUSALS}))


def stratum_of(refusals: Sequence[str]) -> str | None:
    """``A`` for exactly one criterion, ``B`` for two or more, ``None`` for
    none — ``None`` is "not population", never a third stratum."""
    if not refusals:
        return None
    return STRATUM_NEAR_MISS if len(refusals) == 1 else STRATUM_MULTIPLE


def has_rare_reason(refusals: Iterable[str]) -> bool:
    """Any reason absent from :data:`CENSUS_REFUSALS` (< 30 mints/week)."""
    return any(name not in CENSUS_REFUSALS for name in refusals)


def inclusion_probability(refusals: Sequence[str]) -> Decimal | None:
    """The frozen rate of this mint's stratum, oversampled when a rare reason
    is present; ``None`` when the mint is not in the population."""
    stratum = stratum_of(refusals)
    if stratum is None:
        return None
    rare = has_rare_reason(refusals)
    if stratum == STRATUM_NEAR_MISS:
        return RATE_A_RARE if rare else RATE_A_BASE
    return RATE_B_RARE if rare else RATE_B_BASE


def uniform01(mint: str, *, seed: str = FROZEN_SEED) -> Decimal:
    """The mint's own draw in ``[0, 1)`` — stable for the life of the seed.

    Keyed on the mint and not on the instant on purpose: the decision must
    not depend on which tick happened to see the refusal first (the
    pre-registration's own "a taxa é fixa por dia, não por tique").
    """
    digest = blake2b(f"{seed}|{mint}".encode(), digest_size=8).digest()
    with localcontext(CONTEXT):
        return Decimal(int.from_bytes(digest, "big")) / Decimal(_SCALE)


def is_sampled(mint: str, probability: Decimal, *, seed: str = FROZEN_SEED) -> bool:
    with localcontext(CONTEXT):
        return uniform01(mint, seed=seed) < probability
