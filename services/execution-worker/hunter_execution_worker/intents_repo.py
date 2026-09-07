"""``portfolio_exit_intents`` — reading and writing the durable protection.

The intention is the promise; the attempt is one try at it. This module is only
the persistence of the first: the state machine lives in
:mod:`hunter_core.execution.intents` and is never re-implemented here.

**An intention read back from Postgres is not idempotent by itself.** The table
has no column for ``applied_attempts`` (DATABASE.md §19.3 records that as a
closed decision, not an omission), so after a restart the set is rebuilt from
the rows that were really written: ``fills.execution_key`` **∪**
``orders.client_order_id``, the same ``exit:{attempt_id}`` string. Both, because
an attempt that found no book writes an order and no fill — deriving from fills
alone loses it, and the redelivery then lands on an intention that was already
replaced and raises (notes-T3.4.md §10.4c).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import text

from hunter_core.domain.enums import ExitIntentState, ExitReason
from hunter_core.execution.idempotency import applied_attempts_from_execution_keys
from hunter_core.execution.intents import ExitIntent
from hunter_risk.inputs import MarketIdentity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["insert_intent", "live_intents", "save_intent"]

_LIVE = ("open", "blocked_residual")

_SELECT = (
    "SELECT i.id AS intent_id, i.portfolio_id, i.position_id, i.market_id, i.protection_key, "
    "i.reason::text AS reason, i.intended_qty, i.filled_qty, i.state::text AS state, "
    "i.trigger_price, i.degraded_since, i.degraded_reason, i.superseded_by_id, "
    "i.closed_reason, i.closed_at FROM portfolio_exit_intents i "
    "WHERE i.organization_id = :org AND i.portfolio_id = :pf "
)


async def _applied_attempts(
    session: AsyncSession, *, wallet: WalletRef, intent_id: uuid.UUID
) -> tuple[uuid.UUID, ...]:
    """Every attempt already folded into this intention, from the two authorities."""
    rows = await session.execute(
        text(
            "SELECT f.execution_key AS key FROM fills f JOIN orders o ON o.id = f.order_id "
            "AND o.organization_id = f.organization_id AND o.portfolio_id = f.portfolio_id "
            "WHERE f.organization_id = :org AND o.exit_intent_id = :intent "
            "UNION "
            "SELECT o.client_order_id AS key FROM orders o "
            "WHERE o.organization_id = :org AND o.exit_intent_id = :intent"
        ),
        {"org": wallet.organization_id, "intent": intent_id},
    )
    return applied_attempts_from_execution_keys(row.key for row in rows)


async def live_intents(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    market: MarketReference | None = None,
    position_id: uuid.UUID | None = None,
    lock: bool = False,
) -> tuple[ExitIntent, ...]:
    """Every non-terminal intention, rebuilt with its applied attempts."""
    statement = _SELECT + "AND i.state = ANY(:live) "
    params: dict[str, object] = {
        "org": wallet.organization_id,
        "pf": wallet.portfolio_id,
        "live": list(_LIVE),
    }
    if position_id is not None:
        statement += "AND i.position_id = :position "
        params["position"] = position_id
    statement += "ORDER BY i.created_at" + (" FOR UPDATE OF i" if lock else "")
    rows = (await session.execute(text(statement), params)).all()
    identity = None if market is None else market.identity
    return tuple(
        [await _intent(session, wallet=wallet, row=row, identity=identity) for row in rows]
    )


async def _intent(
    session: AsyncSession, *, wallet: WalletRef, row: Any, identity: MarketIdentity | None
) -> ExitIntent:
    """One ``portfolio_exit_intents`` row, plus the attempts already applied.

    ``Any`` because a SQLAlchemy ``Row`` is shaped by its ``SELECT``; every value
    is narrowed here, and the state machine itself validates the result.
    """
    intent_id = cast("uuid.UUID", row.intent_id)
    return ExitIntent(
        intent_id=intent_id,
        portfolio_id=cast("uuid.UUID", row.portfolio_id),
        position_id=cast("uuid.UUID", row.position_id),
        protection_key=cast("str", row.protection_key),
        reason=ExitReason(cast("str", row.reason)),
        intended_qty=cast("Decimal", row.intended_qty),
        filled_qty=cast("Decimal", row.filled_qty),
        state=ExitIntentState(cast("str", row.state)),
        trigger_price=cast("Decimal | None", row.trigger_price),
        market=identity,
        degraded_since=cast("datetime | None", row.degraded_since),
        degraded_reason=cast("str | None", row.degraded_reason),
        superseded_by_id=cast("uuid.UUID | None", row.superseded_by_id),
        closed_reason=cast("str | None", row.closed_reason),
        closed_at=cast("datetime | None", row.closed_at),
        applied_attempts=await _applied_attempts(session, wallet=wallet, intent_id=intent_id),
    )


async def insert_intent(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    market: MarketReference,
    position_id: uuid.UUID,
    protection_key: str,
    reason: ExitReason,
    intended_qty: Decimal,
    trigger_price: Decimal | None,
    now: datetime,
) -> ExitIntent:
    """Arm a durable protection. Written in the transaction that opens the position.

    A position without a durable protection is the failure mode the whole
    intention/attempt split exists to prevent, so this is never a second commit
    (M3 joint decision, item 3).
    """
    intent_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO portfolio_exit_intents (id, organization_id, portfolio_id, position_id, "
            "market_id, reason, protection_key, state, intended_qty, filled_qty, trigger_price, "
            "created_at, updated_at) VALUES (:id, :org, :pf, :position, :market, :reason, :key, "
            "'open', :qty, 0, :trigger, :now, :now)"
        ),
        {
            "id": intent_id,
            "org": wallet.organization_id,
            "pf": wallet.portfolio_id,
            "position": position_id,
            "market": market.market_id,
            "reason": reason.value,
            "key": protection_key,
            "qty": intended_qty,
            "trigger": trigger_price,
            "now": now,
        },
    )
    return ExitIntent(
        intent_id=intent_id,
        portfolio_id=wallet.portfolio_id,
        position_id=position_id,
        protection_key=protection_key,
        reason=reason,
        intended_qty=intended_qty,
        trigger_price=trigger_price,
        market=market.identity,
    )


async def save_intent(session: AsyncSession, *, wallet: WalletRef, intent: ExitIntent) -> None:
    """Persist the intention exactly as the state machine left it.

    Guarded on the row still being non-terminal: a second writer that already
    closed it must win, and this ``UPDATE`` must not resurrect a closed
    protection by overwriting ``closed_at`` with a stale copy.
    """
    await session.execute(
        text(
            "UPDATE portfolio_exit_intents SET intended_qty = :intended, filled_qty = :filled, "
            "state = :state, degraded_since = :degraded_since, degraded_reason = :degraded_reason,"
            " superseded_by_id = :superseded, closed_reason = :closed_reason, "
            "closed_at = :closed_at WHERE id = :id AND organization_id = :org "
            "AND portfolio_id = :pf"
        ),
        {
            "intended": intent.intended_qty,
            "filled": intent.filled_qty,
            "state": intent.state.value,
            "degraded_since": intent.degraded_since,
            "degraded_reason": intent.degraded_reason,
            "superseded": intent.superseded_by_id,
            "closed_reason": intent.closed_reason,
            "closed_at": intent.closed_at,
            "id": intent.intent_id,
            "org": wallet.organization_id,
            "pf": wallet.portfolio_id,
        },
    )
