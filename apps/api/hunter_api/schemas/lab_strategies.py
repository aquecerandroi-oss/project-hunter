"""``GET /api/v1/lab/shadow/strategies`` — brief T3.25.

One row per ``strategies`` key with every version's parameters, lineage,
scoreboard verdict and per-cohort signal counts. Global, no-RLS
(DATABASE.md §16), same as every other Shadow Lab route.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from hunter_api.schemas.lab_scoreboard import ScoreboardMaturityOut
from hunter_core.domain.enums import StrategyVersionStatus


class LineageOut(BaseModel):
    """A replication sibling's parent and arm — DATABASE.md §24.3."""

    replication_parent_id: uuid.UUID
    replication_index: int


class SignalCountsOut(BaseModel):
    """Emitted signals per cohort family (DATABASE.md §24.1)."""

    prospective: int
    replay: int
    replication: int


class StrategyVersionDetailOut(BaseModel):
    strategy_version_id: uuid.UUID
    version: str
    purpose: str
    status: StrategyVersionStatus
    activated_at: datetime | None
    deprecated_at: datetime | None
    code_ref: str | None
    parameters_schema: dict[str, Any]
    """Type/bounds/description per parameter (JSON Schema,
    ``hunter_core.strategies.schema.schema_of``) — "cada diametro" the brief asks
    the web to render, not just the current values."""
    default_parameters: dict[str, Any]
    lineage: LineageOut | None
    promising_at: datetime | None
    promising_by: str | None
    verdict: str
    maturity: ScoreboardMaturityOut
    signal_counts: SignalCountsOut
    obsidian_page: str
    """Convention only: ``03-TRADING/Estrategias/<key>-<version>.md`` — never a
    query against the vault, which is not a database (brief T3.25 item 1)."""


class StrategyOut(BaseModel):
    strategy_id: uuid.UUID
    key: str
    name: str
    description: str | None
    category: str | None
    versions: list[StrategyVersionDetailOut]


class StrategiesOut(BaseModel):
    as_of: datetime
    items: list[StrategyOut]
