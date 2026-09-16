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

**Not yet wired into the fast lane's tick** (T4.35's own scope note): the
selector and the cap below are pure and fully tested; the call site inside
``lab_fast.fast_gate_step`` needs either ``proposals.evaluate_gate`` to expose
a row's own refusal count (it currently only returns a tick-wide aggregate)
or one ``evaluate_gate`` call per row instead of per batch (behaviour-
preserving — the loop body depends on no other row — but a control-flow
change to a hot loop this task's file-level constraints put out of reach:
``proposals.py`` is another agent's file this session, and ``lab.py``/
``config.py`` already sit at the 350-line budget, so carrying the two new
heartbeat counters through ``LabState``/``MemeConfig`` needs a split first).
See ``.claude/state/notes-T4.35.md`` for the one-paragraph plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["RefusalTrailRow", "cap_trail_rows", "is_trail_candidate", "select_trail_row"]

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
