"""T3.66 / EXP-0024 — bootstrap por blocos de dia para dois estimadores e Holm.

Não é código de produção: mora em ``.claude/state/exp-drafts/`` e serve às duas
perguntas pré-registradas em `EXP-0024-controle-contrarian.md`:

* **(a)** ``Δ = média(R_decisão − R_controle)`` se distingue de zero? — a unidade é a
  **diferença pareada** na mesma decisão, e o bloco é o **dia**;
* **(b)** ``expectancy(r_ex_funding) > 0``? — a unidade é o R da decisão, mesmo bloco.

Os dois são o mesmo estimador ("média de uma quantidade por decisão, reamostrando
dias inteiros com reposição"), então há **uma** função e não duas: dar duas
implementações a um contrato numérico é dar a elas liberdade de discordar
(a disciplina de `t357b/pareado.py`).

Por que bloco de dia: decisões do mesmo dia partilham regime e, em mercados
correlacionados, choque — tratá-las como independentes estreita o intervalo
artificialmente ([[KB-0010]], [[KB-0051]]). Reamostram-se **dias inteiros**; dentro
do dia, todas as decisões viajam juntas (é isso que "conjuntos entre mercados"
quer dizer).

``p`` é bicaudal, com piso ``2/B``: um bootstrap nunca prova ``p = 0``.

NumPy sobre janelas em memória; nada de ``Decimal`` aqui, porque nada disto é
dinheiro persistido — a fronteira ``Decimal`` é o banco (PIPELINE §9).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["Estimativa", "holm", "media_por_blocos"]


@dataclass(frozen=True)
class Estimativa:
    """O resultado de um contraste: ponto, IC, ``p`` e o que entrou nele."""

    dias: int
    n: int
    ponto: float
    ic95: tuple[float, float]
    p_bicaudal: float
    reamostragens_validas: int


def media_por_blocos(
    observacoes: list[tuple[str, float]],
    *,
    reamostragens: int = 10_000,
    seed: int = 20260909,
) -> Estimativa:
    """Média de ``valor`` com IC por blocos de dia.

    ``observacoes`` = ``(dia, valor)``. O ``valor`` é a diferença pareada no teste
    (a) e o R da decisão no teste (b) — o estimador não sabe a diferença, e é
    exatamente por isso que ele é um só.

    Amostra vazia devolve ``nan`` em toda parte: **nunca** 0,0, que seria um
    número inventado.
    """
    if not observacoes:
        nan = float("nan")
        return Estimativa(0, 0, nan, (nan, nan), nan, 0)

    dias = sorted({d for d, _ in observacoes})
    por_dia = {dia: np.array([v for d, v in observacoes if d == dia], dtype=float) for dia in dias}
    todos = np.concatenate([por_dia[d] for d in dias])

    rng = np.random.default_rng(seed)
    idx = np.arange(len(dias))
    medias: list[float] = []
    for _ in range(reamostragens):
        escolhidos = rng.choice(idx, size=len(dias), replace=True)
        amostra = np.concatenate([por_dia[dias[i]] for i in escolhidos])
        if amostra.size == 0:
            continue
        medias.append(float(amostra.mean()))

    arr = np.array(medias, dtype=float)
    if arr.size == 0:
        nan = float("nan")
        return Estimativa(len(dias), int(todos.size), float(todos.mean()), (nan, nan), nan, 0)

    lado = float(min((arr <= 0).mean(), (arr >= 0).mean()))
    p = min(1.0, max(2.0 * lado, 2.0 / arr.size))
    return Estimativa(
        dias=len(dias),
        n=int(todos.size),
        ponto=float(todos.mean()),
        ic95=(float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))),
        p_bicaudal=p,
        reamostragens_validas=int(arr.size),
    )


def holm(ps: dict[str, float]) -> dict[str, float]:
    """Holm–Bonferroni: ``p`` ajustado, monótono, nunca acima de 1.

    Cópia deliberada de `t357b/pareado.py::holm` — o mesmo contrato numérico com
    a mesma aritmética, para que dois relatórios do mesmo dia não possam
    discordar sobre o que "ajustado" significa.
    """
    ordem = sorted(ps.items(), key=lambda kv: kv[1])
    m = len(ordem)
    ajustado: dict[str, float] = {}
    corrente = 0.0
    for i, (nome, p) in enumerate(ordem):
        corrente = max(corrente, min(1.0, (m - i) * p))
        ajustado[nome] = corrente
    return ajustado
