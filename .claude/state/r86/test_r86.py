# R86 / H-027 — testes sintéticos com valores conhecidos: razao_mm20d, antecipação, guarda, população, estatística.
# cd .claude/state/r86 && uv run --no-sync --project C:/dev/project-hunter pytest -q test_r86.py
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest
from data86 import Day, cheat_razao_same_day, razao_mm20d, units
from stats86 import Verdict, fit, holm, robust_z, sign_plateau, verdict

OBS = datetime(2026, 9, 25, 12, 15, tzinfo=UTC)
EMIT = OBS + timedelta(seconds=12)
LAST = date(2026, 9, 24)  # último dia UTC completo antes de OBS


def panel(closes: dict[date, str], n: int = 1440, recv: datetime | None = None) -> dict[date, Day]:
    return {d: Day(n, recv or datetime.combine(d + timedelta(days=1), datetime.min.time(), UTC) + timedelta(seconds=3),
                   Decimal(c)) for d, c in closes.items()}


def ramp(last: date = LAST, k: int = 25) -> dict[date, str]:
    """Fechamentos 100, 101, …: no dia `last` o fechamento é 100 + (k − 1)."""
    return {last - timedelta(days=k - 1 - i): str(100 + i) for i in range(k)}


# ---------- valor conhecido ----------

def test_known_value_ramp() -> None:
    p = panel(ramp())  # os 20 últimos: 105..124, média 114,5; último 124
    v, why = razao_mm20d(p, OBS, EMIT)
    assert why is None
    assert v == pytest.approx(124 / 114.5 - 1, abs=1e-15)


def test_flat_is_zero() -> None:
    p = panel({LAST - timedelta(days=i): "50" for i in range(20)})
    assert razao_mm20d(p, OBS, EMIT) == (0.0, None)


def test_signal_at_midnight_uses_previous_day() -> None:
    """obs = 00:00 do dia 25: a vela diária do dia 24 fechou exatamente em obs — entra; o dia 25 não."""
    obs = datetime(2026, 9, 25, 0, 0, tzinfo=UTC)
    p = panel(ramp())
    p[date(2026, 9, 25)] = Day(5, obs, Decimal("1"))
    v, why = razao_mm20d(p, obs, obs + timedelta(seconds=10))
    assert why is None and v == pytest.approx(124 / 114.5 - 1, abs=1e-15)


# ---------- antecipação ----------

def test_current_and_future_days_do_not_change_value() -> None:
    base = panel(ramp())
    v0, _ = razao_mm20d(base, OBS, EMIT)
    for later in (date(2026, 9, 25), date(2026, 9, 26), date(2026, 10, 3)):
        p = dict(base)
        p[later] = Day(1440, datetime(2026, 10, 9, tzinfo=UTC), Decimal("999999"))
        assert razao_mm20d(p, OBS, EMIT)[0] == v0
        p[later] = Day(17, datetime(2026, 10, 9, tzinfo=UTC), Decimal("0.0001"))  # dia em formação/incompleto
        assert razao_mm20d(p, OBS, EMIT)[0] == v0


def test_leakage_probe_catches_the_cheat() -> None:
    """A trapaça (põe o fechamento do dia corrente na média) muda quando o dia corrente muda; a honesta não."""
    base = panel(ramp())
    base[date(2026, 9, 25)] = Day(1440, EMIT, Decimal("200"))
    moved = dict(base)
    moved[date(2026, 9, 25)] = Day(1440, EMIT, Decimal("50"))
    assert razao_mm20d(base, OBS, EMIT) == razao_mm20d(moved, OBS, EMIT)
    assert cheat_razao_same_day(base, OBS) != cheat_razao_same_day(moved, OBS)


def test_day_older_than_window_does_not_matter() -> None:
    p = panel(ramp(k=30))
    v0, _ = razao_mm20d(p, OBS, EMIT)
    p[LAST - timedelta(days=20)] = Day(3, EMIT, Decimal("1"))
    assert razao_mm20d(p, OBS, EMIT)[0] == v0


# ---------- indisponível, nunca interpolado ----------

def test_incomplete_day_inside_window_is_unavailable() -> None:
    p = panel(ramp())
    p[LAST - timedelta(days=7)] = Day(1439, EMIT - timedelta(days=7), Decimal("110"))
    assert razao_mm20d(p, OBS, EMIT) == (None, "dia_incompleto")


def test_missing_day_is_unavailable() -> None:
    p = panel(ramp())
    del p[LAST - timedelta(days=19)]
    assert razao_mm20d(p, OBS, EMIT) == (None, "dia_incompleto")


def test_missing_2359_close_is_unavailable() -> None:
    p = panel(ramp())
    p[LAST] = Day(1440, EMIT - timedelta(hours=12), None)
    assert razao_mm20d(p, OBS, EMIT) == (None, "dia_incompleto")


def test_day_persisted_after_emission_is_refused_by_guard_only() -> None:
    p = panel(ramp())
    p[LAST - timedelta(days=3)] = Day(1440, EMIT + timedelta(seconds=1), Decimal("121"))
    assert razao_mm20d(p, OBS, EMIT) == (None, "chegou_depois")
    v, why = razao_mm20d(p, OBS, EMIT, guard=False)
    assert why is None and v is not None


def test_naive_datetime_refused() -> None:
    with pytest.raises(ValueError):
        razao_mm20d(panel(ramp()), OBS.replace(tzinfo=None), EMIT)


# ---------- população (unidade = estratégia × mercado × barra) ----------

def _row(sid: str, strat: str, ver: str, mkt: str, obs: datetime, r: float | None, atr: float = 0.01) -> dict:
    return {"signal_id": sid, "strategy": strat, "version": ver, "market": mkt, "obs": obs, "t": obs,
            "r": r, "atr_pct": atr, "d_low": 0.05, "ret4h": 0.01, "razao": 0.02, "prospective": True}


def test_units_average_versions_on_same_bar() -> None:
    rows = [_row("a", "momentum", "v1", "M", OBS, 1.0, 0.01), _row("b", "momentum", "v3", "M", OBS, -1.0, 0.03),
            _row("c", "momentum", "v3", "M", OBS + timedelta(minutes=15), 0.5),
            _row("d", "volume_anomaly", "v1", "M", OBS, 2.0)]
    us = units(rows)
    assert len(us) == 3
    m = next(u for u in us if u["strategy"] == "momentum" and u["obs"] == OBS)
    assert m["r"] == pytest.approx(0.0) and m["atr_pct"] == pytest.approx(0.02) and m["n_versions"] == 2


def test_units_ignore_versions_without_r() -> None:
    rows = [_row("a", "momentum", "v1", "M", OBS, None), _row("b", "momentum", "v3", "M", OBS, -1.0)]
    (u,) = units(rows)
    assert u["r"] == -1.0 and u["n_versions"] == 1


# ---------- estatística ----------

def test_robust_z_median_mad() -> None:
    z = robust_z(np.array([1.0, 2.0, 3.0, 4.0, 100.0]))
    assert z[2] == 0.0
    assert z[3] == pytest.approx(1 / 1.4826)


def test_fit_recovers_known_coefficients() -> None:
    rng = np.random.default_rng(1)
    n = 4000
    x = rng.normal(size=(n, 4))
    y = -0.2 + 0.3 * x[:, 0] - 0.1 * x[:, 1] + rng.normal(scale=0.01, size=n)
    b = fit(y, x)
    assert b[0] == pytest.approx(-0.2, abs=1e-3) and b[1] == pytest.approx(0.3, abs=1e-3)
    assert b[2] == pytest.approx(-0.1, abs=1e-3) and abs(b[3]) < 1e-3


def test_holm() -> None:
    assert holm([0.01, 0.04]) == pytest.approx([0.02, 0.04])
    assert holm([0.04, 0.01]) == pytest.approx([0.04, 0.02])
    assert holm([0.3, 1.0]) == pytest.approx([0.6, 1.0])


def test_sign_plateau_counts_distinct_partitions() -> None:
    assert sign_plateau([0.1, 0.2, 0.1, 0.05, -0.1], [1, 2, 3, 4, 5]) == (4, True)
    assert sign_plateau([0.1, 0.2, 0.1, 0.05, -0.1], [1, 1, 1, 4, 5]) == (2, False)


def _v(**kw) -> Verdict:
    base = dict(n=600, days=20, n_pos=200, n_neg=200, beta=0.08, lo=0.01, hi=0.15, lo_m=0.01, hi_m=0.15,
                p_holm=0.01, level_pos=0.02, plateau=True, halves=(0.05, 0.1), invalid_frac=0.0)
    base.update(kw)
    return verdict(**base)  # type: ignore[arg-type]


def test_verdict_rules() -> None:
    assert _v().label == "CONFIRMA"
    assert _v(n=149).label == "LIMITE DE DADO"
    assert _v(days=14).label == "LIMITE DE DADO"
    assert _v(n_pos=29).label == "LIMITE DE DADO"
    assert _v(beta=-0.1, lo=-0.2, hi=0.049, lo_m=-0.2, hi_m=0.049).label == "REFUTA"
    assert _v(level_pos=-0.01).label == "NÃO CONFIRMA"  # perder menos não é vantagem
    assert _v(plateau=False).label == "NÃO CONFIRMA"
    assert _v(halves=(0.05, -0.01)).label == "NÃO CONFIRMA"
    assert _v(p_holm=0.06).label == "NÃO CONFIRMA"
    assert _v(beta=0.04, hi=0.2).label == "NÃO CONFIRMA"  # abaixo do MRE, sem refutar
    assert _v(lo=-0.01).label == "NÃO CONFIRMA"


# ---------- emenda 03:02Z: falha fechada, inferência dupla, regra global, população congelada ----------

def test_fit_checked_refuses_constant_indicator() -> None:
    from stats86 import Unidentified, fit_checked
    y = np.arange(10.0)
    x = np.column_stack([np.ones(10), np.arange(10.0)])  # coluna constante = intercepto duplicado
    with pytest.raises(Unidentified):
        fit_checked(y, x)


def test_fit_checked_refuses_non_finite() -> None:
    from stats86 import Unidentified, fit_checked
    x = np.column_stack([np.arange(10.0), np.arange(10.0) ** 2])
    y = np.arange(10.0)
    y[3] = np.nan
    with pytest.raises(Unidentified):
        fit_checked(y, x)


def test_boot_all_singular_reports_invalid_not_crash() -> None:
    from stats86 import cluster_boot
    # uma linha num dia só: toda réplica é singular (posto 1 < 2)
    y = np.array([1.0])
    x = np.array([[0.0]])
    b, lo, hi, p, bad = cluster_boot(y, x, ["d1"], reps=50)
    assert bad == 50 and np.isnan(lo) and np.isnan(hi) and p == 1.0


def test_verdict_instrument_blocks_refuta_and_confirma() -> None:
    assert _v(beta=-0.1, lo=-0.2, hi=0.0, invalid_frac=0.02).label == "LIMITE (instrumento)"
    assert _v(invalid_frac=0.02).label == "LIMITE (instrumento)"
    assert _v(lo=float("nan")).label == "LIMITE (instrumento)"


def test_verdict_halves_nan_is_not_positive() -> None:
    assert _v(halves=(0.05, float("nan"))).label == "LIMITE (instrumento)"


def test_verdict_market_bootstrap_must_agree() -> None:
    assert _v(lo_m=-0.01).label == "NÃO CONFIRMA"
    assert _v(beta=-0.1, lo=-0.2, hi=0.04, lo_m=-0.3, hi_m=0.06).label == "NÃO CONFIRMA"  # REFUTA exige os dois
    assert _v(beta=-0.1, lo=-0.2, hi=0.04, lo_m=-0.3, hi_m=0.045).label == "REFUTA"


def test_sign_plateau_invalid_cut_not_positive() -> None:
    assert sign_plateau([0.1, float("nan"), 0.1, 0.1, 0.1], [1, 2, 3, 4, 5]) == (3, False)


def test_global_rule() -> None:
    from stats86 import global_label
    assert global_label(["CONFIRMA", "LIMITE DE DADO"]) == "CONFIRMA"
    assert global_label(["REFUTA", "LIMITE DE DADO"]) == "NÃO CONFIRMA"
    assert global_label(["REFUTA", "REFUTA"]) == "REFUTA"
    assert global_label(["LIMITE DE DADO", "LIMITE DE DADO"]) == "LIMITE DE DADO"
    assert global_label(["NÃO CONFIRMA", "LIMITE (instrumento)"]) == "NÃO CONFIRMA"


def test_population_window_and_exchange_frozen() -> None:
    from data86 import eligible
    base = {"exchange": "binance", "market_type": "perpetual", "cohort": "prospective", "tracking_state": "terminal"}
    assert eligible({**base, "emitted_at": datetime(2026, 9, 30, 23, 59, tzinfo=UTC)})
    assert not eligible({**base, "emitted_at": datetime(2026, 10, 1, 0, 0, tzinfo=UTC)})
    assert not eligible({**base, "emitted_at": datetime(2026, 9, 5, 23, 59, tzinfo=UTC)})
    assert not eligible({**base, "exchange": "bybit", "emitted_at": datetime(2026, 9, 20, tzinfo=UTC)})
    assert not eligible({**base, "cohort": "replay:x", "emitted_at": datetime(2026, 9, 20, tzinfo=UTC)})


# ---------- revisão do resultado (Astra, 03:1xZ): corte não identificável e junção fechada ----------

def test_label_blocks_when_a_cut_is_unidentified() -> None:
    from analysis86 import analyze, label
    rng = np.random.default_rng(3)
    us = []
    for i in range(400):
        day = f"2026-09-{1 + i % 20:02d}"
        rz = float(rng.uniform(-0.049, 0.2))  # nenhum valor ≤ −0,05 → corte −0,05 constante
        us.append({"strategy": "momentum", "market": f"M{i % 16}", "obs": None, "day": day, "r": -0.2,
                   "razao": rz, "d_low": float(rng.normal()), "atr_pct": float(rng.uniform(0.005, 0.03)),
                   "ret4h": float(rng.normal())})
    res = analyze(us, reps=200)
    assert res["cuts_invalid"] >= 1
    assert label(res, 0.5).label == "LIMITE (instrumento)"  # type: ignore[attr-defined]


def test_attach_outcomes_refuses_duplicate_ids(tmp_path) -> None:
    from data86 import JoinError, attach_outcomes
    p = tmp_path / "out.csv"
    p.write_text("signal_id,r_multiple,r_ex_funding,result,exit_ts,read_at\n"
                 "a,1.0,1.0,target,,x\na,-1.0,-1.0,stop,,x\n", encoding="utf-8")
    with pytest.raises(JoinError):
        attach_outcomes([{"signal_id": "a"}], p)


def test_check_join_refuses_missing_or_nulled_eligible() -> None:
    from data86 import JoinError, check_join
    rows = [{"signal_id": "a", "r": 1.0}, {"signal_id": "b", "r": None}]
    check_join(rows, {"a"})
    with pytest.raises(JoinError):
        check_join(rows, {"a", "b"})  # elegível perdeu R
    with pytest.raises(JoinError):
        check_join(rows, {"a", "c"})  # elegível sumiu das features
