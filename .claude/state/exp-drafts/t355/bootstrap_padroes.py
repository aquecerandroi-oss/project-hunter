"""Bootstrap de blocos por dia para o contraste padrão-contra-baseline — T3.55b.

Reusa `t342-blocos/blocos.py` **sem tocar nele**: `contraste_por_piso` é
exatamente o contraste que preciso quando o "piso de ATR%" vira o indicador
`1,0 = a barra tem o padrão / 0,0 = não tem` e o piso vira `0,5`. O estimando é o
mesmo da T3.42: *variante menos pai*, com o **dia** como bloco (as decisões do
mesmo dia compartilham regime e, em mercados correlacionados, choque — KB-0010).

O problema é custo: 84 contrastes × 10 000 reamostragens × 47 000 linhas é meia
hora de concatenação. `contraste_rapido` faz a **mesma** conta por estatística
suficiente (soma e contagem por dia), consumindo a **mesma** sequência do mesmo
gerador na mesma ordem, e por isso devolve os mesmos números — o que
`test_bootstrap.py::test_o_atalho_reproduz_blocos_numero_a_numero` prova contra
`blocos.py` de verdade, não contra uma expectativa.

Residual, e por que ele existe: o brief pede baseline **pareada** (mesmo mercado,
mesma hora do dia, barras sem o padrão). Ela entra como deslocamento por célula,
subtraído de toda linha antes do bootstrap, e o sinal do padrão (`+1` long,
`-1` short) é aplicado depois — assim uma vela de baixa que acerta a queda conta
como acerto, e não como retorno negativo.

Assunção declarada: o deslocamento da célula é fixado na amostra inteira e o erro
de estimá-lo **não** é propagado pelo bootstrap. Com 124 barras por célula em 15 m
(31 dias × 4 barras/hora) contra dezenas de ocorrências, é erro de segunda ordem;
em 1 h a célula tem 31 barras e a ressalva vale o registro.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np

for _p in (
    "C:/dev/project-hunter/.claude/state/exp-drafts/t342-blocos",
    "C:/dev/project-hunter/.claude/state/exp-drafts/t355",
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from blocos import Decisao, contraste_por_piso  # noqa: E402,F401  (reuso literal)

PISO = 0.5
"""O piso que separa indicador 1,0 de 0,0. Nunca toca um valor de verdade."""


@dataclass(frozen=True)
class Contraste:
    chave: str
    dias: int
    n_pai: int
    n_variante: int
    exp_pai: float
    exp_variante: float
    delta: float
    ic95: tuple[float, float]
    p_valor: float
    reamostragens_validas: int


def _por_dia(
    dias_linha: np.ndarray, valores: np.ndarray, marca: np.ndarray
) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    dias = sorted(set(dias_linha.tolist()))
    soma_pat = np.zeros(len(dias))
    cont_pat = np.zeros(len(dias))
    soma_tot = np.zeros(len(dias))
    cont_tot = np.zeros(len(dias))
    for k, dia in enumerate(dias):
        sel = dias_linha == dia
        soma_tot[k] = valores[sel].sum()
        cont_tot[k] = sel.sum()
        sel_pat = sel & marca
        soma_pat[k] = valores[sel_pat].sum()
        cont_pat[k] = sel_pat.sum()
    return dias, soma_pat, cont_pat, soma_tot, cont_tot


def contraste_rapido(
    chave: str,
    dias_linha: np.ndarray,
    residuo: np.ndarray,
    marca: np.ndarray,
    *,
    reamostragens: int = 10_000,
    seed: int = 20260909,
) -> Contraste:
    """`mean(residuo | padrão) - mean(residuo | tudo)`, com o dia como bloco."""
    dias, soma_pat, cont_pat, soma_tot, cont_tot = _por_dia(dias_linha, residuo, marca)
    rng = np.random.default_rng(seed)
    idx_dias = np.arange(len(dias))
    deltas = np.empty(reamostragens)
    validas = 0
    for _ in range(reamostragens):
        escolhidos = rng.choice(idx_dias, size=len(dias), replace=True)
        n_pat = cont_pat[escolhidos].sum()
        if n_pat == 0:
            continue  # reamostragem sem nenhuma ocorrência: não há Δ a medir
        deltas[validas] = (
            soma_pat[escolhidos].sum() / n_pat
            - soma_tot[escolhidos].sum() / cont_tot[escolhidos].sum()
        )
        validas += 1
    arr = deltas[:validas]
    if arr.size == 0:
        vazio = float("nan")
        return Contraste(
            chave, len(dias), int(marca.size), 0, vazio, vazio, vazio, (vazio, vazio), 1.0, 0
        )
    ic = (float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5)))
    p = 2.0 * min(float((arr <= 0).mean()), float((arr >= 0).mean()))
    exp_pai = float(residuo.mean())
    exp_var = float(residuo[marca].mean()) if marca.any() else float("nan")
    return Contraste(
        chave=chave,
        dias=len(dias),
        n_pai=int(residuo.size),
        n_variante=int(marca.sum()),
        exp_pai=exp_pai,
        exp_variante=exp_var,
        delta=exp_var - exp_pai,
        ic95=ic,
        p_valor=max(min(p, 1.0), 1.0 / max(arr.size, 1)),
        reamostragens_validas=int(arr.size),
    )


def como_decisoes(dias_linha: np.ndarray, residuo: np.ndarray, marca: np.ndarray) -> list[Decisao]:
    """A mesma população no formato que `blocos.py` come, para o confronto literal."""
    return [
        Decisao(dia=str(d), atr_pct=1.0 if m else 0.0, r_net=float(r))
        for d, r, m in zip(dias_linha.tolist(), residuo.tolist(), marca.tolist(), strict=True)
    ]


def media_por_blocos(
    dias_linha: np.ndarray,
    valores: np.ndarray,
    *,
    reamostragens: int = 10_000,
    seed: int = 20260909,
) -> tuple[float, tuple[float, float]]:
    """Média e IC95 de **uma** população, com o dia como bloco.

    `blocos.py` só sabe contrastar duas populações; a lente de pedágio pergunta
    outra coisa ("quanto sobra por ocorrência"), que é uma média simples. O bloco
    e o gerador são os mesmos, para que os dois intervalos da nota sejam
    comparáveis.
    """
    dias = sorted(set(dias_linha.tolist()))
    soma = np.zeros(len(dias))
    conta = np.zeros(len(dias))
    for k, dia in enumerate(dias):
        sel = dias_linha == dia
        soma[k] = valores[sel].sum()
        conta[k] = sel.sum()
    rng = np.random.default_rng(seed)
    idx = np.arange(len(dias))
    medias = np.empty(reamostragens)
    validas = 0
    for _ in range(reamostragens):
        escolhidos = rng.choice(idx, size=len(dias), replace=True)
        n = conta[escolhidos].sum()
        if n == 0:
            continue
        medias[validas] = soma[escolhidos].sum() / n
        validas += 1
    arr = medias[:validas]
    if arr.size == 0:
        return float("nan"), (float("nan"), float("nan"))
    return float(valores.mean()), (
        float(np.percentile(arr, 2.5)),
        float(np.percentile(arr, 97.5)),
    )


def holm(p_valores: dict[str, float], alfa: float = 0.05) -> dict[str, tuple[float, bool]]:
    """Holm-Bonferroni: devolve `(p ajustado, sobrevive)` por chave.

    A família é declarada por quem chama e entra inteira: escolher a família
    depois de ver os p-valores é a forma barata de fabricar significância.
    """
    ordenados = sorted(p_valores.items(), key=lambda kv: kv[1])
    m = len(ordenados)
    saida: dict[str, tuple[float, bool]] = {}
    maior = 0.0
    for k, (chave, p) in enumerate(ordenados):
        ajustado = min(1.0, max(maior, (m - k) * p))
        maior = ajustado
        saida[chave] = (ajustado, ajustado <= alfa)
    return saida
