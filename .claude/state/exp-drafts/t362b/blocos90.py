"""Bootstrap de blocos de dia para a leitura de 90 dias — T3.62b.

Irmão de ``.claude/state/exp-drafts/t342-blocos/blocos.py``: mesmo bloco (o **dia
inteiro**), mesma justificativa ([[KB-0010]]) — decisões do mesmo dia, em dezesseis
mercados correlacionados, dividem regime e choque, e tratá-las como independentes
estreita o intervalo artificialmente. O que muda aqui é a pergunta: a T3.42
contrastava um subconjunto contra o pai *dentro da mesma reamostragem*; esta nota
precisa de três coisas que aquela função não dá:

1. o IC da **média** de uma população (a expectancy da versão, e de cada janela
   de 30 d separada);
2. o Δ **não pareado** entre duas janelas de calendário disjuntas — J3 contra
   J1+J2 não podem ser pareadas por dia porque **não têm dia em comum**, então
   cada lado reamostra os seus próprios dias e o Δ é a diferença das médias;
3. o Δ **pareado por dia** entre dois grupos de mercado, que dividem o calendário
   — aqui a mesma reamostragem de dias alimenta os dois lados, senão o contraste
   estaria comparando dois calendários diferentes.

Confundir (2) com (3) é o erro que faz um IC parecer estreito: parear o que não
tem par, ou deixar de parear o que tem.

NumPy sobre janelas em memória; nada de pandas. Nada aqui é dinheiro persistido,
então nada aqui é ``Decimal`` (a fronteira ``Decimal`` fica no banco, PIPELINE §9).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Intervalo:
    n: int
    dias: int
    media: float
    ic95: tuple[float, float]
    reamostragens: int


def _por_dia(dias: list[str], valores: np.ndarray) -> tuple[list[str], list[np.ndarray]]:
    """Agrupa os valores por dia, preservando a ordem canônica (dia crescente)."""
    ordem = sorted(set(dias))
    indice = {d: i for i, d in enumerate(ordem)}
    baldes: list[list[float]] = [[] for _ in ordem]
    for d, v in zip(dias, valores, strict=True):
        baldes[indice[d]].append(float(v))
    return ordem, [np.array(b, dtype=float) for b in baldes]


def media(valores: np.ndarray) -> float:
    """Média simples; ``nan`` para amostra vazia — nunca 0,0, que seria inventado."""
    valores = np.asarray(valores, dtype=float)
    if valores.size == 0:
        return float("nan")
    return float(valores.mean())


def ic_media(
    dias: list[str],
    valores: np.ndarray,
    *,
    reamostragens: int = 20_000,
    seed: int = 20260910,
) -> Intervalo:
    """IC 95 % da média, reamostrando **dias inteiros** com reposição."""
    valores = np.asarray(valores, dtype=float)
    if valores.size == 0:
        return Intervalo(0, 0, float("nan"), (float("nan"), float("nan")), 0)
    ordem, baldes = _por_dia(dias, valores)
    rng = np.random.default_rng(seed)
    idx = np.arange(len(ordem))
    amostras = np.empty(reamostragens, dtype=float)
    for k in range(reamostragens):
        escolhidos = rng.choice(idx, size=len(ordem), replace=True)
        amostras[k] = np.concatenate([baldes[i] for i in escolhidos]).mean()
    return Intervalo(
        n=int(valores.size),
        dias=len(ordem),
        media=media(valores),
        ic95=(float(np.percentile(amostras, 2.5)), float(np.percentile(amostras, 97.5))),
        reamostragens=reamostragens,
    )


@dataclass(frozen=True)
class Delta:
    n_a: int
    n_b: int
    media_a: float
    media_b: float
    delta: float
    ic95: tuple[float, float]
    reamostragens_validas: int


def delta_nao_pareado(
    dias_a: list[str],
    valores_a: np.ndarray,
    dias_b: list[str],
    valores_b: np.ndarray,
    *,
    reamostragens: int = 20_000,
    seed: int = 20260910,
) -> Delta:
    """Δ = média(A) − média(B) para janelas de calendário **disjuntas**.

    Cada lado reamostra os seus próprios dias. Não há pareamento possível: J1 e J3
    não compartilham nenhuma data.
    """
    va, vb = np.asarray(valores_a, dtype=float), np.asarray(valores_b, dtype=float)
    ordem_a, baldes_a = _por_dia(dias_a, va)
    ordem_b, baldes_b = _por_dia(dias_b, vb)
    rng = np.random.default_rng(seed)
    ia, ib = np.arange(len(ordem_a)), np.arange(len(ordem_b))
    amostras = np.empty(reamostragens, dtype=float)
    for k in range(reamostragens):
        ma = np.concatenate([baldes_a[i] for i in rng.choice(ia, size=len(ordem_a), replace=True)]).mean()
        mb = np.concatenate([baldes_b[i] for i in rng.choice(ib, size=len(ordem_b), replace=True)]).mean()
        amostras[k] = ma - mb
    return Delta(
        n_a=int(va.size),
        n_b=int(vb.size),
        media_a=media(va),
        media_b=media(vb),
        delta=media(va) - media(vb),
        ic95=(float(np.percentile(amostras, 2.5)), float(np.percentile(amostras, 97.5))),
        reamostragens_validas=reamostragens,
    )


def delta_pareado_por_dia(
    dias: list[str],
    valores: np.ndarray,
    grupo_a: np.ndarray,
    *,
    reamostragens: int = 20_000,
    seed: int = 20260910,
) -> Delta:
    """Δ = média(grupo A) − média(grupo B) com **os mesmos dias** dos dois lados.

    ``grupo_a`` é uma máscara booleana sobre as mesmas linhas. Reamostragens em que
    algum dos lados fica vazio são descartadas (não há Δ a medir) — e o número de
    reamostragens que sobraram é devolvido, porque descartar em silêncio seria
    inventar um denominador.
    """
    valores = np.asarray(valores, dtype=float)
    grupo_a = np.asarray(grupo_a, dtype=bool)
    ordem = sorted(set(dias))
    indice = {d: i for i, d in enumerate(ordem)}
    ra: list[list[float]] = [[] for _ in ordem]
    rb: list[list[float]] = [[] for _ in ordem]
    for d, v, ga in zip(dias, valores, grupo_a, strict=True):
        (ra if ga else rb)[indice[d]].append(float(v))
    ba = [np.array(x, dtype=float) for x in ra]
    bb = [np.array(x, dtype=float) for x in rb]

    rng = np.random.default_rng(seed)
    idx = np.arange(len(ordem))
    amostras: list[float] = []
    for _ in range(reamostragens):
        escolhidos = rng.choice(idx, size=len(ordem), replace=True)
        ca = np.concatenate([ba[i] for i in escolhidos])
        cb = np.concatenate([bb[i] for i in escolhidos])
        if ca.size == 0 or cb.size == 0:
            continue
        amostras.append(float(ca.mean() - cb.mean()))
    arr = np.array(amostras, dtype=float)
    ic = (
        (float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5)))
        if arr.size
        else (float("nan"), float("nan"))
    )
    return Delta(
        n_a=int(grupo_a.sum()),
        n_b=int((~grupo_a).sum()),
        media_a=media(valores[grupo_a]),
        media_b=media(valores[~grupo_a]),
        delta=media(valores[grupo_a]) - media(valores[~grupo_a]),
        ic95=ic,
        reamostragens_validas=int(arr.size),
    )


def profit_factor(valores: np.ndarray) -> float:
    """Soma dos ganhos sobre soma das perdas; ``inf`` sem perda, ``nan`` sem amostra."""
    v = np.asarray(valores, dtype=float)
    if v.size == 0:
        return float("nan")
    perda = -v[v < 0].sum()
    if perda == 0:
        return float("inf")
    return float(v[v > 0].sum() / perda)
