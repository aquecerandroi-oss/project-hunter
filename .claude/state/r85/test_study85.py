"""R85 — testes das saídas (fixa, estrutural, pareada), do contraste do mesmo dia, da inferência e do veredito.

Rodar:
    uv run pytest -q .claude/state/r85/test_study85.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from data85 import build_hl_panel
from stats85 import arm_verdict, boot_d, coverage, day_sums, mbb_idx, summarize
from study85 import COST, contrast, exit_fixed, exit_struct

TODAY = 400


def _rows(sym, days, o, h=None, lo=None, c=None, v=1.0):
    out = []
    for k, d in enumerate(days):
        oo = o(k) if callable(o) else o
        cc = (c(k) if callable(c) else c) if c is not None else oo
        hh = (h(k) if callable(h) else h) if h is not None else max(oo, cc)
        ll = (lo(k) if callable(lo) else lo) if lo is not None else min(oo, cc)
        out.append((sym, d, float(oo), float(hh), float(ll), float(cc), float(v)))
    return out


def _panel(rows, trading=("AUSDT", "BUSDT", "CUSDT")):
    return build_hl_panel(rows, set(trading), set(), TODAY)


# ------------------------------------------------------------------------------ saídas


def test_exit_fixed_net_of_two_legs() -> None:
    hp = _panel(_rows("AUSDT", range(0, 100), lambda k: 100.0 if k < 20 else 110.0))
    r = exit_fixed(hp.p, 0, 10, 10)  # compra na abertura 10 (100), vende na abertura 20 (110)
    assert r is not None
    assert r.opt == pytest.approx(1.1 * (1 - COST) ** 2 - 1) and r.pes == r.opt and r.delay == 0


def test_exit_fixed_waits_for_first_real_open_amendment_2() -> None:
    rows = [r for r in _rows("AUSDT", range(0, 100), lambda k: 100.0 + (k >= 21) * 20) if r[1] != 20]
    hp = _panel(rows)
    r = exit_fixed(hp.p, 0, 10, 10)  # sem vela no dia 20: vende na abertura real do dia 21 (120), atraso 1
    assert r is not None and r.delay == 1 and r.opt == pytest.approx(1.2 * (1 - COST) ** 2 - 1)


def test_exit_fixed_series_end_two_bounds_and_no_entry_without_real_open() -> None:
    hp = _panel(_rows("AUSDT", range(0, 15), 100.0, c=lambda k: 90.0 if k == 14 else 100.0),
                trading=("BUSDT",))  # AUSDT não negocia hoje: fim de série em 14
    r = exit_fixed(hp.p, 0, 10, 10)
    assert r is not None and r.pes == -1.0 and r.opt == pytest.approx(0.9 * (1 - COST) ** 2 - 1)
    gap = _panel([r for r in _rows("AUSDT", range(0, 100), 100.0) if r[1] != 10])
    assert exit_fixed(gap.p, 0, 10, 10) is None


def test_exit_struct_stop_target_gap_and_cap() -> None:
    lows = {12: 94.0}
    hp = _panel(_rows("AUSDT", range(0, 200), 100.0, h=101.0, lo=lambda k: lows.get(k, 99.0)))
    s = exit_struct(hp, 0, 10, stop=95.0, tgt=130.0)  # mínima 94 no dia 12 → stop 95, m = 3
    assert s is not None and s.m == 3 and s.opt == pytest.approx(0.95 * (1 - COST) ** 2 - 1)
    hp2 = _panel(_rows("AUSDT", range(0, 200), lambda k: 80.0 if k == 13 else 100.0, h=101.0, lo=lambda k: 79.0 if k == 13 else 99.0))
    g = exit_struct(hp2, 0, 10, stop=95.0, tgt=130.0)  # abre em 80 abaixo do stop no dia 13: sai na abertura, m = 3
    assert g is not None and g.m == 3 and g.opt == pytest.approx(0.80 * (1 - COST) ** 2 - 1)
    hp3 = _panel(_rows("AUSDT", range(0, 200), 100.0, h=lambda k: 131.0 if k == 15 else 101.0, lo=99.0))
    t = exit_struct(hp3, 0, 10, stop=95.0, tgt=130.0)
    assert t is not None and t.m == 6 and t.opt == pytest.approx(1.30 * (1 - COST) ** 2 - 1)
    cap = exit_struct(hp3, 0, 20, stop=95.0, tgt=500.0)  # nada toca: sai na abertura de e + 60
    assert cap is not None and cap.m == 60 and cap.opt == pytest.approx((1 - COST) ** 2 - 1)
    both = _panel(_rows("AUSDT", range(0, 200), 100.0, h=lambda k: 131.0 if k == 12 else 101.0, lo=lambda k: 94.0 if k == 12 else 99.0))
    b = exit_struct(both, 0, 10, stop=95.0, tgt=130.0)  # stop e alvo na mesma vela: stop primeiro
    assert b is not None and b.opt == pytest.approx(0.95 * (1 - COST) ** 2 - 1)


def test_contrast_is_event_minus_same_day_control_mean() -> None:
    x = contrast([(5, 0.10, 0.10), (5, 0.02, -1.0), (6, 0.0, 0.0)], {5: [(0.04, 0.04), (0.00, 0.00)]})
    assert x.opt.tolist() == pytest.approx([0.08, 0.0]) and x.pes.tolist() == pytest.approx([0.08, -1.02])
    assert x.days.tolist() == [5, 5] and x.dropped_no_control == 1


# ------------------------------------------------------------------------------ inferência e veredito


def test_day_sums_and_ratio_estimator_amendment_3() -> None:
    s, n = day_sums(np.array([0, 0, 3]), np.array([1.0, 3.0, 5.0]), 5)
    assert s.tolist() == [4.0, 0, 0, 5.0, 0] and n.tolist() == [2, 0, 0, 1, 0]
    ident = np.arange(5)[None, :]
    d_star, dropped = boot_d(s, n, ident)
    assert d_star.tolist() == pytest.approx([3.0]) and dropped == 0  # ΣS/ΣN = 9/3, não a média das médias (3,5)
    empty, dropped = boot_d(s, n, np.array([[1, 2, 4]]))
    assert empty.size == 0 and dropped == 1


def test_mbb_shape_contiguous_and_coverage_non_overlapping() -> None:
    idx = mbb_idx(100, 28, 50, 1)
    assert idx.shape == (50, 100) and np.all(np.diff(idx[:, :28], axis=1) == 1)
    assert coverage(np.array([0, 1, 27, 28, 200]), 28) == 3  # intervalos [0,28), [28,56), [196,224)


def _s(d, lo, hi, p=0.001, level=0.02, n=500, cov=90):
    return {"d": d, "lo": lo, "hi": hi, "p": p, "level": level, "n": n, "cov": cov}


def test_verdicts() -> None:
    good = _s(0.02, 0.005, 0.035)
    ok = {"plateau": True, "split": True, "k6": False}
    assert arm_verdict([good, good], [0.01, 0.01], 0.01, **ok) == "CONFIRMA"
    assert arm_verdict([good, good], [0.01, 0.06], 0.01, **ok) == "NÃO CONFIRMA"  # Holm num limite
    assert arm_verdict([good, good], [0.01, 0.01], 0.01, plateau=False, split=True, k6=False) == "NÃO CONFIRMA"
    small = _s(0.001, -0.004, 0.006)
    assert arm_verdict([small, small], [0.4, 0.4], 0.01, **ok) == "REFUTA"  # IC sup < MRE nos dois
    assert arm_verdict([small, _s(0.001, -0.004, 0.012)], [0.4, 0.4], 0.01, **ok) == "NÃO CONFIRMA"
    assert arm_verdict([_s(0.02, 0.005, 0.035, n=100), good], [0.01, 0.01], 0.01, **ok) == "LIMITE DE DADO"
    assert arm_verdict([_s(0.02, 0.005, 0.035, cov=39), good], [0.01, 0.01], 0.01, **ok) == "LIMITE DE DADO"
    assert arm_verdict([good, good], [0.01, 0.01], 0.01, plateau=True, split=True, k6=True) == "NÃO CONFIRMA"
    loses = _s(0.02, 0.005, 0.035, level=-0.001)
    assert arm_verdict([loses, loses], [0.01, 0.01], 0.01, **ok) == "NÃO CONFIRMA"


def test_summarize_centered_p_and_percentile_ci() -> None:
    rng = np.random.default_rng(0)
    days = np.arange(400)
    x = rng.normal(0.03, 0.01, 400)
    s, n = day_sums(days, x, 400)
    out = summarize(s, n, mbb_idx(400, 28, 2000, 3))
    assert out["d"] == pytest.approx(x.mean()) and out["lo"] < out["d"] < out["hi"] and out["p"] < 0.01


def test_exit_struct_open_beyond_target_precedes_intraday_low_astra_result_2() -> None:
    """Abre em 140 (acima do alvo 130) e cai a 90 no mesmo dia: a saída é na abertura, 140, não no stop."""
    hp = _panel(_rows("AUSDT", range(0, 200), lambda k: 140.0 if k == 12 else 100.0,
                      h=lambda k: 141.0 if k == 12 else 101.0, lo=lambda k: 90.0 if k == 12 else 99.0))
    s = exit_struct(hp, 0, 10, stop=95.0, tgt=130.0)
    assert s is not None and s.m == 2 and s.opt == pytest.approx(1.40 * (1 - COST) ** 2 - 1)


def test_k6_blocks_refuta_too_astra_result_3() -> None:
    small = _s(0.001, -0.004, 0.006)
    assert arm_verdict([small, small], [0.4, 0.4], 0.01, plateau=True, split=True, k6=True) == "NÃO CONFIRMA"


def test_structural_row_kept_when_fixed_exit_is_censored_astra_result_4() -> None:
    from collect85 import structural_row

    rows = _rows("AUSDT", range(0, 13), 100.0, h=101.0, lo=lambda k: 90.0 if k == 11 else 99.0)  # dado acaba em 12
    hp = _panel(rows)  # AUSDT negocia hoje: série viva, sem abertura em e + 10 → saída fixa censurada
    assert exit_fixed(hp.p, 0, 10, 10) is None
    s, fixed = structural_row(hp, 0, 10, hh=120.0, ll=96.0, atr_d=2.0, ex10=None)
    assert s is not None and s.m == 2 and fixed is None  # stop 95 tocado no dia 11
