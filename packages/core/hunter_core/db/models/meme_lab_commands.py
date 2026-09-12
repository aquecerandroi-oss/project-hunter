"""``meme_operator_commands`` — an operator's order over an open bet
(``sell_now``) or a pending proposal (``cancel``), written by the API and
applied by the loop (DATABASE.md §34, revision ``0022_meme_lab``).

Split from :mod:`hunter_core.db.models.meme_lab` in T4.16 for the 350-line
budget; that module re-exports the class, so every import of
``hunter_core.db.models.meme_lab.MemeOperatorCommand`` still resolves.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin


class MemeOperatorCommand(Base, UUIDPrimaryKeyMixin):
    """An operator's order over an open bet (``sell_now``) or a pending
    proposal (``cancel``). Written by the API, applied by the loop."""

    __tablename__ = "meme_operator_commands"
    __table_args__ = (
        Index(
            "ix_meme_operator_commands_pending",
            "issued_at",
            postgresql_where=text("applied_at IS NULL"),
        ),
        CheckConstraint("command IN ('sell_now', 'cancel')", name="command_is_a_known_label"),
        CheckConstraint("(bet_id IS NULL) <> (proposal_id IS NULL)", name="exactly_one_target"),
        CheckConstraint("command <> 'sell_now' OR bet_id IS NOT NULL", name="a_sale_targets_a_bet"),
        CheckConstraint(
            "command <> 'cancel' OR proposal_id IS NOT NULL", name="a_cancel_targets_a_proposal"
        ),
        CheckConstraint(
            "(applied_at IS NULL) = (result IS NULL)", name="an_application_says_what_happened"
        ),
        CheckConstraint("char_length(issued_by) > 0", name="issuer_is_not_empty"),
    )

    bet_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "meme_paper_bets.id",
            use_alter=True,
            name="fk_meme_proposals_bet_id_meme_paper_bets",
        )
    )
    """Closes the cycle proposals -> bets -> proposals; ``use_alter`` because a
    cycle cannot be sorted, and the DDL adds it with ``ALTER TABLE`` after both
    tables exist (``ddl/meme_lab.py``)."""
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("meme_proposals.id"))
    command: Mapped[str] = mapped_column(Text)
    issued_by: Mapped[str] = mapped_column(Text)
    issued_at: Mapped[datetime] = mapped_column(server_default=func.now())
    applied_at: Mapped[datetime | None]
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


__all__ = ["MemeOperatorCommand"]
