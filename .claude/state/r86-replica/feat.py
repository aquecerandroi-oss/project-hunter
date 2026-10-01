"""r86-replica — reconstrução independente das variáveis da H-027 (código próprio, sem ler r86/).

razao_mm20d: D = data UTC de obs − 1 dia; os 20 dias D−19..D exigem 1 440 velas 1 min finais
(distintas) e o fechamento da vela que abre às 23:59; guarda: max(received_at) final de cada dia
≤ emitted_at. O dia corrente nunca entra (D < data(obs) por construção).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import numpy as np

MAD_K = 1.4826


@dataclass(frozen=True)
class DayAgg:
    n_final: int
    n_final_distinct: int
    c2359: Decimal | None
    max_recv_final: datetime | None

    @property
    def complete(self) -> bool:
        return self.n_final_distinct == 1440 and self.n_final == 1440 and self.c2359 is not None


def daily_from_candles(candles) -> dict[date, DayAgg]:
    """Agrega velas 1 min cruas (dicts) em DayAgg; só velas is_final contam."""
    n: dict[date, int] = defaultdict(int)
    seen: dict[date, set] = defaultdict(set)
    c: dict[date, Decimal] = {}
    rec: dict[date, datetime] = {}
    for k in candles:
        if not k["is_final"]:
            continue
        ot: datetime = k["open_time"]
        d = ot.date()
        n[d] += 1
        seen[d].add(ot)
        if ot.time() == time(23, 59):
            c[d] = k["close"]
        r = k["received_at"]
        if d not in rec or r > rec[d]:
            rec[d] = r
    return {d: DayAgg(n[d], len(seen[d]), c.get(d), rec.get(d)) for d in n}


def razao_mm20d(days: dict[date, DayAgg], obs: datetime, emitted_at: datetime,
                use_guard: bool = True) -> tuple[float | None, str | None]:
    """Devolve (razão, None) ou (None, motivo). `days` é a série diária de UM mercado."""
    d_last = obs.date() - timedelta(days=1)
    closes: list[Decimal] = []
    for i in range(19, -1, -1):
        d = d_last - timedelta(days=i)
        a = days.get(d)
        if a is None:
            return None, "dia_ausente"
        if not a.complete:
            return None, "dia_incompleto"
        # o dia d fecha em d+1 00:00; tem de estar fechado em obs (sempre, por construção)
        assert datetime.combine(d + timedelta(days=1), time(0), tzinfo=obs.tzinfo) <= obs
        if use_guard and (a.max_recv_final is None or a.max_recv_final > emitted_at):
            return None, "guarda_chegada"
        closes.append(a.c2359)  # type: ignore[arg-type]
    mean = sum(closes, Decimal(0)) / Decimal(20)
    return float(closes[-1] / mean - 1), None


def window_cov(w: dict, obs: datetime, emitted_at: datetime,
               use_guard: bool = True) -> tuple[float | None, float | None, str | None]:
    """distance_from_24h_low e return_4h da janela [obs−1440, obs−1] de velas finais contíguas."""
    full = (w["n"] == 1440 and w["n_distinct"] == 1440 and w["first_open"] == obs - timedelta(minutes=1440)
            and w["last_open"] == obs - timedelta(minutes=1))
    if not full or w["c_m1"] is None:
        return None, None, "janela_24h_incompleta"
    if use_guard and (obs > emitted_at or w["max_recv"] > emitted_at):
        return None, None, "guarda_24h"
    d_low = float((w["c_m1"] - w["lo"]) / w["lo"])
    if w["c_m241"] is None:
        return d_low, None, "sem_return_4h"
    r4 = float(w["c_m1"] / w["c_m241"] - 1)
    return d_low, r4, None


def robust_z(x: np.ndarray) -> np.ndarray:
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    return (x - med) / (MAD_K * mad)


def ols_beta(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return b
