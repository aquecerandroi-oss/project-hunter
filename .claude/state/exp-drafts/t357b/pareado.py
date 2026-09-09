"""T3.57b — Δ pareado por (mercado, barra) com o dia como bloco, e Holm sobre a família.

Por que um terceiro estimador e não `blocos.py` nem `duas_populacoes.py`:

* `t342-blocos/blocos.py` responde "subconjunto contra a população que o contém" —
  cada decisão entra em um dos dois lados, nunca nos dois. Aqui **a mesma barra
  aparece nas duas versões** e o par existe, então usá-lo jogaria fora a informação
  que torna o contraste forte (o ruído comum da barra cancela);
* `t352d/duas_populacoes.py` responde "duas populações sobre o mesmo calendário" e é
  reusado **sem alteração** para o contraste de população inteira (v2 × v1) neste
  mesmo dia um. Ele também não pareia.

Aqui a unidade é a diferença ``r_v2 − r_v1`` na **mesma** (mercado, barra), e o
bloco continua sendo o **dia** (decisões do mesmo dia partilham regime e choque em
quatro mercados correlacionados — KB-0010).

`p` é bootstrap bicaudal (fração de reamostragens do outro lado de zero, dobrada,
com o piso de 1/reamostragens: um bootstrap nunca prova `p = 0`), e Holm corrige a
família de contrastes que este dia um publica.

NumPy em memória; nada de Decimal (PIPELINE §9: a fronteira Decimal é o banco).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
CSV = RAIZ / "t357b-pareado.csv"
COLUNAS = ["dia", "symbol", "bar", "r_v1", "r_v2", "motivo_v1", "r_bruto_v1", "r_bruto_v2"]


@dataclass(frozen=True)
class DeltaPareado:
    dias: int
    n_pares: int
    exp_v1: float
    exp_v2: float
    delta: float
    ic95: tuple[float, float]
    p_bootstrap: float
    reamostragens_validas: int


def delta_pareado(
    pares: list[tuple[str, float, float]],
    *,
    reamostragens: int = 10_000,
    seed: int = 20260909,
) -> DeltaPareado:
    """`pares` = (dia, r_v1, r_v2). Reamostra **dias inteiros** com reposição."""
    dias = sorted({d for d, _, _ in pares})
    por_dia = {dia: np.array([b - a for d, a, b in pares if d == dia], dtype=float) for dia in dias}
    v1 = np.array([a for _, a, _ in pares], dtype=float)
    v2 = np.array([b for _, _, b in pares], dtype=float)

    rng = np.random.default_rng(seed)
    idx = np.arange(len(dias))
    deltas: list[float] = []
    for _ in range(reamostragens):
        esc = rng.choice(idx, size=len(dias), replace=True)
        amostra = np.concatenate([por_dia[dias[i]] for i in esc])
        if amostra.size == 0:
            continue
        deltas.append(float(amostra.mean()))

    arr = np.array(deltas, dtype=float)
    if arr.size == 0:
        nan = float("nan")
        return DeltaPareado(len(dias), len(pares), nan, nan, nan, (nan, nan), nan, 0)
    ponto = float(v2.mean() - v1.mean())
    lado = float(min((arr <= 0).mean(), (arr >= 0).mean()))
    p = min(1.0, max(2.0 * lado, 2.0 / arr.size))
    return DeltaPareado(
        dias=len(dias),
        n_pares=len(pares),
        exp_v1=float(v1.mean()),
        exp_v2=float(v2.mean()),
        delta=ponto,
        ic95=(float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))),
        p_bootstrap=p,
        reamostragens_validas=int(arr.size),
    )


def holm(ps: dict[str, float]) -> dict[str, float]:
    """Holm–Bonferroni: p ajustado, monótono, nunca acima de 1."""
    ordem = sorted(ps.items(), key=lambda kv: kv[1])
    m = len(ordem)
    ajustado: dict[str, float] = {}
    corrente = 0.0
    for i, (nome, p) in enumerate(ordem):
        corrente = max(corrente, min(1.0, (m - i) * p))
        ajustado[nome] = corrente
    return ajustado


def carregar(caminho: Path) -> list[tuple[str, float, float]]:
    with caminho.open(newline="", encoding="utf-8") as fh:
        return [
            (l["dia"], float(l["r_v1"]), float(l["r_v2"]))
            for l in csv.DictReader(fh, fieldnames=COLUNAS)
        ]


def main() -> None:
    pares = carregar(CSV)
    c = delta_pareado(pares)
    print(
        f"pareado por (mercado, barra) | dias {c.dias} | pares {c.n_pares} | "
        f"exp_v1 {c.exp_v1:+.4f} | exp_v2 {c.exp_v2:+.4f} | delta {c.delta:+.4f} | "
        f"IC95 [{c.ic95[0]:+.4f}; {c.ic95[1]:+.4f}] | p {c.p_bootstrap:.4f} | "
        f"reamostragens {c.reamostragens_validas}"
    )


if __name__ == "__main__":
    main()
