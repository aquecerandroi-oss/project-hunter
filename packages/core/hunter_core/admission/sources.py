"""Where an admission request came in through, and what makes it the same request.

Two decisions live here and both happen **before** any lock is taken:

- **the origin is explicit** (``docs/plans/M3.md``, T3.12). ``proposal_source``
  has exactly two members, ``manual`` and ``agent``; a shadow signal carries
  ``purpose = research_only`` and never becomes a proposal, which is a refusal
  at the door rather than a rejected proposal — a rejected proposal is a row, a
  place in the FIFO queue and an audited decision about capital, and shadow
  evidence is entitled to none of the three (``docs/plans/M3.md``, joint
  decision item 9);
- **the idempotency key carries the origin.** ``trade_proposals`` is unique on
  ``(organization_id, idempotency_key)``, so a manual order and an agent
  proposal that happen to mint the same client key would otherwise be the same
  row: the second one would be answered with the first one's decision.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hunter_core.domain.enums import ProposalSource, TradeDirection
from hunter_core.strategies.canonical import params_hash
from hunter_core.strategies.envelope import PURPOSE_RESEARCH_ONLY, AssumedCosts
from hunter_risk.inputs import MarketIdentity

__all__ = [
    "PURPOSE_LIVE",
    "OriginRefused",
    "ProposalRequest",
    "admission_key",
    "request_digest",
    "resolve_source",
]

PURPOSE_LIVE = "live"
"""The only purpose that may reach the wallet. Anything else is refused by name,
so a new label added upstream fails closed instead of being admitted by default.
"""


class OriginRefused(ValueError):
    """The request may not become a proposal at all — wrong origin or purpose.

    Not a rejected decision: a rejection is a *decision about capital*, recorded
    with its checks so the panel can show the whole picture. This is the request
    never having been admissible, and it leaves no row behind.
    """


def resolve_source(source: str | ProposalSource) -> ProposalSource:
    """``manual`` or ``agent``. Anything else is refused, by name."""
    try:
        return ProposalSource(source)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in ProposalSource)
        raise OriginRefused(
            f"{source!r} is not an admission origin; proposal_source is {allowed}. The shadow "
            "bridge is deliberately not a member: a label is a promise that something exists"
        ) from exc


def admission_key(source: ProposalSource, client_key: str) -> str:
    """The value of ``trade_proposals.idempotency_key`` for this request."""
    stripped = client_key.strip()
    if not stripped:
        raise ValueError(
            "client_key is empty; without it a retry cannot be told from a second order"
        )
    return f"{source.value}:{stripped}"


def request_digest(request: ProposalRequest, source: ProposalSource) -> str:
    """The canonical identity of *what was asked* — ``trade_proposals.request_digest``.

    The idempotency key says "this is the same request"; the digest is what
    **proves** it (DATABASE.md §19.3). Without it, a replay of a *rejected*
    proposal could only be compared against the four columns that happen to be
    stored, so a second, different request that reused the key came back as the
    first one's refusal (T3.12, pendência 1).

    Only the fields that decide capital are in it — the wallet, the market, the
    direction, the geometry, the ceiling and the cost hypothesis. The actor is
    not: the same order filed twice by two operators is the same order, and the
    audit trail is where "who" belongs.
    """
    return params_hash(
        {
            "source": source.value,
            "portfolio_id": str(request.portfolio_id),
            "market_id": str(request.market_id),
            "market": request.market.model_dump(mode="json"),
            "direction": request.direction.value,
            "entry_ref": str(request.entry_ref),
            "stop": str(request.stop),
            "requested_notional": (
                None if request.requested_notional is None else str(request.requested_notional)
            ),
            "requested_risk_pct": (
                None if request.requested_risk_pct is None else str(request.requested_risk_pct)
            ),
            "assumed_costs": request.assumed_costs.model_dump(mode="json"),
            "agent_id": None if request.agent_id is None else str(request.agent_id),
        }
    )


class ProposalRequest(BaseModel):
    """One admission request, before the Risk Engine has seen it.

    Frozen, and deliberately without a size: what the wallet may buy is the
    engine's answer, and ``requested_notional`` is only ever a *ceiling* the
    caller adds (RISK_ENGINE.md §4).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_key: str = Field(min_length=1, max_length=200)
    """The caller's own identity for this request — the ``Idempotency-Key`` header
    on the manual route, the signal's identity on the agent bridge."""

    organization_id: uuid.UUID
    portfolio_id: uuid.UUID
    market_id: uuid.UUID
    """The row in ``markets``. The identity below has to name the same market;
    the service compares them against the reference data instead of trusting
    either side."""

    market: MarketIdentity
    direction: TradeDirection
    entry_ref: Decimal = Field(gt=0)
    stop: Decimal = Field(gt=0)
    requested_notional: Decimal | None = Field(default=None, gt=0)
    requested_risk_pct: Decimal | None = Field(default=None, gt=0)
    assumed_costs: AssumedCosts

    agent_id: uuid.UUID | None = None
    signal_id: uuid.UUID | None = None
    agent_enabled: bool = True
    signal_valid: bool = True
    purpose: str = PURPOSE_LIVE

    actor_id: str
    """Who asked, for ``audit_logs``. A user's uuid on the manual route, the
    worker's name on the bridge — never the same field as ``agent_id``, which is
    *what* asked."""

    actor_type: str = "user"

    @field_validator("entry_ref", "stop", "requested_notional", "requested_risk_pct", mode="before")
    @classmethod
    def _never_a_float(cls, value: object) -> object:
        """A float price is refused at the door, not silently converted.

        ``0.1 + 0.2`` reaching ``Decimal`` through Pydantic's coercion arrives as
        ``0.30000000000000004`` and every number downstream inherits it. The pure
        core refuses floats for the same reason (``hunter_risk.base.RiskModel``);
        this is the boundary where the request comes from HTTP, so it has to
        refuse them too rather than rely on the layer behind it.
        """
        if isinstance(value, float):
            raise ValueError(
                f"{value!r} is a float; money and prices are Decimal end to end (CLAUDE.md). "
                "Pass a string or a Decimal, never a binary fraction"
            )
        return value

    @model_validator(mode="after")
    def _long_geometry(self) -> ProposalRequest:
        """A spot long with a stop at or above its reference is a caller bug.

        The engine would refuse it (``signal_validity``), but it would refuse it
        *after* sizing was declared impossible, and the resulting decision would
        say "sem tamanho, insumo ausente: stop_geometry" for what is really a
        malformed request. Refusing here keeps the two apart.
        """
        if self.stop >= self.entry_ref:
            raise ValueError(
                f"stop {self.stop} is not below entry_ref {self.entry_ref}: on a spot long the "
                "protection sits under the entry, and no size exists for the inverse"
            )
        return self

    def origin(self, source: ProposalSource) -> ProposalSource:
        """Refuse the request outright when its origin is not admissible."""
        if self.purpose != PURPOSE_LIVE:
            raise OriginRefused(
                f"purpose {self.purpose!r} may not be admitted; only {PURPOSE_LIVE!r} reaches the "
                f"wallet. {PURPOSE_RESEARCH_ONLY!r} evidence never becomes an order (M3 joint "
                "decision, item 9)"
            )
        if source is ProposalSource.AGENT and self.agent_id is None:
            raise OriginRefused(
                "an agent proposal has to name its agent_id: the origin says which path admitted "
                "it, the agent says who asked, and an audited decision needs both"
            )
        if source is ProposalSource.MANUAL and self.agent_id is not None:
            raise OriginRefused(
                f"a manual order may not name agent {self.agent_id}: the operator's order is not "
                "an agent's, and stamping one would attribute the risk to something that did not "
                "decide it"
            )
        return source
