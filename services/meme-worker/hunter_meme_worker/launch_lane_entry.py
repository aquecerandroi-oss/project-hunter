"""Turn one pump.fun ``create`` frame into a launch-lane proposal (T4.67a) —
or a named refusal, counted and nothing else. No 15-second base row, no
holders, no tape, no pedigree read (module docstring of ``launch_lane.py``):
every input here is the frame itself, the rule set's own frozen numbers, and
the lane's in-memory :class:`~hunter_meme_worker.launch_lane_symbols.RecentSymbols`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from hunter_core.domain.types import uuid7
from hunter_indicators.meme.launch_lane import (
    LaunchFeatures,
    evaluate_launch,
    reconstruct_initial_real_token_reserves,
)
from hunter_meme_worker.lab_values import money_str, optional_money_str
from hunter_meme_worker.launch_lane_repo import LaunchRuleSpec
from hunter_meme_worker.launch_lane_symbols import RecentSymbols
from hunter_meme_worker.proposals import ProposalDraft

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_exchanges.pumpfun.models import NormalizedMemeTokenCreated

__all__ = ["SERIES_LAUNCH", "evaluate_create", "features_of"]

SERIES_LAUNCH = "meme_launch_lane_v1"
"""``reasons[0].series`` of every proposal this lane writes (``docs/DATABASE.md``)."""

DEFAULT_TTL_S = 30
"""How long a launch proposal waits — the entry itself fires within seconds,
so a proposal older than this was never going to be filled anyway."""


def features_of(
    event: NormalizedMemeTokenCreated, *, recent_symbols: RecentSymbols
) -> LaunchFeatures:
    """Read-only: does **not** call ``recent_symbols.observe`` — the caller
    decides when a create becomes evidence for the next one (``launch_lane.py``:
    unconditionally, even a refused create is still a symbol seen)."""
    return LaunchFeatures(
        is_mayhem=event.mayhem_enabled,
        creator_initial_sol=event.creator_initial_sol,
        initial_real_token_reserves=reconstruct_initial_real_token_reserves(
            event.initial_virtual_token_reserves, event.creator_initial_tokens
        ),
        symbol_clone_recent=recent_symbols.is_recent_clone(event.symbol, event.observed_at),
    )


def _reasons(
    event: NormalizedMemeTokenCreated, spec: LaunchRuleSpec, features: LaunchFeatures
) -> list[dict[str, Any]]:
    gate = spec.gate
    return [
        {
            "rule": f"{gate.key}/{gate.version}",
            "series": SERIES_LAUNCH,
            "is_mayhem": features.is_mayhem,
            "creator_initial_sol": optional_money_str(features.creator_initial_sol),
            "max_creator_initial_sol": money_str(gate.max_creator_initial_sol),
            "initial_real_token_reserves": optional_money_str(features.initial_real_token_reserves),
            "symbol_clone_recent": features.symbol_clone_recent,
            "symbol": event.symbol,
        }
    ]


def _quote(spec: LaunchRuleSpec) -> dict[str, Any]:
    """No snapshot exists at ``create`` time — the honest quote is what the
    lane intends to risk, never a fabricated price (``proposals.quote_for``'s
    own convention, minus the snapshot no lane this early can have)."""
    return {
        "reason": "no_snapshot_at_create",
        "size_sol": money_str(spec.size_sol),
        "max_creator_initial_sol": money_str(spec.max_creator_initial_sol),
        "time_stop_s": spec.time_stop_s,
        "exit_key": spec.exit_key,
    }


def _suggested(spec: LaunchRuleSpec) -> dict[str, Any]:
    return {
        "size_sol": money_str(spec.size_sol),
        "time_stop_s": spec.time_stop_s,
        "exit_key": spec.exit_key,
        "exit_on_first_third_party_sell": spec.exit_on_first_third_party_sell,
        "max_drawdown_from_peak_pct": money_str(spec.max_drawdown_from_peak_pct),
    }


def draft_proposal(
    event: NormalizedMemeTokenCreated,
    spec: LaunchRuleSpec,
    features: LaunchFeatures,
    *,
    now: datetime,
) -> ProposalDraft:
    """A ``research_only`` launch set is born ``approved`` by ``rules``, the
    same convention ``proposals.draft_proposal`` uses — ``launch_v0/1`` is
    ``research_only`` (paper by construction: the executor only ever opens an
    ``operator`` set's proposals)."""
    research = spec.kind == "research_only"
    suggested = _suggested(spec)
    return ProposalDraft(
        id=str(uuid7()),
        mint=event.mint,
        rule_set_id=spec.id,
        origin="rules",
        status="approved" if research else "proposed",
        proposed_at=now,
        expires_at=now + timedelta(seconds=DEFAULT_TTL_S),
        features_end_time=event.created_at,
        quote=_quote(spec),
        reasons=_reasons(event, spec, features),
        suggested=suggested,
        decision=dict(suggested) if research else None,
        decided_by="rules" if research else None,
        decided_at=now if research else None,
    )


def evaluate_create(
    event: NormalizedMemeTokenCreated,
    specs: list[LaunchRuleSpec],
    *,
    recent_symbols: RecentSymbols,
    now: datetime,
) -> list[tuple[LaunchRuleSpec, ProposalDraft | tuple[str, ...]]]:
    """Every active launch set against this one ``create`` — a draft, or the
    refusals that stopped it, never silently skipped."""
    features = features_of(event, recent_symbols=recent_symbols)
    out: list[tuple[LaunchRuleSpec, ProposalDraft | tuple[str, ...]]] = []
    for spec in specs:
        refusals = evaluate_launch(features, spec.gate)
        if refusals:
            out.append((spec, refusals))
        else:
            out.append((spec, draft_proposal(event, spec, features, now=now)))
    return out
