"""The probe -> scale step of one gate pass (T4.10, EXP-M3), extracted from
``lab.py`` the same way ``lab_fast.py`` carries the 15-second step: one
function ``_gate_step`` calls per minute, over the DB session it already
opened.

For every set that scales, the open probes not yet scaled are judged by the
line set's gate on this minute's rows — the pure decision lives in
``proposals_scale.evaluate_scale``; this module is only the read/write shell
around it (``lab_repo_lines`` for the open probes and what already scaled,
``lab_repo.insert_proposals`` for the result).
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from hunter_meme_worker.lab_repo import insert_proposals
from hunter_meme_worker.lab_repo_lines import open_probes_for, scaled_parent_ids
from hunter_meme_worker.proposals_scale import REFUSAL_SCALE_GATE_INACTIVE, evaluate_scale

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.lab import LabContext
    from hunter_meme_worker.lab_models import RuleSetSpec
    from hunter_meme_worker.proposals import GateRow

__all__ = ["scale_step"]


async def scale_step(
    ctx: LabContext,
    session: AsyncSession,
    specs: list[RuleSetSpec],
    rows: list[GateRow],
    refusals: dict[str, Counter[str]],
    *,
    now: datetime,
) -> int:
    """T4.10: for every set that scales, the open probes not yet scaled are
    judged by the line set's gate on this minute's rows (``proposals_scale``)."""
    by_label = {spec.label: spec for spec in specs}
    inserted = 0
    for spec in specs:
        if not spec.scales or spec.scale_gate is None:
            continue
        trend = by_label.get(spec.scale_gate)
        if trend is None:
            refusals[spec.name][REFUSAL_SCALE_GATE_INACTIVE] += 1
            continue
        probes = await open_probes_for(session, spec.id)
        if not probes:
            continue
        outcome = evaluate_scale(
            spec,
            trend,
            rows,
            open_probes=probes,
            already_scaled=await scaled_parent_ids(session, spec.id),
            now=now,
            ttl_s=ctx.config.lab_proposal_ttl_s,
        )
        refusals[spec.name].update(outcome.refusals)
        inserted += await insert_proposals(session, outcome.drafts)
    return inserted
