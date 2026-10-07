# R89 — testes sintéticos da H-032 (valores esperados calculados à mão). Sem rede, sem banco.
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

import h032 as h

T0 = datetime(2026, 9, 24, 0, 5, tzinfo=UTC)


def row(mayhem, ret, *, t=T0, others=3, resolved=True, hw=1.2, pnl=None, cap=False, causal=True, mint=None):
    refusals = [f"x{i}" for i in range(others)] + (["mayhem_curve"] if mayhem else [])
    return h.Row(
        mint=mint or f"m{np.random.default_rng().integers(1e12)}", t=t, mayhem=mayhem,
        refusals=tuple(refusals), stratum="B", p=Decimal("0.005"),
        ret=ret if resolved else None, resolved=resolved, hw_x=hw,
        pnl=(ret if pnl is None else pnl) if resolved else None,
        exit_reason="target", cap_applied=cap, causal=causal, tok_flag=mayhem, snap_flag=mayhem,
    )


def test_n_outras_drops_mayhem_and_progress_families():
    refs = ("mayhem_curve", "progress_unknown", "progress_below_min", "age_below_min", "snipers_above_max")
    assert h.n_outras(refs, h.FAMILIES_PRIMARY) == 2
    refs2 = refs + ("participation_above_cap", "curve_volume_1m_zero", "flow_not_polled", "buyers_unknown")
    assert h.n_outras(refs2, h.FAMILIES_PRIMARY) == 6
    assert h.n_outras(refs2, h.FAMILIES_SENSITIVITY) == 2


def test_tercile_ties_go_together():
    x = np.array([1, 1, 1, 2, 2, 3, 3, 3, 3])
    lab, c1, c2 = h.terciles(x)
    # quantis lineares: q(1/3)=1.667, q(2/3)=3.0 → ≤1.667 baixo, >3 alto (nenhum), meio o resto
    assert c1 == pytest.approx(5 / 3) and c2 == pytest.approx(3.0)
    assert list(lab) == [0, 0, 0, 1, 1, 1, 1, 1, 1]


def test_d_adj_known_value_two_strata():
    # estrato 1 (dia 24, bloco 0, tercil t): N {0.1, 0.3} M {0.0}  → d = 0.2, w = 2·1/3
    # estrato 2 (dia 25):                  N {0.0}      M {-0.2, -0.4} → d = 0.3, w = 1·2/3
    # D = (2/3·0.2 + 2/3·0.3)/(4/3) = 0.25
    d25 = T0 + timedelta(days=1)
    rows = [row(False, 0.1), row(False, 0.3), row(True, 0.0), row(False, 0.0, t=d25), row(True, -0.2, t=d25), row(True, -0.4, t=d25)]
    res = h.d_adj(rows, h.FAMILIES_PRIMARY, cuts=(10.0, 20.0))
    assert res.d == pytest.approx(0.25)
    assert res.drop_m == 0 and res.drop_n == 0


def test_d_adj_drops_strata_without_both_groups_and_reports_support():
    d26 = T0 + timedelta(days=2)
    rows = [row(False, 0.1), row(True, 0.0), row(False, 5.0, t=d26), row(False, 5.0, t=d26)]
    res = h.d_adj(rows, h.FAMILIES_PRIMARY, cuts=(10.0, 20.0))
    assert res.d == pytest.approx(0.1)
    assert res.drop_n == pytest.approx(2 / 3) and res.drop_m == 0


def test_raw_contrast_is_nonmayhem_minus_mayhem():
    rows = [row(False, 0.2), row(False, 0.0), row(True, -0.1)]
    assert h.raw_d(rows) == pytest.approx(0.2)


def test_block_bootstrap_matches_estimator_and_is_reproducible():
    rng = np.random.default_rng(1)
    rows = []
    for k in range(200):
        t = T0 + timedelta(minutes=17 * k)
        rows.append(row(bool(k % 3 == 0), float(rng.normal(-0.05 if k % 3 == 0 else 0.0, 0.2)), t=t))
    cuts = (10.0, 20.0)
    point = h.d_adj(rows, h.FAMILIES_PRIMARY, cuts=cuts).d
    b1 = h.bootstrap(rows, h.FAMILIES_PRIMARY, cuts, block="hour", reps=500, seed=7)
    b2 = h.bootstrap(rows, h.FAMILIES_PRIMARY, cuts, block="hour", reps=500, seed=7)
    assert np.array_equal(b1, b2, equal_nan=True)
    # identidade: a réplica com cada bloco uma vez é o estimador pontual
    assert h.bootstrap_identity(rows, h.FAMILIES_PRIMARY, cuts, block="hour") == pytest.approx(point)
    assert abs(np.nanmean(b1) - point) < 0.03


def test_centered_p():
    boot = np.array([0.1, 0.2, 0.3, 0.4, 0.5])  # centrado em 0.3: |b-0.3| = .2 .1 0 .1 .2
    assert h.centered_p(boot, 0.3) == pytest.approx((1 + 0) / 6)  # nenhum |b-0.3| ≥ 0.3


def test_centered_p_counts_extremes():
    boot = np.array([0.0, 0.6, 0.3, 0.3])  # |b-0.3| = .3 .3 0 0 → 2 ≥ 0.3
    assert h.centered_p(boot, 0.3) == pytest.approx((1 + 2) / 5)


def test_cuts_do_not_depend_on_outcomes():
    rows = [row(i % 2 == 0, 0.1 * i, others=i % 7) for i in range(30)]
    c_a = h.population_cuts(rows, h.FAMILIES_PRIMARY)
    rows_b = [h.replace_ret(r, -9.0) for r in rows]
    assert h.population_cuts(rows_b, h.FAMILIES_PRIMARY) == c_a


def test_imputation_scenarios():
    rows = [row(False, 0.2), row(False, -0.4), row(False, 0.0, resolved=False),
            row(True, 0.5), row(True, -0.9), row(True, 0.0, resolved=False)]
    fav = h.impute(rows, "favor")  # a favor da exclusão: N ausente = max N (0.2), M ausente = min M (-0.9)
    assert [r.ret for r in fav if not r.resolved] == [0.2, -0.9]
    con = h.impute(rows, "contra")  # N ausente = min N (-0.4), M ausente = max M (0.5)
    assert [r.ret for r in con if not r.resolved] == [-0.4, 0.5]


def test_bought_top_class():
    assert h.bought_top(row(True, -0.1, hw=1.0)) is True
    assert h.bought_top(row(True, -0.1, hw=1.01)) is False
    assert h.bought_top(row(True, 0.05, hw=0.9)) is False


def test_label_precedence():
    ok = dict(instrument_ok=True, data_ok=True, support_ok=True, nonfinite_ok=True)
    good = dict(d=0.08, lo=0.02, hi=0.14, p=0.01, lo_day=0.01, robust=True, raw_same_sign=True,
                lo_fav=0.01, lo_con=0.005, hi_fav=0.2, hi_con=0.1)
    assert h.label(**ok, **good)[0] == "CONFIRMA"
    assert h.label(**{**ok, "instrument_ok": False}, **good)[0] == "NÃO CONFIRMA — instrumento"
    assert h.label(**{**ok, "data_ok": False}, **good)[0] == "NÃO CONFIRMA — limite de dado"
    assert h.label(**{**ok, "support_ok": False}, **good)[0] == "NÃO CONFIRMA — suporte"
    assert h.label(**{**ok, "nonfinite_ok": False}, **good)[0] == "NÃO CONFIRMA"
    ref = dict(good, d=0.0, lo=-0.03, hi=0.03, lo_fav=-0.02, hi_fav=0.04, lo_con=-0.04, hi_con=0.02, p=0.9)
    assert h.label(**ok, **ref)[0] == "REFUTA"
    # refutação que não sobrevive a um cenário de imputação → NÃO CONFIRMA (errata do R76)
    assert h.label(**ok, **dict(ref, hi_fav=0.06))[0] == "NÃO CONFIRMA"
    # confirmação sem a robustez → NÃO CONFIRMA
    assert h.label(**ok, **dict(good, robust=False))[0] == "NÃO CONFIRMA"
    assert h.label(**ok, **dict(good, lo_day=-0.01))[0] == "NÃO CONFIRMA"
    assert h.label(**ok, **dict(good, d=0.04))[0] == "NÃO CONFIRMA"


def test_round_trip_recomputes_tokens_and_shows_the_cap():
    snap = {"virtual_sol_reserves": Decimal(30), "virtual_token_reserves": Decimal(1073000000),
            "real_sol_reserves": Decimal(0)}
    tokens, rt_free, rt_cap = h.round_trip(snap, Decimal("0.07"), Decimal("1.75"), Decimal("0.0001"), mayhem=True)
    c = Decimal("0.07") / Decimal("1.0175")
    assert abs(tokens - Decimal(1073000000) * c / (Decimal(30) + c)) < Decimal("1e-6")
    # sem teto perde só as taxas (~2 × 1,75 % + prioridade); com teto no SOL real observado (0) perde tudo
    assert -0.045 < rt_free < -0.03
    assert rt_cap < -0.99
    _, rt_free_n, rt_cap_n = h.round_trip(snap, Decimal("0.07"), Decimal("1.75"), Decimal("0.0001"), mayhem=False)
    assert rt_cap_n == pytest.approx(rt_free_n)  # curva normal: nenhum teto


def test_bool_parser_accepts_psql_text():
    assert h._b("true") is True and h._b("t") is True and h._b("false") is False and h._b("") is None
