"""Testes do detector-protótipo — T3.55b.

Cada caso é uma série sintética com ATR **exatamente 10** (`series.py`) e valores
esperados escritos à mão: o teste falha se a regra mudar, não se o número mudar de
carimbo. O último bloco é a prova anti-antecipação, com uma trapaça deliberada que
tem de reprovar exatamente a comparação que o detector honesto passa.
"""

from __future__ import annotations

import random
from decimal import Decimal

import padroes
import pytest
from padroes import Deteccao, detectar, varrer
from series import ATR_PREFIXO, atr, barra, prefixo


def nomes(achados: list[Deteccao]) -> set[str]:
    return {d.nome for d in achados}


def um(achados: list[Deteccao], nome: str) -> Deteccao:
    escolhidos = [d for d in achados if d.nome == nome]
    assert len(escolhidos) == 1, f"esperava exatamente um {nome}, veio {nomes(achados)}"
    return escolhidos[0]


def montar(passo: int, extras: list) -> tuple[list, list]:  # type: ignore[type-arg]
    bars = prefixo(passo)
    bars.extend(extras)
    return bars, atr(bars)


# --------------------------------------------------------------------------
# geometria de uma barra
# --------------------------------------------------------------------------


def test_o_prefixo_tem_atr_exatamente_dez() -> None:
    """A régua dos outros testes é exata: sem isso, todo valor esperado é um chute."""
    bars = prefixo(-2)
    assert atr(bars)[19] == ATR_PREFIXO


def test_martelo_em_tendencia_de_baixa() -> None:
    bars, a = montar(-2, [barra(20, "964", "964.5", "955", "963")])
    achados = detectar(bars, a, 20)
    m = um(achados, "martelo")
    assert m.direcao == "long"
    assert m.barras == 1
    assert m.escala == Decimal("10")
    assert m.stop == Decimal("955")
    assert m.stop_atr == Decimal("0.8")
    assert "enforcado" not in nomes(achados)


def test_a_mesma_geometria_em_tendencia_de_alta_e_enforcado() -> None:
    """Martelo e enforcado só diferem no contexto — e o contexto é anterior à barra."""
    bars, a = montar(+2, [barra(20, "1036", "1036.5", "1027", "1035")])
    achados = detectar(bars, a, 20)
    e = um(achados, "enforcado")
    assert e.direcao == "short"
    assert e.stop == Decimal("1036.5")
    assert e.stop_atr == Decimal("0.15")
    assert "martelo" not in nomes(achados)


def test_a_mesma_geometria_em_tendencia_lateral_nao_e_padrao_nenhum() -> None:
    bars, a = montar(0, [barra(20, "1004", "1004.5", "995", "1003")])
    achados = detectar(bars, a, 20)
    assert nomes(achados) == set()


def test_estrela_cadente() -> None:
    bars, a = montar(+2, [barra(20, "1036", "1046", "1035.5", "1037")])
    e = um(detectar(bars, a, 20), "estrela_cadente")
    assert e.direcao == "short"
    assert e.stop == Decimal("1046")
    assert e.stop_atr == Decimal("0.9")


def test_doji_pega_o_extremo_mais_distante_como_invalidacao() -> None:
    bars, a = montar(-2, [barra(20, "963", "967", "960", "963.2")])
    d = um(detectar(bars, a, 20), "doji")
    assert d.direcao == "neutro"
    assert d.stop == Decimal("967")  # 3,8 acima contra 3,2 abaixo
    assert d.stop_atr == Decimal("0.38")


def test_marubozu_de_alta() -> None:
    bars, a = montar(-2, [barra(20, "962", "971.2", "961.8", "971")])
    m = um(detectar(bars, a, 20), "marubozu_alta")
    assert m.stop == Decimal("961.8")
    assert m.stop_atr == Decimal("0.92")


def test_uma_barra_pequena_demais_contra_o_atr_nao_e_padrao() -> None:
    """`faixa >= 0,5 ATR`: um martelo perfeito de 0,3 ATR é ruído, não afirmação."""
    bars, a = montar(-2, [barra(20, "963.5", "963.6", "961", "963.4")])
    assert nomes(detectar(bars, a, 20)) == set()


def test_barra_sem_faixa_nao_produz_nada() -> None:
    bars, a = montar(-2, [barra(20, "962", "962", "962", "962")])
    assert detectar(bars, a, 20) == []


def test_no_aquecimento_nao_ha_regua_e_nao_ha_padrao() -> None:
    bars = prefixo(-2, n=12)
    bars.append(barra(12, "982", "982.5", "973", "981"))
    assert detectar(bars, atr(bars), 12) == []


# --------------------------------------------------------------------------
# duas e três barras
# --------------------------------------------------------------------------


def test_engolfo_de_alta() -> None:
    bars, a = montar(
        -2,
        [
            barra(20, "964", "965", "957", "958"),
            barra(21, "957", "967", "956", "966"),
        ],
    )
    achados = detectar(bars, a, 21)
    e = um(achados, "engolfo_alta")
    assert e.barras == 2
    assert e.escala == Decimal("10")  # ATR[19], anterior às duas barras
    assert e.stop == Decimal("956")
    assert e.stop_atr == Decimal("1")
    assert "marubozu_alta" not in nomes(achados)


def test_engolfo_de_baixa() -> None:
    bars, a = montar(
        +2,
        [
            barra(20, "1036", "1043", "1035", "1042"),
            barra(21, "1043", "1044", "1033", "1034"),
        ],
    )
    e = um(detectar(bars, a, 21), "engolfo_baixa")
    assert e.direcao == "short"
    assert e.stop == Decimal("1044")
    assert e.stop_atr == Decimal("1")


def test_harami_de_alta() -> None:
    bars, a = montar(
        -2,
        [
            barra(20, "968", "969", "955", "956"),
            barra(21, "959", "963", "958", "962"),
        ],
    )
    achados = detectar(bars, a, 21)
    h = um(achados, "harami_alta")
    assert h.stop == Decimal("955")
    assert h.stop_atr == Decimal("0.7")
    assert "engolfo_alta" not in nomes(achados)


def test_estrela_da_manha() -> None:
    bars, a = montar(
        -2,
        [
            barra(20, "970", "971", "955", "956"),
            barra(21, "955", "958", "953", "957"),
            barra(22, "957", "967", "956", "966"),
        ],
    )
    achados = detectar(bars, a, 22)
    e = um(achados, "estrela_manha")
    assert e.barras == 3
    assert e.stop == Decimal("953")
    assert e.stop_atr == Decimal("1.3")


def test_a_estrela_da_manha_precisa_fechar_acima_do_meio_do_corpo_grande() -> None:
    """Fechar em 962,9 contra um meio de 963 é uma barra bonita e nenhuma estrela."""
    bars, a = montar(
        -2,
        [
            barra(20, "970", "971", "955", "956"),
            barra(21, "955", "958", "953", "957"),
            barra(22, "957", "967", "956", "962.9"),
        ],
    )
    assert "estrela_manha" not in nomes(detectar(bars, a, 22))


def test_tres_soldados() -> None:
    bars, a = montar(
        -2,
        [
            barra(20, "960", "966.5", "959.5", "966"),
            barra(21, "963", "970.5", "962.5", "970"),
            barra(22, "967", "975.5", "966.5", "975"),
        ],
    )
    s = um(detectar(bars, a, 22), "tres_soldados")
    assert s.stop == Decimal("959.5")
    assert s.stop_atr == Decimal("1.55")


def test_tres_corvos() -> None:
    bars, a = montar(
        +2,
        [
            barra(20, "1040", "1040.5", "1033.5", "1034"),
            barra(21, "1037", "1037.5", "1029.5", "1030"),
            barra(22, "1033", "1033.5", "1024.5", "1025"),
        ],
    )
    c = um(detectar(bars, a, 22), "tres_corvos")
    assert c.direcao == "short"
    assert c.stop == Decimal("1040.5")
    assert c.stop_atr == Decimal("1.55")


def test_soldados_com_pavio_superior_grande_nao_sao_soldados() -> None:
    bars, a = montar(
        -2,
        [
            barra(20, "960", "970", "959.5", "966"),
            barra(21, "963", "974", "962.5", "970"),
            barra(22, "967", "979", "966.5", "975"),
        ],
    )
    assert "tres_soldados" not in nomes(detectar(bars, a, 22))


# --------------------------------------------------------------------------
# anti-antecipação
# --------------------------------------------------------------------------


def serie_aleatoria(n: int = 260, semente: int = 20260909) -> list:  # type: ignore[type-arg]
    """Passeio aleatório em Decimal — nenhuma barra desenhada para casar com regra."""
    rng = random.Random(semente)
    preco = Decimal("1000")
    saida = []
    for k in range(n):
        abertura = preco
        passo = Decimal(rng.randint(-40, 40)) / Decimal(10)
        fechamento = abertura + passo
        alta = max(abertura, fechamento) + Decimal(rng.randint(0, 30)) / Decimal(10)
        baixa = min(abertura, fechamento) - Decimal(rng.randint(0, 30)) / Decimal(10)
        saida.append(barra(k, str(abertura), str(alta), str(baixa), str(fechamento)))
        preco = fechamento
    return saida


def test_a_serie_aleatoria_produz_padroes_suficientes_para_o_teste_valer() -> None:
    bars = serie_aleatoria()
    achados = varrer(bars, atr(bars))
    assert len(achados) >= 20, "sem ocorrências a propriedade abaixo é vacuamente verdadeira"


def test_um_padrao_nao_muda_quando_o_futuro_muda() -> None:
    """A prova pedida pelo PIPELINE §2: mexer numa barra posterior não move nada.

    Aqui a barra ``i+1`` (que numa vela viva ainda estaria se formando) é
    substituída por outra completamente diferente, e todas as detecções até ``i``
    têm de sair idênticas — inclusive stop e escala.
    """
    bars = serie_aleatoria()
    a = atr(bars)
    for i in range(30, len(bars) - 1):
        alterada = list(bars)
        alterada[i + 1] = barra(i + 1, "9000", "9500", "8500", "8600")
        assert detectar(alterada, atr(alterada), i) == detectar(bars, a, i)


def test_o_corte_por_prefixo_e_o_corte_por_indice_sao_o_mesmo() -> None:
    bars = serie_aleatoria()
    a = atr(bars)
    for i in range(30, len(bars)):
        prefixo_bars = bars[: i + 1]
        assert detectar(prefixo_bars, atr(prefixo_bars), i) == detectar(bars, a, i)


def detectar_trapaca(bars: list, a: list, i: int) -> list:  # type: ignore[type-arg]
    """Trapaça deliberada: exige que a barra **seguinte** confirme o padrão.

    É a forma mais comum de vazamento em estudo de candlestick ("o martelo que
    funcionou"). Existe para provar que os dois testes acima têm dentes.
    """
    achados = detectar(bars, a, i)
    if i + 1 >= len(bars):
        return achados
    seguinte = bars[i + 1]
    return [
        d
        for d in achados
        if (
            seguinte.close > bars[i].close
            if d.direcao != "short"
            else seguinte.close < bars[i].close
        )
    ]


def test_a_trapaca_reprova_exatamente_o_que_o_detector_honesto_passa() -> None:
    bars = serie_aleatoria()
    a = atr(bars)
    divergencias = 0
    for i in range(30, len(bars) - 1):
        alterada = list(bars)
        alterada[i + 1] = barra(i + 1, "9000", "9500", "8500", "8600")
        if detectar_trapaca(alterada, atr(alterada), i) != detectar_trapaca(bars, a, i):
            divergencias += 1
    assert divergencias > 0, "a trapaça precisa quebrar a propriedade, senão o teste é decorativo"


def test_varrer_e_a_soma_das_deteccoes_barra_a_barra() -> None:
    bars = serie_aleatoria(n=120)
    a = atr(bars)
    esperado = [d for i in range(len(bars)) for d in detectar(bars, a, i)]
    assert varrer(bars, a) == esperado


def test_o_conjunto_de_nomes_e_fechado() -> None:
    """Nenhum padrão pode aparecer sem estar declarado na tabela de definições."""
    bars = serie_aleatoria()
    assert nomes(varrer(bars, atr(bars))) <= set(padroes.NOMES)


@pytest.mark.parametrize("nome", padroes.NOMES)
def test_todo_nome_declarado_tem_direcao(nome: str) -> None:
    assert padroes.DIRECAO[nome] in {"long", "short", "neutro"}
    assert padroes.SINAL[nome] in {1, -1}
