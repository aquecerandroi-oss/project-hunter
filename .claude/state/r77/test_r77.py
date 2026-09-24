"""R77 / H-016 — testes do motor de entrada no recuo (valores conhecidos, séries sintéticas).

Corre com: cd .claude/state/r77 && uv run --project ../../.. pytest test_r77.py -p no:cacheprovider -q --rootdir=.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from chain import OUR, Pt, build_chain, max_gap, state_at
from entry import COST, Cheat, Dip, LookAheadError, find_trigger, simulate_arm

T0 = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)
SOL = 10**9
TOK = 10**6


def at(s: float) -> datetime:
    return T0 + timedelta(seconds=s)


def pts_from_prices(prices, start=-5.0, step=1.0, vtok=1_000_000_000 * TOK, kinds=None, slots=None):
    """Pontos com preço dado (lamports por token*1e6, via vsol = preço * vtok)."""
    out = []
    for k, p in enumerate(prices):
        vsol = int(p * vtok)
        out.append(Pt(at(start + k * step), vsol, vtok, (kinds or {}).get(k, "trade"),
                      (slots or {}).get(k, 1000 + k), True))
    # recomputa last_in_slot
    fixed = []
    for k, q in enumerate(out):
        last = k + 1 >= len(out) or out[k + 1].slot != q.slot
        fixed.append(q._replace(last_in_slot=last))
    return fixed


# ------------------------------------------------------------------------ cadeia


def _tr(s, slot, side, sol, tok, trader="x", sig="a", ei=0):
    return dict(bt=at(s), slot=slot, sig=sig, ei=ei, trader=trader, side=side, sol=sol, tok=tok)


def test_chain_removes_our_trades_and_corrects_photos():
    photos = [dict(t=at(-10), slot=100, vsol=40 * SOL, vtok=800_000_000 * TOK)]
    trades = [
        _tr(1, 101, "buy", 1 * SOL, 10_000_000 * TOK),
        _tr(2, 102, "buy", 7 * SOL // 100, 700_000 * TOK, trader=OUR),
    ]
    # a foto no slot 103 inclui a troca alheia E a nossa compra
    photos.append(dict(t=at(3), slot=103, vsol=41 * SOL + 7 * SOL // 100,
                       vtok=800_000_000 * TOK - 10_000_000 * TOK - 700_000 * TOK))
    pts, info = build_chain(T0, trades, photos)
    assert info["anchor_slot"] == 100
    assert [p.kind for p in pts] == ["anchor", "trade", "photo"]
    # a troca alheia foi aplicada; a nossa não
    assert pts[1].vsol == 41 * SOL and pts[1].vtok == 790_000_000 * TOK
    # a foto foi descontada da nossa compra -> igual à cadeia sem nós
    assert pts[2].vsol == 41 * SOL and pts[2].vtok == 790_000_000 * TOK
    assert info["resync_max_sol"] == 0.0
    assert info["our_trades"] == 1


def test_chain_needs_anchor_before_t0():
    photos = [dict(t=at(1), slot=100, vsol=40 * SOL, vtok=800_000_000 * TOK)]
    pts, info = build_chain(T0, [], photos)
    assert pts is None and info["censor"] == "sem_ancora"


def test_state_at_and_gap():
    pts = pts_from_prices([1.0, 1.0, 1.0], start=-10, step=5)  # t = -10, -5, 0
    assert state_at(pts, at(1.6)) == 2
    assert state_at(pts, at(-6)) == 0
    pts = pts_from_prices([1.0, 1.0, 1.0, 1.0], start=-1, step=20)  # -1, 19, 39, 59
    # buracos a partir de t0: 0->19, 19->39, 39->59, cauda 59->100
    assert max_gap(pts, T0, 100) == pytest.approx(41.0)


# ---------------------------------------------------------------- regra de entrada


def test_dip_uses_running_max_not_t0_price():
    # t0 preço 100 (ponto em -1 s), sobe a 110, cai a 106,6 (<= 110*0,97 = 106,7)
    pts = pts_from_prices([100, 100, 105, 110, 108, 106.6, 90], start=-1)
    k = find_trigger(pts, T0, Dip(3), 20)
    assert pts[k].vsol == int(106.6 * pts[k].vtok)
    assert find_trigger(pts, T0, Dip(5), 20) == 6  # só o 90 fica abaixo de 110*0,95
    assert find_trigger(pts, T0, Dip(20), 20) is None


def test_dip_initial_max_is_state_at_t0():
    pts = pts_from_prices([100, 97], start=-0.5)  # -0,5 s e +0,5 s: cai 3 % logo a seguir a t0
    assert find_trigger(pts, T0, Dip(3), 20) == 1


def test_window_limits_trigger():
    prices = [100] * 23 + [90]  # t = -1 .. 22; o recuo cai aos 22 s
    pts = pts_from_prices(prices, start=-1)
    assert find_trigger(pts, T0, Dip(3), 20) is None
    assert find_trigger(pts, T0, Dip(3), 60) == 23


def test_photos_do_not_trigger_or_set_max_in_main_line():
    pts = pts_from_prices([100, 120, 115, 113], start=-0.5, kinds={1: "photo"})
    # linha principal: o 120 é foto, não cria máxima; 115 vira máxima e 113 > 115*0,97
    assert find_trigger(pts, T0, Dip(3), 20) is None
    # sensibilidade: a foto conta -> 115 <= 120*0,97 = 116,4 dispara
    assert find_trigger(pts, T0, Dip(3, use_photos=True), 20) == 2


def test_slot_final_variant_ignores_intraslot_dip():
    # slot 2000: 110 depois 105 (intra-slot), estado final do slot 106,8
    pts = pts_from_prices([100, 110, 105, 106.8], start=-1, slots={1: 2000, 2: 2000, 3: 2000})
    assert find_trigger(pts, T0, Dip(3), 20) == 2
    assert find_trigger(pts, T0, Dip(3, slot_final=True), 20) is None


# ------------------------------------------------------------ anti-antecipação


def test_cheat_policy_is_caught():
    pts = pts_from_prices([100, 104, 99, 95, 97], start=-1)
    with pytest.raises(LookAheadError):
        find_trigger(pts, T0, Cheat(), 20)


@pytest.mark.parametrize("seed", range(20))
def test_trigger_does_not_change_when_future_changes(seed):
    rnd = random.Random(seed)
    prices = [100.0]
    for _ in range(80):
        prices.append(max(1.0, prices[-1] * (1 + rnd.uniform(-0.04, 0.04))))
    pts = pts_from_prices(prices, start=-1)
    for x, w in ((3, 20), (5, 60), (8, 60), (12, 20)):
        k = find_trigger(pts, T0, Dip(x), w)
        cut = k if k is not None else next(i for i, p in enumerate(pts) if p.t > at(w)) - 1
        fut = [p._replace(vsol=int(p.vsol * rnd.uniform(0.3, 3.0))) for p in pts[cut + 1:]]
        assert find_trigger(pts[: cut + 1] + fut, T0, Dip(x), w) == k


# ------------------------------------------------------------------ pouso e saída


def test_control_fills_at_state_known_at_landing_not_older_point():
    # último ponto antes de t0 em -10 s (preço 100); ponto em +1 s (preço 120)
    pts = pts_from_prices([100, 100, 120], start=-11, step=1)  # -11, -10, -9
    pts = [pts[0], pts[1], pts[2]._replace(t=at(1))]
    a = simulate_arm(pts, T0, 7 * SOL // 100, 1.6)
    assert a["fill_index"] == 2
    pts2 = [pts[0], pts[1], pts[2]._replace(t=at(3))]
    assert simulate_arm(pts2, T0, 7 * SOL // 100, 1.6)["fill_index"] == 1


def test_arm_target_exit_known_value():
    # preço sobe 30 % aos 10 s -> alvo 1,15x; retorno positivo e motivo "target"
    prices = [1.0] * 6 + [1.3] * 10
    pts = pts_from_prices(prices, start=-1, step=2.0, vtok=1_000_000_000 * TOK)
    a = simulate_arm(pts, T0, 7 * SOL // 100, 1.6)
    assert a["reason"] == "target"
    # compra no preço 1,0 com S*(1-c/2) de curva; venda a 1,3 com (1-c/2): ~ 1,3*(1-c/2)^2 - 1
    assert a["ret"] == pytest.approx(1.3 * (1 - float(COST) / 2) ** 2 - 1, abs=0.01)
    assert a["peak_le_cost"] is False


def test_arm_never_above_cost_flag():
    prices = [1.0] * 4 + [0.85] * 10  # só cai
    pts = pts_from_prices(prices, start=-1, step=2.0)
    a = simulate_arm(pts, T0, 7 * SOL // 100, 1.6)
    assert a["reason"] == "trailing" and a["ret"] < 0 and a["peak_le_cost"] is True


def test_arm_path_starts_at_landing_with_our_buy():
    pts = pts_from_prices([1.0] * 20, start=-1, step=2.0)
    a = simulate_arm(pts, T0, 7 * SOL // 100, 1.6)
    P = a["P"]
    assert P["entry_bt"] == at(1.6)
    assert P["path"][0][0] == at(1.6)
    assert all(p[0] > at(1.6) for p in P["path"][1:])
    spend = int(7 * SOL // 100 * (1 - COST / 2))
    assert P["path"][0][1] == pts[1].vsol + spend


# ------------------------------------------------------------------ estatística e regra


def test_mill_stacked_pairs_equal_mean_paired_difference():
    from rule import mill_paired
    rnd = random.Random(7)
    ctrl = [rnd.gauss(-0.03, 0.2) for _ in range(60)]
    pol = [c + 0.04 + rnd.gauss(0, 0.05) for c in ctrl]
    mints = [f"m{i}" for i in range(60)]
    out = mill_paired(pol, ctrl, mints, "teste", reps=2000)
    assert out["D"] == pytest.approx(sum(p - c for p, c in zip(pol, ctrl, strict=True)) / 60, abs=1e-12)
    assert out["lo"] > 0 and out["p"] < 0.01
    assert out["n"] == 60


def _cells(d, lo, lvl, d5):
    names = [(x, w) for w in (20, 60) for x in (3, 5, 8, 12)]
    return {n: dict(D=d.get(n, 0.0), lo=lo.get(n, -1.0), level=lvl.get(n, -0.01), D5=d5.get(n, 0.0))
            for n in names}


def test_rule_confirms_interior_plateau():
    from rule import decide
    c = _cells({(5, 60): 0.08, (8, 60): 0.03}, {(5, 60): 0.02}, {(5, 60): 0.01}, {(5, 60): 0.05})
    label, why = decide(c, frac_falls=True)
    assert label == "CONFIRMA", why


def test_rule_refutes_edge_best():
    from rule import decide
    c = _cells({(3, 60): 0.08, (5, 60): 0.03}, {(3, 60): 0.02}, {(3, 60): 0.01}, {(3, 60): 0.05})
    label, why = decide(c, frac_falls=True)
    assert label == "REFUTA" and any("(b)" in w for w in why)


def test_rule_refutes_when_gain_is_only_not_entering():
    from rule import decide
    c = _cells({(5, 60): 0.08, (8, 60): 0.03}, {(5, 60): 0.02}, {(5, 60): -0.001}, {(5, 60): 0.05})
    label, why = decide(c, frac_falls=True)
    assert label == "REFUTA" and any("(d)" in w for w in why)


def test_rule_refutes_when_gain_dies_at_5s():
    from rule import decide
    c = _cells({(5, 60): 0.08, (8, 60): 0.03}, {(5, 60): 0.02}, {(5, 60): 0.01}, {(5, 60): 0.0})
    label, why = decide(c, frac_falls=True)
    assert label == "REFUTA" and any("(c)" in w for w in why)


def test_rule_refutes_a_and_not_confirm_without_plateau():
    from rule import decide
    c = _cells({(5, 60): 0.08}, {(5, 60): 0.005}, {(5, 60): 0.01}, {(5, 60): 0.05})
    label, why = decide(c, frac_falls=True)
    assert label == "REFUTA" and any("(a)" in w for w in why)
    c = _cells({(5, 60): 0.08, (3, 60): -0.01, (8, 60): -0.01}, {(5, 60): 0.02},
               {(5, 60): 0.01}, {(5, 60): 0.05})
    label, why = decide(c, frac_falls=True)
    assert label == "NÃO CONFIRMA"


def test_rule_real_needs_fraction_to_fall():
    from rule import decide
    c = _cells({(5, 60): 0.08, (8, 60): 0.03}, {(5, 60): 0.02}, {(5, 60): 0.01}, {(5, 60): 0.05})
    assert decide(c, frac_falls=False)[0] == "NÃO CONFIRMA"


def test_hypothesis_label():
    from rule import combine
    assert combine("CONFIRMA", "CONFIRMA") == "CONFIRMA"
    assert combine("REFUTA", "REFUTA") == "REFUTA"
    assert combine("REFUTA", "NÃO CONFIRMA") == "NÃO CONFIRMA"


def test_own_fill_injection_does_not_duplicate():
    from sim_all import with_own
    tape = [_tr(1, 101, "buy", 5, 5, trader=OUR, sig="s1"), _tr(1, 101, "buy", 5, 5, sig="s2")]
    own = [_tr(1, 101, "buy", 5, 5, trader=OUR, sig="s1"), _tr(9, 150, "sell", 5, 5, trader=OUR, sig="s3")]
    out, n = with_own(tape, own)
    assert n == 1 and [t["sig"] for t in out] == ["s1", "s2", "s3"]


def test_injected_own_buy_is_removed_from_photo():
    # a nossa compra não está na fita, mas a foto a inclui: sem injeção a cadeia herdaria a compra
    photos = [dict(t=at(-10), slot=100, vsol=40 * SOL, vtok=800_000_000 * TOK),
              dict(t=at(3), slot=103, vsol=40 * SOL + 7 * SOL // 100, vtok=800_000_000 * TOK - 700_000 * TOK)]
    ours = [_tr(2, 102, "buy", 7 * SOL // 100, 700_000 * TOK, trader=OUR, sig="ours")]
    pts_bad, _ = build_chain(T0, [], photos)
    pts_ok, _ = build_chain(T0, ours, photos)
    assert pts_bad[-1].vsol == 40 * SOL + 7 * SOL // 100
    assert pts_ok[-1].vsol == 40 * SOL and pts_ok[-1].vtok == 800_000_000 * TOK


# --------------------------------------------------- anti-antecipação nas cadeias reais


def _real_chains(limit=120):
    import csv as _csv
    from pathlib import Path as _P

    from chain import load_photos, load_tape, ts
    from sim_all import first_per_mint, own_fills, with_own
    here = _P(__file__).resolve().parent
    if not (here / "cache" / "tape.csv.gz").exists():
        pytest.skip("cache da fita ausente (export do R77 não está nesta máquina)")
    with (here / "pop.csv").open(encoding="utf-8", newline="") as f:
        rows = first_per_mint(list(_csv.DictReader(f)))
    tapes, photos, own = load_tape(), load_photos(), own_fills()
    out = []
    for r in rows[:: max(1, len(rows) // limit)]:
        t0 = ts(r["proposed_at"])
        tape, _ = with_own(tapes.get((r["pop"], r["mint"]), []), own.get(r["mint"], []))
        pts, info = build_chain(t0, tape, photos.get((r["pop"], r["mint"]), []))
        if pts is not None and not info["censor"]:
            out.append((t0, pts))
    return out


def test_real_chains_trigger_invariant_to_future_and_cheat_caught():
    rnd = random.Random(77)
    chains = _real_chains()
    assert len(chains) > 50
    checked = 0
    for t0, pts in chains:
        with pytest.raises(LookAheadError):
            find_trigger(pts, t0, Cheat(), 60)
        for x, w in ((3, 20), (5, 60), (12, 60)):
            k = find_trigger(pts, t0, Dip(x), w)
            ends = [i for i, p in enumerate(pts) if p.t <= t0 + timedelta(seconds=w)]
            cut = k if k is not None else ends[-1]
            fut = [p._replace(vsol=max(1, int(p.vsol * rnd.uniform(0.2, 5.0)))) for p in pts[cut + 1:]]
            assert find_trigger(pts[: cut + 1] + fut, t0, Dip(x), w) == k
            checked += 1
    assert checked >= 150


def test_oracle_entry_beats_causal_entry_on_real_chains():
    """Distância que a guarda protege: comprar no mínimo da janela (olhando o futuro) ganha muito mais."""
    chains = _real_chains()
    size = 7 * SOL // 100
    causal, oracle = [], []
    for t0, pts in chains:
        k = find_trigger(pts, t0, Dip(3), 60)
        a = simulate_arm(pts, pts[k].t if k is not None else t0, size, 1.6, min_index=k or 0)
        win = [i for i, p in enumerate(pts) if t0 < p.t <= t0 + timedelta(seconds=60)] or [state_at(pts, t0)]
        m = min(win, key=lambda i: pts[i].vsol / pts[i].vtok)
        o = simulate_arm(pts, pts[m].t - timedelta(seconds=1.6), size, 1.6)
        if a["ok"] and o["ok"]:
            causal.append(a["ret"] if k is not None else 0.0)
            oracle.append(o["ret"])
    assert len(oracle) > 50
    assert sum(oracle) / len(oracle) > sum(causal) / len(causal) + 0.02


def test_slot_final_uses_last_trade_even_when_a_photo_closes_the_slot():
    """Achado da Astra (ronda 2): trade a 96 e foto a 96 no mesmo slot — a foto escondia o slot inteiro."""
    photos = [dict(t=at(-1), slot=100, vsol=100 * SOL, vtok=1_000_000_000 * TOK),
              dict(t=at(2), slot=101, vsol=96 * SOL, vtok=1_000_000_000 * TOK)]
    trades = [_tr(2, 101, "sell", 4 * SOL, 0)]
    pts, _ = build_chain(T0, trades, photos)
    assert [p.kind for p in pts] == ["anchor", "trade", "photo"]
    assert find_trigger(pts, T0, Dip(3), 20) == 1
    assert find_trigger(pts, T0, Dip(3, slot_final=True), 20) == 1
