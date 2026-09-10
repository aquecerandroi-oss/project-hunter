"""``POST/GET /api/v1/orgs/{org_id}/portfolios/{portfolio_id}/order-requests`` — T3.68.

**Naming deviation from the brief, declared up front (also in
``.claude/state/notes-T3.68.md``).** The brief's contract names the resource
``.../orders``, but ``routers/portfolio.py`` (T3.8a) already serves
``GET .../orders`` for a *different* resource — ``execution_orders`` rows, one
per simulated fill attempt, empty until a proposal is approved. This module's
resource is the **request** the operator files (``trade_proposals``, source
``manual``): it exists before any order does, and most of them are decided
without ever producing one. The two cannot share a path (a second handler at
the same route is not a merge, it is a collision FastAPI resolves arbitrarily),
so this lives at ``order-requests`` instead. ``ManualOrderOut``/
``ManualOrderDetailOut`` add ``market_id``/``direction`` beyond the brief's
literal three-plus-decision shape — additive fields a client that only reads
the documented ones never notices.

``decision`` is the raw ``trade_proposals.risk_decision`` JSONB, passed through
rather than re-modelled: ``PortfolioTradeOut.entry_snapshot``
(``schemas/portfolio_lists.py``) already sets that precedent for a JSONB blob
whose writer (the pure ``hunter_risk`` engine, via
``RiskDecision.to_jsonable()``) already canonicalises every number as a string
(``hunter_core.strategies.canonical.canonical_json``) — re-typing it into a
second Pydantic tree here would be a shape that can drift from the one the
engine actually writes, maintained by a module that does not own either side.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, field_validator

from hunter_api.schemas.common import StrictModel
from hunter_api.schemas.portfolio_lists import OrderOut
from hunter_core.domain.enums import TradeDirection


def _reject_float(value: object) -> object:
    """A JSON number for money is refused at the door, never silently coerced.

    Mirrors ``hunter_core.admission.sources.ProposalRequest._never_a_float``:
    the same boundary rule, restated here because this is a second, earlier
    boundary (HTTP into Pydantic) the request crosses before it ever reaches
    that validator.
    """
    if isinstance(value, float):
        raise ValueError(
            f"{value!r} is a float; money is Decimal end to end (CLAUDE.md). Send a decimal "
            'string, e.g. "97.5", never a bare JSON number'
        )
    return value


DecimalIn = Annotated[Decimal, BeforeValidator(_reject_float)]

MIN_IDEMPOTENCY_KEY_LENGTH = 8
MAX_IDEMPOTENCY_KEY_LENGTH = 128


class ManualOrderCreate(StrictModel):
    """The operator's order, before the engine has seen it — RISK_ENGINE.md §8."""

    market_id: uuid.UUID
    direction: TradeDirection
    stop: DecimalIn = Field(gt=0)
    requested_notional: DecimalIn | None = Field(default=None, gt=0)

    @field_validator("direction")
    @classmethod
    def _long_or_short(cls, value: TradeDirection) -> TradeDirection:
        """``neutral`` names no side to buy or sell; it is a syntactic refusal
        (422 on the field), not the business one ``direction=short`` earns
        downstream (RISK_ENGINE.md §3.1 check 3, ``modality``)."""
        if value is TradeDirection.NEUTRAL:
            raise ValueError("direction must be 'long' or 'short'; 'neutral' names no order")
        return value


class ManualOrderOut(BaseModel):
    """What the operator asked for, and what — if anything — the engine decided.

    ``status`` collapses ``ProposalStatus`` to the two states a caller who did
    not admit the proposal needs: ``pending`` (the engine has not reached this
    row yet — up to ~1 s, ``admission_cycle``'s poll interval) or ``decided``
    (approved, rejected, expired or failed all read the same from here; the
    reasons live inside ``decision``).
    """

    request_id: uuid.UUID
    market_id: uuid.UUID
    direction: TradeDirection
    status: Literal["pending", "decided"]
    filed_at: datetime
    decision: dict[str, Any] | None
    """``trade_proposals.risk_decision`` verbatim, or ``None`` while pending —
    never ``{}``, which is the column's own default for "not decided yet" and
    would otherwise read as an empty, meaningless decision object."""


class ManualOrderDetailOut(ManualOrderOut):
    """``ManualOrderOut`` plus the order/fill it produced, when it produced one."""

    outcome: OrderOut | None
    """The ``orders`` row this request's approval turned into
    (``orders.proposal_id``), or ``None`` — pending, rejected, expired, or
    approved but not yet picked up by the entry cycle."""
