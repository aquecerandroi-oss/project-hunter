"""``meme_mature_opportunities`` (``0066_meme_mature_opportunities``, EXP-M26 R1),
declared here so ``alembic`` autogenerate sees the same schema the DDL created.

One row per (EXP-M26 rule set, mint): the first 1-minute lab evaluation in
which the set's pure gate let the mint through, with the inputs read at that
tick, the coverage guard's result, every refusal of the proposal layer and the
proposal (or the named reason there is none). H-022's first opportunity is a
read of this table, never a reconstruction (design §2.2). Global like
``meme_decision_tapes`` (§1.1): no ``organization_id``, no RLS. Column order,
constraints and index names mirror ``infra/migrations/ddl/meme_mature_opportunities.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base
from hunter_core.db.models._common import PERCENT, TEXT_ARRAY_EMPTY

MATURE_OPPORTUNITIES_TABLE = "meme_mature_opportunities"
_T = MATURE_OPPORTUNITIES_TABLE


class MemeMatureOpportunity(Base):
    """EXP-M26's first opportunity for one (rule set, mint) — written once."""

    __tablename__ = _T
    __table_args__ = (
        UniqueConstraint("rule_set_id", "mint", name=f"uq_{_T}_rule_set_id"),
        CheckConstraint("mint <> ''", name="mint_not_blank"),
        CheckConstraint("features_version <> ''", name="features_version_not_blank"),
        CheckConstraint("code_ref <> ''", name="code_ref_not_blank"),
        CheckConstraint("coverage_version <> ''", name="coverage_version_not_blank"),
        CheckConstraint(
            "features_end_time <= evaluated_at", name="the_minute_closed_before_the_tick"
        ),
        CheckConstraint("lane_since <= features_end_time", name="the_lane_ran_before_the_minute"),
        CheckConstraint(
            "fidelity IN ('faithful', 'earlier_pass_unrecorded', 'write_failed', "
            "'eligible_before_lane')",
            name="fidelity_is_a_known_label",
        ),
        CheckConstraint("age_s IS NULL OR age_s >= 0", name="age_is_not_negative"),
        CheckConstraint(
            "line_points IS NULL OR line_points >= 0", name="line_points_are_not_negative"
        ),
        CheckConstraint("jsonb_typeof(inputs) = 'object'", name="inputs_is_an_object"),
        CheckConstraint("jsonb_typeof(gate) = 'array'", name="gate_is_an_array"),
        CheckConstraint(
            "pedigree IS NULL OR jsonb_typeof(pedigree) = 'object'", name="pedigree_is_an_object"
        ),
        CheckConstraint("jsonb_typeof(coverage) = 'object'", name="coverage_is_an_object"),
        CheckConstraint(
            "coverage_status IN ('covered', 'covered_from_birth', 'gap', 'unread')",
            name="coverage_status_is_a_known_label",
        ),
        CheckConstraint(
            "no_proposal_reason IS NULL OR no_proposal_reason IN "
            "('refused', 'insert_failed', 'not_inserted')",
            name="no_proposal_reason_is_known",
        ),
        CheckConstraint(
            "(proposal_id IS NULL) <> (no_proposal_reason IS NULL)", name="a_proposal_or_a_reason"
        ),
        CheckConstraint(
            "(no_proposal_reason IS NOT DISTINCT FROM 'refused') "
            "= (cardinality(proposal_refusals) > 0)",
            name="refused_iff_refusals_are_named",
        ),
        Index(f"ix_{_T}_rule_set_evaluated_at", "rule_set_id", "evaluated_at"),
        Index(
            f"ix_{_T}_proposal_id",
            "proposal_id",
            postgresql_where=text("proposal_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meme_rule_sets.id"), nullable=False
    )
    mint: Mapped[str] = mapped_column(Text, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(nullable=False)
    features_end_time: Mapped[datetime] = mapped_column(nullable=False)
    features_version: Mapped[str] = mapped_column(Text, nullable=False)
    features_computed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    code_ref: Mapped[str] = mapped_column(Text, nullable=False)
    age_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    curve_progress_pct: Mapped[Decimal | None] = mapped_column(PERCENT, nullable=True)
    mcap_sol: Mapped[Decimal | None] = mapped_column(nullable=True)
    curve_volume_1m_sol: Mapped[Decimal | None] = mapped_column(nullable=True)
    participation_pct: Mapped[Decimal | None] = mapped_column(nullable=True)
    creator_net_seller: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    higher_lows: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    breakout_15m: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    distance_to_support_pct: Mapped[Decimal | None] = mapped_column(PERCENT, nullable=True)
    line_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_points: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    mcap_slope_15m: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    mayhem_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    mayhem_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    migrated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    gate: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    pedigree: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    coverage_version: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_status: Mapped[str] = mapped_column(Text, nullable=False)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    proposal_refusals: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=TEXT_ARRAY_EMPTY
    )
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meme_proposals.id"), nullable=True
    )
    no_proposal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    fidelity: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'faithful'"))
    lane_since: Mapped[datetime] = mapped_column(nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


__all__ = ["MATURE_OPPORTUNITIES_TABLE", "MemeMatureOpportunity"]
