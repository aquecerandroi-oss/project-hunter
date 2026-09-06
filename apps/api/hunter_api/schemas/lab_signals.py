"""``GET /api/v1/lab/shadow/signals`` — one row per shadow decision + its
tracked outcome (SHADOW-LAB.md §2-§5, contract-S3-lab.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from hunter_api.schemas.common import CursorPage
from hunter_api.schemas.lab_common import DecimalStr
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState


class SignalListItemOut(BaseModel):
    signal_id: uuid.UUID
    strategy_version_id: uuid.UUID
    market: str
    cohort: str
    decision_at: datetime
    source_bar_close: datetime
    reference_price: DecimalStr | None
    stop: DecimalStr | None
    target1: DecimalStr | None
    entry_plan: dict[str, Any]
    virtual_entry: DecimalStr | None
    entry_ts: datetime | None
    exit_price: DecimalStr | None
    exit_ts: datetime | None
    result: OutcomeResult
    tracking_state: ShadowTrackingState
    no_entry_reason: str | None
    censored_reason: str | None
    r_multiple: DecimalStr | None
    r_multiple_reason: str | None
    """``meta.r_net_reason`` — why ``r_multiple`` is null when it is."""
    r_ex_funding: DecimalStr | None
    excursions: dict[str, Any]
    """``signal_outcomes.meta.excursions`` verbatim — never trimmed (unit is
    ``price``, never R; see ``excursions.py``'s module docstring)."""
    purpose: str
    supporting_features: dict[str, Any] | None
    """Always present in the schema; ``null`` unless ``?include=envelope``."""


SignalsPage = CursorPage[SignalListItemOut]
