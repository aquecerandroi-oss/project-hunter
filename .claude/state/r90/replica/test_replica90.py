"""R90 réplica — testes SINTÉTICOS do cálculo independente de oi_rel7d (valores conhecidos e sonda de vazamento)."""

from __future__ import annotations

import math

import numpy as np
from replica90 import oi_rel

OBS = 1_000_000_000.0


def series(n: int, end: float, value: float = 100.0) -> tuple[np.ndarray, np.ndarray]:
    t = np.array([end - 300.0 * i for i in range(n)][::-1])
    return t, np.full(n, value)


def test_known_value() -> None:
    t, v = series(2016, OBS - 900)
    v[-1] = 120.0
    assert oi_rel(t, v, OBS) == math.log(120) - math.log(100)


def test_readings_inside_slack_or_future_ignored() -> None:
    t, v = series(2016, OBS - 900)
    base = oi_rel(t, v, OBS)
    t2 = np.append(t, [OBS - 600, OBS, OBS + 3600])
    v2 = np.append(v, [1e9, 1e9, 1e-9])
    assert oi_rel(t2, v2, OBS) == base


def test_short_or_stale_is_none() -> None:
    assert oi_rel(*series(1000, OBS - 900), OBS) is None
    assert oi_rel(*series(2016, OBS - 900 - 900), OBS) is None
