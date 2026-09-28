"""Everton's audited per-mint wallet exception (``0068_meme_wallet_exceptions``,
F1, decision 2026-09-28), declared here so ``alembic`` autogenerate sees the
same schema the DDL created. Names mirror ``infra/migrations/ddl/meme_wallet_exceptions.py``.

One row per exception — wallet, token program, mint, the balance and state the
owner verified, the evidence, the reason, the covering Obsidian note — written
only by the owner's audited CLI (``infra/scripts/wallet_holding_exception.py``),
revoked (never deleted, trigger-enforced). Global (§1.1): no
``organization_id``, no RLS. Read at runtime by one module only
(``hunter_meme_executor.wallet_exceptions``, the holdings verdict); an exception
takes its mint off the "unrecognized" list and never recognizes it for anything.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Index, Numeric, SmallInteger, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin

_T = "meme_wallet_holding_exceptions"


class MemeWalletHoldingException(Base, UUIDPrimaryKeyMixin):
    """One audited exception: this wallet may hold this mint without refusing entries."""

    __tablename__ = _T
    __table_args__ = (
        Index(
            f"ux_{_T}_active",
            "wallet",
            "mint",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        CheckConstraint(
            "token_program IN ('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA', "
            "'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb')",
            name="program_is_a_token_program",
        ),
        CheckConstraint(
            "char_length(wallet) BETWEEN 32 AND 44 AND char_length(mint) BETWEEN 32 AND 44 "
            "AND char_length(created_by) > 0",
            name="identity_is_well_formed",
        ),
        CheckConstraint("char_length(reason) >= 10", name="a_reason_is_given"),
        CheckConstraint(
            "note_path LIKE 'obsidian/%.md' AND char_length(note_sha256) = 64",
            name="note_is_under_obsidian",
        ),
        CheckConstraint(
            "max_atoms BETWEEN 1 AND 18446744073709551615", name="atoms_fit_a_u64"
        ),  # a u64; also refuses NaN, which numeric sorts above every number
        CheckConstraint("decimals BETWEEN 0 AND 255", name="decimals_fit_a_byte"),
        CheckConstraint("jsonb_typeof(evidence) = 'object'", name="evidence_is_an_object"),
        CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by IS NULL) "
            "AND (revoked_at IS NULL) = (revoke_reason IS NULL)",
            name="a_revocation_is_whole",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR (char_length(revoked_by) > 0 "
            "AND char_length(revoke_reason) >= 10 AND revoked_at >= created_at)",
            name="a_revocation_is_named",
        ),
    )

    wallet: Mapped[str] = mapped_column(Text)
    token_program: Mapped[str] = mapped_column(Text)
    mint: Mapped[str] = mapped_column(Text)
    max_atoms: Mapped[Decimal] = mapped_column(Numeric(20, 0))
    """The total (atomic units, all accounts of the mint) verified on chain."""
    decimals: Mapped[int] = mapped_column(SmallInteger)
    require_frozen: Mapped[bool] = mapped_column(Boolean)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    note_path: Mapped[str] = mapped_column(Text)
    note_sha256: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    revoked_at: Mapped[datetime | None]
    revoked_by: Mapped[str | None] = mapped_column(Text)
    revoke_reason: Mapped[str | None] = mapped_column(Text)


__all__ = ["MemeWalletHoldingException"]
