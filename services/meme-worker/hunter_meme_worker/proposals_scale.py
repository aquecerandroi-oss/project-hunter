"""The probe → scale step of the gate (T4.10, EXP-M3): while a rule set's
**probe** is open on a mint, the same mint's closed minute is judged by the
line gate of ``scale_gate`` (``trendline_v0/1``), and when — only when — that
gate is satisfied, a second leg of ``scale_size_sol`` is proposed as a separate
bet that names its ``parent_bet_id``.

What this step will not do, by construction:

- scale before the probe filled (``open_probes`` is read from
  ``meme_paper_bets`` with ``status = 'open' AND leg = 'probe'``);
- scale a probe twice (``already_scaled`` is every parent a bet or a pending
  proposal of the set already names);
- scale a probe that left by time stop without a line (it is no longer open);
- run the line gate with the probe's size: the second leg's participation is
  judged with **its own** size.

Refusals are counted under the scaling set's name with a ``scale:`` prefix, so
the heartbeat tells "the probe's line is not drawn yet" from the probe gate's
own refusals.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterable, Mapping
from datetime import datetime
from typing import Any

from hunter_indicators.meme.rules import evaluate_entry
from hunter_meme_worker.lab_models import RuleSetSpec, money_str
from hunter_meme_worker.proposals import (
    GateOutcome,
    GateRow,
    ProposalDraft,
    draft_proposal,
    entry_features_of,
    gate_reasons,
    quote_for,
)

__all__ = ["REFUSAL_SCALE_GATE_INACTIVE", "evaluate_scale", "scale_suggested"]

REFUSAL_SCALE_GATE_INACTIVE = "scale_gate_inactive"
REFUSAL_NO_SNAPSHOT_FOR_QUOTE = "scale:no_snapshot_for_quote"


def scale_suggested(spec: RuleSetSpec, trend: RuleSetSpec, parent_bet_id: str) -> dict[str, Any]:
    """The second leg runs on the line set's exits (target, trailing, horizon,
    the broken line) at the scaling set's ``scale_size_sol``."""
    assert spec.scale_size_sol is not None
    return {
        "size_sol": money_str(spec.scale_size_sol),
        "target_x": money_str(trend.target_x),
        "trailing_pct": money_str(trend.trailing_pct),
        "max_hold_s": trend.max_hold_s,
        "exit_on_line_break": trend.exit_on_line_break,
        "line_break_snapshots": trend.line_break_snapshots,
        "leg": "scale",
        "parent_bet_id": parent_bet_id,
    }


def evaluate_scale(
    spec: RuleSetSpec,
    trend: RuleSetSpec,
    rows: Iterable[GateRow],
    *,
    open_probes: Mapping[str, str],
    already_scaled: Collection[str],
    now: datetime,
    ttl_s: int,
) -> GateOutcome:
    """Every row whose mint carries an open, not-yet-scaled probe of ``spec``,
    through ``trend``'s gate at the scale size."""
    drafts: list[ProposalDraft] = []
    refusals: Counter[str] = Counter()
    evaluated = 0
    if spec.scale_size_sol is None:
        return GateOutcome(drafts=drafts, refusals=refusals, evaluated=0)
    for row in rows:
        parent = open_probes.get(row.mint)
        if parent is None or parent in already_scaled:
            continue
        evaluated += 1
        features = entry_features_of(row, trend, size_sol=spec.scale_size_sol)
        decision = evaluate_entry(features, trend.gate)
        if not decision.allowed:
            refusals.update(f"scale:{reason}" for reason in decision.refusals)
            continue
        if row.snapshot is None:
            refusals[REFUSAL_NO_SNAPSHOT_FOR_QUOTE] += 1
            continue
        reasons = [
            {"rule": f"{trend.gate.key}/{trend.gate.version}", "scale_of": parent},
            {"scale_gate": trend.label, "probe_rule_set": spec.label},
            *gate_reasons(features, trend)[1:],
        ]
        drafts.append(
            draft_proposal(
                row,
                spec,
                quote=quote_for(row, row.snapshot, spec, size_sol=spec.scale_size_sol),
                reasons=reasons,
                suggested=scale_suggested(spec, trend, parent),
                now=now,
                ttl_s=ttl_s,
            )
        )
    return GateOutcome(drafts=drafts, refusals=refusals, evaluated=evaluated)
