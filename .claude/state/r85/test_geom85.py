"""R85 — testes da geometria causal (ATR, pivôs, perna de Fibonacci, LTA) com séries sintéticas de valor conhecido.

Rodar:
    uv run pytest -q .claude/state/r85/test_geom85.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from geom85 import (
    BANDS,
    fib_scan,
    lta_scan,
    pivots_high,
    pivots_low,
    prefix_divergences,
    wilder_atr,
)

# ------------------------------------------------------------------------------ ATR e pivôs


def test_wilder_atr_hand_values() -> None:
    # H−L = 1..16 com fechamento no meio e sem salto: TR_t = t+1 (o salto do fecho nunca passa de H−L)
    n = 16
    rng = np.arange(1, n + 1, dtype=float)
    close = np.full(n, 100.0)
    high, low = close + rng / 2, close - rng / 2
    atr = wilder_atr(high, low, close, 14)
    assert np.all(np.isnan(atr[:13]))
    assert atr[13] == pytest.approx(7.5)  # média de 1..14
    assert atr[14] == pytest.approx((7.5 * 13 + 15) / 14)
    assert atr[15] == pytest.approx((atr[14] * 13 + 16) / 14)


def test_pivot_high_strict_left_ties_to_older_and_needs_k_right() -> None:
    h = np.array([1, 2, 3, 4, 5, 9, 9, 4, 3, 2, 1, 0, 0], dtype=float)
    ph = pivots_high(h, 5)
    assert list(np.flatnonzero(ph)) == [5]  # o platô 9,9 rende um pivô, na barra mais velha
    assert not pivots_high(h[:10], 5)[5]  # sem 5 barras à direita ainda não é pivô


def test_pivot_low_mirror() -> None:
    lo = np.array([9, 8, 7, 6, 5, 1, 2, 3, 4, 5, 6], dtype=float)
    assert list(np.flatnonzero(pivots_low(lo, 5))) == [5]


# ------------------------------------------------------------------------------ Fibonacci


def _fib_path() -> np.ndarray:
    c = [112.0 + i for i in range(9)]  # 0..8: sobe até 120 (pivô de alta 8)
    c += [118.0, 116, 114, 112, 110, 108, 106, 104, 102, 101, 100]  # 9..19; 20 = 100 abaixo
    c = c[:20] + [100.0]  # idx 20 = 100 (mínima L)
    c += [100.0 + 5 * (i - 20) for i in range(21, 41)]  # 21..40: sobe até 200 (H em 40)
    c += [199.0, 198, 197, 196, 195]  # 41..45 (confirmação em 45: r = 0,05)
    c += [190.0, 185, 180, 175, 170, 165, 160, 155, 150, 145, 140, 135, 130, 125, 120]  # 46..60
    return np.array(c)


def _flat_candles(c: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return c.copy(), c.copy(), c.copy()  # H = L = C: r é exato


def test_fib_events_known_bars_per_band() -> None:
    c = _fib_path()
    h, lo, cl = _flat_candles(c)
    out = fib_scan(h, lo, cl, wilder_atr(h, lo, cl, 14))
    # r = (200 − C)/100: 0,40 em 52 (160), 0,45 em 53, 0,50 em 54, 0,55 em 55, 0,70 em 58
    expected = {0.40: 52, 0.45: 53, 0.50: 54, 0.55: 55, 0.70: 58}
    for (lo_b, _), ev in zip(BANDS, out.events, strict=True):
        assert list(np.flatnonzero(ev)) == [expected[lo_b]], lo_b
    assert list(np.flatnonzero(out.ctrl)) == [45, 46, 47, 48]  # r < 0,236 depois de confirmada
    assert out.swing_h[54] == 200 and out.swing_l[54] == 100


def test_fib_gap_through_band_is_no_event() -> None:
    c = _fib_path()
    c[53] = 160.0  # r 0,40
    c[54] = 135.0  # salta para r 0,65 > 0,618: a faixa 0,50 não tem evento; a 0,55 também não (0,65 ≤ 0,668 → tem)
    h, lo, cl = _flat_candles(c)
    out = fib_scan(h, lo, cl, wilder_atr(h, lo, cl, 14))
    main = BANDS.index((0.50, 0.618))
    assert not out.events[main].any()
    assert list(np.flatnonzero(out.events[BANDS.index((0.55, 0.668))])) == [54]


def test_fib_crossing_at_pivot_bar_itself_consumes_band_amendment_1() -> None:
    """Emenda (1): a busca começa em h, inclusive. Pavio longo: máxima 200, fecho da própria vela h em 145 (r 0,55)."""
    c = _fib_path()
    h, lo, cl = _flat_candles(c)
    cl[40] = 145.0  # r = 0,55 já na vela do pivô: as faixas 0,40/0,45/0,50/0,55 ficam consumidas antes da confirmação
    lo[40] = 145.0
    out = fib_scan(h, lo, cl, wilder_atr(h, lo, cl, 14))
    for lo_b in (0.40, 0.45, 0.50, 0.55):
        assert not out.events[BANDS.index(next(b for b in BANDS if b[0] == lo_b))].any(), lo_b
    assert list(np.flatnonzero(out.events[BANDS.index((0.70, 0.818))])) == [58]


def test_fib_swing_dies_on_close_below_low_and_small_swing_is_ignored() -> None:
    c = _fib_path()
    c[46:] = 99.0  # fecha abaixo de L = 100 logo depois de confirmada: a perna morre, nenhum evento
    h, lo, cl = _flat_candles(c)
    out = fib_scan(h, lo, cl, wilder_atr(h, lo, cl, 14))
    assert not any(ev.any() for ev in out.events)
    small = fib_scan(h, lo, cl, wilder_atr(h, lo, cl, 14), min_amp_atr=1e6)
    assert not small.ctrl.any() and not any(ev.any() for ev in small.events)


# ------------------------------------------------------------------------------ LTA

OFF = 20  # prelúdio em queda monotônica (sem pivô de baixa) para o ATR aquecer


def _lta_path() -> np.ndarray:
    c = [160.0 - 2 * i for i in range(OFF)]  # 0..19: 160 → 122
    c += [120.0 - 2 * i for i in range(10)]  # a−10..a−1: 120 → 102
    c += [101.0]  # a = OFF+10: mínima 100
    c += [101.0 + 3 * i for i in range(1, 10)]  # a+1..a+9: 104 → 128
    c += [126.0, 124, 122, 120, 118, 116, 115, 114, 113, 112, 111]  # a+10..a+20 (b = a+20: mínima 110)
    c += [114.0, 117, 120, 123, 126, 129, 132, 135, 138, 140]  # b+1..b+10 (topo 141 em b+10)
    c += [136.0, 132, 128, 124, 121, 119]  # b+11..b+16: toque 3 em b+16 (mínima 118 = linha)
    c += [123.0, 127, 131, 135, 139, 142]  # b+17..b+22: fecha 142 > 141 em b+22 → B
    c += [144.0, 146, 148, 150]  # b+23..b+26
    c += [120.0, 110]  # b+27, b+28: fecha muito abaixo da linha → morre
    c += [111.0, 112, 113]
    return np.array(c)


def _candles(c: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return c + 1.0, c - 1.0, c


def test_lta_known_touch_break_of_top_and_death() -> None:
    c = _lta_path()
    a = OFF + 10
    b = a + 20
    h, lo, cl = _candles(c)
    out = lta_scan(h, lo, cl, wilder_atr(h, lo, cl, 14))
    assert list(np.flatnonzero(out.a_events)) == [b + 16]
    assert list(np.flatnonzero(out.b_events)) == [b + 22]
    ctrl = list(np.flatnonzero(out.ctrl))
    assert ctrl == [t for t in range(b + 17, b + 27) if t != b + 22]  # confirmada, sem toque, até morrer em b+27


def test_lta_needs_distinct_touch_and_third_touch() -> None:
    c = _lta_path()
    b = OFF + 30
    c[b + 1 : b + 16] = np.linspace(111.5, 119.0, 15)  # nunca se afasta 1 ATR da linha antes do toque
    h, lo, cl = _candles(c)
    out = lta_scan(h, lo, cl, wilder_atr(h, lo, cl, 14))
    assert b + 16 not in set(np.flatnonzero(out.a_events))


# ------------------------------------------------------------------------------ antecipação


def _random_ohlc(n: int, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.04, n)))
    h = c * np.exp(np.abs(rng.normal(0, 0.02, n)))
    lo = c * np.exp(-np.abs(rng.normal(0, 0.02, n)))
    return h, lo, c


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_scans_do_not_change_when_future_or_forming_candles_change(seed: int) -> None:
    h, lo, c = _random_ohlc(600, seed)
    ts = list(range(40, 600, 7))
    assert prefix_divergences(fib_scan, (h, lo, c), ts) == []
    for tol in (0.15, 0.25, 0.35):
        assert prefix_divergences(lambda *x, tol=tol: lta_scan(*x, tol=tol), (h, lo, c), ts) == []
    # a vela seguinte "em formação" muda à vontade: o resultado em t não muda
    h2, lo2, c2 = h.copy(), lo.copy(), c.copy()
    h2[301], lo2[301], c2[301] = h[301] * 3, lo[301] / 3, c[301] * 2
    for scan in (fib_scan, lta_scan):
        a = scan(h[:301], lo[:301], c[:301], wilder_atr(h[:301], lo[:301], c[:301], 14))
        b_ = scan(h2, lo2, c2, wilder_atr(h2, lo2, c2, 14))
        assert np.array_equal(a.flags()[:, :301], b_.flags()[:, :301])


def test_guard_catches_deliberate_lookahead_cheat() -> None:
    """Estratégia trapaceira: pivô usado na própria barra (sem esperar k), comprando o fundo que só se sabe depois."""
    h, lo, c = _random_ohlc(400, 7)

    class Cheat:
        def __init__(self, ev: np.ndarray) -> None:
            self.ev = ev

        def flags(self) -> np.ndarray:
            return self.ev[None, :]

    def cheat_scan(h_, lo_, c_, atr_):
        return Cheat(pivots_low(lo_, 5))  # pivô "conhecido" na barra dele: antecipação de 5 velas

    bad = prefix_divergences(cheat_scan, (h, lo, c), list(range(20, 400, 3)))
    assert len(bad) > 0


def test_lta_expires_exactly_at_b_plus_max_age_astra_result_1() -> None:
    """Revisão do resultado, must-fix 1: 'morre 180 velas depois de b' → em b + max_age a linha já não emite."""
    c = _lta_path()
    b = OFF + 30
    h, lo, cl = _candles(c)
    atr = wilder_atr(h, lo, cl, 14)
    assert b + 16 not in set(np.flatnonzero(lta_scan(h, lo, cl, atr, max_age=16).a_events))
    assert b + 16 in set(np.flatnonzero(lta_scan(h, lo, cl, atr, max_age=17).a_events))
