"""R72 — testes de anti-antecipacao e de valores conhecidos, em series sinteticas.

O teste que interessa e o de **invariancia ao sufixo futuro** (pedido da Astra na revisao
previa): se eu trocar tudo o que acontece DEPOIS do instante t, nenhuma decisao tomada ate t
pode mudar. E essa a armadilha que matou a primeira versao do R66.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from load import sell_net
from sim import LookAheadError, simulate_cheat, simulate_current, simulate_scalp
from swings import count_swings, swing_events

T0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
VSOL = 60_000_000_000
VTOK = 400_000_000_000_000
LOT = 400_000_000_000  # ~0,06 SOL de tokens numa curva de 60 SOL


def _pos(marks_by_second):
    """Constroi uma posicao sintetica cuja marca segue `marks_by_second` (multiplicadores).

    As reservas sao movidas so no lado SOL, o que muda a marca quase proporcionalmente; o
    caminho fica com um ponto por entrada da lista.
    """
    path = []
    for sec, mult in marks_by_second:
        vsol = int(VSOL * mult)
        path.append((T0 + timedelta(seconds=sec), vsol, VTOK, sell_net(vsol, VTOK, LOT)))
    return dict(pop="synt", mint="M", sym="M", entry_bt=T0, tokens=LOT,
                spent=sell_net(VSOL, VTOK, LOT), path=path, source="tape+photos",
                target_x=Decimal("1.15"), trailing=Decimal("0.10"), max_hold=300)


def test_swing_conhecido_uma_oscilacao():
    # 100 -> 90 (queda de 10 %) -> 99,9 (+11 % do fundo) em 20 s: 1 oscilacao a X=8 %, N=30 s
    P = _pos([(0, 1.00), (10, 0.90), (20, 0.999), (30, 1.00)])
    assert count_swings(P["path"], Decimal(8), 30) == 1
    # a X=12 % a queda de 10 % nem abre o mergulho
    assert count_swings(P["path"], Decimal(12), 30) == 0


def test_swing_fora_do_prazo_nao_conta():
    # mesma oscilacao, mas a recuperacao so chega aos 200 s: N=30 s recusa, N=120 tambem
    P = _pos([(0, 1.00), (10, 0.90), (200, 0.999)])
    assert count_swings(P["path"], Decimal(8), 30) == 0
    assert count_swings(P["path"], Decimal(8), 120) == 0


def test_abort_nao_fabrica_oscilacao_em_queda_monotona():
    P = _pos([(0, 1.0), (30, 0.85), (60, 0.70), (90, 0.55), (120, 0.40)])
    assert count_swings(P["path"], Decimal(8), 30) == 0
    assert count_swings(P["path"], Decimal(3), 120) == 0


def test_invariancia_ao_sufixo_futuro():
    """Trocar o futuro depois do ponto K nao pode mudar nenhuma decisao anterior a K."""
    rng = random.Random(72)
    base = [(0, 1.0)]
    mult = 1.0
    for sec in range(2, 302, 2):
        mult *= 1 + rng.uniform(-0.05, 0.05)
        base.append((sec, mult))
    P = _pos(base)
    ref = simulate_scalp(P, Decimal(3), 60)
    assert ref["legs"] >= 2, "a serie sintetica tem de disparar pernas para o teste valer"
    for k in (40, 80, 120):
        mutated = list(base[:k])
        m = base[k - 1][1]
        for sec, _ in base[k:]:
            m *= 1 + rng.uniform(-0.30, 0.30)  # futuro completamente diferente
            mutated.append((sec, m))
        Q = _pos(mutated)
        got = simulate_scalp(Q, Decimal(3), 60)
        # todas as pernas cujo POUSO cai antes do ponto mutado tem de ser identicas
        cut = base[k - 1][0]
        a = [(rb["i"], rb["paid"]) for rb in ref["rebuy_log"]
             if P["path"][rb["i"]][0] < T0 + timedelta(seconds=cut)]
        b = [(rb["i"], rb["paid"]) for rb in got["rebuy_log"]
             if Q["path"][rb["i"]][0] < T0 + timedelta(seconds=cut)]
        assert a == b, "decisao antes de %d s mudou ao trocar o futuro" % cut


def test_guarda_recusa_fill_anterior_ao_gatilho():
    from sim import Guard

    g = Guard()
    with pytest.raises(LookAheadError):
        g.check(5, 4, T0, T0, 1.6)
    with pytest.raises(LookAheadError):
        g.check(5, 6, T0, T0 + timedelta(seconds=9), 1.6)


def test_braco_batoteiro_ganha_ao_causal_e_isso_e_o_controlo():
    """O braco que olha o maximo futuro tem de ganhar. Se empatasse, a guarda estava solta."""
    P = _pos([(0, 1.0), (30, 1.4), (60, 1.8), (90, 0.5), (150, 0.4), (290, 0.35)])
    causal = simulate_scalp(P, Decimal(8), 60)
    cheat = simulate_cheat(P)
    cur = simulate_current(P)
    assert cheat["final"] > causal["final"]
    assert cheat["final"] > cur["final"]


def test_custo_por_perna_e_o_declarado():
    """Sem movimento nenhum, uma venda imediata perde exatamente c/2 mais o impacto da curva."""
    P = _pos([(0, 1.0), (10, 1.0), (300, 1.0)])
    res = simulate_current(P, cost=Decimal("0.0223"))
    # nunca atinge 1,15x; sai por trailing (nao) ou time_stop
    assert res["reason"] == "time_stop"
    # a marca embute 1,25 %; a venda simulada cobra 1,115 % sobre o bruto
    bruto = VSOL - (VSOL * VTOK) // (VTOK + LOT)
    assert res["final"] == int(Decimal(bruto) * (1 - Decimal("0.0223") / 2))


def test_break_even_algebrico():
    """Multiplicador de tokens por ciclo = (1-c/2)^2/(1-X); equilibrio em X = c - c^2/4."""
    c = Decimal("0.0223")
    x_be = c - c * c / 4
    assert (1 - c / 2) ** 2 / (1 - x_be) == pytest.approx(1.0, abs=1e-12)
    assert float(x_be) == pytest.approx(0.0221756775, abs=1e-9)


def test_a_guarda_apanha_uma_politica_que_espreita_o_futuro():
    """Prova negativa: uma versao batoteira do simulador FALHA a invariancia ao sufixo.

    Sem este teste, o teste de invariancia poderia estar a passar por vacuidade.
    """
    import sim as S

    original = S._fill_index

    def leaky(points, i, latency_s):
        # espreita: pousa no MELHOR ponto dos proximos 20, nao no da latencia
        hi = min(i + 20, len(points) - 1)
        return max(range(i, hi + 1), key=lambda k: points[k][1])

    rng = random.Random(72)
    base, mult = [(0, 1.0)], 1.0
    for sec in range(2, 302, 2):
        mult *= 1 + rng.uniform(-0.05, 0.05)
        base.append((sec, mult))
    S._fill_index = leaky
    try:
        P = _pos(base)
        with pytest.raises(LookAheadError):
            simulate_scalp(P, Decimal(3), 60)
    finally:
        S._fill_index = original
