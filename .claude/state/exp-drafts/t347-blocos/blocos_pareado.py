"""Bootstrap de blocos por dia para o contraste **pareado** — T3.47.

Não é código de produção: mora em ``.claude/state/exp-drafts/`` e responde a uma
única pergunta desta nota — *o Δ pareado (mesma decisão, geometria mais larga)
se distingue de zero quando o dia é o bloco?*

Diferença para ``t342-blocos/blocos.py``: lá a variante era **subconjunto** da
população do pai (um piso de ATR% apaga decisões) e o contraste era população
contra população. Aqui a variante decide **as mesmas barras** com stop e alvo
mais largos, então existe par decisão a decisão e o estimando é a média dos
``Δ = r_net(variante) − r_net(pai)``. Reamostram-se **dias inteiros** com
reposição, porque decisões do mesmo dia em quatro mercados correlacionados
compartilham choque ([[KB-0010]]).

NumPy sobre janelas em memória; nada de ``Decimal`` porque nada disto é dinheiro
persistido (a fronteira ``Decimal`` fica no banco, PIPELINE §9).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Par:
    """Um par ``(mercado, barra)`` resolvido nas duas coortes."""

    rotulo: str
    dia: str
    delta: float


@dataclass(frozen=True)
class ContrastePareado:
    rotulo: str
    pares: int
    dias: int
    delta: float
    ic95: tuple[float, float]
    reamostragens_validas: int
    amostras: np.ndarray = field(repr=False, default_factory=lambda: np.empty(0))


_NAN = float("nan")


def bootstrap_pareado(
    pares: list[Par],
    *,
    reamostragens: int = 10_000,
    seed: int = 20260908,
) -> ContrastePareado:
    """Δ médio pareado e IC 95 % percentil com o **dia** como bloco."""
    rotulo = pares[0].rotulo if pares else ""
    dias = sorted({p.dia for p in pares})
    if not dias:
        return ContrastePareado(rotulo, 0, 0, _NAN, (_NAN, _NAN), 0)

    por_dia = {
        dia: np.array([p.delta for p in pares if p.dia == dia], dtype=float) for dia in dias
    }
    todos = np.concatenate([por_dia[d] for d in dias])

    rng = np.random.default_rng(seed)
    idx = np.arange(len(dias))
    amostras = np.empty(reamostragens, dtype=float)
    for i in range(reamostragens):
        escolhidos = rng.choice(idx, size=len(dias), replace=True)
        amostras[i] = float(np.concatenate([por_dia[dias[j]] for j in escolhidos]).mean())

    return ContrastePareado(
        rotulo=rotulo,
        pares=int(todos.size),
        dias=len(dias),
        delta=float(todos.mean()),
        ic95=(float(np.percentile(amostras, 2.5)), float(np.percentile(amostras, 97.5))),
        reamostragens_validas=int(amostras.size),
        amostras=amostras,
    )


def ler_csv(caminho: str) -> dict[str, list[Par]]:
    """Lê o dump ``rotulo,dia,delta_r,r_pai,r_var`` (sem cabeçalho) do ``q12``."""
    import csv

    grupos: dict[str, list[Par]] = {}
    with open(caminho, newline="", encoding="utf-8") as fh:
        for linha in csv.reader(fh):
            if not linha or not linha[0].strip():
                continue
            rotulo, dia, delta = linha[0].strip(), linha[1].strip(), float(linha[2])
            grupos.setdefault(rotulo, []).append(Par(rotulo=rotulo, dia=dia, delta=delta))
    return grupos


if __name__ == "__main__":  # pragma: no cover - manivela manual
    import sys

    for rotulo, pares in sorted(ler_csv(sys.argv[1]).items()):
        c = bootstrap_pareado(pares)
        print(
            f"{rotulo} | pares {c.pares:3d} | dias {c.dias:2d} | delta {c.delta:+.4f} | "
            f"IC95 [{c.ic95[0]:+.4f}; {c.ic95[1]:+.4f}] | reamostragens {c.reamostragens_validas}"
        )
