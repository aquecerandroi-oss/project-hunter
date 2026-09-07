"""The entry side of RISK_ENGINE.md §10: one attempt, behind one approval.

An entry is a single attempt against the eligible book and whatever does not
fill is cancelled for good — no automatic parcelling, which is what the M3 joint
decision (item 3) forbids. Two identities make that safe to replay:

- ``client_order_id = entry:{proposal_id}`` — derived, never random, so a
  redelivered ``proposals.decided`` collides with ``uq_orders_client_order_id``
  instead of opening a second position for one decision;
- ``execution_key = entry:{proposal_id}`` — the same idea one level down, on
  ``fills`` (``docs/DATABASE.md`` §18.3).

And the guarantee of §8, as a constructor rather than a convention: the order
**holds** the :class:`~hunter_risk.decision.RiskDecision`. A boolean would let a
caller build the order of a rejected proposal and pass ``True``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, model_validator

from hunter_core.domain.enums import OrderSide
from hunter_core.domain.market import NormalizedTrade
from hunter_core.execution.adapter import EntryWithoutApproval, ExecutionModel
from hunter_core.execution.idempotency import decision_fingerprint
from hunter_risk.decision import RiskDecision

__all__ = ["MarketEntryOrder", "client_order_id_for_entry", "execution_key_for_entry"]


def client_order_id_for_entry(proposal_id: uuid.UUID) -> str:
    """Derived, never random: the replay of one decision is one order."""
    return f"entry:{proposal_id}"


def execution_key_for_entry(proposal_id: uuid.UUID) -> str:
    return f"entry:{proposal_id}"


class MarketEntryOrder(ExecutionModel):
    """The one attempt an approved entry gets — and it carries the approval itself.

    The order **holds the** :class:`~hunter_risk.decision.RiskDecision`, not a
    boolean saying one existed. With a flag, a caller could build the order of a
    rejected proposal, pass ``True`` and get a fill (Astra, T3.4 diff review,
    finding 1). With the object there is nothing to flip: ``RiskDecision``
    refuses to be ``approved`` while any check did not pass, and the size here
    can only be at or below the size the engine published.
    """

    decision: RiskDecision
    qty: Decimal = Field(gt=0)
    """At or below ``decision.sizing.qty``: a ceiling, never a suggestion."""
    decision_at: datetime
    """When the decision was made. The eligible book is the one *after* this plus
    the declared latency — never the snapshot the decision itself looked at."""
    side: OrderSide = OrderSide.BUY

    @model_validator(mode="after")
    def _only_behind_an_approval(self) -> MarketEntryOrder:
        sizing = self.decision.sizing
        if not self.decision.approved or self.decision.kind != "entry" or sizing is None:
            raise EntryWithoutApproval(
                f"decision {self.decision.proposal_id} is not an approved entry: "
                f"approved={self.decision.approved} kind={self.decision.kind}"
            )
        if self.qty > sizing.qty:
            raise EntryWithoutApproval(
                f"the order asks for more than the decision approved: {self.qty} > {sizing.qty}"
            )
        if self.side is not OrderSide.BUY:
            raise ValueError("spot entries are long-only (directive §6)")
        return self

    @property
    def proposal_id(self) -> uuid.UUID:
        return self.decision.proposal_id

    @property
    def portfolio_id(self) -> uuid.UUID:
        return self.decision.portfolio_id

    @property
    def entry_ref(self) -> Decimal:
        """The price the sizing was measured at — the slippage comparison base."""
        sizing = self.decision.sizing
        assert sizing is not None
        return sizing.sizing_price

    @property
    def stop(self) -> Decimal:
        sizing = self.decision.sizing
        assert sizing is not None
        return sizing.stop

    @property
    def client_order_id(self) -> str:
        return client_order_id_for_entry(self.proposal_id)

    @property
    def execution_key(self) -> str:
        return execution_key_for_entry(self.proposal_id)

    @classmethod
    def from_decision(cls, decision: RiskDecision, *, decision_at: datetime) -> MarketEntryOrder:
        """Build the order the decision authorises — or refuse, loudly."""
        if not decision.approved or decision.kind != "entry" or decision.sizing is None:
            raise EntryWithoutApproval(
                f"decision {decision.proposal_id} is not an approved entry: "
                f"approved={decision.approved} kind={decision.kind}"
            )
        return cls(decision=decision, qty=decision.sizing.qty, decision_at=decision_at)

    def report_identity(self, observed_trade: NormalizedTrade | None) -> dict[str, Any]:
        """The identity every report of this order carries.

        An entry has no *trigger*: nothing fired it but the decision, so
        ``trigger_trade_id`` stays empty and only the trade observed at the
        attempt is recorded.
        """
        return {
            "kind": "entry",
            "execution_key": self.execution_key,
            "client_order_id": self.client_order_id,
            "proposal_id": self.proposal_id,
            "submitted_qty": self.qty,
            "decision_fingerprint": decision_fingerprint(self.decision),
            "side": OrderSide.BUY,
            "planned_price": self.entry_ref,
            "decision_at": self.decision_at,
            "observed_trade_id": None if observed_trade is None else observed_trade.trade_id,
        }
