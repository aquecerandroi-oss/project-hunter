"""Assembling ``GET /api/v1/lab/shadow/curve`` — brief T3.18.

The cumulative net-R series over every **resolved** outcome (``terminal`` with
a known ``r_multiple``) — deliberately *not* gated by ``is_evaluable()``'s
horizon-maturation rule: that gate exists to keep the scoreboard's aggregate
stats from over-representing fast trades, which does not apply to plotting a
trajectory. Excluding just-resolved-but-not-yet-matured trades from the curve
would carve an artificial gap out of its most recent stretch.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from hunter_api.schemas.lab_curve import CurveOut, CurvePointOut
from hunter_api.services.lab_summary_metrics import quantize4
from hunter_core.domain.enums import ShadowTrackingState

if TYPE_CHECKING:
    import uuid

    from hunter_api.repositories.lab_summary import OutcomeRow

__all__ = ["MAX_CURVE_POINTS", "build_curve"]

MAX_CURVE_POINTS = 2000


def build_curve(
    *, strategy_version_id: uuid.UUID, rows: list[OutcomeRow], as_of: datetime
) -> CurveOut:
    resolved = [
        r
        for r in rows
        if r.tracking_state is ShadowTrackingState.TERMINAL and r.r_multiple is not None
    ]
    resolved.sort(key=lambda r: cast("datetime", r.exit_ts))

    truncated = len(resolved) > MAX_CURVE_POINTS
    windowed = resolved[:MAX_CURVE_POINTS]

    points: list[CurvePointOut] = []
    cumulative = Decimal(0)
    for row in windowed:
        r_value = cast("Decimal", row.r_multiple)
        cumulative += r_value
        points.append(
            CurvePointOut(
                ts=cast("datetime", row.exit_ts),
                r=quantize4(r_value),
                cum_r=quantize4(cumulative),
            )
        )

    return CurveOut(
        strategy_version_id=strategy_version_id,
        as_of=as_of,
        points=points,
        truncated=truncated,
    )
