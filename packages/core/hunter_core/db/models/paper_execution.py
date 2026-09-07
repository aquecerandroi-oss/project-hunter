"""Durable exit intentions and the participation ledger — DATABASE.md §18.4/§18.5.

Two tables for two things the M3 joint decision refuses to leave implicit.

**Intention is not attempt** (RISK_ENGINE.md §10). An entry is one attempt and
whatever is unfilled is cancelled for good. A *protection* is not: the attempt
ends, the intention survives for the remaining quantity, with new attempts of
their own identity, and only ends when the intended quantity is liquidated or an
explicit, audited substitution replaces it. The attempt is still an ``orders``
row — which now carries ``exit_intent_id`` — and the intention is a row here. The
scenario this exists to prevent: a stop for 10 units finds 4 sellable, the
cancellation of the remainder closes the intention, and 6 units are left
unprotected, including across a restart.

**Participation is a budget, not a per-order ceiling** (RISK_ENGINE.md §4). It is
keyed on ``(market_id, capital scope)``, shared by every agent and the manual
order, and consumed over a rolling 60 s window. Recording it as an immutable
**event log** is what makes "não fracionar ordens para contornar limites" a
mechanism: the second order of 0,8 % finds the budget already spent by the
first, cancelling gives back only the unexecuted part, and a retry does not
restart anything because the window is keyed on when the effect happened.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import org_fk, pg_enum, tenant_scoped_fk
from hunter_core.domain.enums import ExitIntentState, ExitReason, ParticipationEntryKind

_LIVE_INTENT = "state IN ('open', 'blocked_residual')"
"""An intention still holding sellable quantity — the two non-terminal states."""


class PortfolioExitIntent(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A durable intention to exit, distinct from any single attempt at it."""

    __tablename__ = "portfolio_exit_intents"
    __table_args__ = (
        org_fk(),
        tenant_scoped_fk("portfolio_id", "portfolios"),
        # The full identity of the position, not just its id. With a
        # single-column FK an intention could name organization A's position
        # while declaring portfolio B and market ETH: every constraint passes,
        # the worker locks the wrong wallet and holds the wrong market in
        # collection (Astra's counter-example to the first draft).
        ForeignKeyConstraint(
            ["position_id", "organization_id", "portfolio_id", "market_id"],
            [
                "positions.id",
                "positions.organization_id",
                "positions.portfolio_id",
                "positions.market_id",
            ],
            ondelete="CASCADE",
        ),
        # A successor must belong to the same position; RESTRICT because an
        # intention that supersedes another may not be deleted out from under it.
        #
        # **Deferred, and that is what makes a substitution writable at all.**
        # Replacing A with B under the same ``protection_key`` has no legal
        # order otherwise: inserting B first hits the live partial unique
        # (A is still open), and retiring A first points at a B that does not
        # exist yet. With the check deferred to COMMIT the protocol is
        # (1) retire A naming B's id — application-generated UUIDs are known in
        # advance — then (2) insert B. Astra raised this in the diff review; it
        # is better closed here than discovered by T3.4.
        ForeignKeyConstraint(
            ["superseded_by_id", "position_id"],
            ["portfolio_exit_intents.id", "portfolio_exit_intents.position_id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            # Named explicitly: the convention would generate 66 characters and
            # Postgres truncates identifiers at 63.
            name="fk_portfolio_exit_intents_superseded_by_id",
        ),
        UniqueConstraint("id", "position_id", name="uq_portfolio_exit_intents_id_position"),
        # The target of ``orders.exit_intent_id``'s composite FK.
        UniqueConstraint(
            "id",
            "organization_id",
            "portfolio_id",
            "market_id",
            name="uq_portfolio_exit_intents_id_scope",
        ),
        # One live intention per protection, not per reason: a position with two
        # take-profit levels legitimately has two ``target`` intentions with
        # different quantities, and §10 never asks for a single target — it asks
        # that the same unit is not sold twice, which the shared lock does.
        Index(
            "uq_portfolio_exit_intents_live",
            "position_id",
            "protection_key",
            unique=True,
            postgresql_where=text(_LIVE_INTENT),
        ),
        Index("ix_portfolio_exit_intents_org_portfolio_state", "organization_id", "state"),
        CheckConstraint("intended_qty > 0", name="intended_qty_positive"),
        CheckConstraint(
            "filled_qty >= 0 AND filled_qty <= intended_qty", name="filled_qty_within_intent"
        ),
        CheckConstraint(
            "trigger_price IS NULL OR trigger_price > 0", name="trigger_price_positive"
        ),
        # Fulfilled means the intended quantity was really liquidated — so an
        # intention can never be marked done by decree, and a protection whose
        # quantity was taken by a competing one terminates as ``voided``.
        CheckConstraint(
            "(state = 'fulfilled') = (filled_qty = intended_qty)", name="fulfilled_means_filled"
        ),
        CheckConstraint(
            "(state = 'superseded') = (superseded_by_id IS NOT NULL)",
            name="superseded_names_its_successor",
        ),
        CheckConstraint("state <> 'voided' OR closed_reason IS NOT NULL", name="voided_states_why"),
        CheckConstraint(
            "(state IN ('fulfilled', 'superseded', 'voided')) = (closed_at IS NOT NULL)",
            name="terminal_states_are_closed",
        ),
        CheckConstraint("id <> superseded_by_id", name="no_self_supersession"),
        CheckConstraint(
            "(degraded_since IS NULL) = (degraded_reason IS NULL)",
            name="degradation_is_all_or_nothing",
        ),
        CheckConstraint("char_length(protection_key) > 0", name="protection_key_not_empty"),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(index=True)
    position_id: Mapped[uuid.UUID] = mapped_column(index=True)
    market_id: Mapped[uuid.UUID] = mapped_column(index=True)
    reason: Mapped[ExitReason] = mapped_column(pg_enum("exit_reason"))
    """Reuses the existing enum instead of coining a second vocabulary for the
    same idea: stop, target, invalidation, manual, kill switch, risk event."""

    protection_key: Mapped[str] = mapped_column(Text)
    """The protection's stable identity within the position (``stop``,
    ``target:1``, ``target:2``, ``manual``). Price is deliberately **not** the
    identity: moving a stop is a revision of the same protection, not a new one."""

    state: Mapped[ExitIntentState] = mapped_column(
        pg_enum("exit_intent_state"), server_default=ExitIntentState.OPEN.value
    )
    intended_qty: Mapped[Decimal]
    filled_qty: Mapped[Decimal] = mapped_column(server_default="0")
    trigger_price: Mapped[Decimal | None]
    degraded_since: Mapped[datetime | None]
    degraded_reason: Mapped[str | None] = mapped_column(Text)
    """Set together. No usable book does not fabricate a fill: the exit stays
    pending and *marked* degraded, with an alert, and a candle never supplies a
    retroactive fill."""

    superseded_by_id: Mapped[uuid.UUID | None]
    closed_reason: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None]


class ParticipationConsumption(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """One immutable entry in the participation budget of ``(market, wallet)``."""

    __tablename__ = "participation_consumptions"
    __table_args__ = (
        org_fk(),
        tenant_scoped_fk("portfolio_id", "portfolios"),
        # Default ``NO ACTION``, deliberately, on all three: a plain
        # ``DELETE FROM orders`` is refused because erasing an executed
        # consumption silently gives the market's budget back, while an
        # organization-wide cascade still passes, since the ledger rows go with
        # it in the same statement.
        ForeignKeyConstraint(
            ["proposal_id", "organization_id", "portfolio_id", "market_id"],
            [
                "trade_proposals.id",
                "trade_proposals.organization_id",
                "trade_proposals.portfolio_id",
                "trade_proposals.market_id",
            ],
        ),
        ForeignKeyConstraint(
            ["order_id", "organization_id", "portfolio_id", "market_id"],
            [
                "orders.id",
                "orders.organization_id",
                "orders.portfolio_id",
                "orders.market_id",
            ],
        ),
        # And the fill has to be a fill *of that order*. Without this the entry
        # names a real fill, a real order and a real market that have nothing to
        # do with each other: an 80-USDT BTC execution booked against the ETH
        # budget leaves those 80 available to the next BTC entry, and uniqueness
        # per fill does not correct a wrong attribution (Astra, diff review).
        ForeignKeyConstraint(["fill_id", "order_id"], ["fills.id", "fills.order_id"]),
        # Idempotency by *logical effect*, not by a fresh UUID per attempt:
        # one reservation and one release per proposal, one execution per fill.
        # A replayed fill therefore cannot spend the budget twice, and a retry
        # cannot renew ``occurred_at`` to slide the 60 s window forward.
        Index(
            "uq_participation_reserved",
            "proposal_id",
            unique=True,
            postgresql_where=text("kind = 'reserved'"),
        ),
        Index(
            "uq_participation_released",
            "proposal_id",
            unique=True,
            postgresql_where=text("kind = 'released'"),
        ),
        Index(
            "uq_participation_executed",
            "fill_id",
            unique=True,
            postgresql_where=text("kind = 'executed'"),
        ),
        Index(
            "ix_participation_window",
            "organization_id",
            "portfolio_id",
            "market_id",
            "occurred_at",
        ),
        CheckConstraint("notional > 0", name="notional_positive"),
        CheckConstraint(
            "(kind = 'executed') = (fill_id IS NOT NULL AND order_id IS NOT NULL)",
            name="execution_names_its_fill",
        ),
    )

    portfolio_id: Mapped[uuid.UUID] = mapped_column(index=True)
    """The capital scope of RISK_ENGINE.md §11 in practice: with one principal
    wallet per ``(organization, workspace)``, the wallet's lock serialises the
    budget. More than one wallet in a scope would need a lock of its own first —
    a written condition, not an assumption."""

    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("markets.id", ondelete="RESTRICT"), index=True
    )
    """Pinned to the proposal's market — and, for an execution, to the order's.
    The budget is keyed on ``(market_id, capital scope)``, so a misattributed
    entry is not a bookkeeping detail: it hands one market's minute to another."""
    proposal_id: Mapped[uuid.UUID] = mapped_column(index=True)
    """The reservation's identity. Legitimate because a proposal has exactly one
    reservation cycle — ``trade_proposals.reservation_state`` is a single axis on
    a single row — and that invariant is what makes a separate reservation id
    unnecessary here."""

    order_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    fill_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    kind: Mapped[ParticipationEntryKind] = mapped_column(pg_enum("participation_entry_kind"))
    notional: Mapped[Decimal]
    occurred_at: Mapped[datetime]
    """When the durable effect happened — the fill's timestamp for an execution,
    not when the ledger row was written. The rolling window is keyed on this, so
    the turn of a minute forgives nothing inside the 60 s."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
