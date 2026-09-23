"""Which refusal instant is a legitimate opportunity — the other half of
EXP-M23 (T4.85); the rates and the draw live in
:mod:`hunter_meme_worker.refused_probe_sampler`, re-exported here so callers
have one import.

**Why this exists.** R69 (23/09/2026) closed with the empty square of the
2×2: 41 905 refusals recorded in ``meme_gate_refusals_by_mint`` since 17/09
and **not one outcome measured**. While that square is empty, a gate that
SELECTS and a gate that merely bets LESS OFTEN look exactly alike in our
data. This module decides which refused mints get a paper bet;
:mod:`hunter_meme_worker.refused_probe_step` turns the choice into a proposal
and the existing Lab loop fills, marks and closes it under the desk's own
exit policy.

Three rules, each one a test in ``tests/test_refused_probe.py``:

- **Population** — a mint that, at a judged instant, collects at least one
  refusal **by a criterion** from an ``operator`` set and that no arm admitted
  at that instant or before it. An admission that came *later* cannot cancel a
  bet already decided: that would be look-ahead, and it would make the
  population depend on how the backlog happened to be batched.
- **Non-anticipation** (:func:`is_readable_at`, R69's own guard carried over,
  ``.claude/state/r69/test_cohort.py``) — ``as_of <= now``,
  ``computed_at <= now``, ``tape_as_of <= as_of``, and a photo that is not
  from the future of its own row.
- **One draw per mint, ever**, at its **first eligible opportunity**. If a
  mint were re-drawn at every opportunity its true inclusion probability
  would be the **maximum** over them while the bet would carry the rate of
  the entering one, and the inverse-probability weights of the analysis would
  be wrong by up to two orders of magnitude (0,001 against 0,10). Hence
  ``drawn``: the caller passes the mints already decided.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_meme_worker.refused_probe_sampler import (
    CENSUS_REFUSALS,
    EXPERIMENT,
    FROZEN_SEED,
    PROBE_CLOCK,
    PROBE_RULE_SET_ID,
    PROBE_RULE_SET_NAME,
    PROBE_RULE_SET_VERSION,
    RATE_A_BASE,
    RATE_A_RARE,
    RATE_B_BASE,
    RATE_B_RARE,
    STRATUM_MULTIPLE,
    STRATUM_NEAR_MISS,
    STRUCTURAL_REFUSALS,
    criteria_refusals,
    has_rare_reason,
    inclusion_probability,
    is_sampled,
    stratum_of,
    uniform01,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

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
    "ProbePick",
    "RefusedRow",
    "criteria_refusals",
    "first_opportunities",
    "has_rare_reason",
    "inclusion_probability",
    "is_readable_at",
    "is_sampled",
    "pick_probes",
    "probe_reason_block",
    "stratum_of",
    "uniform01",
]


@dataclass(frozen=True, slots=True)
class RefusedRow:
    """One judged instant at which an ``operator`` set refused one mint.

    ``as_of`` is the refusal instant ``t``; the three provenance stamps are
    what :func:`is_readable_at` checks against it.
    """

    mint: str
    as_of: datetime
    refusals: tuple[str, ...]
    refused_by: str
    computed_at: datetime | None = None
    """``meme_features_15s.computed_at`` — when the row was written."""
    tape_as_of: datetime | None = None
    """``meme_features_15s.tape_as_of`` — the end of the tape window folded
    into the row; ``None`` means there was no tape, not a tape from later."""
    snapshot_observed_at: datetime | None = None
    """The photo the row names. ``None`` = nothing to quote a fill against."""


@dataclass(frozen=True, slots=True)
class ProbePick:
    """One mint the sampler drew, with the number the analysis weights by."""

    row: RefusedRow
    stratum: str
    probability: Decimal


def is_readable_at(row: RefusedRow, *, now: datetime) -> bool:
    """R69's guard, carried over: nothing in the bet may come from after the
    refusal it claims to describe.

    ``as_of <= now`` (not a future candle), ``computed_at <= now`` (not a row
    written retroactively — the trap R69 found), ``tape_as_of <= as_of`` (the
    tape window does not end after its own row — the ``features_tape``
    opening Astra found), and a photo that is not from the future of its own
    row. Without a photo there is nothing to quote and the instant is simply
    not an opportunity.
    """
    if row.as_of > now:
        return False
    if row.computed_at is None or row.computed_at > now:
        return False
    if row.tape_as_of is not None and row.tape_as_of > row.as_of:
        return False
    return row.snapshot_observed_at is not None and row.snapshot_observed_at <= row.as_of


def _merged_by(left: str, right: str) -> str:
    return "+".join(sorted({*left.split("+"), *right.split("+")}))


def first_opportunities(
    rows: Iterable[RefusedRow],
    *,
    admitted: Mapping[str, datetime],
    now: datetime,
    drawn: frozenset[str] = frozenset(),
) -> list[RefusedRow]:
    """Per mint, the **earliest** eligible refusal instant of this tick, with
    every reason of that instant merged across the ``operator`` sets that
    judged it. Mints already drawn and instants that fail
    :func:`is_readable_at` never reach the lottery.

    ``admitted`` maps a mint to the **earliest instant** an arm admitted it in
    this tick, and an admission removes only the refusals at or after it. An
    admission that came *later* than the refusal must not cancel it: that
    would decide a bet with information from after the instant it claims to
    describe — the same look-ahead :func:`is_readable_at` forbids — and it
    would make the population depend on how the backlog happened to be
    batched (one tick seeing both instants would drop the mint, two ticks
    would not).

    Ordered by mint, so the result of a tick does not depend on the order the
    rows arrived in.
    """
    merged: dict[tuple[str, datetime], RefusedRow] = {}
    for row in rows:
        admitted_at = admitted.get(row.mint)
        if admitted_at is not None and admitted_at <= row.as_of:
            continue
        if row.mint in drawn or not is_readable_at(row, now=now):
            continue
        names = criteria_refusals(row.refusals)
        if not names:
            continue
        key = (row.mint, row.as_of)
        previous = merged.get(key)
        if previous is None:
            merged[key] = replace(row, refusals=names)
        else:
            merged[key] = replace(
                previous,
                refusals=criteria_refusals((*previous.refusals, *names)),
                refused_by=_merged_by(previous.refused_by, row.refused_by),
            )
    earliest: dict[str, RefusedRow] = {}
    for row in merged.values():
        held = earliest.get(row.mint)
        if held is None or row.as_of < held.as_of:
            earliest[row.mint] = row
    return [earliest[mint] for mint in sorted(earliest)]


def pick_probes(
    rows: Iterable[RefusedRow],
    *,
    admitted: Mapping[str, datetime],
    now: datetime,
    drawn: frozenset[str] = frozenset(),
    seed: str = FROZEN_SEED,
) -> list[ProbePick]:
    """The mints this tick draws, each with its stratum and the probability
    that must be written on its bet."""
    picks: list[ProbePick] = []
    for row in first_opportunities(rows, admitted=admitted, now=now, drawn=drawn):
        stratum = stratum_of(row.refusals)
        probability = inclusion_probability(row.refusals)
        if stratum is None or probability is None:
            continue
        if not is_sampled(row.mint, probability, seed=seed):
            continue
        picks.append(ProbePick(row=row, stratum=stratum, probability=probability))
    return picks


def probe_reason_block(pick: ProbePick) -> dict[str, Any]:
    """What goes into ``meme_proposals.reasons`` beside the gate's own
    decomposition — and, through ``meme_paper_bets.proposal_id`` (unique),
    what every bet of this arm carries: **all** the refusal reasons, the
    stratum, the inclusion probability and the draw that produced it, plus
    the three provenance stamps of the instant the features were read at.

    The probability is a string, as every number of this codebase that is not
    a count: a float would not survive the round trip the analysis makes.
    """
    row = pick.row
    return {
        "probe": f"{PROBE_RULE_SET_NAME}/{PROBE_RULE_SET_VERSION}",
        "experiment": EXPERIMENT,
        "refused_by": row.refused_by,
        "refusals": list(row.refusals),
        "stratum": pick.stratum,
        "inclusion_probability": str(pick.probability),
        "sampler_seed": FROZEN_SEED,
        "sampler_draw": str(uniform01(row.mint)),
        "as_of": row.as_of.isoformat(),
        "computed_at": None if row.computed_at is None else row.computed_at.isoformat(),
        "tape_as_of": None if row.tape_as_of is None else row.tape_as_of.isoformat(),
        "snapshot_observed_at": (
            None if row.snapshot_observed_at is None else row.snapshot_observed_at.isoformat()
        ),
    }
