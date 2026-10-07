"""h036 — testes do pipeline da consulta (escritos antes de look.py).

Rodar: uv run --no-sync pytest .claude/state/h036/test_look.py -q
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

import look  # noqa: E402

pytestmark = pytest.mark.unit


def test_spread_pick_uses_minute_then_neighbours_then_median_then_p90() -> None:
    ser = {datetime(2026, 10, 8, 10, 0, tzinfo=UTC): 0.0002, datetime(2026, 10, 8, 10, 2, tzinfo=UTC): 0.0004}
    t = datetime(2026, 10, 8, 10, 1, tzinfo=UTC)
    assert look.leg_spread(ser, datetime(2026, 10, 8, 10, 0, tzinfo=UTC), med=(0.0009, 9000), p90=0.003) == (0.0002, "minuto")
    assert look.leg_spread(ser, t, med=(0.0009, 9000), p90=0.003) == (0.0002, "vizinho")  # −1 min antes de +1 min
    far = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    assert look.leg_spread(ser, far, med=(0.0009, 9000), p90=0.003) == (0.0009, "mediana_7d")
    assert look.leg_spread(ser, far, med=(0.0009, 4000), p90=0.003) == (0.003, "p90")  # mediana com < 50 % da janela


def test_primary_and_stress_r_by_hand() -> None:
    # O = 100, B = 102, U = 2, Φ = 0; spread 4 bp na entrada, 2 bp na saída, 6 bp no minuto seguinte à saída
    # primário: c_in = 5 + 2 = 7 bp, c_out = 5 + 1 = 6 bp → custo = (0,07 + 0,0612)/2 = 0,0656 R; G = 1 → 0,9344
    # estresse: c_in = 9 bp, c_out = 5 + 3 + 2 = 10 bp → (0,09 + 0,102)/2 = 0,096 R → 0,904
    p, s = look.trade_r(open_=100.0, base=102.0, risk=2.0, funding=0.0, sp_in=0.0004, sp_out=0.0002, sp_out_next=0.0006)
    assert p == pytest.approx(1 - 0.0656)
    assert s == pytest.approx(1 - 0.096)


def test_day_and_week_index_from_t0_date() -> None:
    assert look.day_index(datetime(2026, 10, 7, 12, 0, tzinfo=UTC)) == 0
    assert look.day_index(datetime(2026, 10, 7, 23, 59, tzinfo=UTC)) == 0
    assert look.day_index(datetime(2026, 10, 12, 0, 1, tzinfo=UTC)) == 5  # segunda: abre a semana ISO 1


def test_daily_arrays() -> None:
    days = np.array([0, 0, 2])
    p = np.array([1.0, -1.0, 0.5])
    s = np.array([0.9, -1.1, 0.4])
    c, sp, ss = look.daily(days, p, s, n_days=4)
    assert c.tolist() == [[2.0, 0.0, 1.0, 0.0]]
    assert sp.tolist() == [[0.0, 0.0, 0.5, 0.0]]
    assert ss == pytest.approx(np.array([[-0.2, 0.0, 0.4, 0.0]]))


def test_label_unstable_to_missing_cost_is_downgraded() -> None:
    import decision as dc
    assert look.robust_label(dc.CONFIRMA, dc.NAO_CONFIRMA) == dc.NAO_CONFIRMA
    assert look.robust_label(dc.REFUTA, dc.NAO_CONFIRMA) == dc.NAO_CONFIRMA
    assert look.robust_label(dc.CONFIRMA, dc.CONFIRMA) == dc.CONFIRMA
    assert look.robust_label(dc.CONTINUA, dc.REFUTA) == dc.CONTINUA  # intermediária sem rótulo continua


def test_day_index_with_other_base() -> None:
    assert look.day_index(datetime(2026, 9, 10, 1, 0, tzinfo=UTC), base=datetime(2026, 9, 9, tzinfo=UTC).date()) == 1


def test_unstable_interim_futility_stops_as_not_confirmed() -> None:
    import decision as dc
    # um REFUTA intermediário instável não pode virar "continua" (daria novas chances de REFUTA): para como NÃO CONFIRMA
    assert look.robust_label(dc.REFUTA, dc.NAO_CONFIRMA, final=False) == dc.NAO_CONFIRMA
    assert look.robust_label(dc.CONFIRMA, dc.CONTINUA, final=False) == dc.CONTINUA


def test_stress_next_minute_fallback() -> None:
    from datetime import timedelta
    x = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)
    ser = {x: 0.0002, x + timedelta(minutes=2): 0.0007}
    assert look.next_spread(ser, x, p90=0.003) == (0.0007, "+2 min")
    assert look.next_spread({x: 0.0002}, x, p90=0.003) == (0.003, "p90")
