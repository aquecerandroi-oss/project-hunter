"""``meme_decision_tapes`` (``0062_meme_decision_tapes``, T4.89), declared here
so ``alembic`` autogenerate sees the same schema the DDL created.

One row per decision instant of the ``meme_event_gate_v1`` lane: the newest
fills of the WS tape it judged (each with ``block_time``/``received_at``) and
the derived block it also appends to the proposal's ``reasons`` — what the
desk actually saw, which ``meme_trades`` (a polling copy ~44 s late) cannot
tell (R73, KB-0153). Global like ``meme_trades`` (§1.1): no
``organization_id``, no RLS. Column order, constraints and index names mirror
``infra/migrations/ddl/meme_decision_tapes.py`` exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base
from hunter_core.db.models._common import UUID_ARRAY_EMPTY

DECISION_TAPES_TABLE = "meme_decision_tapes"


class MemeDecisionTape(Base):
    """What the event lane saw at ``as_of`` (the evaluation instant)."""

    __tablename__ = DECISION_TAPES_TABLE
    __table_args__ = (
        UniqueConstraint("mint", "as_of", name=f"uq_{DECISION_TAPES_TABLE}_mint_as_of"),
        CheckConstraint("mint <> ''", name="mint_not_blank"),
        CheckConstraint("series <> ''", name="series_not_blank"),
        CheckConstraint("jsonb_typeof(trades) = 'array'", name="trades_is_an_array"),
        CheckConstraint("jsonb_typeof(derived) = 'object'", name="derived_is_an_object"),
        CheckConstraint(
            "jsonb_typeof(trades) <> 'array' OR jsonb_array_length(trades) <= trades_in_window",
            name="slice_within_window",
        ),
        CheckConstraint(
            "jsonb_typeof(trades) <> 'array' OR jsonb_array_length(trades) <= 200",
            name="slice_is_bounded",
        ),
        Index(f"ix_{DECISION_TAPES_TABLE}_as_of", "as_of"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    mint: Mapped[str] = mapped_column(Text, nullable=False)
    as_of: Mapped[datetime] = mapped_column(nullable=False)
    series: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default=UUID_ARRAY_EMPTY
    )
    trades: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    trades_in_window: Mapped[int] = mapped_column(Integer, nullable=False)
    derived: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


__all__ = ["DECISION_TAPES_TABLE", "MemeDecisionTape"]
