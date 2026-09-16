"""The Lab's two audit tables of ``0046_meme_rule_set_history`` (T4.35),
declared here so ``alembic`` autogenerate sees the same schema the DDL
created — the "reverses and re-applies" migration test compares the metadata
with the live database and refused the head on 16/09/2026 because these two
tables (and their indexes) existed only in ``infra/migrations/ddl``.

``meme_rule_set_param_history`` — one row per ``--set-param … --apply`` on a
rule set: old and new value, who, why, the audit ``system_events`` row. R27
(16/09) had to *infer* ``operator/5``'s previous sniper cap from refusal
counts because the params were edited in place and nothing kept the history.

``meme_gate_refusals_by_mint`` — the sampled per-mint trail of the fast
lane's gate (near-misses and proposals, capped per tick, pruned after 7 d),
so "why did coin X not become a proposal at 16:20" is one ``SELECT``, not an
hour of forensics. Both are global tables like ``meme_tokens`` (§1.1): no
``organization_id``, no RLS. Column order, constraints and index names mirror
``infra/migrations/ddl/{meme_rule_set_history,meme_gate_refusals}.py`` exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base

PARAM_HISTORY_TABLE = "meme_rule_set_param_history"
GATE_REFUSALS_TABLE = "meme_gate_refusals_by_mint"


class MemeRuleSetParamHistory(Base):
    """One param change of one rule set, written in the same transaction as
    the ``UPDATE`` by ``infra/scripts/meme_rule_set.py``."""

    __tablename__ = PARAM_HISTORY_TABLE
    __table_args__ = (
        CheckConstraint("changed_by <> ''", name="changed_by_not_blank"),
        CheckConstraint("btrim(reason) <> ''", name="reason_not_blank"),
        CheckConstraint("key <> ''", name="key_not_blank"),
        Index(f"ix_{PARAM_HISTORY_TABLE}_rule_set_changed_at", "rule_set_id", "changed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    rule_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meme_rule_sets.id"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    changed_by: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    system_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class MemeGateRefusalByMint(Base):
    """One judged ``(rule set, mint, instant)`` of the fast lane: ``refusal``
    is ``NULL`` when the row became a proposal."""

    __tablename__ = GATE_REFUSALS_TABLE
    __table_args__ = (
        UniqueConstraint("rule_set_id", "mint", "as_of", name=f"uq_{GATE_REFUSALS_TABLE}"),
        CheckConstraint("mint <> ''", name="mint_not_blank"),
        CheckConstraint("refusal IS NULL OR refusal <> ''", name="refusal_not_blank"),
        Index(f"ix_{GATE_REFUSALS_TABLE}_mint_as_of", "mint", "as_of"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    as_of: Mapped[datetime] = mapped_column(nullable=False)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meme_rule_sets.id"), nullable=False
    )
    mint: Mapped[str] = mapped_column(Text, nullable=False)
    refusal: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    limit: Mapped[Decimal | None] = mapped_column("limit", Numeric, nullable=True)


__all__ = [
    "GATE_REFUSALS_TABLE",
    "PARAM_HISTORY_TABLE",
    "MemeGateRefusalByMint",
    "MemeRuleSetParamHistory",
]
