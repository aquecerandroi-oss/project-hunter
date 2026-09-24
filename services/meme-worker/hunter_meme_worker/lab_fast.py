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
(``lab_trail.write_refusal_trail``).

**T4.85 (EXP-M23) — the refused probe rides on the same loop.** The same
per-row ``evaluate_gate`` that feeds the trail also feeds
``refused_probe_step``: for an ``operator`` set, every refusal **by a
criterion** becomes an opportunity, and the mints any arm admitted this
instant are collected beside them, **with the instant** (an admission that
came later than a refusal cannot cancel it — that would be look-ahead, and
it would make the population depend on how the backlog was batched). Both
are known here and nowhere else, so the probe costs the tick one bounded
read and, on the rare tick that draws a mint, one insert per draw.

``_probe_step`` runs in its **own** transaction, opened after the desk's has
committed, and swallows its own failure: ``role_session`` is one
transaction, so a statement timeout inside the desk's block would have
rolled the desk's own proposals back. The arm is ``research_only`` and its
paper bets are subtracted from the desk's pedigree read
(``lab_repo_fast._PEDIGREE``), so nothing on a money path changes."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_worker.entry_pullback import EVENT_LANE_ONLY
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
from hunter_meme_worker.proposal_race import insert_proposals_reserved, reserve_all
from hunter_meme_worker.proposals import (
    REFUSAL_ALREADY_OPEN,
    GateRow,
    entry_features_of,
    evaluate_gate,
)
from hunter_meme_worker.refused_probe import RefusedRow
from hunter_meme_worker.refused_probe_step import (
    probe_spec_of,
    refused_row_of,
    run_refused_probe,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from hunter_indicators.meme.pedigree import PedigreeFeatures
    from hunter_indicators.meme.pedigree_e2b import E2bFeatures
    from hunter_meme_worker.lab import LabContext
    from hunter_meme_worker.lab_models import RuleSetSpec
    from hunter_meme_worker.proposals import ProposalDraft

logger = get_logger(__name__)

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


async def _probe_step(
    ctx: LabContext,
    specs: list[RuleSetSpec],
    *,
    rows: list[GateRow],
    refused: list[RefusedRow],
    admitted: dict[str, datetime],
    now: datetime,
    pedigree: Mapping[str, PedigreeFeatures] | None,
    e2b: Mapping[tuple[str, datetime], E2bFeatures] | None,
) -> None:
    """EXP-M23's arm, in its own transaction and with its own failure.

    ``pedigree`` and ``e2b`` are the values the desk's session already read
    for this very tick — plain dataclasses, not rows of a closed transaction —
    so the probe's decomposition carries the same blocks the desk read without
    a second query on the fast lane."""
    spec = probe_spec_of(specs)
    if spec is None or not refused:
        return
    try:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await run_refused_probe(
                session,
                ctx.state.probe,
                spec,
                rows=rows,
                refused=refused,
                admitted=admitted,
                now=now,
                ttl_s=ctx.config.lab_proposal_ttl_s,
                pedigree=pedigree,
                e2b=e2b,
            )
    except Exception as exc:
        logger.warning("meme_refused_probe_failed", error=type(exc).__name__, detail=str(exc))


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
    # T4.85 (EXP-M23): what the desk's gate refused this tick, and who any arm
    # admitted — the two halves of the probe's population, both already known
    # here and nowhere else.
    refused_rows: list[RefusedRow] = []
    admitted: dict[str, datetime] = {}
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
                if outcome.drafts and spec.entry_pullback is not None:
                    # T4.91: a pullback set waits on the live tape - only the event lane
                    # arms it; no draft, no trail row, no probe population here.
                    spec_refusals[EVENT_LANE_ONLY] += len(outcome.drafts)
                    continue
                spec_refusals.update(outcome.refusals)
                drafts.extend(outcome.drafts)
                candidate = _trail_row(spec, row, outcome.refusals)
                if candidate is not None:
                    trail_candidates.append(candidate)
                if spec.kind == "operator":
                    refused = refused_row_of(spec, row, outcome.refusals)
                    if refused is not None:
                        refused_rows.append(refused)
            for draft in drafts:  # the earliest instant any arm took this mint
                at = draft.features_end_time
                if admitted.get(draft.mint, at) >= at:
                    admitted[draft.mint] = at
            refusals.setdefault(spec.name, Counter()).update(spec_refusals)
            rows_total += len(rows)
            ttl = ctx.config.lab_proposal_ttl_s if spec.ttl_s is None else spec.ttl_s
            # T4.52b-4 (race fix): reserve each mint before its own insert
            # awaits, not after the whole batch — closes the window the event
            # lane could otherwise land a duplicate proposal in.
            reserve_all(ctx.caches, spec.id, drafts, now=now, ttl_s=ttl)
            inserted = await insert_proposals_reserved(
                session, ctx.caches, spec.id, drafts, now=now, ttl_s=ttl
            )
            proposals_total += inserted
        await write_refusal_trail(session, ctx.state.trail, trail_candidates)
    # T4.85 (EXP-M23), after Astra's review of 23/09/2026: the probe runs in
    # its **own** transaction, opened after the desk's has committed, and its
    # failure is contained here. ``role_session`` is one transaction
    # (``hunter_core.db.session``), so a statement timeout on the probe's read
    # inside the block above would have rolled back ``operator/5`` and
    # ``operator/6``'s proposals of this tick — an experiment undoing the
    # desk's work. It never runs before the real inserts are durable, and a
    # raise here costs the tick nothing.
    await _probe_step(
        ctx,
        specs,
        rows=rows,
        refused=refused_rows,
        admitted=admitted,
        now=now,
        pedigree=pedigree,
        e2b=e2b,
    )
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
