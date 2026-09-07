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
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hunter_core.domain.enums import ProposalSource, TradeDirection
from hunter_core.strategies.canonical import params_hash
from hunter_core.strategies.envelope import PURPOSE_PAPER, PURPOSE_RESEARCH_ONLY, AssumedCosts
from hunter_risk.inputs import MarketIdentity

__all__ = [
    "PURPOSE_LIVE",
    "REQUEST_PAYLOAD_KEYS",
    "OriginRefused",
    "ProposalRequest",
    "admission_key",
    "request_digest",
    "request_payload",
    "resolve_source",
]

REQUEST_PAYLOAD_KEYS: tuple[str, ...] = (
    "client_key",
    "market_id",
    "direction",
    "entry_ref",
    "stop",
    "target",
    "requested_notional",
    "assumed_costs",
)
"""The keys of ``trade_proposals.request_payload`` — DATABASE.md §21.1.

Frozen here next to the digest because the two answer the same question from
opposite ends: the payload is *what was asked*, and the digest is the proof that
two askings are the same one. The database holds the same eight in a CHECK
(``ck_trade_proposals_request_payload_is_a_geometry``), deliberately written out
there rather than imported, so a change on one side does not silently become
true on the other.
"""

PURPOSE_LIVE = "live"
"""Real money, Phase 4. Refused by name — not merely "not paper" — so an
operator reading a refusal for this one sees *why* rather than a generic
"not admissible" (D10, ``.claude/state/decisions-delegated-2026-09-07.md``):
``ENABLE_LIVE_TRADING`` stays ``false`` and ``LiveExecutionAdapter`` raises
``LiveTradingDisabled`` regardless of what reaches this gate.
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
            "target": None if request.target is None else str(request.target),
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


def request_payload(request: ProposalRequest) -> dict[str, Any]:
    """The geometry archived in ``trade_proposals.request_payload`` (§21.1).

    What the operator actually asked for, in the canonical form the rest of the
    project uses for a number that has to survive a round trip: **money as a
    JSON string**, never a JSON number, because a JSON number comes back through
    most parsers as a float and a price that returns as ``0.30000000000000004``
    is the whole reason ``Decimal`` is enforced at this boundary.

    Every key is always present; "absent" is JSON ``null``, never omission, so a
    reader never has to decide whether a missing ``target`` means "no target" or
    "the writer forgot". ``target`` is ``request.target`` when the caller named
    one — the T3.14 bridge passes the shadow signal's own target — and ``null``
    for every request that does not (the operator's route today has no
    take-profit field of its own; the exit geometry usually comes from the
    protection cycle).

    ``organization_id``, ``portfolio_id``, ``agent_id`` and ``signal_id`` are
    **not** here: they are columns, and repeating them would be a second answer
    to a question the row already answers. ``market_id`` and ``direction`` are
    the deliberate exception — they are what makes the payload readable on its
    own, and the composite foreign keys of §18.3 already make the two
    disagreeing unrepresentable.
    """
    return {
        "client_key": request.client_key,
        "market_id": str(request.market_id),
        "direction": request.direction.value,
        "entry_ref": str(request.entry_ref),
        "stop": str(request.stop),
        "target": None if request.target is None else str(request.target),
        "requested_notional": (
            None if request.requested_notional is None else str(request.requested_notional)
        ),
        "assumed_costs": request.assumed_costs.model_dump(mode="json"),
    }


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
    target: Decimal | None = Field(default=None, gt=0)
    """The take-profit level, when the caller has one. ``None`` travels as JSON
    ``null`` (§21.1) — never omission — through both :func:`request_digest` and
    :func:`request_payload`, so a request without a target and a request whose
    writer forgot it are never the same fact."""

    requested_notional: Decimal | None = Field(default=None, gt=0)
    requested_risk_pct: Decimal | None = Field(default=None, gt=0)
    assumed_costs: AssumedCosts

    agent_id: uuid.UUID | None = None
    signal_id: uuid.UUID | None = None
    agent_enabled: bool = True
    signal_valid: bool = True
    purpose: str = PURPOSE_PAPER
    """The wallet the request may reach (D10). Defaults to ``paper`` — the only
    coorte with a fictitious wallet in front of it today; ``live`` is Phase 4 and
    ``research_only`` evidence is never a request at all."""

    actor_id: str
    """Who asked, for ``audit_logs``. A user's uuid on the manual route, the
    worker's name on the bridge — never the same field as ``agent_id``, which is
    *what* asked."""

    actor_type: str = "user"

    @field_validator(
        "entry_ref", "stop", "target", "requested_notional", "requested_risk_pct", mode="before"
    )
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
        if self.purpose == PURPOSE_LIVE:
            raise OriginRefused(
                f"purpose {PURPOSE_LIVE!r} may not be admitted: live é Fase 4; "
                "ENABLE_LIVE_TRADING=false"
            )
        if self.purpose != PURPOSE_PAPER:
            raise OriginRefused(
                f"purpose {self.purpose!r} may not be admitted; only {PURPOSE_PAPER!r} reaches "
                f"the wallet. {PURPOSE_RESEARCH_ONLY!r} evidence never becomes an order (M3 joint "
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
