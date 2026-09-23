"""The per-mint gate refusal trail, sampled (T4.35).

R27 (16/09/2026, ``obsidian/03-TRADING/Meme/Estudo-2026-09-16-a-porta-real-versus-a-replica.md``)
found the only durable record of what the gate saw was
``meme_lab_ticks.refusals`` — a count **per tick**, by name, never by mint:
"why did Kintsugi not become a proposal at 16:20" cost an hour of SQL
forensics replaying the gate photo by photo. ``meme_gate_refusals_by_mint``
(``0046``) is the answer recorded going forward, kept small by construction:
only a mint that became a proposal (``refusal is None``) or missed by
**exactly one** named criterion (a near-miss) is worth a row — most refused
rows fail several criteria at once, and a pile of those teaches nothing this
table exists to answer.

**Wired into the fast lane's tick since T4.43** (``lab_fast.fast_gate_step``,
one ``evaluate_gate`` call per row instead of per batch — behaviour-
preserving, since the gate's loop body depends on no other row): the drafts
are still batched into one ``insert_proposals`` per rule set, but each row's
own ``GateOutcome.refusals`` is now visible, which is what
:func:`select_trail_row` needs. ``decode_value_limit`` below is the numeric
half of a near-miss row — the value the gate read and the threshold it was
judged against, for the refusal names this revision already knows how to
decode (``rules.py``/``rules_criteria.py``'s own naming: ``snipers_above_max``
→ ``snipers``/``max_snipers``, and so on); a name not in the table still gets
a row, with both ``NULL`` (docs/DATABASE.md §54.2's own declared behaviour).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_indicators.meme.rules import participation_pct

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hunter_indicators.meme.rules import EntryFeatures, EntryGate

__all__ = [
    "RefusalTrailRow",
    "cap_trail_rows",
    "decode_value_limit",
    "is_trail_candidate",
    "select_trail_row",
]

DEFAULT_TRAIL_CAP = 200
"""Rows written per tick, ceiling. R27's own numbers: 524 ticks/3 h with 5
``snipers_above_max`` refusals at the one instant that mattered — the
selection below already keeps the volume small; this is the backstop."""


@dataclass(frozen=True, slots=True)
class RefusalTrailRow:
    as_of: datetime
    rule_set_id: str
    mint: str
    refusal: str | None
    value: Decimal | int | None = None
    limit: Decimal | int | None = None


def is_trail_candidate(refusal_count: int) -> bool:
    """A row worth keeping: zero refusals (it became a proposal) or exactly
    one (a near-miss — ``passed_criteria >= total - 1``). Two or more failed
    criteria is the common case and answers no "why not" question a single
    number would settle."""
    if refusal_count < 0:
        raise ValueError(f"refusal_count must be >= 0, got {refusal_count}")
    return refusal_count <= 1


def select_trail_row(
    *,
    as_of: datetime,
    rule_set_id: str,
    mint: str,
    refusals: Sequence[str],
    value: Decimal | int | None = None,
    limit: Decimal | int | None = None,
) -> RefusalTrailRow | None:
    """``refusals`` is every named criterion this mint failed at this instant
    (empty when it became a proposal). ``None`` when it is not a near-miss or
    a proposal — two or more failures, nothing recorded."""
    if not is_trail_candidate(len(refusals)):
        return None
    return RefusalTrailRow(
        as_of=as_of,
        rule_set_id=rule_set_id,
        mint=mint,
        refusal=refusals[0] if refusals else None,
        value=value,
        limit=limit,
    )


def cap_trail_rows(
    rows: Sequence[RefusalTrailRow], *, limit: int = DEFAULT_TRAIL_CAP
) -> tuple[list[RefusalTrailRow], bool]:
    """``(kept, capped)`` — the first ``limit`` rows, oldest tick order
    preserved (the caller's own order), and whether anything was dropped. A
    bounded write per tick, named in the heartbeat when wired
    (``lab_refusal_trail_rows``/``lab_refusal_trail_capped``)."""
    if limit < 0:
        raise ValueError(f"limit must be >= 0, got {limit}")
    if len(rows) <= limit:
        return list(rows), False
    return list(rows[:limit]), True


_Numeric = Decimal | int | None
_NUMERIC_REFUSALS: dict[
    str, tuple[Callable[[EntryFeatures], _Numeric], Callable[[EntryGate], _Numeric]]
] = {
    "age_below_min": (lambda f: f.age_s, lambda g: g.min_age_s),
    "age_above_max": (lambda f: f.age_s, lambda g: g.max_age_s),
    "progress_below_min": (lambda f: f.progress_pct, lambda g: g.min_progress_pct),
    "progress_above_max": (lambda f: f.progress_pct, lambda g: g.max_progress_pct),
    "participation_above_cap": (
        lambda f: participation_pct(f.intended_size_sol, f.curve_volume_1m_sol),
        lambda g: g.max_participation_pct,
    ),
    "distance_below_min": (
        lambda f: f.distance_to_support_pct,
        lambda g: g.min_distance_to_support_pct,
    ),
    "distance_above_max": (
        lambda f: f.distance_to_support_pct,
        lambda g: g.max_distance_to_support_pct,
    ),
    "hype_below_min": (lambda f: f.hype_score, lambda g: g.min_hype_score),
    "dev_share_above_max": (lambda f: f.dev_share, lambda g: g.max_dev_share),
    "snipers_below_min": (lambda f: f.snipers, lambda g: g.min_snipers),
    "snipers_above_max": (lambda f: f.snipers, lambda g: g.max_snipers),
    "top10_below_min": (lambda f: f.top10_share, lambda g: g.min_top10_share),
    "top10_above_max": (lambda f: f.top10_share, lambda g: g.max_top10_share),
    "buyers_below_min": (lambda f: f.unique_buyers_1m, lambda g: g.min_unique_buyers),
    "holders_below_min": (lambda f: f.holders, lambda g: g.min_holders),
    # T4.61a (EXP-M13): the fraction lost from the window's peak against the ceiling.
    "recent_drawdown": (lambda f: f.recent_drawdown_pct, lambda g: g.max_recent_drawdown_pct),
    # T4.66 (EXP-M19): the crowd — the retention floor, the age floor, the
    # new-wallets floor, the quick-flip ceiling.
    "early_retention_below_min": (
        lambda f: f.early_retention_pct,
        lambda g: g.min_early_retention_pct,
    ),
    "early_age_below_min": (lambda f: f.early_age_s, lambda g: g.min_early_age_s),
    "new_wallets_below_min": (lambda f: f.new_wallets_30s, lambda g: g.min_new_wallets_30s),
    "quick_flip_above_max": (
        lambda f: f.quick_flip_share_30s,
        lambda g: g.max_quick_flip_share_30s,
    ),
    # T4.80 (R65/KB-0147): the judged minute's buy count against the ceiling.
    "buys_1m_above_max": (lambda f: f.buys_1m, lambda g: g.max_buys_1m),
}
"""One entry per refusal name this revision already decodes into a numeric
pair (docs/DATABASE.md §54.2's own example, ``snipers_above_max``). A name
absent here — most refusals, including every *unknown* one (``*_unknown``)
and every boolean one (``creator_is_net_seller``, ``mayhem_curve``…) — is not
a coding gap: those refusals have no single number to show, and
:func:`decode_value_limit` answers ``(None, None)`` for them, same as the
schema already allows."""


def decode_value_limit(
    refusal: str, features: EntryFeatures, gate: EntryGate
) -> tuple[_Numeric, _Numeric]:
    """The number the gate read and the threshold it judged it against, for a
    near-miss's one named refusal — ``(None, None)`` when ``refusal`` is not
    in :data:`_NUMERIC_REFUSALS` (not yet decoded, or nothing numeric to
    show)."""
    decoder = _NUMERIC_REFUSALS.get(refusal)
    if decoder is None:
        return None, None
    value_of, limit_of = decoder
    return value_of(features), limit_of(gate)
