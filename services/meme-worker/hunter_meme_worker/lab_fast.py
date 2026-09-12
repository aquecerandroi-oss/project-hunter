"""The 15-second gate step of the Lab tick (T4.16): every rule set whose
``clock`` is ``15s`` over every row of ``meme_features_15s`` this process has
not judged yet (``as_of`` inside the last ``lab_fast_backlog_s``, at or before
the tick), the pedigree of the mints read once per step, proposals inserted
through the same ``insert_proposals`` as the minute gate — one proposal per
``(rule_set, mint, as_of)`` by the schema's own unique index.

The fill is the minute loop's own (``lab_bets.fill_approved``): the first
photo with ``observed_at > decided_at`` — on a young mint, the fast lane's
next 15-second photo. Nothing here reads a clock: ``now`` is the tick's.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_meme_worker.lab_repo import insert_proposals, open_mints_for
from hunter_meme_worker.lab_repo_fast import fast_window, load_fast_gate_rows, pedigree_for
from hunter_meme_worker.proposals import evaluate_gate

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_meme_worker.lab import LabContext
    from hunter_meme_worker.lab_models import RuleSetSpec

WORKER_ROLE = "hunter_worker"

__all__ = ["fast_gate_step"]


async def fast_gate_step(
    ctx: LabContext,
    specs: list[RuleSetSpec],
    refusals: dict[str, Counter[str]],
    *,
    now: datetime,
) -> tuple[int, int]:
    """``(rows evaluated, proposals inserted)`` for the sets on the 15-second clock."""
    fast = [spec for spec in specs if spec.clock == "15s"]
    if not fast:
        return 0, 0
    since = fast_window(now, ctx.state.last_fast_as_of, backlog_s=ctx.config.lab_fast_backlog_s)
    rows_total = proposals_total = 0
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        rows = await load_fast_gate_rows(
            session, since=since, until=now, features_version=ctx.config.features_15s_version
        )
        if not rows:
            return 0, 0
        pedigree = await pedigree_for(session, sorted({row.mint for row in rows}))
        for spec in fast:
            already_open = await open_mints_for(session, spec.id)
            outcome = evaluate_gate(
                spec,
                rows,
                now=now,
                ttl_s=ctx.config.lab_proposal_ttl_s,
                already_open=already_open,
                pedigree=pedigree,
            )
            refusals.setdefault(spec.name, Counter()).update(outcome.refusals)
            rows_total += outcome.evaluated
            proposals_total += await insert_proposals(session, outcome.drafts)
    ctx.state.last_fast_as_of = max(row.end_time for row in rows)
    return rows_total, proposals_total
