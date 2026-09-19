"""T4.67b — the launch lane's own reads and the one write that claims a
proposal for real money.

A ``launch_v0/*`` proposal is written by the radar's launch lane (T4.67a) as a
``research_only`` row: born ``approved`` by ``rules``, ``mode = 'paper'``,
``reasons[0].series = 'meme_launch_lane_v1'``. The paper loop fills it in
shadow like any research set. With ``MEME_LAUNCH_LANE=on`` the executor reads
those rows here (only those: the rule set's **name**, every version, and the
series label — anything else is not a launch proposal) and, once its fast
admission decided, **claims** the row in the same transaction that writes the
buy order: ``mode = 'live'`` guarded by ``mode = 'paper'`` (rowcount 0 means
another writer moved it — the caller skips). The regular entries loop reads
``mode = 'live'`` rows without a buy order, so claim and order are one
transaction on purpose: it can never see a claimed launch without its order.
``decided_by`` stays ``rules`` (the research set approved the signal); the
executor's own decision is the order row's ``admission``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import text

from hunter_meme_executor.launch_config import LAUNCH_RULE_SET_NAME, LAUNCH_SERIES
from hunter_meme_executor.repo import Candidate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "LaunchCandidate",
    "buy_submitted_at",
    "claim_launch_proposal",
    "created_at_of",
    "launch_candidates",
]

_CANDIDATES = text(
    "SELECT p.id, p.mint, p.decision, p.suggested, p.quote, p.reasons, p.decided_at, "
    "  p.decided_by, p.status, p.proposed_at, p.features_end_time, rs.params, rs.version "
    "FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id = p.rule_set_id "
    "WHERE rs.name = :name AND rs.status = 'active' AND p.origin = 'rules' "
    "  AND p.mode = 'paper' AND p.status IN ('approved', 'filled', 'unfilled') "
    "  AND p.proposed_at >= :since "
    "  AND NOT EXISTS (SELECT 1 FROM meme_live_orders o "
    "                  WHERE o.proposal_id = p.id AND o.side = 'buy') "
    "ORDER BY p.proposed_at"
)
_SUBMITTED_AT = text("SELECT submitted_at FROM meme_live_orders WHERE client_order_id = :key")
_CLAIM = text(
    "UPDATE meme_proposals SET mode = 'live', "
    "  decision = coalesce(decision, '{}'::jsonb) || CAST(:note AS jsonb) "
    "WHERE id = :id AND mode = 'paper' AND origin = 'rules' "
    "  AND status IN ('approved', 'filled', 'unfilled') RETURNING id"
)


@dataclass(frozen=True, slots=True)
class LaunchCandidate:
    candidate: Candidate
    suggested: dict[str, Any]
    quote: dict[str, Any]
    reasons: list[dict[str, Any]]
    rule_set_params: dict[str, Any]
    rule_set_version: str
    features_end_time: datetime | None = None
    """T4.67a stamps the **create instant** here (``event.created_at``)."""

    @property
    def id(self) -> str:
        return self.candidate.id

    @property
    def mint(self) -> str:
        return self.candidate.mint

    @property
    def series(self) -> str | None:
        first = self.reasons[0] if self.reasons else {}
        value = first.get("series")
        return None if value is None else str(value)

    @property
    def is_launch(self) -> bool:
        """The radar's label, checked in Python so a set renamed by hand is not enough."""
        return self.series == LAUNCH_SERIES


def _stamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def created_at_of(candidate: LaunchCandidate) -> tuple[datetime | None, str | None]:
    """The coin's creation instant with its provenance: the proposal's own
    ``reasons[0].created_at`` or ``quote.created_at`` when a lane writes one,
    else ``features_end_time`` (T4.67a stamps the create frame's instant there);
    ``None`` when none is there — the caller falls back to
    ``meme_tokens.created_at`` and, last, ``proposed_at`` (a lower bound on the
    age, labelled so)."""
    first = candidate.reasons[0] if candidate.reasons else {}
    stamp = _stamp(first.get("created_at"))
    if stamp is not None:
        return stamp, "meme_proposals.reasons[0].created_at"
    stamp = _stamp(candidate.quote.get("created_at"))
    if stamp is not None:
        return stamp, "meme_proposals.quote.created_at"
    stamp = candidate.features_end_time
    if stamp is not None and stamp.tzinfo is not None:
        return stamp, "meme_proposals.features_end_time"
    return None, None


def _reasons(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [cast(dict[str, Any], x) for x in cast(list[Any], raw) if isinstance(x, dict)]


def _rows_to_candidates(rows: Any) -> list[LaunchCandidate]:
    out: list[LaunchCandidate] = []
    for r in rows:
        reasons = _reasons(r["reasons"])
        out.append(
            LaunchCandidate(
                candidate=Candidate(
                    id=str(r["id"]),
                    mint=str(r["mint"]),
                    decision=dict(r["decision"] or {}),
                    decided_at=r["decided_at"] or r["proposed_at"],
                    decided_by=str(r["decided_by"] or "rules"),
                    status=str(r["status"]),
                    proposed_at=r["proposed_at"],
                ),
                suggested=dict(r["suggested"] or {}),
                quote=dict(r["quote"] or {}),
                reasons=reasons,
                rule_set_params=dict(r["params"] or {}),
                rule_set_version=str(r["version"]),
                features_end_time=r["features_end_time"],
            )
        )
    return out


async def launch_candidates(
    session: AsyncSession, *, now: datetime, lookback_s: float = 60
) -> list[LaunchCandidate]:
    """Launch proposals with no buy attempt yet, newest window only (a launch
    older than a minute is not a candidate for anything — the caller refuses by
    age long before that, and the row would otherwise be re-read forever)."""
    rows = (
        await session.execute(
            _CANDIDATES,
            {"name": LAUNCH_RULE_SET_NAME, "since": now - timedelta(seconds=lookback_s)},
        )
    ).mappings()
    return [c for c in _rows_to_candidates(rows) if c.is_launch]


async def buy_submitted_at(session: AsyncSession, client_order_id: str) -> datetime | None:
    """When the buy left the process (``submitted_at``), for ``proposal_to_submit_ms``."""
    return (await session.execute(_SUBMITTED_AT, {"key": client_order_id})).scalar()


async def claim_launch_proposal(session: AsyncSession, proposal_id: str, *, now: datetime) -> bool:
    """``mode = 'live'`` on the research row, guarded by ``mode = 'paper'``: ``True``
    when this call claimed it. Same transaction as the order insert (module doc)."""
    note = json.dumps({"launch_lane": {"claimed_at": now.isoformat(), "by": "executor:launch"}})
    claimed = await session.execute(_CLAIM, {"id": proposal_id, "note": note})
    return claimed.scalar() is not None
