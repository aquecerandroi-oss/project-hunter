"""``meme_token_state_history`` (``0067_meme_token_state_history``, EXP-M26 J),
declared here so ``alembic`` autogenerate sees the same schema the DDL created.

One row per effective change of ``meme_tokens.completed_at``/``migrated_at``
(and per value a token is born with), written **only** by the two deferred
constraint triggers the migration installs on ``meme_tokens`` (``SECURITY
DEFINER``; neither role holds ``INSERT``). ``recorded_at`` is ``clock_timestamp()``
at commit: the value of either column *as known at an instant L* is the last
change with ``recorded_at <= L`` (``docs/DATABASE.md`` §70). Global (§1.1): no
``organization_id``, no RLS. The id is ``BIGSERIAL`` (declared deviation from
§1): the rows are born inside the database. Retention is the token's
(``ON DELETE CASCADE``). Names mirror ``infra/migrations/ddl/meme_token_state_history.py``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base

TOKEN_STATE_HISTORY_TABLE = "meme_token_state_history"  # noqa: S105 - a table name
_T = TOKEN_STATE_HISTORY_TABLE


class MemeTokenStateHistory(Base):
    """One change of a token's ``completed_at`` or ``migrated_at`` — never rewritten."""

    __tablename__ = _T
    __table_args__ = (
        CheckConstraint(
            "column_name IN ('completed_at', 'migrated_at')", name="column_is_a_state_column"
        ),
        CheckConstraint("operation IN ('insert', 'update')", name="operation_is_a_known_label"),
        CheckConstraint("old_value IS DISTINCT FROM new_value", name="a_row_is_a_change"),
        CheckConstraint(
            "operation <> 'insert' OR old_value IS NULL", name="an_insert_starts_from_nothing"
        ),
        Index(f"ix_{_T}_mint_recorded_at", "mint", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mint: Mapped[str] = mapped_column(
        Text, ForeignKey("meme_tokens.mint", ondelete="CASCADE"), nullable=False
    )
    column_name: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[datetime | None] = mapped_column(nullable=True)
    new_value: Mapped[datetime | None] = mapped_column(nullable=True)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    db_role: Mapped[str] = mapped_column(Text, nullable=False)
    """The role the writer had ``SET`` (``current_setting('role')``), else the login."""
    recorded_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=text("clock_timestamp()")
    )


__all__ = ["TOKEN_STATE_HISTORY_TABLE", "MemeTokenStateHistory"]
