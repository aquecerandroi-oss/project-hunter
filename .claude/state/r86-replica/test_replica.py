"""r86-replica — testes da reconstrução independente (H-027). Fixtures sintéticas, rotuladas."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from feat import DayAgg, daily_from_candles, razao_mm20d, robust_z, ols_beta, window_cov

T0 = datetime(2026, 9, 1, tzinfo=UTC)


def _candles(days: int, close_of_day, final=True, recv_lag=timedelta(seconds=2)):
    """Fixture sintética: `days` dias completos de velas 1 min; o fechamento 23:59 do dia i = close_of_day(i)."""
    out = []
    for i in range(days):
        d0 = T0 + timedelta(days=i)
        for m in range(1440):
            ot = d0 + timedelta(minutes=m)
            c = close_of_day(i) if m == 1439 else Decimal("1")
            out.append({"open_time": ot, "close": c, "low": c, "is_final": final, "received_at": ot + timedelta(minutes=1) + recv_lag})
    return out


def _agg(candles):
    return {d: a for d, a in daily_from_candles(candles).items()}


def test_known_value_linear_closes():
    # fechamentos 1..20 → média 10,5; razão = 20/10,5 − 1
    agg = _agg(_candles(21, lambda i: Decimal(i + 1)))
    obs = T0 + timedelta(days=20, minutes=15)  # D = dia 19 (fechamento 20)
    r, why = razao_mm20d(agg, obs, obs + timedelta(seconds=10))
    assert why is None
    assert r == pytest.approx(20 / 10.5 - 1, abs=1e-15)


def test_current_day_and_non_final_do_not_change_value():
    base = _candles(21, lambda i: Decimal(i + 1))
    obs = T0 + timedelta(days=20, minutes=15)
    r0, _ = razao_mm20d(_agg(base), obs, obs + timedelta(seconds=10))
    # muda TODO o dia corrente (dia 20) e acrescenta velas não finais com valores absurdos em dias passados
    mutated = [dict(c) for c in base]
    for c in mutated:
        if c["open_time"] >= T0 + timedelta(days=20):
            c["close"] = Decimal("999")
    extra = [{"open_time": T0 + timedelta(days=19, minutes=1439), "close": Decimal("12345"), "low": Decimal("1"),
              "is_final": False, "received_at": T0}]
    r1, _ = razao_mm20d(_agg(mutated + extra), obs, obs + timedelta(seconds=10))
    assert r1 == r0


def test_control_leaky_definition_changes():
    # controle do próprio teste: uma definição vazada (D = dia corrente, emulada deslocando obs em +1 dia,
    # sem guarda) MUDA quando o dia corrente muda — logo o teste acima teria apanhado o vazamento.
    base = _candles(21, lambda i: Decimal(i + 1))
    obs = T0 + timedelta(days=20, minutes=15)
    mutated = [dict(c) for c in base]
    for c in mutated:
        if c["open_time"] >= T0 + timedelta(days=20):
            c["close"] = Decimal("999")
    leak = obs + timedelta(days=1)
    a, _ = razao_mm20d(_agg(base), leak, leak, use_guard=False)
    b, _ = razao_mm20d(_agg(mutated), leak, leak, use_guard=False)
    assert a is not None and b is not None and a != b
    # meia-noite exata: D = dia anterior, que acabou de fechar
    obs0 = T0 + timedelta(days=21)
    r_a, why = razao_mm20d(_agg(base), obs0, obs0 + timedelta(seconds=10))
    assert why is None and r_a == pytest.approx(21 / 11.5 - 1)


def test_missing_minute_or_missing_2359_is_unavailable():
    base = _candles(21, lambda i: Decimal(i + 1))
    obs = T0 + timedelta(days=20, minutes=15)
    holed = [c for c in base if c["open_time"] != T0 + timedelta(days=5, minutes=100)]
    assert razao_mm20d(_agg(holed), obs, obs)[1] == "dia_incompleto"
    no2359 = [c for c in base if c["open_time"] != T0 + timedelta(days=5, minutes=1439)]
    assert razao_mm20d(_agg(no2359), obs, obs)[1] == "dia_incompleto"
    short = [c for c in base if c["open_time"] >= T0 + timedelta(days=2)]
    assert razao_mm20d(_agg(short), obs, obs)[1] == "dia_ausente"


def test_arrival_guard():
    base = _candles(21, lambda i: Decimal(i + 1))
    obs = T0 + timedelta(days=20, minutes=15)
    late = [dict(c) for c in base]
    late[19 * 1440 + 5]["received_at"] = obs + timedelta(minutes=1)
    assert razao_mm20d(_agg(late), obs, obs + timedelta(seconds=10))[1] == "guarda_chegada"


def test_window_cov():
    obs = T0 + timedelta(days=2)
    lows = Decimal("2")
    w = {"n": 1440, "n_distinct": 1440, "first_open": obs - timedelta(minutes=1440), "last_open": obs - timedelta(minutes=1),
         "lo": lows, "max_recv": obs, "c_m1": Decimal("3"), "c_m241": Decimal("2.5")}
    d_low, r4, why = window_cov(w, obs, obs + timedelta(seconds=5))
    assert why is None and d_low == pytest.approx(0.5) and r4 == pytest.approx(0.2)
    w2 = dict(w, n=1439, n_distinct=1439)
    assert window_cov(w2, obs, obs)[2] == "janela_24h_incompleta"
    w3 = dict(w, max_recv=obs + timedelta(seconds=6))
    assert window_cov(w3, obs, obs + timedelta(seconds=5))[2] == "guarda_24h"


def test_robust_z_and_ols():
    x = np.array([1.0, 2.0, 3.0, 4.0, 100.0])
    z = robust_z(x)
    assert z[2] == 0.0 and z[1] == pytest.approx(-1 / 1.4826)
    rng = np.random.default_rng(1)
    X = rng.normal(size=(500, 2))
    y = 0.3 + 0.7 * X[:, 0] - 0.2 * X[:, 1]
    b = ols_beta(np.column_stack([np.ones(500), X]), y)
    assert b == pytest.approx([0.3, 0.7, -0.2])


def test_dayagg_type():
    a = DayAgg(1440, 1440, Decimal("1"), T0)
    assert a.complete
    assert date(2026, 9, 1) == T0.date()
