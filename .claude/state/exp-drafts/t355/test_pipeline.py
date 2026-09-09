"""Anti-antecipação no dado real, não só na série sintética — T3.55b.

`test_padroes.py` prova a propriedade sobre passeios aleatórios. Aqui ela é
provada sobre a exportação que a nota publica: se a série for cortada em qualquer
ponto, as ocorrências do prefixo comum têm de sair **idênticas** — mesmo nome,
mesma barra, mesma entrada, mesmo stop, mesma escala. É a mesma afirmação que o
`tl_scan` da T3.34 faz (`scan(as_of=i) == scan(prefixo)`), aplicada ao detector
de velas.

O teste pula se `barras.csv` não existir: o arquivo é uma exportação da VPS, não
um fixture versionado.
"""

from __future__ import annotations

import os

import pytest
from medir import MAIOR, PASSO, TF, carregar, corridas
from padroes import varrer

BARRAS = "C:/dev/project-hunter/.claude/state/exp-drafts/t355/barras.csv"
CORTES = (200, 500, 1000, 1500, 2500)


@pytest.fixture(scope="module")
def series():
    if not os.path.exists(BARRAS):
        pytest.skip("barras.csv nao exportado nesta maquina")
    return carregar(BARRAS)


def atr_de(corrida, tf):
    from hunter_indicators.patterns.scale import atr_series

    return list(atr_series(corrida, timeframe=TF[tf]))


@pytest.mark.parametrize("simbolo", ["BTCUSDT", "DOGEUSDT", "SAHARAUSDT"])
def test_cortar_a_serie_nao_muda_o_passado(series, simbolo: str) -> None:
    bars = series[(simbolo, "15m")]
    corrida = corridas(bars, PASSO["15m"])[0]
    completo = varrer(corrida, atr_de(corrida, "15m"))
    assert completo, "a serie real precisa produzir ocorrencias para o teste valer"
    for corte in CORTES:
        prefixo = corrida[:corte]
        parcial = varrer(prefixo, atr_de(prefixo, "15m"))
        esperado = [d for d in completo if d.idx < corte]
        assert parcial == esperado, f"{simbolo} divergiu no corte {corte}"


def test_a_ultima_barra_utilizavel_deixa_dezesseis_barras_de_futuro(series) -> None:
    """O universo do estudo para 16 barras antes do fim: sem isso a baseline mede
    uma janela que o padrao nao teve."""
    corrida = corridas(series[("BTCUSDT", "15m")], PASSO["15m"])[0]
    assert MAIOR == 16
    ultima_usavel = len(corrida) - MAIOR - 1
    assert ultima_usavel + MAIOR < len(corrida)


def test_a_serie_exportada_e_contigua(series) -> None:
    """A exportacao exige completude por balde; o que sobra tem de ser uma corrida so
    por (mercado, timeframe) nesta janela — se um dia nao for, `corridas` quebra e o
    estudo mede pedacos, nunca costura."""
    for (simbolo, tf), bars in series.items():
        pedacos = corridas(bars, PASSO[tf])
        assert sum(len(p) for p in pedacos) == len(bars), f"{simbolo} {tf}"
        for pedaco in pedacos:
            for anterior, seguinte in zip(pedaco, pedaco[1:], strict=False):
                assert seguinte.open_time - anterior.open_time == PASSO[tf]
