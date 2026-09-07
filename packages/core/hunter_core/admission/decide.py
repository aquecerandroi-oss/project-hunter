"""Deciding a request the API already filed — in its own row.

One function, in a module of its own so ``record.py`` keeps its size budget
(``infra/scripts/check_file_size.py``) and so the *second half* of §19.4 has a
name: the API files a request, and this is where the engine turns that row into
a decision without ever writing a second one.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.admission.record import kill_switch_snapshot
from hunter_core.admission.reservation import RESERVATION_TTL
from hunter_core.admission.sources import request_digest
from hunter_core.domain.enums import ProposalSource, ProposalStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.admission.sources import ProposalRequest
    from hunter_core.risk.scopes import EffectiveKillSwitch
    from hunter_risk.decision import RiskDecision

__all__ = ["decide_pending"]


async def decide_pending(
    session: AsyncSession,
    request: ProposalRequest,
    *,
    proposal_id: uuid.UUID,
    source: ProposalSource,
    decision: RiskDecision,
    scopes: EffectiveKillSwitch,
    as_of: datetime,
) -> bool:
    """Decide a request the API already filed — **in its own row**.

    ``0007_paper_roles`` §19.4 splits the act in two: the API files a request
    (``source = manual``, ``status = pending``, no decision, no sequence, no
    reservation) and the engine decides it. Inserting a *second* row for the
    same request would leave the pending one for ever, take a second place in
    the FIFO queue and give the operator two proposals for one order — which is
    why this is an ``UPDATE`` and not an insert (adversarial review of
    2026-09-07, must-fix 1).

    Guarded on the row still being pending, so two engines racing for the same
    request produce exactly one decision: the loser's ``UPDATE`` matches nothing
    and it replays the winner's answer instead.

    ``decided_at`` is the instant of *this* evaluation. Nothing here invents one
    for a row that was never decided (suggestion 9 of the same review).
    """
    approved = decision.approved
    decided = await session.scalar(
        text(
            "UPDATE trade_proposals SET status = :status, risk_decision = CAST(:decision AS jsonb),"
            " rejection_reason = :reason, kill_switch_snapshot = CAST(:snapshot AS jsonb), "
            "request_digest = coalesce(request_digest, :digest), decided_at = :decided, "
            "expires_at = :expires WHERE id = :id AND organization_id = :org "
            "AND status = 'pending' AND decided_at IS NULL RETURNING id"
        ),
        {
            "id": proposal_id,
            "org": request.organization_id,
            "status": (ProposalStatus.APPROVED if approved else ProposalStatus.REJECTED).value,
            "decision": json.dumps(decision.to_jsonable()),
            "reason": ", ".join(decision.rejection_reasons) or None,
            "snapshot": json.dumps(kill_switch_snapshot(scopes)),
            "digest": request_digest(request, source),
            "decided": as_of,
            "expires": as_of + RESERVATION_TTL if approved else None,
        },
    )
    return decided is not None
