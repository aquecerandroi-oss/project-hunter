"""The desk's decision on a ``meme_proposals`` row — one set of rules, one guarded
statement, two callers (T4.28).

The API's ``POST …/meme/proposals/{id}/approve`` (the operator's click, T4.7/T4.14)
and the executor's stage-1 auto-approval (``MEME_LIVE_AUTO_APPROVE``, T4.28) must
open a real proposal the **same** way: a row still ``proposed`` and before its
deadline, a size within the set's own ceiling, ``mode = 'live'`` only where the
live flag is on, and the write guarded by ``WHERE status = 'proposed'`` so a
concurrent decision (or the loop's ``expired`` stamp) wins by rowcount, never by
overwrite. Those rules live here, pure and named, and the SQL is the one both
run — the API maps a refusal to 409/422, the executor to a skipped candidate.

Nothing here reads a clock, a network or a secret; nothing here touches
``meme_paper_bets`` or ``meme_live_orders``. The executor's admission (the 25
checks of ``docs/RISK_ENGINE_MEME.md`` §4) still runs **after** this decision:
opening a live proposal is not buying.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Literal, cast

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "AUTO_STAGE1_DECIDED_BY",
    "DECIDE_PROPOSAL",
    "DecisionStatus",
    "ProposalDecision",
    "ProposalMode",
    "decide_proposal",
    "live_mode_refusal",
    "max_sol_per_bet_of",
    "proposal_state_refusal",
    "size_cap_refusal",
]

AUTO_STAGE1_DECIDED_BY = "executor:auto_stage1"
"""``meme_proposals.decided_by`` of a proposal the executor opened on its own
(stage 1, ``obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md``). The
desk shows it; the executor rejects such a proposal by name when its own
admission refuses the buy."""

ProposalMode = Literal["paper", "live"]
DecisionStatus = Literal["approved", "rejected"]
_DECISIONS: frozenset[str] = frozenset({"approved", "rejected"})

DECIDE_PROPOSAL = text(
    "UPDATE meme_proposals SET status = :status, decision = CAST(:decision AS jsonb), "
    "  decided_by = :decided_by, decided_at = :decided_at, mode = :mode "
    "WHERE id = :id AND status = 'proposed'"
)
"""The one write of a decision. ``status = 'proposed'`` in the ``WHERE`` is the
concurrency rule: rowcount 0 means somebody (another operator, the loop's
``expired`` stamp, the executor) already decided — the caller refuses, never
retries."""


def proposal_state_refusal(
    status: str, expires_at: datetime, now: datetime, *, approving: bool
) -> str | None:
    """``not_proposed`` for a row already decided or expired by the loop;
    ``expired`` for an approval at or after ``expires_at`` (between the deadline
    and the loop's stamp the row still reads ``proposed``, and approving it would
    fill a window the contract closed). A rejection past the deadline is still a
    decision."""
    if status != "proposed":
        return "not_proposed"
    if approving and now >= expires_at:
        return "expired"
    return None


def max_sol_per_bet_of(params: Mapping[str, Any]) -> Decimal | None:
    """The set's own ceiling from ``meme_rule_sets.params``; absent or
    unreadable is **no ceiling here** (the loop applies the set's ceilings on
    fill; the executor's policy applies its own on admission)."""
    raw: Any = params.get("max_sol_per_bet")
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, float):
        return Decimal(str(raw))
    if isinstance(raw, (int, str)):
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None
    return None


def size_cap_refusal(max_sol_per_bet: Decimal | None, size_sol: Decimal) -> str | None:
    """``exceeds_max_sol_per_bet`` when the decided size is above the set's ceiling."""
    if max_sol_per_bet is not None and size_sol > max_sol_per_bet:
        return "exceeds_max_sol_per_bet"
    return None


def live_mode_refusal(mode: str, *, live_enabled: bool) -> str | None:
    """``meme_live_disabled``: ``mode = 'live'`` needs the caller's own live flag
    (``docs/RISK_ENGINE_MEME.md`` §3.4). Paper never needs it."""
    if mode == "live" and not live_enabled:
        return "meme_live_disabled"
    return None


@dataclass(frozen=True, slots=True)
class ProposalDecision:
    """What :data:`DECIDE_PROPOSAL` writes. ``decision`` is JSON (money as strings,
    the JSONB convention of every table here) or SQL ``NULL``."""

    proposal_id: str
    status: DecisionStatus
    decision: dict[str, Any] | None
    decided_by: str
    decided_at: datetime
    mode: ProposalMode

    def __post_init__(self) -> None:
        if self.status not in _DECISIONS:
            raise ValueError(f"a decision is approved or rejected, not {self.status!r}")
        if self.mode not in ("paper", "live"):
            raise ValueError(f"mode is paper or live, not {self.mode!r}")
        if not self.decided_by.strip():
            raise ValueError("decided_by is empty")

    def parameters(self) -> dict[str, Any]:
        return {
            "id": self.proposal_id,
            "status": self.status,
            "decision": None if self.decision is None else json.dumps(self.decision, default=str),
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "mode": self.mode,
        }


async def decide_proposal(session: AsyncSession, decided: ProposalDecision) -> bool:
    """Run :data:`DECIDE_PROPOSAL`; ``True`` when this call moved the row out of
    ``proposed``, ``False`` when something else already had."""
    result = cast("CursorResult[Any]", await session.execute(DECIDE_PROPOSAL, decided.parameters()))
    return result.rowcount == 1
