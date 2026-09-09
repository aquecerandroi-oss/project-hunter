"""``GET /api/v1/radar/coverage`` — an honest snapshot of how much Radar
exists yet (T3.46's quant study, ``.claude/state/notes-T3.46.md``): coverage
of the monitored universe, baseline maturity, detector health and the
highest score ever recorded. Additive to the T2.6 radar contract — nothing
on ``schemas/radar.py`` changes.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from hunter_api.schemas.radar import DecimalStr
from hunter_core.domain.enums import AnomalyType

__all__ = ["RadarCoverageOut", "RadarDetectorOut"]


class RadarDetectorOut(BaseModel):
    """One of the twelve ``AnomalyType`` members against what it has actually
    produced in the last 31 days, plus why it is silent when it is.
    """

    type: AnomalyType
    rows_31d: int
    disarmed_reason: str | None = None
    """The scanner's own declared reason (``hb:scanner:*``'s
    ``detectors_disarmed`` field, ``services/scanner-worker
    /hunter_scanner_worker/health.py``) — ``None`` both when the detector is
    producing AND when it is silent with no reason declared. The two must
    stay tellable apart on screen (``rows_31d`` does that): a detector with
    ``rows_31d == 0`` and ``disarmed_reason is None`` is the defect T3.46
    flagged (``ORDERBOOK_IMBALANCE``, ``OPEN_INTEREST_SPIKE``,
    ``TRADE_VELOCITY_SPIKE`` today) — silence with no reason declared,
    exactly what this project's own honesty rule forbids."""


class RadarCoverageOut(BaseModel):
    markets_monitored: int
    markets_with_anomaly: int
    baselines_usable: int
    baselines_under_construction: int
    bootstrap_pointer: str | None
    """The scanner's own ``baselines_state`` heartbeat sentence (e.g.
    ``"bootstrapping 1000FLOKIUSDT (4/200)"``) — ``None`` only when no
    ``hb:scanner:*`` heartbeat could be read at all, never an invented
    "idle"."""
    baseline_gate_v2_pct: DecimalStr | None
    """% of ``feature_baselines`` rows whose ``distinct_days``/``sample_size``
    clear the *active* ``opportunity_weights.weights["baseline_gate"]`` —
    ``None`` when there is no active weight vector or no baseline row exists
    yet, never a fabricated ``0``."""
    detectors: list[RadarDetectorOut]
    max_score_ever: DecimalStr | None
    first_anomaly_at: datetime | None
    as_of: datetime
