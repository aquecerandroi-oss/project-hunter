"""The 60 s participation budget of one ``(market, wallet)`` — RISK_ENGINE.md §4.

``participation_consumptions`` is an immutable log of three effects (reserved,
executed, released) and this module turns it into the one number the pure engine
takes as ``MarketLiquidity.participation_used_quote``:

```
usado = Σ(executed com occurred_at > as_of − 60 s)
      + Σ por reserva ainda 'held' de max(0, reservado − executado − liberado)
```

Three properties of that formula, each of which the schema deliberately leaves
to this service (DATABASE.md §18.5, "o que **não** é DDL"):

- **only the executed leg gets the rolling cut.** A reservation that is still
  executable does not age out of the budget — the minute is not free again just
  because the commitment is old;
- **the executed part of a standing reservation is counted once.** It is inside
  the first term, and it *reduces* the balance of the second, so 80 reserved
  with 30 filled is 80 committed, never 110;
- **a balance never goes negative and never pays for a neighbour.** A
  reservation that somehow executed more than it reserved commits its execution,
  and the excess does not discount anybody else's commitment.

The SQL only fetches rows; the algebra is a pure function so it can be proved
without a container (``tests/unit/admission/test_participation_budget.py``).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from hunter_core.db.repositories.base import TenantRepository
from hunter_core.domain.enums import ParticipationEntryKind, ReservationState
from hunter_core.domain.types import ensure_utc, uuid7

__all__ = [
    "ConsumptionRow",
    "ParticipationRepository",
    "participation_used",
]

_ZERO = Decimal(0)


class ConsumptionRow(BaseModel):
    """One entry of the log, with the tenure of the reservation it belongs to."""

    model_config = ConfigDict(frozen=True)

    proposal_id: uuid.UUID
    kind: ParticipationEntryKind
    notional: Decimal
    occurred_at: datetime
    reservation_state: ReservationState
    """Read from ``trade_proposals`` in the same statement: what still counts as
    a commitment is decided by the state, never by ``reserved_until`` — expiry
    is a transition taken under the wallet's lock, not a timestamp comparison
    (DATABASE.md §18.3)."""


def participation_used(rows: tuple[ConsumptionRow, ...], *, cut: datetime) -> Decimal:
    """Quote notional this market has already taken inside the window."""
    moment = ensure_utc(cut)
    executed_in_window = _ZERO
    by_proposal: dict[uuid.UUID, dict[ParticipationEntryKind, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: _ZERO)
    )
    held: set[uuid.UUID] = set()
    for row in rows:
        if row.kind is ParticipationEntryKind.EXECUTED and ensure_utc(row.occurred_at) > moment:
            executed_in_window += row.notional
        by_proposal[row.proposal_id][row.kind] += row.notional
        if row.reservation_state is ReservationState.HELD:
            held.add(row.proposal_id)

    standing = _ZERO
    for proposal_id in held:
        legs = by_proposal[proposal_id]
        balance = (
            legs[ParticipationEntryKind.RESERVED]
            - legs[ParticipationEntryKind.EXECUTED]
            - legs[ParticipationEntryKind.RELEASED]
        )
        standing += max(_ZERO, balance)
    return executed_in_window + standing


class ParticipationRepository(TenantRepository):
    """Reads and appends of one organization's participation log."""

    async def entries(
        self, *, portfolio_id: uuid.UUID, market_id: uuid.UUID, cut: datetime
    ) -> tuple[ConsumptionRow, ...]:
        """Everything that can still weigh on this market's budget.

        Two disjunctions, on purpose: an execution inside the window, or *any*
        leg of a reservation that is still standing — whose own legs may be
        older than the window and still have to be netted against it.
        """
        statement = text(
            "SELECT c.proposal_id, c.kind::text AS kind, c.notional, c.occurred_at, "
            "p.reservation_state::text AS reservation_state "
            "FROM participation_consumptions c "
            "JOIN trade_proposals p ON p.id = c.proposal_id "
            "AND p.organization_id = c.organization_id "
            "WHERE c.organization_id = :org AND c.portfolio_id = :pf AND c.market_id = :market "
            "AND (c.occurred_at > :cut OR p.reservation_state = 'held')"
        )
        rows = await self.session.execute(
            statement,
            {
                "org": self.organization_id,
                "pf": portfolio_id,
                "market": market_id,
                "cut": ensure_utc(cut),
            },
        )
        return tuple(ConsumptionRow.model_validate(row, from_attributes=True) for row in rows)

    async def used(
        self, *, portfolio_id: uuid.UUID, market_id: uuid.UUID, cut: datetime
    ) -> Decimal:
        """The number the engine receives as ``participation_used_quote``."""
        rows = await self.entries(portfolio_id=portfolio_id, market_id=market_id, cut=cut)
        return participation_used(rows, cut=cut)

    async def append(
        self,
        *,
        portfolio_id: uuid.UUID,
        market_id: uuid.UUID,
        proposal_id: uuid.UUID,
        kind: ParticipationEntryKind,
        notional: Decimal,
        occurred_at: datetime,
    ) -> None:
        """Append one entry, idempotent by **logical effect**.

        ``ON CONFLICT DO NOTHING`` against the partial unique indexes of §18.5
        (one reservation and one release per proposal, one execution per fill):
        a retry must not spend the minute twice, and must not renew
        ``occurred_at`` to slide the window forward. Executions are written by
        the execution path (T3.5), which owns the ``fill_id`` the index keys on.
        """
        statement = text(
            "INSERT INTO participation_consumptions (id, organization_id, portfolio_id, "
            "market_id, proposal_id, kind, notional, occurred_at) VALUES (:id, :org, :pf, "
            ":market, :proposal, :kind, :notional, :occurred) ON CONFLICT DO NOTHING"
        )
        await self.session.execute(
            statement,
            {
                "id": uuid7(),
                "org": self.organization_id,
                "pf": portfolio_id,
                "market": market_id,
                "proposal": proposal_id,
                "kind": kind.value,
                "notional": notional,
                "occurred": ensure_utc(occurred_at),
            },
        )
