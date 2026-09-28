"""R84 — testes do painel, do universo ponto-no-tempo, do sinal, da carteira, da inferência e do veredito.

Valores esperados calculados à mão sobre painéis sintéticos pequenos. Rodar:
    uv run pytest -q .claude/state/r84/test_r84.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from engine import simulate, targets, week  # noqa: E402
from panel import build_panel  # noqa: E402
from stats84 import holm_verdict, mbb_indices, p_centered  # noqa: E402

TODAY = 1000  # dia UTC fictício "hoje"; col = dia - day0


def _rows(sym: str, days: range, close, vol=1.0, open_=None):
    out = []
    for k, d in enumerate(days):
        c = close(k) if callable(close) else close
        o = (open_(k) if callable(open_) else open_) if open_ is not None else c
        v = vol(k) if callable(vol) else vol
        out.append((sym, d, float(o), float(c), float(v)))
    return out


# ------------------------------------------------------------------------------ painel


def test_gap_of_14_days_splits_13_does_not() -> None:
    rows = _rows("AUSDT", range(0, 10), 1.0) + _rows("AUSDT", range(24, 30), 2.0)  # 14 dias ausentes (10..23)
    rows += _rows("BUSDT", range(0, 10), 1.0) + _rows("BUSDT", range(23, 30), 2.0)  # 13 ausentes
    p = build_panel(rows, trading={"AUSDT", "BUSDT"}, excluded_bases=set(), today_epoch_day=TODAY, day0=0, day_end=40)
    assert p.ids == ["AUSDT#0", "AUSDT#1", "BUSDT"]
    assert list(p.ended) == [True, False, False]  # 1.ª parte termina; símbolo TRADING não termina
    b = p.ids.index("BUSDT")
    assert p.open_ff[b, 15] == 1.0 and np.isnan(p.open[b, 15])  # lacuna curta: preço carregado
    assert p.open_ff[b, 23] == 2.0
    assert np.isnan(p.close_ff[b, 31])  # depois da última vela: nada


def test_long_gap_classified_as_same_asset_is_not_split_and_every_long_gap_is_listed() -> None:
    rows = _rows("AUSDT", range(0, 10), 1.0) + _rows("AUSDT", range(30, 40), 2.0)  # 20 d ausentes
    p = build_panel(rows, {"AUSDT"}, set(), TODAY, day0=0, day_end=50, keep_together={("AUSDT", 30)})
    assert p.ids == ["AUSDT"] and not p.ended[0]
    assert p.long_gaps == [("AUSDT", 9, 30, 20)]
    assert p.open_ff[0, 20] == 1.0  # marca carregada durante a lacuna


def test_non_trading_symbol_ends_and_current_day_candle_is_dropped() -> None:
    rows = _rows("XUSDT", range(0, 20), 1.0) + _rows("YUSDT", range(990, TODAY + 1), 3.0)
    p = build_panel(rows, trading={"YUSDT"}, excluded_bases=set(), today_epoch_day=TODAY, day0=0)
    x, y = p.ids.index("XUSDT"), p.ids.index("YUSDT")
    assert p.ended[x] and not p.ended[y]
    assert p.last[y] == TODAY - 1  # a vela de hoje (em formação) não entra


def test_documented_migration_links_old_series_to_new_at_the_swap_ratio() -> None:
    from config import apply_links

    rows = _rows("ERDUSDT", range(0, 10), 0.02, vol=5.0) + _rows("EGLDUSDT", range(9, 15), 20.0, vol=7.0)
    out, trading = apply_links(rows, {"EGLDUSDT"}, links=(("ERDUSDT", "EGLDUSDT", 1000.0),))
    erd = sorted((d, c, v) for s, d, o, c, v in out if s == "ERDUSDT")
    assert [d for d, _, _ in erd] == list(range(0, 15))  # dia 9 do novo (sobreposto) não duplica
    assert all(math.isclose(c, 0.02) for _, c, _ in erd)  # 20 / 1000 = 0,02: preço por unidade antiga
    assert erd[-1][2] == 7.0  # volume em USDT não muda
    assert not any(s == "EGLDUSDT" for s, *_ in out)
    assert "ERDUSDT" in trading  # a série continua viva


# ------------------------------------------------------------------ universo e sinal


def _universe_panel(n_coins=4, top=None):
    """Moedas C0..C3 listadas no dia 0; semana T = col 70 (segunda fictícia)."""
    rows = []
    for j in range(n_coins):
        rows += _rows(f"C{j}USDT", range(0, 100), lambda k, j=j: 100 + j + k * (1 if j % 2 == 0 else -0.5), vol=10 - j)
    return rows


def test_signal_is_close_of_T_minus_2_over_14_days_before() -> None:
    p = build_panel(_universe_panel(), set(), set(), TODAY, day0=0, day_end=120)
    wk = week(p, 70, lookback=14, top=20)
    c0 = p.ids.index("C0USDT")
    k = list(wk.idx).index(c0)
    assert math.isclose(wk.m[k], (100 + 68) / (100 + 54) - 1)  # d = 68, d-14 = 54
    c1 = list(wk.idx).index(p.ids.index("C1USDT"))
    assert wk.m[c1] < 0
    assert wk.n == 4


def test_top_n_by_30d_volume_ties_by_symbol_age_and_exclusions() -> None:
    rows = _rows("AAAUSDT", range(0, 100), 1.0, vol=5.0) + _rows("BBBUSDT", range(0, 100), 1.0, vol=5.0)
    rows += _rows("CCCUSDT", range(0, 100), 1.0, vol=9.0)
    rows += _rows("NEWUSDT", range(35, 100), 1.0, vol=99.0)  # 1.ª vela col 35 = T-35: 34 dias em T-1 → fora
    rows += _rows("OLDUSDT", range(34, 100), 1.0, vol=50.0)  # col 34 = T-36: 35 dias em T-1 → dentro
    rows += _rows("USDCUSDT", range(0, 100), 1.0, vol=999.0)  # excluída por desenho
    p = build_panel(rows, set(), {"USDC"}, TODAY, day0=0, day_end=120)
    wk = week(p, 70, lookback=14, top=3)
    got = [p.ids[i] for i in wk.idx]
    assert got == ["OLDUSDT", "CCCUSDT", "AAAUSDT"]  # AAA ganha o empate com BBB pelo símbolo


def test_volume_window_is_T_minus_30_to_T_minus_1_and_missing_is_zero() -> None:
    rows = _rows("AUSDT", range(0, 100), 1.0, vol=lambda k: 1000.0 if k == 70 else 1.0)  # volume enorme EM T
    rows += _rows("BUSDT", range(0, 100), 1.0, vol=lambda k: 100.0 if k == 39 else 1.0)  # em T-31: fora
    rows += _rows("CUSDT", range(0, 100), 1.0, vol=lambda k: 3.0 if k == 40 else 1.0)  # em T-30: dentro
    p = build_panel(rows, set(), set(), TODAY, day0=0, day_end=120)
    assert [p.ids[i] for i in week(p, 70, 14, top=1).idx] == ["CUSDT"]


def test_missing_signal_candle_makes_coin_ineligible_without_replacement() -> None:
    rows = _universe_panel(3)
    rows = [r for r in rows if not (r[0] == "C0USDT" and r[1] == 68)]  # sem a vela de sábado
    p = build_panel(rows, set(), set(), TODAY, day0=0, day_end=120)
    wk = week(p, 70, 14, top=2)
    assert wk.n == 1 and p.ids[wk.idx[0]] == "C1USDT"


# ------------------------------------------------------------------ sem antecipação


def test_no_candle_from_T_on_and_no_close_of_T_minus_1_changes_the_week() -> None:
    base = _universe_panel(6)
    p0 = build_panel(base, set(), set(), TODAY, day0=0, day_end=120)
    rng = np.random.default_rng(1)
    changed = []
    for s, d, o, c, v in base:
        if d >= 70:  # futuro: preço e volume embaralhados
            changed.append((s, d, o * rng.uniform(0.1, 10), c * rng.uniform(0.1, 10), v * rng.uniform(0.1, 1e6)))
        elif d == 69:  # vela de domingo: o fecho não pode entrar no sinal (uma barra de folga)
            changed.append((s, d, o, c * rng.uniform(0.1, 10), v))
        else:
            changed.append((s, d, o, c, v))
    p1 = build_panel(changed, set(), set(), TODAY, day0=0, day_end=120)
    for lb in (7, 14, 28):
        a, b = week(p0, 70, lb, top=4), week(p1, 70, lb, top=4)
        assert list(a.idx) == list(b.idx) and np.array_equal(a.m, b.m)
        for arm in ("ew", "ts", "cs"):
            assert targets(a, arm) == targets(b, arm)


def test_control_a_leaky_signal_would_be_caught() -> None:
    """Controle do próprio teste: ler o fecho de T (d = T) muda o sinal quando o futuro muda."""
    base = _universe_panel(4)
    fut = [(s, d, o, c * (3.0 if d == 70 and s == "C1USDT" else 1.0), v) for s, d, o, c, v in base]
    p0 = build_panel(base, set(), set(), TODAY, day0=0, day_end=120)
    p1 = build_panel(fut, set(), set(), TODAY, day0=0, day_end=120)
    i = p0.ids.index("C1USDT")
    leak0 = p0.close[i, 70] / p0.close[i, 56] - 1
    leak1 = p1.close[i, 70] / p1.close[i, 56] - 1
    assert leak0 < 0 < leak1  # o vazamento vira o sinal; o sinal honesto não viu nada
    assert np.array_equal(week(p0, 70, 14, 4).m, week(p1, 70, 14, 4).m)


# ------------------------------------------------------------------------ carteira


def test_targets_ts_ew_cs() -> None:
    p = build_panel(_universe_panel(4), set(), set(), TODAY, day0=0, day_end=120)
    wk = week(p, 70, 14, top=20)
    ew, ts, cs = targets(wk, "ew", min_n=1), targets(wk, "ts", min_n=1), targets(wk, "cs", min_n=1)
    assert ew == {i: 0.25 for i in wk.idx}
    pos = {p.ids.index("C0USDT"), p.ids.index("C2USDT")}
    assert ts == {i: 0.25 for i in pos}  # só as de sinal > 0, cada uma 1/N, resto caixa
    assert len(cs) == 2 and set(cs.values()) == {0.5}  # ceil(4/3) = 2, totalmente investida
    assert targets(wk, "ts", min_n=5) == {}  # semana não avaliável: caixa


def _two_coin_panel():
    # A: abre 100 em T, 110 em T+7, 132 em T+14. B: 100, 90, 90.
    def path(vals):
        return lambda k: vals[0] if k < 77 else (vals[1] if k < 84 else vals[2])

    rows = _rows("AUSDT", range(0, 100), path([100, 110, 132]), vol=2.0)
    rows += _rows("BUSDT", range(0, 100), path([100, 90, 90]), vol=1.0)
    return rows


def test_hand_computed_two_weeks_with_cost_on_effective_weights() -> None:
    p = build_panel(_two_coin_panel(), {"AUSDT", "BUSDT"}, set(), TODAY, day0=0, day_end=120)
    a, b = p.ids.index("AUSDT"), p.ids.index("BUSDT")
    plan = [{a: 0.5, b: 0.5}, {a: 0.5}]
    r, info = simulate(p, [70, 77], plan, bound="opt", cost=0.0015)
    assert math.isclose(r[0], (1 - 0.0015 * 1.0) * (1 + 0.5 * 0.10 + 0.5 * -0.10) - 1)
    # pesos efetivos em T+7: A 0,55, B 0,45; giro = |0,5−0,55| + |0−0,45| = 0,5
    assert math.isclose(r[1], (1 - 0.0015 * 0.5) * (1 + 0.5 * 0.20) - 1)
    assert info["delist_events"] == 0


def test_delisting_two_bounds() -> None:
    rows = _rows("AUSDT", range(0, 100), 100.0) + _rows("DUSDT", range(0, 73), lambda k: 100.0 if k < 72 else 80.0)
    p = build_panel(rows, {"AUSDT"}, set(), TODAY, day0=0, day_end=120)
    d = p.ids.index("DUSDT")
    assert p.ended[d] and p.last[d] == 72
    r_opt, i_opt = simulate(p, [70], [{d: 1.0}], bound="opt", cost=0.0015)
    r_pes, _ = simulate(p, [70], [{d: 1.0}], bound="pes", cost=0.0015)
    assert math.isclose(r_opt[0], (1 - 0.0015) * ((80 / 100) * (1 - 0.0015)) - 1)
    assert math.isclose(r_pes[0], (1 - 0.0015) * 0.0 - 1)
    assert i_opt["delist_events"] == 1


def test_held_coin_in_short_gap_is_frozen_at_the_carried_mark_not_sold() -> None:
    """Astra (R84 design #3): marca carregada não é preço executável — a posição fica, sem venda nem compra."""
    # G: 100 até col 76; sem velas 77..80 (lacuna de 4 d); volta a 50 em 81. A: sempre 100.
    rows = _rows("AUSDT", range(0, 100), 100.0)
    rows += _rows("GUSDT", [d for d in range(0, 100) if not 77 <= d <= 80], lambda k: 100.0)
    rows = [(s, d, 50.0 if (s == "GUSDT" and d >= 81) else o, 50.0 if (s == "GUSDT" and d >= 81) else c, v)
            for s, d, o, c, v in rows]
    p = build_panel(rows, {"AUSDT", "GUSDT"}, set(), TODAY, day0=0, day_end=120)
    a, g = p.ids.index("AUSDT"), p.ids.index("GUSDT")
    # semana 1 (T=70): 50/50; semana 2 (T=77, G sem vela real): o plano quer vender G, mas G fica congelada
    r, info = simulate(p, [70, 77], [{a: 0.5, g: 0.5}, {a: 1.0}], bound="opt", cost=0.0)
    assert math.isclose(r[0], 0.0)  # G carregada a 100 em T+7 (col 77 = fecho de 76)
    assert math.isclose(r[1], 0.5 * (50 / 100 - 1))  # G continua dentro e toma a queda na volta
    assert info["frozen"] == 1
    # e uma moeda sem vela em T não é comprada: o peso dela vira caixa
    r2, _ = simulate(p, [77], [{a: 0.5, g: 0.5}], bound="opt", cost=0.0)
    assert math.isclose(r2[0], 0.0)


def test_mondays_are_mondays_and_start_when_20_are_listed() -> None:
    import datetime as dt

    from analyze import mondays

    d0 = (dt.date(2020, 1, 1) - dt.date(1970, 1, 1)).days
    rows = []
    for j in range(20):
        rows += _rows(f"C{j:02d}USDT", range(d0 + 3 * j, d0 + 200), 1.0)
    p = build_panel(rows, set(), set(), d0 + 400, day0=d0)
    ts = mondays(p, d0 + 190)
    days = [dt.date(1970, 1, 1) + dt.timedelta(days=p.day0 + t) for t in ts]
    assert all(x.weekday() == 0 for x in days)
    # a 20.ª moeda lista em d0+57; precisa de 1.ª vela ≤ T−36 → T ≥ d0+93
    assert p.day0 + ts[0] >= d0 + 93 and p.day0 + ts[0] - 7 < d0 + 93


# ------------------------------------------------------------------------ inferência


def test_moving_blocks_are_contiguous_and_deterministic() -> None:
    idx = mbb_indices(20, block=8, reps=50, seed=20260928)
    assert idx.shape == (50, 20)
    for row in idx:
        for s in (0, 8):
            assert list(row[s : s + 8]) == list(range(row[s], row[s] + 8))
        assert row.max() <= 19
    assert np.array_equal(idx, mbb_indices(20, block=8, reps=50, seed=20260928))


def test_centered_p_is_small_for_a_clear_effect_and_near_half_for_none() -> None:
    rng = np.random.default_rng(3)
    idx = mbb_indices(400, 8, 2000, 20260928)
    strong = rng.normal(0.01, 0.02, 400)
    null = rng.normal(0.0, 0.02, 400)
    null -= null.mean()
    assert p_centered(strong, idx) < 0.01
    assert 0.3 < p_centered(null, idx) < 0.7


def test_verdict_rules() -> None:
    ok = {"n": 300, "d": 0.004, "lo": 0.001, "hi": 0.007, "level": 0.002, "plateau": True, "split": True, "p": 0.01}
    other = {"p": 0.01}
    assert holm_verdict([ok, ok], [other, other], mre=0.0025) == "CONFIRMA"
    # Holm com dois testes: p = 0,04 e 0,04 → ajustados 0,08 → não passa
    assert holm_verdict([dict(ok, p=0.04)] * 2, [{"p": 0.04}] * 2, mre=0.0025) == "NÃO CONFIRMA"
    # p = 0,02 e o outro 0,9 → ajustado 0,04 → passa
    assert holm_verdict([dict(ok, p=0.02)] * 2, [{"p": 0.9}] * 2, mre=0.0025) == "CONFIRMA"
    refute = dict(ok, d=-0.001, lo=-0.006, hi=0.002, p=0.6)
    assert holm_verdict([refute, refute], [other, other], mre=0.0025) == "REFUTA"
    assert holm_verdict([refute, ok], [other, other], mre=0.0025) == "NÃO CONFIRMA"  # limites divergem
    assert holm_verdict([dict(ok, n=150)] * 2, [other, other], mre=0.0025) == "LIMITE DE DADO"
    assert holm_verdict([dict(ok, split=False), ok], [other, other], mre=0.0025) == "NÃO CONFIRMA"
    assert holm_verdict([dict(ok, d=0.002), ok], [other, other], mre=0.0025) == "NÃO CONFIRMA"  # abaixo do MRE
    assert holm_verdict([dict(ok, level=-0.001), ok], [other, other], mre=0.0025) == "NÃO CONFIRMA"
