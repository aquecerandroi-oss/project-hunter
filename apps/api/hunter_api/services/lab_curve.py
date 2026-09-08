"""Assembling ``GET /api/v1/lab/shadow/curve`` — briefs T3.18 e T3.18c.

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
    from collections.abc import Sequence

    from hunter_api.repositories.lab_scoreboard import ReplayRunWindow
    from hunter_api.repositories.lab_summary import OutcomeRow

__all__ = ["MAX_CURVE_POINTS", "OVERLAP_REASON", "build_curve", "overlapping_runs"]

MAX_CURVE_POINTS = 2000

OVERLAP_REASON = "janelas_sobrepostas"
"""Por que a curva recusa o coringa ``replay`` em vez de desenhar (T3.18c, item
10).

Duas corridas sobre a **mesma** janela são a mesma história contada duas vezes:
somadas numa curva acumulada, elas dobram o R e sugerem o dobro da evidência.
Recusar com motivo é a única saída honesta — a curva de uma corrida específica
(``cohort=replay:<uuid>``) continua disponível, e é ela que responde a pergunta.
"""


def overlapping_runs(windows: Sequence[ReplayRunWindow]) -> list[tuple[str, str]]:
    """Os pares de corridas cujas janelas se cruzam, em ordem estável.

    Janelas são semi-abertas (``[from, to)``, ``replay_runs`` §25.1): duas
    corridas adjacentes que se tocam no instante não se sobrepõem.
    """
    ordered = sorted(windows, key=lambda item: (item.window_from, item.window_to))
    clashes: list[tuple[str, str]] = []
    for index, current in enumerate(ordered):
        for other in ordered[index + 1 :]:
            if other.window_from >= current.window_to:
                break
            clashes.append((str(current.run_id), str(other.run_id)))
    return clashes


def build_curve(
    *, strategy_version_id: uuid.UUID, rows: list[OutcomeRow], as_of: datetime, cohort: str
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
        cohort=cohort,
        points=points,
        truncated=truncated,
    )
