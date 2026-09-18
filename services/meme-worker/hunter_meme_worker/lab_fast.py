"""The 15-second gate step of the Lab tick (T4.16): every rule set whose
``clock`` is ``15s`` over every row of ``meme_features_15s`` this process has
not judged yet (``as_of`` inside the last ``lab_fast_backlog_s``, at or before
the tick), the pedigree of the mints read once per step, proposals inserted
through the same ``insert_proposals`` as the minute gate — one proposal per
``(rule_set, mint, as_of)`` by the schema's own unique index.

The fill is the minute loop's own (``lab_bets.fill_approved``): the first
photo with ``observed_at > decided_at`` — on a young mint, the fast lane's
next 15-second photo. Nothing here reads a clock: ``now`` is the tick's.

**T4.43 — the per-mint refusal trail.** ``evaluate_gate`` is now called once
per row instead of once per batch (behaviour-preserving: the gate's loop body
depends on no other row) so this step sees each row's own refusals, not only
the tick-wide count; the drafts stay batched into one ``insert_proposals``
per rule set, same as before. For every row, ``_trail_row`` turns that row's
refusals into at most one ``meme_gate_refusals_by_mint`` candidate — a
proposal (zero refusals) or a near-miss (exactly one, R27's own definition:
refused at the last criterion the gate would have checked, one step short of
a proposal). ``already_open`` is excluded on purpose: it fires *before* the
gate reads a single criterion (an open position, not a judgement), so an
open bet re-evaluated every tick would not teach "why not" and would drown
the cap in a name that is not a gate refusal at all. All the candidates of
the tick — every set, every row — are written once, capped, at the end
(``lab_trail.write_refusal_trail``)."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_meme_worker.event_gate_caches import refresh_event_gate_caches
from hunter_meme_worker.gate_refusal_trail import (
    RefusalTrailRow,
    decode_value_limit,
    select_trail_row,
)
from hunter_meme_worker.lab_repo import open_mints_for
from hunter_meme_worker.lab_repo_e2b import lineage_for
from hunter_meme_worker.lab_repo_fast import fast_window, load_fast_gate_rows
from hunter_meme_worker.lab_trail import write_refusal_trail
from hunter_meme_worker.proposal_race import insert_proposals_reserved
from hunter_meme_worker.proposals import (
    REFUSAL_ALREADY_OPEN,
    GateRow,
    entry_features_of,
    evaluate_gate,
)

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_meme_worker.lab import LabContext
    from hunter_meme_worker.lab_models import RuleSetSpec
    from hunter_meme_worker.proposals import ProposalDraft

WORKER_ROLE = "hunter_worker"

__all__ = ["fast_gate_step"]


def _trail_row(spec: RuleSetSpec, row: GateRow, refusals: Counter[str]) -> RefusalTrailRow | None:
    """One row's own refusals → at most one trail candidate. ``None`` for two
    or more failed criteria (:func:`~.gate_refusal_trail.is_trail_candidate`)
    and for ``already_open`` (a structural skip, not a criterion — see the
    module docstring)."""
    names = tuple(refusals.elements())
    if names == (REFUSAL_ALREADY_OPEN,):
        return None
    trail = select_trail_row(as_of=row.end_time, rule_set_id=spec.id, mint=row.mint, refusals=names)
    if trail is None or trail.refusal is None:
        return trail
    value, limit = decode_value_limit(trail.refusal, entry_features_of(row, spec), spec.gate)
    return replace(trail, value=value, limit=limit)


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
    trail_candidates: list[RefusalTrailRow] = []
    open_mints_by_spec: dict[str, frozenset[str]] = {}
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        rows = await load_fast_gate_rows(
            session, since=since, until=now, features_version=ctx.config.features_15s_version
        )
        if not rows:
            return 0, 0
        # T4.31 (EXP-M9): the E2-b tape is bounded by each row's own instant,
        # never by the tick's clock — a backlog row would read the future.
        pedigree, e2b = await lineage_for(session, rows, fast)
        for spec in fast:
            open_mints_by_spec[spec.id] = already_open = await open_mints_for(session, spec.id)
            if ctx.caches is not None:  # T4.52b-3: the event gate's own inserts count too
                already_open = already_open | ctx.caches.recently_proposed_mints(spec.id, now=now)
            drafts: list[ProposalDraft] = []
            spec_refusals: Counter[str] = Counter()
            for row in rows:
                outcome = evaluate_gate(
                    spec,
                    [row],
                    now=now,
                    ttl_s=ctx.config.lab_proposal_ttl_s,
                    already_open=already_open,
                    pedigree=pedigree,
                    e2b=e2b,
                )
                spec_refusals.update(outcome.refusals)
                drafts.extend(outcome.drafts)
                candidate = _trail_row(spec, row, outcome.refusals)
                if candidate is not None:
                    trail_candidates.append(candidate)
            refusals.setdefault(spec.name, Counter()).update(spec_refusals)
            rows_total += len(rows)
            ttl = ctx.config.lab_proposal_ttl_s if spec.ttl_s is None else spec.ttl_s
            # T4.52b-4 (race fix): reserve each mint before its own insert
            # awaits, not after the whole batch — closes the window the event
            # lane could otherwise land a duplicate proposal in.
            inserted = await insert_proposals_reserved(
                session, ctx.caches, spec.id, drafts, now=now, ttl_s=ttl
            )
            proposals_total += inserted
        await write_refusal_trail(session, ctx.state.trail, trail_candidates)
    if ctx.caches is not None:
        refresh_event_gate_caches(
            ctx.caches,
            specs=fast,
            rows=rows,
            open_mints=open_mints_by_spec,
            pedigree=pedigree,
            e2b=e2b,
            now=now,
        )
    ctx.state.last_fast_as_of = max(row.end_time for row in rows)
    return rows_total, proposals_total
