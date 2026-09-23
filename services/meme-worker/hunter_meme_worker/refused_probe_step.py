"""The lane that turns a refusal into a paper bet (T4.85, EXP-M23).

One step, hung off the end of the 15-second tick (``lab_fast.fast_gate_step``)
because that is where the desk's gate says no: the rows are already loaded,
the pedigree and the E2-b tape are already read, and the mints admitted by the
other arms of the same tick are already known. The step adds **one** bounded
read (which of these mints this arm has ever proposed) and, on the rare tick
that draws one, one insert.

From the insert on, nothing here is special: a ``research_only`` proposal is
born ``approved`` (``proposals.draft_proposal``), ``lab_bets.fill_approved``
prices it on the **first photo after the decision** and
``lab_bets.process_open_bets`` marks and closes it under the same exit rules,
the same fee and the same censoring as every other bet in the Lab. That
sameness *is* the experiment: EXP-M23's "simetria obrigatória" — same
simulator, same costs, same follow-up for admitted and refused, with censoring
and non-executability recorded as results (``unfilled`` with a name,
``indeterminate``) instead of dropped.

**Paper by construction, not by flag.** ``hunter_meme_executor.auto_approve``
only ever opens proposals of a set whose ``kind`` is ``operator``; this arm is
``research_only``, so no code path can turn one of these into an order.

**The control arm is not seeded here** — it already exists. Every approved
``operator/6`` proposal also becomes a ``meme_paper_bets`` row through the
same ``fill_approved`` (``lab_repo.load_approved_proposals`` does not filter by
``kind``), with 0,07 SOL, 1,15×, 300 s, trailing 10 % armed at the entry and
``exit_on_line_break``. Those are the contemporaneous admitted bets with the
same parameters that the pre-registration asks for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.logging import get_logger
from hunter_indicators.meme.pedigree import PEDIGREE_V1
from hunter_meme_worker.lab_repo import insert_proposals
from hunter_meme_worker.proposals import (
    draft_proposal as _draft_proposal,
)
from hunter_meme_worker.proposals import (
    entry_features_of,
    gate_reasons,
    quote_for,
)
from hunter_meme_worker.proposals_identity import event_features_of, identity_features_of
from hunter_meme_worker.refused_probe import (
    PROBE_CLOCK,
    ProbePick,
    RefusedRow,
    criteria_refusals,
    first_opportunities,
    pick_probes,
    probe_reason_block,
)

if TYPE_CHECKING:
    from collections import Counter
    from collections.abc import Iterable, Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_indicators.meme.pedigree import PedigreeFeatures
    from hunter_indicators.meme.pedigree_e2b import E2bFeatures
    from hunter_meme_worker.lab_models import RuleSetSpec
    from hunter_meme_worker.proposals import GateRow, ProposalDraft

__all__ = [
    "MEMORY_S",
    "RefusedProbeState",
    "probe_drafts",
    "probe_spec_of",
    "refused_row_of",
    "run_refused_probe",
]

logger = get_logger(__name__)

MEMORY_S = 3_600
"""How long a decided mint stays in the in-process memory. The 15-second lane
holds a mint for at most ~300 s, so an hour is generous; the memory exists to
stop a mint from getting a second lottery, not to be a cache."""

_PROBED = text(
    "SELECT mint FROM meme_proposals WHERE rule_set_id = :rule_set_id AND mint = ANY(:mints)"
)
"""The durable half of "one bet per mint, ever": the in-process memory dies
with the worker, this row does not. Bounded by the tick's own candidate list,
which the lottery has not been run on yet."""


@dataclass
class RefusedProbeState:
    """What survives between ticks — and nothing a restart could not rebuild."""

    drawn: dict[str, datetime] = field(default_factory=dict[str, datetime])
    """Mints whose lottery has already been decided, drawn or not. A mint must
    not be re-drawn: re-drawing every 15 s would make its true inclusion
    probability the **maximum** over its opportunities while the bet would
    carry the rate of the entering one, and the inverse-probability weights of
    the analysis would be wrong by up to two orders of magnitude."""
    considered_total: int = 0
    proposals_total: int = 0
    unquotable_total: int = 0
    """Refusal instants with no photo to price a fill against. They are not an
    opportunity (there is nothing to quote), and EXP-M23 forbids a silent
    exclusion — so they are counted and named in the heartbeat instead of
    disappearing. Refutation rule 2 of the pre-registration is about exactly
    this kind of coverage artefact."""

    def remember(self, mints: Iterable[str], *, now: datetime) -> None:
        cutoff = now - timedelta(seconds=MEMORY_S)
        self.drawn = {mint: at for mint, at in self.drawn.items() if at > cutoff} | {
            mint: now for mint in mints
        }


def _admitted_by(admitted: Mapping[str, datetime], row: RefusedRow) -> bool:
    """An arm took this mint **at or before** this refusal instant. A later
    admission is the future and cannot cancel a bet already decided."""
    at = admitted.get(row.mint)
    return at is not None and at <= row.as_of


def probe_spec_of(specs: Sequence[RuleSetSpec]) -> RuleSetSpec | None:
    """The active set on this arm's own clock, or ``None`` — which is the whole
    lane's off switch before ``0060`` is applied."""
    for spec in specs:
        if spec.clock == PROBE_CLOCK and spec.status == "active":
            return spec
    return None


def refused_row_of(spec: RuleSetSpec, row: GateRow, refusals: Counter[str]) -> RefusedRow | None:
    """One judged instant of one ``operator`` set → an opportunity, or ``None``
    when the mint collected no refusal **by a criterion** at that instant."""
    names = criteria_refusals(refusals.elements())
    if not names:
        return None
    return RefusedRow(
        mint=row.mint,
        as_of=row.end_time,
        refusals=names,
        refused_by=spec.label,
        computed_at=row.computed_at,
        tape_as_of=row.tape_as_of,
        snapshot_observed_at=None if row.snapshot is None else row.snapshot.observed_at,
    )


def probe_drafts(
    spec: RuleSetSpec,
    picks: Sequence[ProbePick],
    rows: Mapping[tuple[str, datetime], GateRow],
    *,
    now: datetime,
    ttl_s: int,
    pedigree: Mapping[str, PedigreeFeatures] | None = None,
    e2b: Mapping[tuple[str, datetime], E2bFeatures] | None = None,
) -> list[ProposalDraft]:
    """One proposal per pick, priced on the photo of the **refusal instant**.

    ``reasons[0]`` is the probe's own block (every refusal reason, the
    stratum, the inclusion probability, the draw and the three provenance
    stamps); the rest is the ordinary decomposition, so the features on the
    bet are the ones readable at ``as_of`` and not one candle later.
    """
    drafts: list[ProposalDraft] = []
    for pick in picks:
        row = rows.get((pick.row.mint, pick.row.as_of))
        if row is None or row.snapshot is None:
            continue
        lineage = None if pedigree is None else pedigree.get(row.mint)
        drafts.append(
            _draft_proposal(
                row,
                spec,
                quote=quote_for(row, row.snapshot, spec),
                reasons=[
                    probe_reason_block(pick),
                    *gate_reasons(
                        entry_features_of(row, spec),
                        spec,
                        pedigree=lineage,
                        pedigree_gate=None if lineage is None else PEDIGREE_V1,
                        e2b=None if e2b is None else e2b.get((row.mint, row.end_time)),
                        series=row.series,
                        identity=identity_features_of(row),
                        event=event_features_of(row),
                    ),
                ],
                suggested=spec.suggested(),
                now=now,
                ttl_s=ttl_s,
            )
        )
    return drafts


async def _probed_mints(
    session: AsyncSession, rule_set_id: str, mints: list[str]
) -> frozenset[str]:
    rows = await session.execute(_PROBED, {"rule_set_id": rule_set_id, "mints": mints})
    return frozenset(str(mint) for mint in rows.scalars().all())


async def run_refused_probe(
    session: AsyncSession,
    state: RefusedProbeState,
    spec: RuleSetSpec | None,
    *,
    rows: Sequence[GateRow],
    refused: Sequence[RefusedRow],
    admitted: Mapping[str, datetime],
    now: datetime,
    ttl_s: int,
    pedigree: Mapping[str, PedigreeFeatures] | None = None,
    e2b: Mapping[tuple[str, datetime], E2bFeatures] | None = None,
) -> int:
    """Draw this tick's refused mints and write the proposals. ``0`` — and not
    a single statement — when the arm is not seeded or the tick refused
    nothing new."""
    if spec is None or not refused:
        return 0
    candidates = {
        row.mint
        for row in refused
        if row.mint not in state.drawn and not _admitted_by(admitted, row)
    }
    if not candidates:
        return 0
    probed = await _probed_mints(session, spec.id, sorted(candidates))
    opportunities = first_opportunities(
        refused, admitted=admitted, now=now, drawn=frozenset(state.drawn) | probed
    )
    state.remember((*(row.mint for row in opportunities), *probed), now=now)
    # Counted before any early return: a refusal nobody could price is a
    # result of EXP-M23 (its refutation rule 2), never a silent exclusion.
    state.unquotable_total += sum(1 for row in refused if row.snapshot_observed_at is None)
    if not opportunities:
        return 0
    state.considered_total += len(opportunities)
    picks = pick_probes(opportunities, admitted={}, now=now)
    if not picks:
        return 0
    index = {(row.mint, row.end_time): row for row in rows}
    ttl = ttl_s if spec.ttl_s is None else spec.ttl_s
    inserted = await insert_proposals(
        session, probe_drafts(spec, picks, index, now=now, ttl_s=ttl, pedigree=pedigree, e2b=e2b)
    )
    state.proposals_total += inserted
    logger.info(
        "meme_refused_probe_sampled",
        rule_set=spec.label,
        considered=len(opportunities),
        drawn=len(picks),
        proposals=inserted,
        strata=_strata_of(picks),
    )
    return inserted


def _strata_of(picks: Sequence[ProbePick]) -> dict[str, Any]:
    return {
        stratum: sum(1 for pick in picks if pick.stratum == stratum)
        for stratum in sorted({pick.stratum for pick in picks})
    }
