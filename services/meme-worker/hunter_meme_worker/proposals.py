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
from hunter_indicators.meme.rules import EntryFeatures, evaluate_entry, participation_pct
from hunter_meme_worker.lab_models import RuleSetSpec, Snapshot, money_str, optional_money_str

__all__ = ["GateOutcome", "GateRow", "ProposalDraft", "evaluate_gate"]

HUNDRED = Decimal(100)
REFUSAL_ALREADY_OPEN = "already_open"
REFUSAL_NO_SNAPSHOT_FOR_QUOTE = "no_snapshot_for_quote"


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


def _entry_features(row: GateRow, spec: RuleSetSpec) -> EntryFeatures:
    return EntryFeatures(
        mint=row.mint,
        age_s=_age_s(row),
        progress_pct=_progress_pct(row.curve_progress_pct),
        creator_net_seller=row.creator_sold,
        curve_volume_1m_sol=row.curve_volume_1m_sol,
        intended_size_sol=spec.size_sol,
        curve_complete=row.completed_at is not None,
        migrated=row.migrated_at is not None,
    )


def _quote(row: GateRow, snapshot: Snapshot, spec: RuleSetSpec) -> dict[str, Any]:
    """The snapshot the desk sees, and what ``size_sol`` would cost **with** the fee.

    The keys are the ones the desk reads (contract, Emendas of T4.7):
    ``observed_at``, ``source``, ``mcap_sol``, ``curve_progress_pct``,
    ``price_sol_per_token``, ``size_sol``, ``fee_pct``, ``fee_sol``, ``cost_sol``,
    ``tokens``, ``reason`` — plus the reserves, so the number can be re-derived.
    """
    cost = quote_buy(snapshot.reserves, spec.size_sol, spec.fee_pct)
    progress = _progress_pct(row.curve_progress_pct)
    return {
        **snapshot.as_json(),
        "mcap_sol": optional_money_str(row.mcap_sol),
        "curve_progress_pct": optional_money_str(progress),
        "price_sol_per_token": money_str(marginal_price_sol(snapshot.reserves)),
        "size_sol": money_str(spec.size_sol),
        "fee_pct": money_str(spec.fee_pct),
        "curve_cost_sol": money_str(cost.curve_cost_sol),
        "fee_sol": money_str(cost.fee_sol),
        "cost_sol": money_str(cost.total_sol),
        "tokens": money_str(cost.tokens),
        "reason": None,
    }


def _reasons(features: EntryFeatures, spec: RuleSetSpec) -> list[dict[str, Any]]:
    """Which rule fired and the value of every feature it read — the decomposition."""
    gate = spec.gate
    share = participation_pct(features.intended_size_sol, features.curve_volume_1m_sol)
    progress = features.progress_pct
    return [
        {"rule": f"{gate.key}/{gate.version}"},
        {"feature": "age_s", "value": features.age_s, "window": [gate.min_age_s, gate.max_age_s]},
        {
            "feature": "curve_progress_pct",
            "value": optional_money_str(progress),
            "window": [money_str(gate.min_progress_pct), money_str(gate.max_progress_pct)],
        },
        {"feature": "creator_net_seller", "value": features.creator_net_seller},
        {
            "feature": "participation_pct",
            "value": optional_money_str(share),
            "cap": money_str(gate.max_participation_pct),
        },
    ]


def evaluate_gate(
    spec: RuleSetSpec,
    rows: Iterable[GateRow],
    *,
    now: datetime,
    ttl_s: int,
    already_open: Mapping[str, Any] | frozenset[str] | set[str],
) -> GateOutcome:
    """Every row of one closed minute through the gate of one rule set."""
    drafts: list[ProposalDraft] = []
    refusals: Counter[str] = Counter()
    evaluated = 0
    for row in rows:
        evaluated += 1
        if row.mint in already_open:
            refusals[REFUSAL_ALREADY_OPEN] += 1
            continue
        features = _entry_features(row, spec)
        decision = evaluate_entry(features, spec.gate)
        if not decision.allowed:
            refusals.update(decision.refusals)
            continue
        if row.snapshot is None:
            refusals[REFUSAL_NO_SNAPSHOT_FOR_QUOTE] += 1
            continue
        research = spec.kind == "research_only"
        suggested = spec.suggested()
        drafts.append(
            ProposalDraft(
                id=str(uuid7()),
                mint=row.mint,
                rule_set_id=spec.id,
                origin="rules",
                status="approved" if research else "proposed",
                proposed_at=now,
                expires_at=now + timedelta(seconds=ttl_s),
                features_end_time=row.end_time,
                quote=_quote(row, row.snapshot, spec),
                reasons=_reasons(features, spec),
                suggested=suggested,
                decision=dict(suggested) if research else None,
                decided_by="rules" if research else None,
                decided_at=now if research else None,
            )
        )
    return GateOutcome(drafts=drafts, refusals=refusals, evaluated=evaluated)
