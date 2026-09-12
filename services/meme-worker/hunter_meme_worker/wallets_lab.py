"""``lab_context`` of a real buy (T4.12): what every active rule set's gate said
about that mint in the **last closed minute before the fill** — the answer to
"would the Lab have done the same?", written on the ledger row.

The row the gate reads is the same one the Lab tick reads (``lab_repo.
load_gate_rows``, the token and the folded snapshot joined), restricted to one
mint and to ``end_time <= block_time`` — the minute the fill could have been
decided on, never a later one (non-anticipation, the Lab's own rule). The
verdict per set is the gate's own (``hunter_indicators.meme.rules.
evaluate_entry`` through ``proposals.entry_features_of``): ``accepted`` or the
named refusals. A mint the fold never wrote a row for is ``no_features_row``
with every set ``accepted = null`` — the Lab did not see it, which is a fact,
not a refusal. The minute's ``hype_score``/``line_reason`` (T4.10a) ride along.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_indicators.meme.rules import evaluate_entry
from hunter_meme_worker.lab_rows import snapshot_from_row
from hunter_meme_worker.lab_values import optional_money_str
from hunter_meme_worker.proposals import GateRow, entry_features_of

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.lab_models import RuleSetSpec

__all__ = ["NO_FEATURES_ROW", "LabContext", "gate_row_from", "lab_context_for"]

NO_FEATURES_ROW = "no_features_row"

_LAB_ROW = text(
    "SELECT f.mint, f.end_time, f.curve_progress_pct, f.progress_reason, f.mcap_sol, "
    "       f.creator_net_seller, f.curve_volume_1m_sol, "
    "       f.snapshot_observed_at, f.snapshot_source, "
    "       f.higher_lows, f.breakout_15m, f.distance_to_support_pct, f.line_reason, "
    "       f.hype_score, f.hype_reason, f.dev_share, f.dev_share_reason, f.snipers, "
    "       t.created_at, t.completed_at, t.migrated_at, t.initial_real_token_reserves, "
    "       s.virtual_sol_reserves, s.virtual_token_reserves, s.real_sol_reserves, "
    "       s.real_token_reserves, s.total_supply, s.complete, s.mcap_sol AS snapshot_mcap_sol "
    "FROM meme_features_1m f "
    "JOIN meme_tokens t ON t.mint = f.mint "
    "LEFT JOIN meme_curve_snapshots s ON s.mint = f.mint "
    "  AND s.observed_at = f.snapshot_observed_at AND s.source = f.snapshot_source "
    "WHERE f.mint = :mint AND f.end_time <= :at AND f.features_version = :version "
    "ORDER BY f.end_time DESC LIMIT 1"
)


@dataclass(frozen=True, slots=True)
class LabContext:
    context: dict[str, Any]
    hype_score: Decimal | None
    line_reason: str | None


def gate_row_from(r: Mapping[Any, Any]) -> GateRow:
    """One ``_LAB_ROW`` result as the gate reads it (the ``load_gate_rows`` mapping)."""
    snapshot = None
    if r["virtual_sol_reserves"] is not None and r["virtual_token_reserves"] > 0:
        snapshot = snapshot_from_row(
            {**dict(r), "observed_at": r["snapshot_observed_at"], "source": r["snapshot_source"]}
        )
    return GateRow(
        mint=str(r["mint"]),
        end_time=r["end_time"],
        created_at=r["created_at"],
        curve_progress_pct=r["curve_progress_pct"],
        progress_reason=r["progress_reason"],
        mcap_sol=r["mcap_sol"],
        creator_sold=r["creator_net_seller"],
        curve_volume_1m_sol=r["curve_volume_1m_sol"],
        completed_at=r["completed_at"],
        migrated_at=r["migrated_at"],
        snapshot=snapshot,
        higher_lows=r["higher_lows"],
        breakout_15m=r["breakout_15m"],
        distance_to_support_pct=r["distance_to_support_pct"],
        line_reason=r["line_reason"],
        hype_score=r["hype_score"],
        hype_reason=r["hype_reason"],
        dev_share=r["dev_share"],
        dev_share_reason=r["dev_share_reason"],
        snipers=r["snipers"],
    )


def verdicts(row: GateRow | None, specs: Sequence[RuleSetSpec]) -> dict[str, dict[str, Any]]:
    """Per rule set: ``accepted`` (``None`` without a row) and the refusals by name."""
    out: dict[str, dict[str, Any]] = {}
    for spec in specs:
        if row is None:
            out[spec.label] = {"kind": spec.kind, "accepted": None, "refusals": []}
            continue
        decision = evaluate_entry(entry_features_of(row, spec), spec.gate)
        out[spec.label] = {
            "kind": spec.kind,
            "accepted": decision.allowed,
            "refusals": list(decision.refusals),
        }
    return out


async def lab_context_for(
    session: AsyncSession,
    *,
    mint: str,
    at: datetime,
    specs: Sequence[RuleSetSpec],
    features_version: str,
    now: datetime,
) -> LabContext:
    """The gate of every active set over the last closed minute ``<= at``."""
    r = (
        (await session.execute(_LAB_ROW, {"mint": mint, "at": at, "version": features_version}))
        .mappings()
        .first()
    )
    row = None if r is None else gate_row_from(r)
    context: dict[str, Any] = {
        "minute": None if row is None else row.end_time.isoformat(),
        "features_version": features_version,
        "reason": NO_FEATURES_ROW if row is None else None,
        "rule_sets": verdicts(row, specs),
        "hype_score": None if row is None else optional_money_str(row.hype_score),
        "hype_reason": None if row is None else row.hype_reason,
        "line_reason": None if row is None else row.line_reason,
        "evaluated_at": now.isoformat(),
    }
    return LabContext(
        context=context,
        hype_score=None if row is None else row.hype_score,
        line_reason=None if row is None else row.line_reason,
    )
