"""h036 — testes sintéticos do instrumento de custo (escritos antes de cost_instrument.py).

Rodar: uv run --no-sync pytest .claude/state/h036/test_cost_instrument.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "lab-cost-sweep"))

import cost_instrument as ci  # noqa: E402

pytestmark = pytest.mark.unit


def _leg(**kw: object) -> ci.Legs:
    base: dict[str, object] = {
        "open": 100.0, "base": 110.0, "risk": 5.0, "result": "stop", "exit_at_open": False,
        "exit_high": None, "target1": 110.0, "sp_in": 0.0004, "sp_out": 0.0006, "bid_in": 99.98,
        "entry_lows": (99.9, 99.95, 99.97),
    }
    base.update(kw)
    return ci.Legs(**base)  # type: ignore[arg-type]


def test_cost_in_r_uses_each_leg_on_its_own_price() -> None:
    # (0,0006·100 + 0,0002·110) / 5 = (0,06 + 0,022) / 5 = 0,0164 R
    assert ci.cost_r(open_=100.0, base=110.0, risk=5.0, c_in=0.0006, c_out=0.0002) == pytest.approx(0.0164)


def test_taker_leg_is_fee_plus_half_spread() -> None:
    legs = _leg(sp_in=0.0004, sp_out=0.0006)
    c_in, c_out = ci.taker_taker(legs, fee=0.0005)
    assert c_in == pytest.approx(0.0007)  # 5 + 4/2 bp
    assert c_out == pytest.approx(0.0008)  # 5 + 6/2 bp


def test_resting_target_is_maker_only_on_trade_through() -> None:
    through = _leg(result="target", exit_high=110.5, target1=110.0)
    touch = _leg(result="target", exit_high=110.0, target1=110.0)
    gap = _leg(result="target", exit_at_open=True, exit_high=None, target1=110.0)
    stop = _leg(result="stop")
    kw = {"taker": 0.0005, "maker": 0.0002}
    assert ci.taker_in_resting_tp(through, strict=True, **kw)[1] == pytest.approx(0.0002)
    assert ci.taker_in_resting_tp(touch, strict=False, **kw)[1] == pytest.approx(0.0002)
    assert ci.taker_in_resting_tp(touch, strict=True, **kw)[1] == pytest.approx(0.0008)  # toque sem atravessar: taker
    # abriu acima do alvo ORIGINAL: o Lab credita o alvo, mas sem a abertura não se sabe se passou do limite no grid
    # (Astra H-036 must-fix 5) — estrito cobra taker; o modo de toque aceita como maker
    assert ci.taker_in_resting_tp(gap, strict=True, **kw)[1] == pytest.approx(0.0008)
    assert ci.taker_in_resting_tp(gap, strict=False, **kw)[1] == pytest.approx(0.0002)
    assert ci.taker_in_resting_tp(stop, strict=True, **kw)[1] == pytest.approx(0.0008)
    assert ci.taker_in_resting_tp(stop, strict=True, **kw)[0] == pytest.approx(0.0007)


def test_passive_entry_fills_only_when_price_trades_below_the_bid() -> None:
    assert ci.passive_fill(bid=99.98, lows=(99.99, 99.97), minutes=1) is False
    assert ci.passive_fill(bid=99.98, lows=(99.99, 99.97), minutes=2) is True
    assert ci.passive_fill(bid=99.98, lows=(99.98,), minutes=1) is False  # tocar não basta (fila)
    assert ci.passive_fill(bid=99.98, lows=(None, 99.0), minutes=2) is None  # vela faltando: desconhecido


def test_passive_entry_cost_is_maker_fee_plus_price_vs_open() -> None:
    # comprar no bid 99,98 contra a abertura 100: (99,98 − 100)/100 = −2 bp de melhora; + 2 bp de taxa = 0
    assert ci.passive_entry_cost(bid=99.98, open_=100.0, maker=0.0002) == pytest.approx(0.0)


def test_spread_fallback_order() -> None:
    assert ci.pick_spread(0.0003, (0.0009,), market_median=0.0005, cohort_p90=0.002) == (0.0003, "minuto")
    assert ci.pick_spread(None, (None, 0.0009), market_median=0.0005, cohort_p90=0.002) == (0.0009, "vizinho")
    assert ci.pick_spread(None, (None,), market_median=0.0005, cohort_p90=0.002) == (0.0005, "mediana_mercado")
    assert ci.pick_spread(None, (), market_median=None, cohort_p90=0.002) == (0.002, "p90_coorte")


def test_effective_cost_matches_weighted_definition() -> None:
    # dois trades: h = (O+B)/U; k_i = 2·cost_r/h·1e4; efetivo = Σh·k/Σh = 2·Σcost_r/Σh·1e4
    h = np.array([40.0, 20.0])
    cr = np.array([0.04, 0.06])  # k = 20 bp e 60 bp
    k = 2 * cr / h * 1e4
    assert k == pytest.approx([20.0, 60.0])
    assert ci.effective_cost_bp(cr, h) == pytest.approx((40 * 20 + 20 * 60) / 60)


def test_net_r_at_measured_cost() -> None:
    g = np.array([0.5, -1.0])
    phi = np.array([0.01, 0.0])
    cr = np.array([0.05, 0.05])
    assert ci.net_r(g, phi, cr) == pytest.approx([0.44, -1.05])


def test_tick_is_finest_decimal_seen_and_limit_is_ceiled_to_it() -> None:
    assert ci.tick_of(("9.0580000000", "8.9510000000", "8.9500000000")) == pytest.approx(0.001)
    assert ci.tick_of(("0.0310400000", "0.0310500000")) == pytest.approx(0.00001)
    assert ci.limit_at_or_above(9.0563223459, 0.001) == pytest.approx(9.057)
    assert ci.limit_at_or_above(9.057, 0.001) == pytest.approx(9.057)  # já no grid: não sobe


def test_passive_scenario_counts_unfilled_signals_as_no_trade() -> None:
    # 3 sinais: 2 executados (R líquido 0,5 e −1,0), 1 não executado (0): média por sinal −0,1667
    r = ci.passive_signal_r(np.array([0.5, -1.0, 9.9]), np.array([True, True, False]))
    assert r == pytest.approx([0.5, -1.0, 0.0])
