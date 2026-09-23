"""R74 — valores conhecidos em series sinteticas, equivalencia com o R72 e a guarda de futuro.

Correr: `cd .claude/state/r74 && uv run pytest test_r74.py -p no:cacheprovider -q`
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

import pytest

import policies as PO  # noqa: F401  (poe o r72 no sys.path)
import test_r72 as base  # helper `_pos` do R72: marca proporcional ao multiplicador
from load import sell_net
from policies import EntryPop, FirstPop, LookAheadError, Target, View, run_exit
from sim import gross_sell, simulate_cheat, simulate_current

C = Decimal("0.0223")


def _net(mult):
    vsol = int(base.VSOL * mult)
    return int(Decimal(gross_sell(vsol, base.VTOK, base.LOT)) * (1 - C / 2))


def _walk(seed, step=0.05):
    rng = random.Random(seed)
    out, m = [(0, 1.0)], 1.0
    for sec in range(2, 302, 2):
        m *= 1 + rng.uniform(-step, step)
        out.append((sec, m))
    return out


def test_alvo_valores_conhecidos():
    P = base._pos([(0, 1.0), (10, 1.10), (20, 1.20), (40, 1.25), (300, 1.25)])
    r108 = run_exit(P, Target("1.08"))
    assert (r108["reason"], r108["final"]) == ("policy", _net(1.10))
    r115 = run_exit(P, Target("1.15"))
    assert (r115["reason"], r115["final"]) == ("policy", _net(1.20))
    assert r115["hold_s"] == pytest.approx(21.6)
    r150 = run_exit(P, Target("1.50"))
    assert r150["reason"] == "time_stop" and r150["hold_s"] == pytest.approx(301.6)


def test_primeiro_repique_so_depois_da_queda():
    # sobe 20 % sem queda: repique nao dispara; o alvo 1,15 dispara
    up = base._pos([(0, 1.0), (10, 1.2), (300, 1.2)])
    assert run_exit(up, FirstPop(5))["reason"] == "time_stop"
    # 1,00 -> 0,94 (queda de 6 %) -> 0,99 (+5,3 % do fundo): repique de 5 % dispara no 30 s
    P = base._pos([(0, 1.0), (10, 0.97), (20, 0.94), (30, 0.99), (300, 0.99)])
    r5 = run_exit(P, FirstPop(5))
    assert (r5["reason"], r5["final"]) == ("policy", _net(0.99))
    # a 8 % a queda de 6 % nem abre o mergulho
    assert run_exit(P, FirstPop(8))["reason"] == "time_stop"


def test_recuo_de_10_por_cento_continua_armado():
    P = base._pos([(0, 1.0), (10, 1.05), (20, 0.94), (300, 0.5)])
    for pol in (Target("1.30"), FirstPop(3), FirstPop(8)):
        r = run_exit(P, pol)
        assert r["reason"] == "trailing" and r["final"] == _net(0.94), pol.name
    # e desligado so quando pedido (diagnostico)
    assert run_exit(P, FirstPop(8), trailing=None)["reason"] == "time_stop"


def test_diagnostico_r72_e_marca_de_entrada_mais_x():
    P = base._pos([(0, 1.0), (10, 1.02), (20, 1.031), (300, 1.0)])
    r = run_exit(P, EntryPop(3))
    assert r["reason"] == "policy" and r["final"] == _net(1.031)


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("tx", ["1.08", "1.15", "1.30"])
def test_equivalente_ao_simulate_current_do_r72(seed, tx):
    P = base._pos(_walk(seed))
    for lat in (1.6, 5.0):
        mine = run_exit(P, Target(tx), latency_s=lat)
        ref = simulate_current(P, latency_s=lat, target_x=Decimal(tx))
        assert mine["final"] == ref["final"]


def test_na_mesa_valores_conhecidos():
    # sai no alvo aos 10 s a 1,16; aos 100 s a marca chega a 1,60; aos 290 s volta a 1,00
    P = base._pos([(0, 1.0), (10, 1.16), (100, 1.60), (290, 1.00)])
    r = run_exit(P, Target("1.15"))
    assert r["final"] == _net(1.16)
    assert r["left_max"] == _net(1.60) - _net(1.16)
    assert r["left_end"] == _net(1.00) - _net(1.16)
    # saida por tempo: nao ha futuro dentro da janela -> indisponivel (estrutural), nunca zero
    t = run_exit(P, Target("1.70"), trailing=None)
    assert t["reason"] == "time_stop" and t["left_max"] is None and t["left_end"] is None


def test_invariancia_ao_sufixo_futuro():
    """Trocar o futuro depois de K nao muda nenhuma saida cujo pouso cai antes de K."""
    rng = random.Random(74)
    checked = 0
    for seed in range(20):
        b = _walk(seed)
        for pol_f in (lambda: Target("1.08"), lambda: FirstPop(3), lambda: FirstPop(5)):
            ref = run_exit(base._pos(b), pol_f())
            for k in (20, 60, 100):
                cut = base.T0 + timedelta(seconds=b[k - 1][0])
                if base.T0 + timedelta(seconds=ref["hold_s"]) >= cut:
                    continue
                m, mut = b[k - 1][1], list(b[:k])
                for sec, _ in b[k:]:
                    m *= 1 + rng.uniform(-0.3, 0.3)
                    mut.append((sec, m))
                got = run_exit(base._pos(mut), pol_f())
                assert (got["final"], got["reason"], got["hold_s"]) == (
                    ref["final"], ref["reason"], ref["hold_s"])
                checked += 1
    assert checked >= 20, "o teste tem de exercer saidas antes do corte"


def test_view_recusa_o_futuro():
    v = View([(0,), (1,), (2,)])
    v.cursor = 1
    assert v[1] == (1,) and v[-1] == (1,)
    for bad in (2, slice(0, 3)):
        with pytest.raises(LookAheadError):
            v[bad]


class _Batoteiro:
    """Politica que espreita: vende se o PROXIMO ponto for pior que este."""

    name = "batoteiro"

    def reset(self, spent, mark0):
        pass

    def step(self, view, i):
        return "policy" if view[i + 1][3] < view[i][3] else None


def test_a_guarda_apanha_uma_politica_que_espreita():
    P = base._pos(_walk(3))
    with pytest.raises(LookAheadError):
        run_exit(P, _Batoteiro())


def test_braco_oraculo_ganha_e_e_o_controlo():
    P = base._pos([(0, 1.0), (30, 1.4), (60, 1.8), (90, 0.5), (150, 0.4), (290, 0.35)])
    cheat = simulate_cheat(P)["final"]
    # o oraculo e um teto: nenhuma politica causal o passa; o alvo 1,50 pode igualá-lo
    # (dispara no proprio pico), o 1,15 e o repique ficam estritamente abaixo
    for pol in (Target("1.15"), Target("1.50"), FirstPop(3)):
        assert cheat >= run_exit(P, pol)["final"]
    assert cheat > run_exit(P, Target("1.15"))["final"]
    assert cheat > run_exit(P, FirstPop(3))["final"]


def test_marca_da_serie_sintetica_e_proporcional():
    assert sell_net(int(base.VSOL * 1.15), base.VTOK, base.LOT) == pytest.approx(
        1.15 * sell_net(base.VSOL, base.VTOK, base.LOT), abs=1)


# ---------------- estatistica e regra congelada ----------------

T = ["1.08", "1.12", "1.15", "1.20", "1.30", "1.50"]
F = ["pop3", "pop5", "pop8"]


def _cells(ds, lo=None):
    return {n: dict(D=d, lo=(d - 0.03 if lo is None else lo.get(n, d - 0.03)), hi=d + 0.03)
            for n, d in ds.items()}


def test_boot_vetorizado_igual_ao_do_r72():
    import stats
    from run import boot_ci as boot72

    rng = random.Random(1)
    d = [rng.gauss(0.02, 0.2) for _ in range(300)]
    m = ["m%d" % (i // 2) for i in range(300)]  # clusters de 2
    a, b = stats.boot_ci(d, m), boot72(d, m)
    assert a[0] == pytest.approx(b[0], abs=0.006) and a[1] == pytest.approx(b[1], abs=0.006)
    assert stats.perm_p([0.1] * 30) < 0.001
    assert stats.perm_p([0.1, -0.1] * 15) > 0.9


def test_regra_confirma_no_interior_com_patamar():
    import stats

    ds = {"1.08": -0.02, "1.12": -0.01, "1.15": 0.0, "1.20": 0.06, "1.30": 0.04, "1.50": 0.01,
          "pop3": -0.01, "pop5": -0.02, "pop8": -0.03}
    base, lat5 = _cells(ds), _cells(ds)
    lab, why = stats.verdict(base, lat5, T, F, "1.15")
    assert lab == "CONFIRMA", why


def test_regra_refuta_quando_o_melhor_esta_na_borda():
    import stats

    ds = {"1.08": -0.02, "1.12": -0.01, "1.15": 0.0, "1.20": 0.03, "1.30": 0.06, "1.50": 0.09,
          "pop3": -0.01, "pop5": -0.02, "pop8": -0.03}
    assert stats.verdict(_cells(ds), _cells(ds), T, F, "1.15")[0] == "REFUTA"


def test_regra_refuta_se_o_ganho_morre_a_5s():
    import stats

    ds = {"1.08": -0.02, "1.12": -0.01, "1.15": 0.0, "1.20": 0.06, "1.30": 0.04, "1.50": 0.01,
          "pop3": -0.01, "pop5": -0.02, "pop8": -0.03}
    slow = dict(ds, **{"1.20": -0.001})
    assert stats.verdict(_cells(ds), _cells(slow), T, F, "1.15")[0] == "REFUTA"


def test_regra_nao_confirma_sem_patamar():
    import stats

    ds = {"1.08": -0.02, "1.12": -0.01, "1.15": 0.0, "1.20": 0.06, "1.30": -0.01, "1.50": -0.02,
          "pop3": -0.01, "pop5": -0.02, "pop8": -0.03}
    assert stats.verdict(_cells(ds), _cells(ds), T, F, "1.15")[0] == "NAO CONFIRMA"


def test_holm_e_wilson_valores_conhecidos():
    import stats

    h = stats.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert h == {"a": 0.03, "c": 0.06, "b": 0.06}
    lo, hi = stats.wilson(0, 76)
    assert lo == 0.0 and hi == pytest.approx(0.0481, abs=5e-4)


def test_permutacao_por_cluster_nao_infla_com_duplicados():
    import stats

    # 10 mints, cada um repetido 5 vezes: por cluster so ha 2^10 sinais possiveis
    d = [0.1 if i < 5 else -0.02 for i in range(10) for _ in range(5)]
    m = [i for i in range(10) for _ in range(5)]
    assert stats.perm_p(d, m) > stats.perm_p(d)


def test_queda_que_cruza_mergulho_e_recuo_sai_por_recuo():
    # 1,00 -> 0,88: abre o mergulho do repique de 8 % E dispara o recuo de 10 % no mesmo ponto
    P = base._pos([(0, 1.0), (10, 0.88), (20, 0.97), (300, 0.97)])
    r = run_exit(P, FirstPop(8))
    assert r["reason"] == "trailing" and r["final"] == _net(0.88)


def test_repique_depois_dos_300s_nao_conta_e_pouso_terminal_segue_a_latencia():
    P = base._pos([(0, 1.0), (100, 0.95), (299, 0.96), (302, 1.2), (304, 1.3)])
    r16 = run_exit(P, FirstPop(5))
    assert r16["reason"] == "time_stop" and r16["hold_s"] == pytest.approx(301.6)
    assert r16["final"] == _net(0.96)  # o estado dos 302 s ainda nao existe aos 301,6 s
    r5 = run_exit(P, FirstPop(5), latency_s=5.0)
    assert r5["hold_s"] == pytest.approx(305.0) and r5["final"] == _net(1.3)


def test_na_mesa_indisponivel_sem_observacao_depois_do_pouso():
    P = base._pos([(0, 1.0), (10, 1.2), (11, 1.2)])
    r = run_exit(P, Target("1.15"))
    assert r["reason"] == "policy" and r["left_max"] is None and r["left_end"] is None


def test_reset_so_recebe_o_instante_da_entrada():
    """Astra: com `P` no reset, uma politica lia `P["path"]` e contornava a View."""
    seen = []

    class Espiao:
        name = "espiao"

        def reset(self, *args):
            seen.extend(args)

        def step(self, view, i):
            return None

    run_exit(base._pos(_walk(1)), Espiao())
    assert len(seen) == 2 and all(type(a) is int for a in seen)


def test_empate_no_melhor_alvo_prefere_o_interior():
    import stats

    ds = {"1.08": 0.06, "1.12": 0.01, "1.15": 0.0, "1.20": 0.06, "1.30": 0.04,
          "pop3": -0.01, "pop5": -0.02, "pop8": -0.03}
    lab, why = stats.verdict(_cells(ds), _cells(ds), T[:-1], F, "1.15")
    assert not any("(b)" in w for w in why), why


def test_tempo_maximo_curto_corta_a_vitoria_tardia_e_mantem_a_populacao():
    # H-012: o alvo so chega aos 40 s; com max_hold 30 s sai por tempo aos 31,6 s a 1,05
    P = base._pos([(0, 1.0), (10, 1.05), (40, 1.2), (300, 1.2)])
    r = run_exit(P, Target("1.15"), seconds=30)
    assert r["reason"] == "time_stop" and r["hold_s"] == pytest.approx(31.6)
    assert r["final"] == _net(1.05)
    assert run_exit(P, Target("1.15"))["reason"] == "policy"
    # so 2 pontos dentro dos 30 s, mas 4 dentro dos 300 s: continua elegivel
    Q = base._pos([(0, 1.0), (10, 1.0), (100, 1.0), (200, 1.0)])
    assert run_exit(Q, Target("1.15"), seconds=30)["ok"]
