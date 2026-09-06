"""Features, anomalies, regimes and opportunities — DATABASE.md §5.

All global. Composite indexes are declared ascending: Postgres scans a btree
backwards at the same cost, so ``ORDER BY <col> DESC`` on the trailing column of
these indexes is served without a DESC index, and an ascending index compares
cleanly under ``alembic check``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import (
    CONFIDENCE,
    JSONB_EMPTY,
    SCORE,
    SQL_FALSE,
    TEXT_ARRAY_EMPTY,
    UUID_ARRAY_EMPTY,
    pg_enum,
)
from hunter_core.domain.enums import (
    AnomalyEvaluationState,
    AnomalyStatus,
    AnomalyType,
    FeatureCategory,
    MarketRegime,
    OpportunityStage,
    OpportunityStatus,
    RegimeScope,
    TradeDirection,
)

_MARKET_FK = "markets.id"


class FeatureDefinition(Base, UUIDPrimaryKeyMixin):
    """The registry a ``FeatureCalculator`` publishes itself into (PIPELINE.md §2)."""

    __tablename__ = "feature_definitions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_feature_definitions_name"),)

    name: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    category: Mapped[FeatureCategory] = mapped_column(pg_enum("feature_category"))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    description: Mapped[str | None] = mapped_column(Text)
    inputs: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=TEXT_ARRAY_EMPTY)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class FeatureSnapshot(Base):
    """One wide JSONB row per market per closed minute."""

    __tablename__ = "feature_snapshots"
    __table_args__ = {"postgresql_partition_by": "RANGE (ts)"}

    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(_MARKET_FK, ondelete="CASCADE"), primary_key=True
    )
    ts: Mapped[datetime] = mapped_column(primary_key=True)
    feature_set_version: Mapped[str] = mapped_column(Text)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)


class Anomaly(Base, UUIDPrimaryKeyMixin):
    """A detector firing on one market. One ``active`` row per (market, type)."""

    __tablename__ = "anomalies"
    __table_args__ = (
        Index("ix_anomalies_market_detected", "market_id", "detected_at"),
        Index("ix_anomalies_status_detected", "status", "detected_at"),
        Index("ix_anomalies_type_detected", "type", "detected_at"),
        Index(
            "uq_anomalies_active_per_market_type",
            "market_id",
            "type",
            unique=True,
            postgresql_where=text("status = 'active'::anomaly_status"),
        ),
    )

    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_MARKET_FK, ondelete="CASCADE"))
    type: Mapped[AnomalyType] = mapped_column(pg_enum("anomaly_type"))
    severity: Mapped[Decimal] = mapped_column(SCORE)
    confidence: Mapped[Decimal] = mapped_column(CONFIDENCE)
    detected_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None]
    status: Mapped[AnomalyStatus] = mapped_column(
        pg_enum("anomaly_status"), server_default=AnomalyStatus.ACTIVE.value
    )
    evaluation_state: Mapped[AnomalyEvaluationState] = mapped_column(
        pg_enum("anomaly_evaluation_state"), server_default=AnomalyEvaluationState.OK.value
    )
    """Whether the data behind the last evaluation can be believed — a different
    question from ``status``, which is where the anomaly is in its lifecycle.
    ``active`` + ``unknown`` is the state of an anomaly whose feed went away: it
    stays active and becomes ineligible, and is never resolved by absence."""
    baseline: Mapped[Decimal | None]
    current_value: Mapped[Decimal | None]
    deviation: Mapped[Decimal | None]
    unit: Mapped[str | None] = mapped_column(Text)
    feature_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, server_default=JSONB_EMPTY)
    detector_version: Mapped[str | None] = mapped_column(Text)


class MarketRegimeRow(Base, UUIDPrimaryKeyMixin):
    """The classified regime for a scope over a time window.

    ``end_time IS NULL`` means "in force"; the partial unique index makes a
    second open regime per scope impossible.
    """

    __tablename__ = "market_regimes"
    __table_args__ = (
        Index("ix_market_regimes_scope_start", "scope", "start_time"),
        Index(
            "uq_market_regimes_open_per_scope",
            "scope",
            unique=True,
            postgresql_where=text("end_time IS NULL"),
        ),
    )

    scope: Mapped[RegimeScope] = mapped_column(pg_enum("regime_scope"))
    regime: Mapped[MarketRegime] = mapped_column(pg_enum("market_regime"))
    confidence: Mapped[Decimal | None] = mapped_column(CONFIDENCE)
    start_time: Mapped[datetime]
    end_time: Mapped[datetime | None]
    supporting_features: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    classifier_version: Mapped[str | None] = mapped_column(Text)


class OpportunityWeights(Base, UUIDPrimaryKeyMixin):
    """A versioned weight vector for the opportunity score.

    At most one version is active at a time — the partial unique index makes a
    second one impossible instead of leaving the scorer to pick arbitrarily from
    whatever ``WHERE is_active`` returns.
    """

    __tablename__ = "opportunity_weights"
    __table_args__ = (
        Index(
            "uq_opportunity_weights_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    version: Mapped[str] = mapped_column(Text, unique=True)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(server_default=SQL_FALSE)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Opportunity(Base, UUIDPrimaryKeyMixin):
    """A scored, explainable setup on a market. Global: the same row is read by
    every organization; ``IN_POSITION``/``BLOCKED_BY_RISK`` are derived per org
    at read time and are deliberately absent from ``opportunity_status``.
    """

    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opportunities_status_score", "status", "score"),
        Index("ix_opportunities_market_first_seen", "market_id", "first_seen_at"),
        Index(
            "uq_opportunities_open_per_market",
            "market_id",
            unique=True,
            postgresql_where=text("expired_at IS NULL"),
        ),
        CheckConstraint(
            "(status = 'EXPIRED'::opportunity_status) = (expired_at IS NOT NULL)",
            name="expired_at_matches_status",
        ),
    )

    market_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(_MARKET_FK, ondelete="CASCADE"))
    direction: Mapped[TradeDirection] = mapped_column(pg_enum("trade_direction"))
    score: Mapped[Decimal] = mapped_column(SCORE)
    confidence: Mapped[Decimal] = mapped_column(CONFIDENCE)
    peak_score: Mapped[Decimal | None] = mapped_column(SCORE)
    status: Mapped[OpportunityStatus] = mapped_column(
        pg_enum("opportunity_status"), server_default=OpportunityStatus.NORMAL.value
    )
    decomposition: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    weights_version: Mapped[str | None] = mapped_column(Text)
    regime_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("market_regimes.id", ondelete="SET NULL"), index=True
    )
    anomaly_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), server_default=UUID_ARRAY_EMPTY
    )
    supporting_signal_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), server_default=UUID_ARRAY_EMPTY
    )
    stage: Mapped[OpportunityStage] = mapped_column(
        pg_enum("opportunity_stage"), server_default=OpportunityStage.NONE.value
    )
    """EARLY / DEVELOPING / EXTENDED, or ``NONE`` while the ATR is warming up.
    Orthogonal to ``status``: a WATCHING opportunity can be EARLY and a HOT one
    EXTENDED, and it is the pair that answers "is this worth entering?"."""

    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    """The deterministic pt-BR answer to "why are we looking at this?", generated
    from ``decomposition`` by a template — never by an LLM. Stored rather than
    rendered on read so the sentence a person saw can be reproduced after the
    weights version changes."""

    below_40_since: Mapped[datetime | None]
    """Start of the current run of *valid* observations scoring under 40, or
    ``NULL``. Durable because the 15-minute expiry has to survive a restart, and
    recomputable from nothing else: a quality gap breaks the run (the unknown
    interval is never counted as "below 40"), and only the process that saw the
    observations knows that."""

    feature_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    """The full envelope of the current sample: the exact feature vector used,
    per-entry ``ts``/quality/availability, ``as_of``, ``baseline_ids``,
    ``regime_id``, versions, and the ``state_in``/``state_out`` of the hysteresis
    and confirmation counters. Recomputing a stored score from its envelope is a
    guarantee; replaying the intra-minute trajectory is explicitly not (M2 is a
    bar-only profile)."""

    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expired_at: Mapped[datetime | None]
    """Terminal. The partial unique index above keys episode identity on this
    column, and the CHECK keeps it in lockstep with ``status = 'EXPIRED'`` so the
    two can never disagree about whether an episode is still open."""


class OpportunityHistory(Base):
    """Score trajectory of an opportunity, one row per preserved sample.

    Written on a delta of >= 3 points against the **last persisted** score, on a
    change of status/stage/version/quality, and periodically every five minutes —
    so the series is a record of decisions, not a fixed-rate sampling of them.
    """

    __tablename__ = "opportunity_history"
    __table_args__ = {"postgresql_partition_by": "RANGE (ts)"}

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    ts: Mapped[datetime] = mapped_column(primary_key=True)
    score: Mapped[Decimal] = mapped_column(SCORE)
    confidence: Mapped[Decimal | None] = mapped_column(CONFIDENCE)
    status: Mapped[OpportunityStatus] = mapped_column(pg_enum("opportunity_status"))
    stage: Mapped[OpportunityStage] = mapped_column(
        pg_enum("opportunity_stage"), server_default=OpportunityStage.NONE.value
    )
    """A stage change is one of the triggers that writes a history row, so the
    row has to carry the stage it changed to — otherwise the trajectory shows a
    sample appearing for no visible reason."""

    decomposition: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    """Same shape as ``Opportunity.feature_snapshot``, per preserved sample. This
    is what makes "recompute this score from what it actually saw" true after the
    baselines, the weights and the regime have all moved on."""
