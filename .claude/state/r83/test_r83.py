# R83 — testes sintéticos com valores conhecidos: fórmula = produção, sem antecipação, guarda, tercis, população.
# cd .claude/state/r83 && uv run --project C:/dev/project-hunter pytest -q test_r83.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest
from h023 import assign_extremes, distance, population, window_ok

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import NormalizedCandle
from hunter_indicators.features.context import build_context
from hunter_indicators.features.price import DistanceFromExtreme
from hunter_indicators.features.state import FeatureState
from infra.research.guards import Instants, check_observable

M = timedelta(minutes=1)
OBS = datetime(2026, 9, 20, 12, 15, tzinfo=UTC)


def k(open_time: datetime, close: str, high: str | None = None, low: str | None = None, final: bool = True):
    c = Decimal(close)
    return NormalizedCandle(
        exchange="binance", symbol="XUSDT", timeframe=Timeframe.M1, open_time=open_time,
        close_time=open_time + M, open=c, high=Decimal(high) if high else c, low=Decimal(low) if low else c,
        close=c, volume=Decimal("1"), quote_volume=None, trade_count=None, taker_buy_volume=None,
        is_final=final, event_ts=None,
    )


def day_series(extra_after: list[NormalizedCandle] | None = None) -> list[NormalizedCandle]:
    """1 500 velas finais até `OBS` (fecho da última = OBS): preço 100, pico 110 a 600 min, vale 90 a 30 min."""
    out = []
    for i in range(1500, 0, -1):
        t = OBS - i * M
        out.append(k(t, "100", high="110" if i == 600 else None, low="90" if i == 30 else None))
    out[-1] = k(OBS - M, "99")  # última vela fechada: close 99
    return out + (extra_after or [])


def sql_mirror(candles: list[NormalizedCandle], obs: datetime):
    """O que `q_feat.sql` faz: velas finais com abertura em [obs − 1440, obs − 1]."""
    w = [c for c in candles if c.is_final and obs - 1440 * M <= c.open_time < obs]
    last = [c for c in candles if c.is_final and c.open_time == obs - M]
    return (len(w), min(c.open_time for c in w), max(c.open_time for c in w),
            max(c.high for c in w), min(c.low for c in w), last[0].close if last else None)


def production(candles: list[NormalizedCandle], kind: str) -> Decimal | None:
    ctx = build_context(exchange="binance", symbol="XUSDT", as_of=OBS, candles=candles)
    v = DistanceFromExtreme(kind=kind).compute(ctx, FeatureState())  # type: ignore[arg-type]
    return v.value  # None quando indisponível (FeatureValue.unavailable)


def mirror_value(candles, kind):
    n, first, last, hi, lo, close = sql_mirror(candles, OBS)
    assert window_ok(n, first, last, OBS) is None
    return distance(close, hi if kind == "high" else lo)


def test_known_values():
    c = day_series()
    assert mirror_value(c, "high") == (Decimal("99") - 110) / 110  # −0,1
    assert mirror_value(c, "low") == (Decimal("99") - 90) / 90  # +0,1
    assert float(mirror_value(c, "high")) == pytest.approx(-0.1)


@pytest.mark.parametrize("kind", ["high", "low"])
def test_reconstruction_equals_the_production_class(kind):
    c = day_series()
    assert mirror_value(c, kind) == production(c, kind)


@pytest.mark.parametrize("kind", ["high", "low"])
def test_no_look_ahead_candle_after_obs_and_forming_candle_do_not_change_it(kind):
    base = mirror_value(day_series(), kind)
    later = [k(OBS, "500", high="999", low="1"), k(OBS + M, "1", high="999", low="1")]
    forming = [k(OBS, "500", high="999", low="1", final=False)]
    for extra in (later, forming):
        c = day_series(extra)
        assert mirror_value(c, kind) == base
        assert production(c, kind) == base


def test_non_final_candle_inside_the_window_is_not_read():
    c = day_series()
    # uma versão não final do minuto do pico, com máxima absurda, ao lado da final
    c.append(k(OBS - 600 * M, "100", high="1000", final=False))
    assert mirror_value(c, "high") == (Decimal("99") - 110) / 110


def test_hole_in_the_window_is_absent_never_zero():
    c = [x for x in day_series() if x.open_time != OBS - 700 * M]
    n, first, last, *_ = sql_mirror(c, OBS)
    assert window_ok(n, first, last, OBS) == "janela_incompleta"
    assert production(c, "high") is None
    c2 = [x for x in day_series() if x.open_time != OBS - M]
    n, first, last, *_ = sql_mirror(c2, OBS)
    assert window_ok(n, first, last, OBS) == "ultima_vela_ausente"


def test_mill_guard_refuses_a_window_that_ends_after_the_signal():
    emitted = OBS + timedelta(seconds=2)
    assert check_observable(Instants(as_of=OBS, computed_at=OBS), emitted, "ok") is None
    cheat = OBS + M  # janela deslocada um minuto: inclui a vela que fecha depois do sinal
    assert check_observable(Instants(as_of=cheat, computed_at=cheat), emitted, "cheat") is not None
    late = Instants(as_of=OBS, computed_at=OBS + timedelta(seconds=30))  # vela chegou depois do sinal
    assert check_observable(late, emitted, "late") is not None


def _r(strategy, v):
    return {"strategy": strategy, "x": v}


def test_terciles_within_group_known_cuts_and_ties():
    rows = [_r("a", v) for v in (1, 2, 3, 4, 5, 6, 7, 8, 9)] + [_r("b", v) for v in (10, 20, 30, 40, 50, 60)]
    lab = assign_extremes(rows, "x", Fraction(1, 3))
    # a: terciles -> (xs[3]=4, xs[6]=7): baixo <= 4, alto > 7
    assert lab[:9] == ["baixo"] * 4 + ["meio"] * 3 + ["alto"] * 2
    # b: (xs[2]=30, xs[4]=50)
    assert lab[9:] == ["baixo"] * 3 + ["meio"] * 2 + ["alto"]
    tied = [_r("a", v) for v in (1, 1, 1, 1, 1, 1, 2, 3, 4)]
    assert assign_extremes(tied, "x", Fraction(1, 3))[:6] == ["baixo"] * 6


def test_neighbour_cut_half_is_median_split_and_missing_stays_out():
    rows = [_r("a", v) for v in (1, 2, 3, 4, 5, 6)] + [_r("a", None)]
    lab = assign_extremes(rows, "x", Fraction(1, 2))
    assert lab == ["baixo"] * 4 + ["alto"] * 2 + [None]  # xs[3]=4


def _p(sv, market, obs, cohort, sid, mt="perpetual"):
    return {"sv": sv, "market": market, "obs": obs, "cohort": cohort, "prospective": cohort == "prospective",
            "signal_id": sid, "market_type": mt}


def test_population_one_decision_per_version_market_obs_prospective_first():
    rows = [_p("m/v1", "A", OBS, "replay:z", "1"), _p("m/v1", "A", OBS, "prospective", "2"),
            _p("m/v1", "A", OBS, "replay:a", "3"), _p("m/v2", "A", OBS, "replay:a", "4"),
            _p("m/v1", "A", OBS, "prospective", "5", mt="spot")]
    pop, cnt = population(rows)
    assert [r["signal_id"] for r in pop] == ["2", "4"]
    assert cnt == {"fora_spot": 1, "fora_duplicada": 2, "dentro": 2}


def test_the_look_ahead_test_catches_a_leaky_window():
    """Controle do próprio teste: uma janela que admite a vela que abre em `obs` muda o valor."""
    c = day_series([k(OBS, "500", high="999", low="1")])
    leaky = [x for x in c if x.is_final and OBS - 1439 * M <= x.open_time <= OBS]
    hi = max(x.high for x in leaky)
    assert distance(leaky[-1].close, hi) != mirror_value(c, "high")


def test_fila_label_order_and_errata():
    from h023 import fila_label

    base = dict(n=9000, rho_max=0.4, d=0.08, lo=0.02, hi=0.14, p=0.01, p_holm=0.02, level_alto=0.05, shape="planalto")
    assert fila_label(**base)[0] == "CONFIRMA"
    assert fila_label(**dict(base, rho_max=0.81))[0] == "LIMITE DE DADO/MEDIDA"
    assert fila_label(**dict(base, n=149))[0] == "LIMITE DE DADO/MEDIDA"
    assert fila_label(**dict(base, d=-0.02, lo=-0.05, hi=0.009))[0] == "REFUTA"
    # IC largo com o efeito previsto dentro: a literal dispara, a errata segura em NÃO CONFIRMA
    lab, why = fila_label(**dict(base, d=0.03, lo=-0.02, hi=0.20))
    assert lab == "NÃO CONFIRMA" and "literal" in why[0]
    assert fila_label(**dict(base, shape="pico"))[0] == "NÃO CONFIRMA"
    assert fila_label(**dict(base, level_alto=-0.01))[0] == "NÃO CONFIRMA"
    assert fila_label(**dict(base, p_holm=0.06))[0] == "NÃO CONFIRMA"


def _episodes(effect: float, n: int = 120, seed: int = 1):
    import numpy as np

    rng = np.random.default_rng(seed)
    sel = np.arange(n) % 2 == 0
    y = rng.normal(0, 1, n) + effect * sel
    return y, sel, [f"e{i}" for i in range(n)], ["s1" if i < n // 2 else "s2" for i in range(n)]


def test_episode_permutation_is_invariant_to_duplicated_versions():
    import numpy as np
    from stats83 import episode_perm_p

    from infra.research.resampling import permutation_p

    y, sel, ep, st = _episodes(0.3)
    p1 = episode_perm_p(y, sel, ep, st, reps=2000, seed=5)
    y5, sel5 = np.repeat(y, 5), np.repeat(sel, 5)
    ep5, st5 = [e for e in ep for _ in range(5)], [s for s in st for _ in range(5)]
    assert episode_perm_p(y5, sel5, ep5, st5, reps=2000, seed=5) == p1
    # a permutação linha a linha trata as 5 cópias como independentes e encolhe o p
    assert permutation_p(y5, sel5, st5, reps=2000, seed=5) < p1 / 3


def test_episode_permutation_detects_a_known_effect_and_not_a_null():
    from stats83 import episode_perm_p

    assert episode_perm_p(*_episodes(1.5), reps=2000, seed=5) < 0.001
    assert episode_perm_p(*_episodes(0.0, seed=3), reps=2000, seed=5) > 0.05


def test_bootstrap_two_sided_p():
    from stats83 import boot_p_two_sided

    y, sel, ep, _ = _episodes(1.5)
    assert boot_p_two_sided(y, sel, ep, reps=2000, seed=1) < 0.001
    y0, sel0, ep0, _ = _episodes(0.0, seed=3)
    assert boot_p_two_sided(y0, sel0, ep0, reps=2000, seed=1) > 0.05


def test_distinct_partitions_collapse():
    from stats83 import distinct

    from infra.research.resampling import Interval
    from infra.research.stats import CurvePoint

    ci = Interval(0.0, 0.1, 0.0, 10)
    pts = [CurvePoint(0.2, 10, 10, 0.05, ci, True), CurvePoint(0.25, 10, 10, 0.05, ci, True),
           CurvePoint(0.3, 12, 12, 0.04, ci, True)]
    assert [p.threshold for p in distinct(pts)] == [0.2, 0.3]


def test_upper_between_fila_bar_and_mre_is_not_refuted_by_the_fila():
    """IC sup em [+0,01, +0,05): o moinho carimba REFUTA (IC sup < MRE); a fila, não (só IC sup < +0,01)."""
    from h023 import fila_label

    lab, _ = fila_label(n=9187, rho_max=0.385, d=-0.0324, lo=-0.1131, hi=0.0376, p=0.497, p_holm=0.497,
                        level_alto=-0.2482, shape="ausente")
    assert lab == "NÃO CONFIRMA"
    assert fila_label(n=9187, rho_max=0.385, d=-0.02, lo=-0.05, hi=0.0099, p=0.5, p_holm=0.5,
                      level_alto=-0.2, shape="ausente")[0] == "REFUTA"
