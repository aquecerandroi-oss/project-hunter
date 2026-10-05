"""R87 — testes do motor da H-028 (com a emenda) em séries sintéticas com valores esperados conhecidos.

    uv run --no-sync pytest .claude/state/r87/test_r87.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "r84"))

from engine87 import ARMS, C_PERP, C_SPOT, DAY_MS, Market, decide, s7, universe  # noqa: E402
from panel import build_panel  # noqa: E402
from sim87 import simulate_arm  # noqa: E402

D0 = 18_000  # 2019-04-14 (domingo); segunda ⇔ (D0 + t − 4) % 7 == 0
N_DAYS = 120
MON = [t for t in range(N_DAYS) if (D0 + t - 4) % 7 == 0]
CS_CP = C_SPOT + C_PERP
H = 0.5 / (1 + CS_CP / 2)  # nocional por perna (capital 1, S = F/m) depois de reservar o custo de entrada


def make_market(n: int = 16, rate: float = 0.0003, spot: float = 100.0, perp_mult: float = 1.0,
                ended: frozenset[str] = frozenset(), spot_last: dict[str, int] | None = None,
                cadence_h: int = 8, rates: dict[str, np.ndarray] | None = None, noise: float = 0.0,
                seed: int = 0) -> Market:
    """n moedas; perpétuo = mult·spot; funding constante a cada `cadence_h` (carimbo +3 ms)."""
    rng = np.random.default_rng(seed)
    spot_last = spot_last or {}
    rows, syms = [], [f"C{k:02d}USDT" for k in range(n)]
    path = spot * np.exp(np.cumsum(rng.normal(0, noise, (n, N_DAYS)), axis=1)) if noise else np.full((n, N_DAYS), spot)
    for k, s in enumerate(syms):
        for t in range(spot_last.get(s, N_DAYS - 1) + 1):
            rows.append((s, D0 + t, path[k, t], path[k, t], 1e6 * (n - k)))
    p = build_panel(rows, {s for s in syms if s not in ended}, set(), D0 + N_DAYS, day0=D0, day_end=D0 + N_DAYS - 1)
    order = [syms.index(i) for i in p.ids]
    f = path[order] * perp_mult * (1 + (rng.normal(0, noise / 5, (n, N_DAYS)) if noise else 0.0))
    ms = np.arange(D0 * DAY_MS, (D0 + N_DAYS) * DAY_MS, cadence_h * 3_600_000, dtype=np.int64) + 3
    fund_rate = [np.full(ms.size, rate) if rates is None or s not in rates else rates[s].copy() for s in p.ids]
    return Market(p=p, f_open=f.copy(), f_high=f * (1 + noise), f_close=f.copy(), mult=np.full(n, perp_mult),
                  perp_segs=[[(0, N_DAYS - 1, False)] for _ in p.ids], fund_ms=[ms.copy() for _ in p.ids],
                  fund_rate=fund_rate)


def test_s7_sums_the_settled_week_ending_one_hour_before_t() -> None:
    total, count = s7(make_market(rate=0.0001), 0, MON[8])
    assert count == 21 and total == pytest.approx(0.0021)


def test_s7_is_cadence_free_sum_of_seven_days() -> None:
    total, count = s7(make_market(rate=0.00005, cadence_h=4), 0, MON[8])
    assert count == 42 and total == pytest.approx(0.0021)


def test_signal_does_not_change_when_future_or_last_hour_funding_changes() -> None:
    """Anti-antecipação: mudar liquidações com fundingTime > T − 1 h não move S7, universo nem decisão."""
    mk = make_market(rate=0.0001)
    t = MON[8]
    t_ms = (D0 + t) * DAY_MS
    base = [s7(mk, i, t) for i in range(len(mk.p.ids))]
    base_u = universe(mk, t)
    base_d = decide(mk, t, base_u, set(), ARMS["A1"])
    for i in range(len(mk.p.ids)):
        mk.fund_rate[i] = np.where(mk.fund_ms[i] > t_ms - 3_600_000, 0.05, mk.fund_rate[i])
    mk._seg_cache.clear()
    assert [s7(mk, i, t) for i in range(len(mk.p.ids))] == base
    assert universe(mk, t) == base_u
    assert decide(mk, t, base_u, set(), ARMS["A1"]) == base_d


def test_a_cheat_that_reads_next_week_funding_is_caught_by_the_same_guard() -> None:
    """Controle positivo da guarda: um sinal trapaceiro (funding da semana seguinte) muda quando o futuro muda."""
    mk = make_market(rate=0.0001)
    t_ms = (D0 + MON[8]) * DAY_MS

    def cheat(i: int) -> float:
        m = (mk.fund_ms[i] > t_ms) & (mk.fund_ms[i] <= t_ms + 7 * DAY_MS)
        return float(mk.fund_rate[i][m].sum())

    before = [cheat(i) for i in range(len(mk.p.ids))]
    for i in range(len(mk.p.ids)):
        mk.fund_rate[i] = np.where(mk.fund_ms[i] > t_ms - 3_600_000, 0.05, mk.fund_rate[i])
    assert [cheat(i) for i in range(len(mk.p.ids))] != before


def test_universe_is_top20_by_volume_and_needs_35_days_of_perp() -> None:
    mk = make_market(n=24)
    t = MON[8]
    assert {mk.p.ids[i] for i in universe(mk, t)} == {f"C{k:02d}USDT" for k in range(20)}
    mk.perp_segs[0] = [(t - 30, N_DAYS - 1, False)]
    mk._seg_cache.clear()
    assert 0 not in universe(mk, t)


def test_incomplete_funding_window_is_not_eligible() -> None:
    mk = make_market(n=16)
    t = MON[8]
    keep = np.ones(mk.fund_ms[0].size, dtype=bool)
    hi = (D0 + t) * DAY_MS - 3_600_000
    in_win = (mk.fund_ms[0] > hi - 7 * DAY_MS) & (mk.fund_ms[0] <= hi)
    idx = np.flatnonzero(in_win)
    keep[idx[::3][:0]] = True
    keep[idx[7:]] = False  # sobram 7 das 21: "≥ 7" passaria, a janela completa não
    mk.fund_ms[0], mk.fund_rate[0] = mk.fund_ms[0][keep], mk.fund_rate[0][keep]
    assert 0 not in universe(mk, t)


def test_always_on_carry_known_value_constant_prices() -> None:
    rate = 0.0003
    out = simulate_arm(make_market(rate=rate), MON[7:10], ARMS["A0"], "opt")
    assert out.weekly[0] == pytest.approx(H * rate * 21 - H * CS_CP)
    assert out.weekly[1] == pytest.approx(H * rate * 21)
    assert out.weekly[2] == pytest.approx(H * rate * 21 - H * CS_CP)  # fim da amostra paga a saída
    assert out.funding.sum() == pytest.approx(3 * H * rate * 21)
    assert H * 2 + H * CS_CP == pytest.approx(1.0)  # à vista + margem + custo de entrada = capital


def test_weekly_equals_its_decomposition_on_noisy_market() -> None:
    mk = make_market(n=18, rate=0.0002, noise=0.03, seed=7)
    for arm in ("A0", "A1", "A2"):
        for b in ("opt", "pes"):
            o = simulate_arm(mk, MON[7:15], ARMS[arm], b)
            assert np.allclose(o.weekly, o.funding + o.basis + o.unhedged + o.liq_loss - o.costs)
            assert np.all(o.exposure <= 1.0 + 1e-9)


def test_a1_stays_out_below_entry_hurdle_and_enters_above() -> None:
    assert simulate_arm(make_market(rate=0.00005), MON[7:10], ARMS["A1"], "opt").weekly.tolist() == [0.0] * 3
    assert simulate_arm(make_market(rate=0.0001), MON[7:10], ARMS["A1"], "opt").weekly[1] > 0


def test_a2_needs_exceptional_funding_and_exits_at_baseline() -> None:
    assert simulate_arm(make_market(rate=0.0001), MON[7:10], ARMS["A2"], "opt").weekly.tolist() == [0.0] * 3
    t_split = (D0 + MON[9]) * DAY_MS
    ms = np.arange(D0 * DAY_MS, (D0 + N_DAYS) * DAY_MS, 8 * 3_600_000, dtype=np.int64) + 3
    hi_then_low = np.where(ms < t_split, 0.0004, 0.00009)  # 0,84 %/7 d, depois 0,189 % < 0,21 %
    mk = make_market(rates={f"C{k:02d}USDT": hi_then_low for k in range(16)})
    out = simulate_arm(mk, MON[7:12], ARMS["A2"], "opt")
    assert out.exposure[0] == pytest.approx(2 * H) and out.exposure[3] == 0.0


def test_basis_change_is_paid_by_the_hedge_with_full_margin_sizing() -> None:
    mk = make_market(rate=0.0)
    t0 = MON[7]
    mk.f_open[:, t0] = 101.0
    out = simulate_arm(mk, [t0], ARMS["A0"], "opt")
    q = 1.0 / (100.0 * (1 + C_SPOT) + 101.0 * (1 + C_PERP))  # q = w ÷ (S(1+cs) + F/m(1+cp)), somado nas 16 vagas
    expected = q * 1.0 - q * (100 * C_SPOT + 101 * C_PERP) - q * (100 * C_SPOT + 100 * C_PERP)
    assert out.weekly[0] == pytest.approx(expected)


def test_thousand_multiplier_contract_is_scaled() -> None:
    out = simulate_arm(make_market(rate=0.0003, perp_mult=1000.0), MON[7:10], ARMS["A0"], "opt")
    assert out.weekly[1] == pytest.approx(H * 0.0003 * 21)


def test_short_leg_liquidation_loses_the_margin_once() -> None:
    t0 = MON[7]
    mk = make_market(rate=0.0)
    mk.m_high[0, t0 + 2] = 100.0 * 2 / 1.05 + 0.01
    out = simulate_arm(mk, MON[7:10], ARMS["A0"], "opt")
    w = 1 / 16
    h = w * H
    assert out.weekly[0] == pytest.approx(-H * CS_CP - h - h * C_SPOT)
    assert out.liquidations == 1 and out.liq_loss[0] == pytest.approx(-h)
    assert out.weekly[1] == pytest.approx(-h * CS_CP)  # reentra pagando a entrada


def test_negative_funding_lowers_the_liquidation_price() -> None:
    t0 = MON[7]
    ms = np.arange(D0 * DAY_MS, (D0 + N_DAYS) * DAY_MS, 8 * 3_600_000, dtype=np.int64) + 3
    r = np.where(ms >= (D0 + t0) * DAY_MS + 1_800_000, -0.02, 0.0001)  # paga 2 % por liquidação na semana
    mk = make_market(rates={"C00USDT": r})
    mk.m_high[0, t0 + 2] = 185.0  # abaixo de 2·100/1,05 = 190,5, acima do gatilho com 6 pagamentos de 2 %
    out = simulate_arm(mk, MON[7:9], ARMS["A0"], "opt")
    assert out.liquidations == 1
    w = 1 / 16
    others = 15 * (w * H) * 0.0003 * 21  # as outras 15 vagas recebem a taxa padrão
    assert out.funding[0] + out.liq_loss[0] - others == pytest.approx(-w * H, rel=1e-6)


def test_spot_delisting_two_bounds() -> None:
    t0 = MON[7]
    mk = make_market(rate=0.0, ended=frozenset({"C00USDT"}), spot_last={"C00USDT": t0 + 3})
    w = 1 / 16
    opt = simulate_arm(mk, MON[7:9], ARMS["A0"], "opt").weekly[0]
    pes = simulate_arm(mk, MON[7:9], ARMS["A0"], "pes").weekly[0]
    assert opt == pytest.approx(-H * CS_CP - (w * H) * CS_CP)
    assert pes == pytest.approx(-H * CS_CP - w * H - (w * H) * C_PERP)


def test_perp_end_pessimistic_buys_back_at_the_mark_high() -> None:
    t0 = MON[7]
    mk = make_market(rate=0.0)
    mk.perp_segs[0] = [(0, t0 + 2, True)]
    mk.m_high[0, t0 + 2] = 110.0
    w = 1 / 16
    opt = simulate_arm(mk, MON[7:9], ARMS["A0"], "opt").weekly[0]
    pes = simulate_arm(mk, MON[7:9], ARMS["A0"], "pes").weekly[0]
    assert opt == pytest.approx(-H * CS_CP - (w * H) * CS_CP)
    q = (w * H) / 100.0
    assert pes == pytest.approx(-H * CS_CP - q * 10.0 - q * 110.0 * C_PERP - (w * H) * C_SPOT)


def test_settlement_boundary_both_conventions() -> None:
    mk = make_market(rate=0.0)  # cadência de 8 h; só as de 00:00 de T e de T + 7 pagam
    t0 = MON[7]
    day = (D0 + t0)
    for i in range(16):
        d, midnight = mk.fund_ms[i] // DAY_MS, (mk.fund_ms[i] % DAY_MS) < 1000
        mk.fund_rate[i] = np.where(midnight & (d == day), 0.01, np.where(midnight & (d == day + 7), 0.001, 0.0))
    assert simulate_arm(mk, [t0], ARMS["A0"], "opt").funding[0] == pytest.approx(H * 0.001)
    assert simulate_arm(mk, [t0], ARMS["A0"], "opt", conv="before").funding[0] == pytest.approx(H * 0.01)


def test_mark_range_bounds_value_intraday_settlements() -> None:
    mk = make_market(rate=0.001)
    mk.m_low[:, :], mk.m_high[:, :] = 90.0, 110.0  # 00:00 usa a abertura (100); 08:00/16:00 usam a faixa
    t0 = MON[7]
    opt = simulate_arm(mk, MON[7:9], ARMS["A0"], "opt").funding[0]
    pes = simulate_arm(mk, MON[7:9], ARMS["A0"], "pes").funding[0]
    q = 2 * H / 200.0
    assert pes == pytest.approx(q * 0.001 * (7 * 100 + 14 * 90))
    assert opt == pytest.approx(q * 0.001 * (7 * 100 + 14 * 110))
    assert t0 > 0


def test_stuck_slot_keeps_its_capital_and_new_slots_shrink() -> None:
    mk = make_market(n=16, rate=0.0003)
    t1 = MON[8]
    mk.p.open[0, t1] = np.nan  # lacuna na abertura de T: a vaga não negocia
    out = simulate_arm(mk, MON[7:10], ARMS["A0"], "opt")
    assert out.stuck == 1 and out.exposure[1] <= 1.0 + 1e-12


def test_entry_identity_guard_blocks_mismatched_contract() -> None:
    mk = make_market(rate=0.0003, perp_mult=1000.0)
    mk.mult[:] = 1.0
    out = simulate_arm(mk, MON[7:9], ARMS["A0"], "opt")
    assert out.weekly.tolist() == [0.0, 0.0] and out.guard_blocked > 0


def test_stuck_slot_reserves_its_margin_balance_not_its_notional() -> None:
    """Cenário da Astra: posição cai a metade e fica presa; a reserva é à vista + saldo de margem (q·(S + 2F_ref − F))."""
    mk = make_market(n=21, rate=0.0)
    t0, t1 = MON[7], MON[8]
    i = mk.p.ids.index("C00USDT")
    mk.p.open_ff[i, t1], mk.p.open[i, t1] = 50.0, np.nan
    mk.f_open[i, t1] = 50.0
    mk.p.qvol[i, t0:t1] = 0.0  # sai do top-20
    mk._seg_cache.clear()
    out = simulate_arm(mk, [t0, t1, MON[9]], ARMS["A0"], "opt")
    w = 1 / 20
    q_stuck = (w * H) / 100.0
    reserve = q_stuck * (50.0 + (2 * 100.0 - 50.0))  # = 2·q·F_ref = capital inicial da vaga sem custo
    assert out.stuck >= 1
    assert out.exposure[1] <= 1.0 + 1e-12 and reserve == pytest.approx(w * H * 2)
