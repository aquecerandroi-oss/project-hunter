"""Testes da aritmética do D-P19 — a meta de R$ 9.000/dia em DINHEIRO.

Cada função pura tem um caso que passa e um que falha/degenera, na mesma
disciplina do contrato (`docs/RISK_ENGINE.md` §3): insumo ausente ou janela
incompleta vira `None` com motivo, nunca zero e nunca média de janela reduzida.

Nada aqui redigita um limite: `PAPER_V1` e `round_trip_cost_fraction` vêm de
`packages/risk-core`, e a ordem de desempate dos tetos é a `CAP_ORDER` do §4.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from meta_em_dinheiro import (
    CUSTO_RT_LAB,
    Cenario,
    brl,
    caps_do_motor,
    dinheiro_por_dia,
    impacto_raiz_quadrada,
    mediana_interpolada,
    percentil_nearest_rank,
    referencias_de_volume,
    valor_de_1r_usdt,
)

from hunter_risk.limits import PAPER_V1

D = Decimal


# ---------------------------------------------------------------- medianas


def test_a_mediana_de_n_impar_e_o_elemento_do_meio() -> None:
    assert mediana_interpolada([D(1), D(3), D(2)]) == D(2)


def test_a_mediana_de_n_par_interpola_como_percentile_cont() -> None:
    # é a convenção que a T3.60 usou no banco (percentile_cont(0.5)), não o
    # nearest-rank: com 4 valores a mediana cai entre o 2º e o 3º.
    assert mediana_interpolada([D(1), D(2), D(3), D(4)]) == D("2.5")


def test_a_mediana_de_populacao_vazia_e_erro_nao_zero() -> None:
    with pytest.raises(ValueError):
        mediana_interpolada([])


def test_o_percentil_e_nearest_rank_igual_ao_do_T3_78() -> None:
    pop = [D(10), D(20), D(30), D(40), D(50)]
    assert percentil_nearest_rank(pop, D("0.10")) == D(10)
    assert percentil_nearest_rank(pop, D("0.50")) == D(30)
    assert percentil_nearest_rank(pop, D("0.90")) == D(50)


def test_o_percentil_de_populacao_vazia_e_erro() -> None:
    with pytest.raises(ValueError):
        percentil_nearest_rank([], D("0.5"))


# ------------------------------------------- referência de volume (§4)


def _serie(valores: list[int], minuto_inicial: int = 0) -> list[tuple[int, Decimal]]:
    return [(minuto_inicial + i, D(v)) for i, v in enumerate(valores)]


def test_a_referencia_e_o_minimo_entre_o_ultimo_minuto_e_a_mediana_de_30() -> None:
    # 29 minutos de 100 e um último minuto de 10: a referência é o minuto.
    serie = _serie([100] * 29 + [10])
    refs = referencias_de_volume(serie, janela=30)
    assert refs == [(29, D(10))]


def test_quando_o_ultimo_minuto_e_o_maior_a_referencia_e_a_mediana() -> None:
    serie = _serie([100] * 29 + [10_000])
    refs = referencias_de_volume(serie, janela=30)
    # mediana de 29 valores 100 + um 10.000 = 100
    assert refs == [(29, D(100))]


def test_janela_incompleta_nao_produz_referencia() -> None:
    serie = _serie([100] * 29)
    assert referencias_de_volume(serie, janela=30) == []


def test_buraco_na_janela_invalida_a_referencia_em_vez_de_encolher_a_janela() -> None:
    # 31 minutos declarados, mas o minuto 5 não existe: nenhuma janela de 30
    # minutos contíguos termina antes do minuto 34.
    serie = [(m, D(100)) for m in range(31) if m != 5]
    assert referencias_de_volume(serie, janela=30) == []


# ------------------------------------------------------- tetos do motor


def test_com_mercado_fino_quem_manda_e_a_participacao() -> None:
    caps = caps_do_motor(
        equity_usdt=D(100_000),
        d_stop=D("0.02"),
        referencia_volume=D(50_000),
        participacao=PAPER_V1.max_participation_pct,
    )
    assert caps.binding == "market_participation"
    assert caps.notional == D(500)  # 1 % de 50.000


def test_com_mercado_fundo_e_stop_largo_quem_manda_e_o_risco_por_operacao() -> None:
    # d_stop = 3 % (o topo da banda do perfil): 100.000 x 0,0025 / 0,032 =
    # 7.812,5, abaixo dos 10.000 do teto por moeda.
    caps = caps_do_motor(
        equity_usdt=D(100_000),
        d_stop=D("0.03"),
        referencia_volume=D(100_000_000),
        participacao=PAPER_V1.max_participation_pct,
    )
    assert caps.binding == "risk_per_trade"
    assert caps.notional == D("7812.5")


def test_com_stop_mediano_o_teto_por_moeda_ja_passa_na_frente_do_risco() -> None:
    # d_stop = 2 % (perto da mediana da família): o orçamento de risco compra
    # 11.363 de notional, e quem segura em R$100 mil é max_asset_exposure_pct.
    caps = caps_do_motor(
        equity_usdt=D(100_000),
        d_stop=D("0.02"),
        referencia_volume=D(100_000_000),
        participacao=PAPER_V1.max_participation_pct,
    )
    assert caps.binding == "asset_exposure"
    assert caps.valores["risk_per_trade"] > caps.notional == D(100_000) * PAPER_V1.max_asset_exposure_pct


def test_com_stop_estreito_o_teto_por_moeda_passa_na_frente_do_risco() -> None:
    # stop de 0,3 % (o piso do perfil): o orçamento de risco compra muito
    # notional e quem segura é max_asset_exposure_pct = 10 %.
    caps = caps_do_motor(
        equity_usdt=D(100_000),
        d_stop=D("0.003"),
        referencia_volume=D(100_000_000),
        participacao=PAPER_V1.max_participation_pct,
    )
    assert caps.binding == "asset_exposure"
    assert caps.notional == D(100_000) * PAPER_V1.max_asset_exposure_pct


def test_empate_entre_tetos_resolve_pela_ordem_declarada_do_contrato() -> None:
    # participação exatamente igual ao orçamento de risco: CAP_ORDER coloca
    # risk_per_trade antes de market_participation.
    d_stop = D("0.03")
    alvo = D(100_000) * PAPER_V1.risk_per_trade_pct / (d_stop + CUSTO_RT_LAB)
    caps = caps_do_motor(
        equity_usdt=D(100_000),
        d_stop=d_stop,
        referencia_volume=alvo / PAPER_V1.max_participation_pct,
        participacao=PAPER_V1.max_participation_pct,
    )
    assert caps.notional == alvo
    assert caps.binding == "risk_per_trade"
    assert "market_participation" in caps.empatados


def test_referencia_de_volume_ausente_nao_vira_zero() -> None:
    with pytest.raises(ValueError):
        caps_do_motor(
            equity_usdt=D(100_000),
            d_stop=D("0.02"),
            referencia_volume=None,
            participacao=PAPER_V1.max_participation_pct,
        )


# --------------------------------------------------- valor de 1 R e dinheiro


def test_1r_e_notional_vezes_a_distancia_de_stop_a_identidade_da_T3_60() -> None:
    # r_net do Lab tem denominador |entrada - stop| SEM custo (notes-T3.60 §2),
    # então o dinheiro de 1 R é notional x d_stop.
    assert valor_de_1r_usdt(D(10_000), D("0.02")) == D(200)


def test_1r_com_stop_nulo_e_erro_nao_infinito() -> None:
    with pytest.raises(ValueError):
        valor_de_1r_usdt(D(10_000), D(0))


def test_o_cambio_e_multiplicacao_exata_em_decimal() -> None:
    assert brl(D("200"), D("5.1198")) == D("1023.96")


def test_o_dinheiro_do_dia_e_apostas_x_1r_x_r_medido() -> None:
    # 7 apostas/dia, 1 R = R$40, R medido +0,25 por aposta -> R$70/dia
    assert dinheiro_por_dia(D(7), D(40), D("0.25")) == D(70)


def test_com_expectancy_negativa_o_dinheiro_do_dia_e_negativo_nao_zero() -> None:
    # "Se a expectancy líquida for <= 0, não existe tamanho positivo que
    # resolva" (Astra, D-P19): aumentar 1 R só aumenta o prejuízo.
    pequeno = dinheiro_por_dia(D(7), D(40), D("-0.34"))
    grande = dinheiro_por_dia(D(7), D(400), D("-0.34"))
    assert pequeno < 0
    assert grande < pequeno


# ------------------------------- impacto raiz quadrada (SENSIBILIDADE)


def test_o_impacto_raiz_quadrada_cresce_com_a_raiz_do_tamanho() -> None:
    # k.sqrt(Q/ADV): quadruplicar Q dobra o impacto.
    um = impacto_raiz_quadrada(D(10_000), D(100_000_000), D("0.5"))
    quatro = impacto_raiz_quadrada(D(40_000), D(100_000_000), D("0.5"))
    assert (quatro / um).quantize(D("0.0001")) == D("2.0000")


def test_o_impacto_raiz_quadrada_com_adv_zero_e_erro() -> None:
    with pytest.raises(ValueError):
        impacto_raiz_quadrada(D(10_000), D(0), D("0.5"))


# --------------------------------------------------------------- cenário


def test_o_cenario_publica_o_teto_e_o_esperado_lado_a_lado() -> None:
    c = Cenario(
        nome="teste",
        apostas_por_dia=D(7),
        valor_1r_brl=D(40),
        r_por_aposta=D("-0.34"),
    )
    assert c.teto_brl_dia == D(280)  # se toda aposta fechasse +1 R
    assert c.esperado_brl_dia == D("-95.2")
    assert c.teto_brl_dia > 0 > c.esperado_brl_dia
