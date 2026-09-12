"""The gate step: one closed minute of ``meme_features_1m`` → proposals, or
named refusals counted — never a silent zero.

Contract §Semântica 1: for every active rule set the gate
(``hunter_indicators.meme.rules.evaluate_entry``, T4.5) is evaluated over the
rows of a minute that has **closed** (``end_time <= now − 1 min``, chosen by the
loop, stamped here as ``features_end_time``). A ``research_only`` proposal is
born already ``approved`` with ``decision = suggested`` and ``decided_by =
'rules'``; an ``operator`` proposal is born ``proposed`` and waits for the desk.

Two readings this module fixes so the gate judges what T4.2 actually wrote:

- ``curve_progress_pct`` is stored as a **fraction** (``0.16`` = 16 %) and the
  gate's window is in **percent** (2–50); the conversion is here, once;
- ``age_s`` is ``end_time − meme_tokens.created_at`` in seconds, not
  ``age_minutes × 60``: a token 45 s old is not 0 minutes old.

What it will not do: read a missing feed as a fine one. ``creator_sold`` is
``NULL`` with ``no_holders_reader`` in every row today and the curve's minute
volume has no producer, so the frozen EXP-M1 gate refuses every row by name
(``creator_net_seller_unknown``, ``curve_volume_1m_unknown``). The loop counts
those refusals into the heartbeat and ``GET /meme/lab``, which is how "nothing
proposed" becomes a measured fact instead of an empty desk.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any

from hunter_core.domain.types import uuid7
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import marginal_price_sol, quote_buy
from hunter_indicators.meme.pedigree import PEDIGREE_V1, PedigreeFeatures, evaluate_pedigree
from hunter_indicators.meme.rules import EntryFeatures, evaluate_entry
from hunter_meme_worker.lab_models import RuleSetSpec, Snapshot, money_str, optional_money_str
from hunter_meme_worker.proposals_plan import manual_plan, ticker_of
from hunter_meme_worker.proposals_reasons import gate_reasons

__all__ = [
    "SERIES_15S",
    "GateOutcome",
    "GateRow",
    "ProposalDraft",
    "draft_proposal",
    "entry_features_of",
    "evaluate_gate",
    "gate_reasons",
    "quote_for",
]

HUNDRED = Decimal(100)
REFUSAL_ALREADY_OPEN = "already_open"
REFUSAL_NO_SNAPSHOT_FOR_QUOTE = "no_snapshot_for_quote"
SERIES_15S = "meme_features_15s_v1"
"""The series a 15-second row names in ``reasons[0]`` (T4.16): the desk can
tell a proposal judged per photo from one judged per closed minute."""


@dataclass(frozen=True, slots=True)
class GateRow:
    """One ``meme_features_1m`` row joined with its token and its snapshot."""

    mint: str
    end_time: datetime
    created_at: datetime | None
    curve_progress_pct: Decimal | None
    """A fraction, as T4.2 stores it; ``None`` with ``progress_reason``."""
    progress_reason: str | None
    mcap_sol: Decimal | None
    creator_sold: bool | None
    curve_volume_1m_sol: Decimal | None
    """No producer today (``no_trade_feed``); the column is here so the day a
    trade feed lands the gate needs no change."""
    completed_at: datetime | None
    migrated_at: datetime | None
    snapshot: Snapshot | None
    """The snapshot the minute was folded from (``snapshot_observed_at``)."""
    higher_lows: bool | None = None
    breakout_15m: bool | None = None
    distance_to_support_pct: Decimal | None = None
    line_reason: str | None = None
    hype_score: Decimal | None = None
    hype_reason: str | None = None
    dev_share: Decimal | None = None
    dev_share_reason: str | None = None
    snipers: int | None = None
    """T4.10 (``0026``): the line and the hype of the minute — read by the
    EXP-M2/EXP-M3 gates, ignored by a gate that does not ask."""
    net_sol_flow_1m: Decimal | None = None
    mcap_delta_60s: Decimal | None = None
    buys_1m: int | None = None
    sells_1m: int | None = None
    unique_buyers_1m: int | None = None
    tape_reason: str | None = None
    holders_rising: bool | None = None
    holders_reason: str | None = None
    progress_rising: bool | None = None
    holders: int | None = None
    holders_prev: int | None = None
    """T4.21: the two holders readings behind ``holders_rising`` (arm 2's floor and 'not falling')."""
    """T4.16: the flow of the minute (or of the last 60 s on the 15-second
    series) and the two trends — read by the EXP-M5 gate."""
    series: str | None = None
    """``None`` for a closed minute of ``meme_features_1m``; ``SERIES_15S`` for
    a row of the 15-second series, where ``end_time`` is the instant judged."""
    symbol: str | None = None
    """T4.19: the token's ticker, named in the operator's ``manual_plan``;
    ``None`` (identity never came) reads as the mint abbreviated."""


@dataclass(frozen=True, slots=True)
class ProposalDraft:
    """One ``meme_proposals`` row to insert."""

    id: str
    mint: str
    rule_set_id: str
    origin: str
    status: str
    proposed_at: datetime
    expires_at: datetime
    features_end_time: datetime
    quote: dict[str, Any]
    reasons: list[dict[str, Any]]
    suggested: dict[str, Any]
    decision: dict[str, Any] | None
    decided_by: str | None
    decided_at: datetime | None


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """What one minute produced for one rule set, refusals counted by name."""

    drafts: list[ProposalDraft]
    refusals: Counter[str] = field(default_factory=Counter[str])
    evaluated: int = 0


def _age_s(row: GateRow) -> int | None:
    if row.created_at is None or row.created_at > row.end_time:
        return None
    return int((row.end_time - row.created_at).total_seconds())


def _progress_pct(fraction: Decimal | None) -> Decimal | None:
    if fraction is None:
        return None
    with localcontext(CONTEXT):
        return fraction * HUNDRED


def entry_features_of(
    row: GateRow, spec: RuleSetSpec, *, size_sol: Decimal | None = None
) -> EntryFeatures:
    """The row as ``spec``'s gate reads it, sized ``size_sol`` (default: the set's)."""
    return EntryFeatures(
        mint=row.mint,
        age_s=_age_s(row),
        progress_pct=_progress_pct(row.curve_progress_pct),
        creator_net_seller=row.creator_sold,
        curve_volume_1m_sol=row.curve_volume_1m_sol,
        intended_size_sol=spec.size_sol if size_sol is None else size_sol,
        curve_complete=row.completed_at is not None,
        migrated=row.migrated_at is not None,
        higher_lows=row.higher_lows,
        breakout_15m=row.breakout_15m,
        distance_to_support_pct=row.distance_to_support_pct,
        line_reason=row.line_reason,
        hype_score=row.hype_score,
        hype_reason=row.hype_reason,
        dev_share=row.dev_share,
        dev_share_reason=row.dev_share_reason,
        snipers=row.snipers,
        net_sol_flow_1m=row.net_sol_flow_1m,
        mcap_delta_60s=row.mcap_delta_60s,
        buys_1m=row.buys_1m,
        sells_1m=row.sells_1m,
        unique_buyers_1m=row.unique_buyers_1m,
        tape_reason=row.tape_reason,
        holders_rising=row.holders_rising,
        holders_reason=row.holders_reason,
        progress_rising=row.progress_rising,
        holders=row.holders,
        holders_prev=row.holders_prev,
    )


def quote_for(
    row: GateRow, snapshot: Snapshot, spec: RuleSetSpec, *, size_sol: Decimal | None = None
) -> dict[str, Any]:
    """The snapshot the desk sees, and what ``size_sol`` would cost **with** the fee.

    The keys are the ones the desk reads (contract, Emendas of T4.7):
    ``observed_at``, ``source``, ``mcap_sol``, ``curve_progress_pct``,
    ``price_sol_per_token``, ``size_sol``, ``fee_pct``, ``fee_sol``, ``cost_sol``,
    ``tokens``, ``reason`` — plus the reserves, so the number can be re-derived.
    """
    size = spec.size_sol if size_sol is None else size_sol
    cost = quote_buy(snapshot.reserves, size, spec.fee_pct)
    progress = _progress_pct(row.curve_progress_pct)
    return {
        **snapshot.as_json(),
        "mcap_sol": optional_money_str(row.mcap_sol),
        "curve_progress_pct": optional_money_str(progress),
        "price_sol_per_token": money_str(marginal_price_sol(snapshot.reserves)),
        "size_sol": money_str(size),
        "fee_pct": money_str(spec.fee_pct),
        "curve_cost_sol": money_str(cost.curve_cost_sol),
        "fee_sol": money_str(cost.fee_sol),
        "cost_sol": money_str(cost.total_sol),
        "tokens": money_str(cost.tokens),
        "reason": None,
    }


def evaluate_gate(
    spec: RuleSetSpec,
    rows: Iterable[GateRow],
    *,
    now: datetime,
    ttl_s: int,
    already_open: Mapping[str, Any] | frozenset[str] | set[str],
    pedigree: Mapping[str, PedigreeFeatures] | None = None,
) -> GateOutcome:
    """Every row of one instant (a closed minute, or a 15-second row) through
    the gate of one rule set.

    ``pedigree`` (T4.16, EXP-M6) is the two counts per mint at proposal time,
    read by the caller (the loop always reads them); a set with
    ``pedigree_exclusions`` refuses ``creator_serial`` / ``symbol_clone`` — or
    the unknowns by name — **alongside** its own gate's refusals (both are
    counted: a row excluded by its pedigree still tells the heartbeat what the
    gate would have said), and a mint absent from the mapping is a mint whose
    pedigree was not read (``pedigree_unknown``), never a clean one. ``None``
    means the caller did not ask (the scale step, a unit test of the gate
    alone): the exclusions are not applied.

    ``ttl_s`` is the loop's; a set that names its own (T4.19, ``operator/3``:
    180 s for a buy by hand) overrides it. An ``operator`` proposal also
    carries ``suggested.manual_plan``, written now from the set's params.
    """
    drafts: list[ProposalDraft] = []
    refusals: Counter[str] = Counter()
    evaluated = 0
    ttl = ttl_s if spec.ttl_s is None else spec.ttl_s
    for row in rows:
        evaluated += 1
        if row.mint in already_open:
            refusals[REFUSAL_ALREADY_OPEN] += 1
            continue
        lineage: PedigreeFeatures | None = None
        excluded: tuple[str, ...] = ()
        if spec.pedigree_exclusions and pedigree is not None:
            lineage = pedigree.get(row.mint)
            excluded = (
                ("pedigree_unknown",)
                if lineage is None
                else evaluate_pedigree(lineage, PEDIGREE_V1)
            )
        features = entry_features_of(row, spec)
        decision = evaluate_entry(features, spec.gate)
        if excluded or not decision.allowed:
            refusals.update((*excluded, *decision.refusals))
            continue
        if row.snapshot is None:
            refusals[REFUSAL_NO_SNAPSHOT_FOR_QUOTE] += 1
            continue
        suggested = spec.suggested()
        if spec.kind == "operator":
            suggested["manual_plan"] = manual_plan(
                spec, ticker=ticker_of(row.symbol, row.mint), proposed_at=now, ttl_s=ttl
            )
        drafts.append(
            draft_proposal(
                row,
                spec,
                quote=quote_for(row, row.snapshot, spec),
                reasons=gate_reasons(
                    features,
                    spec,
                    pedigree=lineage,
                    pedigree_gate=PEDIGREE_V1 if lineage is not None else None,
                    series=row.series,
                ),
                suggested=suggested,
                now=now,
                ttl_s=ttl,
            )
        )
    return GateOutcome(drafts=drafts, refusals=refusals, evaluated=evaluated)


def draft_proposal(
    row: GateRow,
    spec: RuleSetSpec,
    *,
    quote: dict[str, Any],
    reasons: list[dict[str, Any]],
    suggested: dict[str, Any],
    now: datetime,
    ttl_s: int,
) -> ProposalDraft:
    """A ``research_only`` proposal is born approved by ``rules``; an
    ``operator`` one is born ``proposed`` and waits for the desk."""
    research = spec.kind == "research_only"
    return ProposalDraft(
        id=str(uuid7()),
        mint=row.mint,
        rule_set_id=spec.id,
        origin="rules",
        status="approved" if research else "proposed",
        proposed_at=now,
        expires_at=now + timedelta(seconds=ttl_s),
        features_end_time=row.end_time,
        quote=quote,
        reasons=reasons,
        suggested=suggested,
        decision=dict(suggested) if research else None,
        decided_by="rules" if research else None,
        decided_at=now if research else None,
    )
