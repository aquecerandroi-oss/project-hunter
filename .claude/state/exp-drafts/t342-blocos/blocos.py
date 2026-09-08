"""Bootstrap de blocos por dia para o contraste 'piso de ATR%' — T3.42.

Não é código de produção: mora em ``.claude/state/exp-drafts/`` e serve a uma
única pergunta desta nota — *o Δ de expectancy entre a variante (subconjunto da
população do pai definido por um piso de ATR%) e o pai se distingue de zero
quando o dia é o bloco?*

Por que bloco de dia: as decisões do mesmo dia compartilham regime e, em quatro
mercados correlacionados, choque; tratá-las como independentes estreita o
intervalo artificialmente ([[KB-0010]]). Reamostram-se **dias inteiros** com
reposição; dentro do dia, todas as decisões vão juntas.

O Δ é calculado como ``média(r_net | atr_pct >= piso) − média(r_net)`` **na
mesma reamostragem**, porque a variante é subconjunto exato do pai (medido: 17
de 37 e 11 de 37 pareiam, Δ pareado 0,0000 R) — o par não é decisão a decisão,
é população contra população.

NumPy sobre janelas em memória; nada de Decimal aqui porque nada disto é
dinheiro persistido (a fronteira Decimal fica no banco, PIPELINE §9).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Decisao:
    dia: str
    atr_pct: float
    r_net: float


@dataclass(frozen=True)
class Contraste:
    piso: float
    dias: int
    n_pai: int
    n_variante: int
    exp_pai: float
    exp_variante: float
    delta: float
    ic95: tuple[float, float]
    reamostragens_validas: int


def expectancy(valores: np.ndarray) -> float:
    """Média simples; ``nan`` para amostra vazia (nunca 0,0, que seria um número inventado)."""
    if valores.size == 0:
        return float("nan")
    return float(valores.mean())


def contraste_por_piso(
    decisoes: list[Decisao],
    piso: float,
    *,
    reamostragens: int = 10_000,
    seed: int = 20260908,
) -> Contraste:
    dias = sorted({d.dia for d in decisoes})
    por_dia: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for dia in dias:
        linhas = [d for d in decisoes if d.dia == dia]
        por_dia[dia] = (
            np.array([d.r_net for d in linhas], dtype=float),
            np.array([d.atr_pct for d in linhas], dtype=float),
        )

    todos_r = np.concatenate([por_dia[d][0] for d in dias])
    todos_atr = np.concatenate([por_dia[d][1] for d in dias])
    mantidos = todos_atr >= piso

    rng = np.random.default_rng(seed)
    deltas: list[float] = []
    idx_dias = np.arange(len(dias))
    for _ in range(reamostragens):
        escolhidos = rng.choice(idx_dias, size=len(dias), replace=True)
        r = np.concatenate([por_dia[dias[i]][0] for i in escolhidos])
        atr = np.concatenate([por_dia[dias[i]][1] for i in escolhidos])
        sel = atr >= piso
        if not sel.any():
            continue  # reamostragem sem nenhuma decisão acima do piso: não há Δ a medir
        deltas.append(float(r[sel].mean() - r.mean()))

    arr = np.array(deltas, dtype=float)
    ic = (float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))) if arr.size else (float("nan"), float("nan"))
    return Contraste(
        piso=piso,
        dias=len(dias),
        n_pai=int(todos_r.size),
        n_variante=int(mantidos.sum()),
        exp_pai=expectancy(todos_r),
        exp_variante=expectancy(todos_r[mantidos]),
        delta=expectancy(todos_r[mantidos]) - expectancy(todos_r),
        ic95=ic,
        reamostragens_validas=int(arr.size),
    )


def ler_csv(caminho: str) -> list[Decisao]:
    import csv

    with open(caminho, newline="", encoding="utf-8") as fh:
        return [
            Decisao(dia=linha["dia"], atr_pct=float(linha["atr_pct"]), r_net=float(linha["r_net"]))
            for linha in csv.DictReader(fh)
        ]


if __name__ == "__main__":  # pragma: no cover - manivela manual
    import sys

    decisoes = ler_csv(sys.argv[1])
    for piso in (0.008, 0.010):
        c = contraste_por_piso(decisoes, piso)
        print(
            f"piso {piso:.3f} | dias {c.dias} | n_pai {c.n_pai} | n_var {c.n_variante} | "
            f"exp_pai {c.exp_pai:+.4f} | exp_var {c.exp_variante:+.4f} | "
            f"delta {c.delta:+.4f} | IC95 [{c.ic95[0]:+.4f}; {c.ic95[1]:+.4f}] | "
            f"reamostragens {c.reamostragens_validas}"
        )
