"""Manual paper orders: file, read and list — T3.68.

``hunter_api.services.admission.file_manual_order`` (T3.12) is the **only**
write this module drives: every mutation goes through it, one admission path,
inside the org session (RLS) the audit row already comes from. No SQL write
happens in this file. Everything that has to be derived before that call —
wallet-open, SPOT eligibility, the live entry reference and cost hypothesis —
lives in :mod:`hunter_api.services.orders_derive` (split out for CLAUDE.md's
350-line budget); this module is the orchestration: file, read one, list.

``ENABLE_PAPER_AUTONOMY`` plays no role here: that flag gates the *bridge*
(signal -> proposal, M4, ``docs/plans/M3.md`` question 9); the manual route has
filed paper orders through this same admission service since T3.12 regardless
of it (RISK_ENGINE.md §8).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text

from hunter_api.repositories.base import clamp_page_size, decode_cursor, encode_cursor
from hunter_api.schemas.orders import ManualOrderCreate, ManualOrderDetailOut, ManualOrderOut
from hunter_api.schemas.portfolio_lists import OrderOut
from hunter_api.services import admission
from hunter_api.services.orders_derive import (
    ensure_wallet_open,
    market_identity,
    reference_and_costs,
)
from hunter_core.db.models.execution_orders import Order
from hunter_core.domain.enums import ProposalStatus, TradeDirection
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_api.auth.rbac import OrgContext

__all__ = ["file_order", "get_manual_order_detail", "list_manual_orders"]

_SELECT_ONE = text(
    "SELECT id AS proposal_id, market_id, direction::text AS direction, status::text AS status, "
    "risk_decision, created_at FROM trade_proposals WHERE organization_id = :org "
    "AND portfolio_id = :pf AND id = :id AND source = 'manual'"
)


def _row_to_out(row: Any) -> ManualOrderOut:
    status = ProposalStatus(row.status)
    decision: dict[str, Any] | None = dict(row.risk_decision) if row.risk_decision else None
    return ManualOrderOut(
        request_id=row.proposal_id,
        market_id=row.market_id,
        direction=TradeDirection(row.direction),
        status="pending" if status is ProposalStatus.PENDING else "decided",
        filed_at=ensure_utc(row.created_at),
        decision=decision,
    )


async def _load_row(
    session: AsyncSession, *, org_id: uuid.UUID, portfolio_id: uuid.UUID, request_id: uuid.UUID
) -> Any:
    return (
        await session.execute(_SELECT_ONE, {"org": org_id, "pf": portfolio_id, "id": request_id})
    ).one_or_none()


async def _load_outcome(
    session: AsyncSession, *, org_id: uuid.UUID, portfolio_id: uuid.UUID, proposal_id: uuid.UUID
) -> OrderOut | None:
    """The most recent ``orders`` row this request produced, or ``None``.

    T3.4's entry cycle writes at most one order per approved proposal (one
    attempt, terminal cancellation of the remainder) — ``ORDER BY ... LIMIT 1``
    is defensive, not a sign several are expected.
    """
    statement = (
        select(Order)
        .where(
            Order.organization_id == org_id,
            Order.portfolio_id == portfolio_id,
            Order.proposal_id == proposal_id,
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(1)
    )
    row = (await session.execute(statement)).scalars().first()
    if row is None:
        return None
    return OrderOut(
        id=row.id,
        market_id=row.market_id,
        side=row.side,
        type=row.type,
        purpose=row.purpose,
        execution_mode=row.execution_mode,
        status=row.status,
        qty=row.qty,
        price=row.price,
        stop_price=row.stop_price,
        filled_qty=row.filled_qty,
        avg_fill_price=row.avg_fill_price,
        created_at=ensure_utc(row.created_at),
        completed_at=None if row.completed_at is None else ensure_utc(row.completed_at),
    )


async def get_manual_order_detail(
    session: AsyncSession, *, org_id: uuid.UUID, portfolio_id: uuid.UUID, request_id: uuid.UUID
) -> ManualOrderDetailOut | None:
    row = await _load_row(session, org_id=org_id, portfolio_id=portfolio_id, request_id=request_id)
    if row is None:
        return None
    base = _row_to_out(row)
    outcome = await _load_outcome(
        session, org_id=org_id, portfolio_id=portfolio_id, proposal_id=row.proposal_id
    )
    return ManualOrderDetailOut(**base.model_dump(), outcome=outcome)


async def list_manual_orders(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    limit: int | None,
    cursor: str | None,
) -> tuple[list[ManualOrderOut], str | None]:
    """Newest-first cursor page of this wallet's manual requests."""
    size = clamp_page_size(limit)
    conditions = ["organization_id = :org", "portfolio_id = :pf", "source = 'manual'"]
    params: dict[str, Any] = {"org": org_id, "pf": portfolio_id, "limit": size + 1}
    after = decode_cursor(cursor)
    if after is not None:
        conditions.append("(created_at, id) < (:after_ts, :after_id)")
        params["after_ts"], params["after_id"] = after
    statement = text(
        "SELECT id AS proposal_id, market_id, direction::text AS direction, "  # noqa: S608
        "status::text AS status, risk_decision, created_at FROM trade_proposals "
        f"WHERE {' AND '.join(conditions)} ORDER BY created_at DESC, id DESC LIMIT :limit"
    )
    rows = (await session.execute(statement, params)).all()
    page = rows[:size]
    next_cursor = (
        encode_cursor(page[-1].created_at, page[-1].proposal_id) if len(rows) > size else None
    )
    return [_row_to_out(row) for row in page], next_cursor


async def file_order(
    session: AsyncSession,
    redis: redis_asyncio.Redis,
    *,
    context: OrgContext,
    portfolio_id: uuid.UUID,
    idempotency_key: str,
    body: ManualOrderCreate,
    now: datetime,
) -> ManualOrderOut:
    """Derive, then file through :func:`hunter_api.services.admission.file_manual_order`.

    ``direction='short'`` is refused here, before any derivation runs: SPOT has
    no short in this profile — ``max_leverage=1`` on ``paper_v1``
    (RISK_ENGINE.md §2) *is* "no short", and the pure engine's ``modality``
    check (§3.1, check 3) would refuse it identically later, only after this
    route had already spent a Redis round trip finding out.
    """
    await ensure_wallet_open(session, context.org_id, portfolio_id)
    identity = await market_identity(session, body.market_id)
    if body.direction is TradeDirection.SHORT:
        raise admission.OrderRefusedError(
            "direction 'short' is refused on SPOT (reason: short_not_supported_spot): "
            "risk_profile paper_v1 sets max_leverage=1 and no short is implemented "
            "(RISK_ENGINE.md §2, §3.1 check 3 'modality')"
        )
    entry_ref, costs = await reference_and_costs(redis, identity, now=now)
    filed = await admission.file_manual_order(
        session,
        context=context,
        idempotency_key=idempotency_key,
        portfolio_id=portfolio_id,
        market_id=body.market_id,
        market=identity,
        direction=body.direction,
        entry_ref=entry_ref,
        stop=body.stop,
        assumed_costs=costs,
        now=now,
        requested_notional=body.requested_notional,
    )
    row = await _load_row(
        session, org_id=context.org_id, portfolio_id=portfolio_id, request_id=filed.proposal_id
    )
    if row is None:  # pragma: no cover - just written/read in the same transaction
        raise RuntimeError(f"proposal {filed.proposal_id} vanished right after being filed")
    return _row_to_out(row)
