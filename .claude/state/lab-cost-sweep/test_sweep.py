"""lab-cost-sweep — testes sintéticos com valor esperado conhecido (escritos antes do sweep.py).

Rodar: uv run pytest .claude/state/lab-cost-sweep/test_sweep.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

import sweep  # noqa: E402

pytestmark = pytest.mark.unit


def _row(**kw: str) -> dict[str, str]:
    base = {
        "signal_id": "s1", "strategy": "momentum", "version": "v3", "mt": "perpetual", "symbol": "AAAUSDT",
        "cohort": "prospective", "emitted_at": "2026-09-10 10:00:00+00", "entry_ts": "2026-09-10 10:01:00+00",
        "exit_ts": "2026-09-10 12:01:00+00", "result": "target",
        "stop": "97", "entry_c": "100.06", "exit_base": "103", "r_multiple": "", "r_ex_funding": "",
        "r_net_reason": "", "funding_per_unit": "0", "spread_bps": "2", "slippage_bps": "5", "fee_bps": "4",
    }
    base.update(kw)
    return base


def lab_r(o: float, b: float, s: float, c_bp: float, f_bp: float, fund: float) -> float:
    """Fórmula do Lab (pricing.py) escrita à parte, para conferir a reconstrução."""
    e = o * (1 + c_bp / 1e4)
    x = b * (1 - c_bp / 1e4)
    f = f_bp / 1e4
    return ((x - e) - f * e - f * x - fund) / (e - s)


def test_reconstruct_open_and_gross() -> None:
    t = sweep.Trade.from_row(_row())
    assert t.open == pytest.approx(100.0, abs=1e-12)  # 100,06 / (1 + 6 bp)
    # denominador = unidade de risco que o Lab gravou: E_lab − S = 100,06 − 97 = 3,06
    assert t.gross_r == pytest.approx(3.0 / 3.06)  # (103 − 100) / 3,06
    assert t.funding_r == 0.0
    assert t.duration_min == pytest.approx(120.0)
    assert t.day == "2026-09-10" and t.month == "2026-09"


def test_lab_r_recomputed_matches_independent_formula() -> None:
    t = sweep.Trade.from_row(_row(funding_per_unit="0.05"))
    assert t.lab_r_recomputed() == pytest.approx(lab_r(100, 103, 97, 6, 4, 0.05), abs=1e-12)


def test_scenario_fee_only_is_linear_in_fee() -> None:
    t = sweep.Trade.from_row(_row(funding_per_unit="0.03"))
    # 5 bp por perna, sem slippage: R = (103 − 100 − 0,0005·(100+103) − 0,03) / 3,06
    expected = (3.0 - 0.0005 * 203 - 0.03) / 3.06
    assert t.scenario_r(fee_bp=5.0, slip_bp=0.0, with_funding=True) == pytest.approx(expected, abs=1e-12)
    assert t.scenario_r(fee_bp=5.0, slip_bp=0.0, with_funding=False) == pytest.approx(expected + 0.03 / 3.06,
                                                                                    abs=1e-12)


def test_scenario_with_lab_costs_reproduces_lab_formula() -> None:
    t = sweep.Trade.from_row(_row(funding_per_unit="0.02"))
    assert t.scenario_r(fee_bp=4.0, slip_bp=6.0, with_funding=True) == pytest.approx(
        lab_r(100, 103, 97, 6, 4, 0.02), abs=1e-12)


def test_negative_fee_is_a_rebate() -> None:
    t = sweep.Trade.from_row(_row())
    assert t.scenario_r(fee_bp=-0.5, slip_bp=0.0, with_funding=True) > t.gross_r


def test_missing_funding_is_none_not_zero() -> None:
    t = sweep.Trade.from_row(_row(funding_per_unit="", r_net_reason="funding_missing"))
    assert t.funding_r is None
    assert t.scenario_r(fee_bp=5.0, slip_bp=0.0, with_funding=True) is None
    assert t.scenario_r(fee_bp=5.0, slip_bp=0.0, with_funding=False) is not None


def test_spot_has_no_funding() -> None:
    t = sweep.Trade.from_row(_row(mt="spot", funding_per_unit="", r_net_reason="funding_schedule_unknown"))
    assert t.funding_r == 0.0


def test_break_even_round_trip_known_value() -> None:
    # dois trades, O = 100, S = 98 (risco 2): ganhos brutos +4 e −2 → Σ(G) = 2 − 1 = +1 R.
    # h_i = (O + B)/(O − S): (100+104)/2 = 102 ; (100+98)/2 = 99 → Σh = 201.
    # k*/2 · 1e-4 · 201 = 1 → k* = 2e4/201 bp ida-e-volta.
    a = sweep.Trade.from_row(_row(stop="98", entry_c="100", exit_base="104", spread_bps="0", slippage_bps="0"))
    b = sweep.Trade.from_row(_row(stop="98", entry_c="100", exit_base="98", spread_bps="0", slippage_bps="0"))
    g = np.array([a.gross_r, b.gross_r])
    h = np.array([a.notional_per_r, b.notional_per_r])
    assert sweep.break_even_bp(g, h) == pytest.approx(2e4 / 201, rel=1e-12)
    # no custo de equilíbrio a média do cenário zera
    k = sweep.break_even_bp(g, h)
    rs = [t.scenario_r(fee_bp=k / 2, slip_bp=0.0, with_funding=True) for t in (a, b)]
    assert float(np.mean(rs)) == pytest.approx(0.0, abs=1e-12)


def test_cluster_bootstrap_mean_single_cluster_value() -> None:
    # Todos os valores iguais → IC degenerado no próprio valor.
    y = np.full(10, 0.3)
    groups = ["d1"] * 5 + ["d2"] * 5
    est, lo, hi = sweep.cluster_ci(lambda idx: float(np.mean(y[idx])), groups, reps=200, seed=1)
    assert est == pytest.approx(0.3) and lo == pytest.approx(0.3) and hi == pytest.approx(0.3)


def test_cluster_bootstrap_resamples_whole_clusters() -> None:
    # cluster A = +1 (1 obs), cluster B = −1 (9 obs). Reamostrar observações daria médias perto de −0,8;
    # reamostrar clusters dá só três médias possíveis por réplica de 2 clusters: +1, −0,8 (A+B) e −1.
    y = np.array([1.0] + [-1.0] * 9)
    groups = ["A"] + ["B"] * 9
    draws = sweep.cluster_draws(lambda idx: float(np.mean(y[idx])), groups, reps=500, seed=7)
    assert set(np.round(draws, 6)).issubset({1.0, -0.8, -1.0})


def test_summary_counts_days_and_trades_per_day() -> None:
    rows = [_row(signal_id=f"s{i}", emitted_at=f"2026-09-1{i % 3} 10:00:00+00") for i in range(6)]
    ts = [sweep.Trade.from_row(r) for r in rows]
    s = sweep.activity(ts)
    assert s["n"] == 6 and s["days"] == 3 and s["per_active_day"] == pytest.approx(2.0)


def test_fast_ratio_ci_equals_generic_bootstrap() -> None:
    rng = np.random.default_rng(3)
    num = rng.normal(0.1, 1.0, 200)
    den = rng.uniform(50, 150, 200)
    groups = [f"g{i % 17:02d}" for i in range(200)]
    est, lo, hi = sweep.ratio_ci(num, den, groups, scale=2e4, reps=300, seed=11)
    d = sweep.cluster_draws(lambda idx: 2e4 * num[idx].sum() / den[idx].sum(), groups, reps=300, seed=11)
    assert est == pytest.approx(2e4 * num.sum() / den.sum())
    assert lo == pytest.approx(float(np.percentile(d, 2.5)), rel=1e-12)
    assert hi == pytest.approx(float(np.percentile(d, 97.5)), rel=1e-12)


def test_naive_timestamp_is_refused() -> None:
    with pytest.raises(ValueError):
        sweep.Trade.from_row(_row(emitted_at="2026-09-10 10:00:00"))


def test_open_at_stop_does_not_blow_up() -> None:
    # abertura exatamente no stop: O − S = 0, mas o Lab gravou E − S = 6 bp de O > 0; o R do cenário fica finito.
    t = sweep.Trade.from_row(_row(stop="100", entry_c="100.06", exit_base="100", result="stop"))
    r = t.scenario_r(fee_bp=5.0, slip_bp=0.0, with_funding=True)
    assert r == pytest.approx(-(0.0005 * 200) / 0.06, abs=1e-9)
    assert t.gross_r == pytest.approx(0.0)


def test_effective_cost_is_h_weighted_not_median() -> None:
    # Astra (must-fix 4): 51 % dos trades a 10 bp e 49 % a 30 bp, pesos iguais → mediana 10 bp, média 19,8 bp.
    h = np.ones(100)
    k = np.array([10.0] * 51 + [30.0] * 49)
    assert float(np.median(k)) == 10.0
    assert sweep.effective_cost_bp(h, k) == pytest.approx(19.8)
    # com pesos h, o custo que entra no R médio é Σ h·k / Σ h
    h2 = np.array([1.0, 3.0])
    assert sweep.effective_cost_bp(h2, np.array([10.0, 30.0])) == pytest.approx(25.0)
