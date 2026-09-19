"""The treasury swap audit trail (DATABASE.md, revision ``0051_meme_treasury_swaps``,
T4.54) — mirrors ``ddl/meme_treasury_swaps.py`` byte for byte so ``alembic
check`` finds nothing to autogenerate.

One row per USDC->SOL attempt ``hunter_meme_executor.treasury`` ever made,
updated in place as it advances ``quoted -> simulated -> submitted ->
confirmed | failed``, or stops at ``refused`` before anything is built. A
``refused`` row names why and sends nothing; a ``confirmed`` row always
carries its signature, its filled amount and the wallet's SOL balance after.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Integer, Numeric, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin

TREASURY_SWAP_STATUSES = (
    "quoted",
    "simulated",
    "submitted",
    "confirmed",
    "failed",
    "refused",
)


class MemeTreasurySwap(Base, UUIDPrimaryKeyMixin):
    """One attempt to swap USDC for SOL to keep the wallet's gas topped up."""

    __tablename__ = "meme_treasury_swaps"
    __table_args__ = (
        Index("ix_meme_treasury_swaps_requested_at", "requested_at"),
        Index(
            "ix_meme_treasury_swaps_signature",
            "signature",
            unique=True,
            postgresql_where=text("signature IS NOT NULL"),
        ),
        CheckConstraint(
            "status IN ('quoted', 'simulated', 'submitted', 'confirmed', 'failed', 'refused')",
            name="status_is_a_known_label",
        ),
        CheckConstraint("(status = 'refused') = (refusal IS NOT NULL)", name="a_refusal_is_named"),
        CheckConstraint(
            "status <> 'refused' OR signature IS NULL", name="a_refused_swap_sends_nothing"
        ),
        CheckConstraint(
            "status <> 'confirmed' OR (signature IS NOT NULL "
            "AND sol_out_filled IS NOT NULL AND wallet_sol_after IS NOT NULL)",
            name="a_confirmed_swap_has_a_fill",
        ),
        CheckConstraint(
            "usdc_in >= 0 AND sol_out_quoted >= 0 "
            "AND (sol_out_filled IS NULL OR sol_out_filled >= 0) "
            "AND price_impact_pct >= 0 AND slippage_bps >= 0 "
            "AND wallet_sol_before >= 0 "
            "AND (wallet_sol_after IS NULL OR wallet_sol_after >= 0)",
            name="amounts_are_not_negative",
        ),
        CheckConstraint("char_length(reason) > 0", name="identity_is_not_empty"),
        CheckConstraint("(input_mint IS NULL) = (output_mint IS NULL)", name="mint_pair_is_named"),
    )

    requested_at: Mapped[datetime] = mapped_column(server_default=func.now())
    reason: Mapped[str] = mapped_column(Text)
    """Why this tick attempted a swap — ``sol_below_floor`` today, named so a
    future trigger does not silently share the label."""

    usdc_in: Mapped[Decimal]
    sol_out_quoted: Mapped[Decimal]
    sol_out_filled: Mapped[Decimal | None]
    price_impact_pct: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    slippage_bps: Mapped[int] = mapped_column(Integer)
    signature: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    refusal: Mapped[str | None] = mapped_column(Text)
    wallet_sol_before: Mapped[Decimal]
    wallet_sol_after: Mapped[Decimal | None]
    input_mint: Mapped[str | None] = mapped_column(Text)
    """T4.73: the mint pair of a generic ``infra/scripts/meme_spot_swap.py``
    swap; ``NULL`` for the USDC->SOL treasury (``0051``)."""
    output_mint: Mapped[str | None] = mapped_column(Text)


__all__ = ["TREASURY_SWAP_STATUSES", "MemeTreasurySwap"]
