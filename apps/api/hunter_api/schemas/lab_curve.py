"""``GET /api/v1/lab/shadow/curve`` — brief T3.18.

The cumulative net-R series of one version's resolved outcomes, ordered by
exit time. Never money: the web applies the T3.17 ruler over ``r``/``cum_r``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from hunter_api.schemas.lab_common import LAB_LABEL, DecimalStr


class CurvePointOut(BaseModel):
    ts: datetime
    r: DecimalStr
    cum_r: DecimalStr


class CurveOut(BaseModel):
    strategy_version_id: uuid.UUID
    as_of: datetime
    cohort: str
    """A coorte que esta curva desenha, ecoada (T3.18c, item 10): sem ela, uma
    linha de replay e a linha viva chegam ao cliente com o mesmo formato e
    nenhuma forma de saber qual é qual."""
    label: str = LAB_LABEL
    points: list[CurvePointOut]
    truncated: bool
    """``true`` when the resolved-outcome population exceeds 2 000 points and
    the tail (most recent exits) was dropped to keep the response bounded."""


__all__ = ["CurveOut", "CurvePointOut"]
