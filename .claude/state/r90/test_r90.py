"""R90 / H-033 — testes sintéticos (valores conhecidos) do instrumento. SINTÉTICO: nada aqui é dado de mercado.

cd .claude/state/r90 && PYTHONPATH=C:/dev/project-hunter uv run --no-sync --project C:/dev/project-hunter pytest test_r90.py -q
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from data90 import (LAG, Oi, cheat_oi_rel_no_slack, oi_reason, oi_rel7d_from_history, oi_vol, row_from_csv,
                    units)
from stats90 import MRE, cluster_boot, global_label, holm, verdict

T = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
M5 = timedelta(minutes=5)


def hist(n: int, end: datetime, value: float = 100.0) -> list[Oi]:
    """n buckets de 5 min terminando em `end` (inclusive), OI constante."""
    return [Oi(end - i * M5, value) for i in range(n)][::-1]


# ---------- variável: OI em nível relativo à própria semana ----------

def test_oi_rel7d_known_value_constant_history_then_jump() -> None:
    cur = T - LAG  # 11:45 exato
    h = hist(2016, cur, 100.0)
    h[-1] = Oi(cur, 110.0)  # leitura corrente 10 % acima
    v, why = oi_rel7d_from_history(h, T)
    assert why is None
    # mediana de ln sobre 2016 valores (2015 de ln100 e 1 de ln110) = ln100
    assert v == pytest.approx(math.log(110.0) - math.log(100.0), abs=1e-12)


def test_future_and_inside_slack_readings_do_not_change_value() -> None:
    cur = T - LAG
    h = hist(2016, cur, 100.0)
    base, _ = oi_rel7d_from_history(h, T)
    poisoned = h + [Oi(cur + M5, 1e9), Oi(T, 1e9), Oi(T + timedelta(hours=1), 1e-9)]
    v, _ = oi_rel7d_from_history(poisoned, T)
    assert v == base


def test_cheat_without_slack_is_caught_by_leakage_probe() -> None:
    """Sonda de vazamento: uma leitura que só existe depois do corte (dentro da folga) mexe na trapaça, não na medida."""
    cur = T - LAG
    h = hist(2016, cur, 100.0) + [Oi(T - M5, 100.0), Oi(T, 100.0)]
    honest0, cheat0 = oi_rel7d_from_history(h, T)[0], cheat_oi_rel_no_slack(h, T)
    h2 = h[:-1] + [Oi(T, 500.0)]  # muda só a leitura do bucket do próprio sinal
    assert oi_rel7d_from_history(h2, T)[0] == honest0
    assert cheat_oi_rel_no_slack(h2, T) != cheat0


def test_short_window_and_stale_reading_are_unavailable_never_zero() -> None:
    cur = T - LAG
    v, why = oi_rel7d_from_history(hist(1000, cur), T)
    assert v is None and why == "oi_janela_curta"
    v, why = oi_rel7d_from_history(hist(2016, cur - timedelta(minutes=15)), T)
    assert v is None and why == "oi_velho"
    v, why = oi_rel7d_from_history([], T)
    assert v is None and why == "oi_ausente"


def test_naive_datetime_refused() -> None:
    with pytest.raises(ValueError):
        oi_rel7d_from_history(hist(10, T.replace(tzinfo=None)), T.replace(tzinfo=None))  # type: ignore[arg-type]


# ---------- guardas sobre o export SQL ----------

def _raw(**kw: str) -> dict[str, str]:
    base = {
        "signal_id": "s1", "strategy": "momentum", "version": "v3", "market_id": "m1", "symbol": "XUSDT",
        "obs": "2026-09-20 12:00:00+00", "emitted_at": "2026-09-20 12:00:09+00", "tracking_state": "terminal",
        "has_r": "t", "env_atr_pct": "0.01", "n": "1440", "lo24": "90", "qv24": "1000000", "n_qv": "1440",
        "max_recv": "2026-09-20 12:00:05+00", "close_last": "99", "close_m240": "95",
        "oi_ts": "2026-09-20 11:45:00+00", "oi_cur": "110", "n_win": "2016",
        "med_ln_oi": repr(math.log(100.0)), "t_first": "2026-09-13 11:50:00+00", "oi_created_at": "",
    }
    base.update(kw)
    return base


def test_row_from_csv_values() -> None:
    r = row_from_csv(_raw())
    assert r["oi_rel"] == pytest.approx(math.log(1.1), abs=1e-12)
    assert r["x"] == pytest.approx(-math.log(1.1), abs=1e-12)  # favorável = alto
    assert r["d_low"] == pytest.approx(99 / 90 - 1)
    assert r["ret4h"] == pytest.approx(99 / 95 - 1)
    assert r["oi_vol"] == pytest.approx(math.log(110 * 99 / 1_000_000))
    assert r["why"] is None


@pytest.mark.parametrize(("kw", "why"), [
    ({"oi_created_at": "2026-09-20 12:00:01+00"}, "oi_chegou_depois"),
    ({"oi_ts": "2026-09-20 11:50:00+00"}, "oi_dentro_da_folga"),
    ({"oi_ts": "2026-09-20 11:30:00+00"}, "oi_velho"),
    ({"n_win": "1814"}, "oi_janela_curta"),
    ({"oi_cur": ""}, "oi_ausente"),
    ({"n": "1439"}, "velas_incompletas"),
    ({"max_recv": "2026-09-20 12:00:10+00"}, "velas_chegaram_depois"),
    ({"env_atr_pct": ""}, "sem_atr"),
])
def test_guards_refuse(kw: dict[str, str], why: str) -> None:
    r = row_from_csv(_raw(**kw))
    assert r["why"] == why and r["x"] is None


def test_arrival_verified_before_obs_is_kept() -> None:
    r = row_from_csv(_raw(oi_created_at="2026-09-20 11:45:07+00", oi_dispatched_at="2026-09-20 11:45:08+00"))
    assert r["why"] is None and r["verified"] is True


def test_oi_vol_missing_when_quote_volume_incomplete() -> None:
    assert oi_vol(110.0, 99.0, 1_000_000.0, 1439) is None
    assert oi_reason(oi_ts=None, oi_cur=None, n_win=None, created=None, obs=T) == "oi_ausente"


def test_units_average_versions_same_bar() -> None:
    a = row_from_csv(_raw(signal_id="a"))
    b = row_from_csv(_raw(signal_id="b", version="v4", env_atr_pct="0.03"))
    a["r"], b["r"] = 1.0, -0.5
    us = units([a, b])
    assert len(us) == 1 and us[0]["r"] == pytest.approx(0.25) and us[0]["atr_pct"] == pytest.approx(0.02)


# ---------- estatística e rótulo ----------

def test_cluster_boot_recovers_injected_slope() -> None:
    rng = np.random.default_rng(1)
    n = 900
    x = rng.normal(size=(n, 1))
    y = 0.3 * x[:, 0] + rng.normal(scale=0.5, size=n)
    days = [f"d{i % 25}" for i in range(n)]
    b, lo, hi, p, bad = cluster_boot(y, x, days, reps=500)
    assert b == pytest.approx(0.3, abs=0.06) and lo > 0 and p < 0.01 and bad == 0


def test_holm_and_global_rules() -> None:
    assert holm([0.01, 1.0]) == [0.02, 1.0]
    assert global_label(["REFUTA", "LIMITE DE DADO"]) == "NÃO CONFIRMA"
    assert global_label(["REFUTA", "REFUTA"]) == "REFUTA"
    assert global_label(["CONFIRMA", "LIMITE DE DADO"]) == "CONFIRMA"


def test_verdict_order() -> None:
    kw = dict(n=869, days=23, n_pos=400, n_neg=400, beta=0.0, lo=-0.05, hi=0.04, lo_m=-0.05, hi_m=0.045,
              p_holm=0.9, level_pos=-0.2, plateau=False, halves=(0.0, 0.0), invalid_frac=0.0)
    assert verdict(**kw).label == "REFUTA"  # type: ignore[arg-type]
    assert verdict(**{**kw, "hi_m": MRE + 0.01}).label == "NÃO CONFIRMA"  # type: ignore[arg-type]
    assert verdict(**{**kw, "days": 14}).label == "LIMITE DE DADO"  # type: ignore[arg-type]
    assert verdict(**{**kw, "invalid_frac": 0.02}).label == "LIMITE (instrumento)"  # type: ignore[arg-type]


# ---------- emenda (Astra H-033-prereg): janela inteira no outbox, prova pós-commit, duplicatas, LIMITE global ----------

from data90 import JoinError, check_join, window_evidence  # noqa: E402
from stats90 import global_label as _gl  # noqa: E402


def test_window_evidence_refuses_late_window_sample_and_proves_full_window() -> None:
    obs = T
    cur = T - LAG
    buckets = [cur - i * M5 for i in range(2016)]
    ev = {b: (b + timedelta(seconds=7), b + timedelta(seconds=8)) for b in buckets}  # (c_max, d_max)
    late, proven = window_evidence(ev, cur, obs, outbox_start=buckets[-1] - M5, used=set(buckets))
    assert late is False and proven is True
    ev[buckets[100]] = (obs + timedelta(seconds=1), obs + timedelta(seconds=2))  # amostra antiga inserida depois
    late, proven = window_evidence(ev, cur, obs, outbox_start=buckets[-1] - M5, used=set(buckets))
    assert late is True and proven is False


def test_window_not_proven_when_outbox_starts_inside_window_or_dispatch_after_obs() -> None:
    cur = T - LAG
    buckets = [cur - i * M5 for i in range(2016)]
    ev = {b: (b + timedelta(seconds=7), b + timedelta(seconds=8)) for b in buckets[:500]}
    late, proven = window_evidence(ev, cur, T, outbox_start=buckets[499])
    assert late is False and proven is False  # janela começa antes do outbox: presumida, não provada
    ev2 = {b: (b + timedelta(seconds=7), T + timedelta(seconds=1)) for b in buckets}
    assert window_evidence(ev2, cur, T, outbox_start=buckets[-1] - M5, used=set(buckets)) == (False, False)


def test_current_reading_proof_uses_dispatch_not_insert() -> None:
    r = row_from_csv(_raw(oi_created_at="2026-09-20 11:45:07+00", oi_dispatched_at="2026-09-20 12:00:30+00"))
    assert r["why"] is None and r["verified"] is False  # inserida antes, mas só provada (despachada) depois
    r = row_from_csv(_raw(oi_created_at="2026-09-20 11:45:07+00", oi_dispatched_at="2026-09-20 11:45:08+00"))
    assert r["verified"] is True


def test_late_candles_flag() -> None:
    assert row_from_csv(_raw(n_late="2"))["late_candles"] is True
    assert row_from_csv(_raw(n_late="0"))["late_candles"] is False


def test_check_join_refuses_duplicate_feature_ids() -> None:
    a = row_from_csv(_raw(signal_id="a"))
    a["r"] = 0.1
    with pytest.raises(JoinError):
        check_join([a, dict(a)], {"a"})


def test_global_both_limits_any_cause() -> None:
    assert _gl(["LIMITE (instrumento)", "LIMITE DE DADO"]) == "LIMITE"
    assert _gl(["LIMITE DE DADO", "LIMITE DE DADO"]) == "LIMITE"
    assert _gl(["NÃO CONFIRMA", "LIMITE DE DADO"]) == "NÃO CONFIRMA"


def test_load_ev_aggregates_raw_events(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from data90 import load_ev
    p = tmp_path / "ev.csv"
    p.write_text(
        "symbol,b,created_at,dispatched_at\n"
        "XUSDT,2026-09-26T05:00:00+00:00,2026-09-26 05:00:07+00,2026-09-26 05:00:08+00\n"
        "XUSDT,2026-09-26T05:00:00+00:00,2026-09-26 05:00:09+00,2026-09-26 05:00:20+00\n"
        "YUSDT,2026-09-26T05:05:00+00:00,2026-09-26 04:59:00+00,\n", encoding="utf-8")
    ev, start = load_ev(p)
    b = datetime(2026, 9, 26, 5, 0, tzinfo=UTC)
    assert ev["XUSDT"][b] == (datetime(2026, 9, 26, 5, 0, 9, tzinfo=UTC), datetime(2026, 9, 26, 5, 0, 20, tzinfo=UTC))
    assert start == datetime(2026, 9, 26, 4, 59, tzinfo=UTC)
    d = ev["YUSDT"][datetime(2026, 9, 26, 5, 5, tzinfo=UTC)][1]
    assert d > datetime(2100, 1, 1, tzinfo=UTC)  # sem despacho = nunca provado


def test_slack_parameter_moves_staleness_window() -> None:
    r = row_from_csv(_raw(oi_ts="2026-09-20 11:30:00+00"), lag=timedelta(minutes=30))
    assert r["why"] is None
    r = row_from_csv(_raw(oi_ts="2026-09-20 11:45:00+00"), lag=timedelta(minutes=30))
    assert r["why"] == "oi_dentro_da_folga"
    r = row_from_csv(_raw(oi_ts="2026-09-20 11:15:00+00"), lag=timedelta(minutes=30))
    assert r["why"] == "oi_velho"


# ---------- revisão do resultado (Astra H-033-resultado): lacunas de instrumento, sem efeito nos números atuais ----------

def test_window_proof_requires_every_used_bucket_to_have_event() -> None:
    cur = T - LAG
    buckets = [cur - i * M5 for i in range(2016)]
    ev = {b: (b + timedelta(seconds=7), b + timedelta(seconds=8)) for b in buckets}
    gap = buckets[50]
    del ev[gap]
    assert window_evidence(ev, cur, T, outbox_start=buckets[-1] - M5, used=set(buckets)) == (False, False)
    assert window_evidence(ev, cur, T, outbox_start=buckets[-1] - M5, used=set(buckets) - {gap}) == (False, True)
    assert window_evidence(ev, cur, T, outbox_start=buckets[-1] - M5, used=None)[1] is False  # sem lista: não certifica


def _synthetic_units(half_zero: bool) -> list[dict]:
    rng = np.random.default_rng(7)
    us = []
    for i in range(200):
        day = f"2026-09-{1 + i // 10:02d}"
        x = 0.0 if (half_zero and i < 100 and i % 5 < 3) else float(rng.normal())
        us.append({"day": day, "market": f"m{i % 12}", "x": x, "d_low": float(rng.normal()),
                   "atr_pct": float(rng.normal()), "ret4h": float(rng.normal()), "r": float(rng.normal())})
    return us


def test_mad_zero_inside_a_half_is_instrument_limit() -> None:
    from analysis90 import analyze, label
    res = analyze(_synthetic_units(half_zero=True), reps=200, robust=False)
    assert label(res, 1.0).label == "LIMITE (instrumento)"  # type: ignore[attr-defined]
    ok = analyze(_synthetic_units(half_zero=False), reps=200, robust=False)
    assert label(ok, 1.0).label != "LIMITE (instrumento)"  # type: ignore[attr-defined]


def test_confirm_requires_positive_beta_at_30_and_60_min_slack() -> None:
    from analysis90 import label
    res = {"n": 869, "days": 23, "n_pos": 400, "n_neg": 469, "beta": 0.2, "lo": 0.1, "hi": 0.3, "lo_m": 0.1,
           "hi_m": 0.3, "level_pos": 0.1, "plateau": True, "halves": (0.2, 0.2), "invalid_frac": 0.0,
           "cuts_invalid": 0}
    assert label(res, 0.001, slack=(0.1, 0.1)).label == "CONFIRMA"  # type: ignore[attr-defined]
    lab = label(res, 0.001, slack=(0.1, -0.01))
    assert lab.label == "NÃO CONFIRMA" and lab.clauses["folgas_30_60>0"] is False  # type: ignore[attr-defined]
    assert label(res, 0.001, slack=(0.1, float("nan"))).label == "NÃO CONFIRMA"  # type: ignore[attr-defined]
