"""``GET /api/v1/lab/shadow/versions`` — the frozen catalogue (DATABASE.md §16.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from hunter_core.domain.enums import StrategyVersionStatus


class VersionOut(BaseModel):
    strategy_version_id: uuid.UUID
    strategy_key: str
    version: str
    status: StrategyVersionStatus
    code_ref: str | None
    activated_at: datetime | None
    deprecated_at: datetime | None
    superseded_by: uuid.UUID | None
    """Best-effort: reconstructed from the deprecated row's free-text
    ``changelog`` (``infra/scripts/activate_strategy_version.py`` writes
    ``"superseded by <version> (..."``) — there is no durable, FK-backed
    column for this relationship. ``null`` whenever the pattern is absent
    (an ordinary deprecation, or one predating ``--supersede``)."""
    params_hash: str
    default_parameters: dict[str, Any]


class VersionsOut(BaseModel):
    items: list[VersionOut]
