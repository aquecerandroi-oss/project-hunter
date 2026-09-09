"""T3.52d/T3.54c — contraste transversal entre DUAS populações, com o dia como bloco.

`t342-blocos/blocos.py` responde "subconjunto contra a população que o contém" e é
reusado sem alteração no portão de regime (`portao.py`). Aqui a pergunta é outra:
`mean_reversion_h1 v1` **não** é subconjunto de `mean_reversion v10` — são duas
grades de decisão diferentes sobre o mesmo calendário. O estimador tem de reamostrar
**dias** e, dentro do dia reamostrado, levar as decisões das duas populações juntas;
Δ = média(A) − média(B) na mesma reamostragem. Reamostragem em que uma das duas fica
vazia não tem Δ e é descartada (nunca contada como zero).

Oráculo de conferência (`test_oraculo.py`): alimentado com "subconjunto" e "população
inteira", este estimador tem de devolver o mesmo Δ pontual que `blocos.py` devolve
para o mesmo par — é a prova de que os dois não divergem no que compartilham.

NumPy em memória; nada de Decimal (PIPELINE §9: a fronteira Decimal é o banco).
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
CSV = RAIZ / "t352d-h1-vs-v10.csv"
COLUNAS = ["versao", "dia", "symbol", "r_net", "r_bruto"]


@dataclass(frozen=True)
class Contraste:
    campo: str
    dias: int
    n_a: int
    n_b: int
    exp_a: float
    exp_b: float
    delta: float
    ic95: tuple[float, float]
    reamostragens_validas: int


def _por_dia(linhas: list[dict[str, str]], versao: str, campo: str) -> dict[str, np.ndarray]:
    saida: dict[str, list[float]] = {}
    for l in linhas:
        if l["versao"] == versao:
            saida.setdefault(l["dia"], []).append(float(l[campo]))
    return {d: np.array(v, dtype=float) for d, v in saida.items()}


def contraste(
    linhas: list[dict[str, str]],
    versao_a: str,
    versao_b: str,
    campo: str,
    *,
    reamostragens: int = 10_000,
    seed: int = 20260909,
) -> Contraste:
    a = _por_dia(linhas, versao_a, campo)
    b = _por_dia(linhas, versao_b, campo)
    dias = sorted(set(a) | set(b))
    vazio = np.empty(0, dtype=float)

    rng = np.random.default_rng(seed)
    idx = np.arange(len(dias))
    deltas: list[float] = []
    for _ in range(reamostragens):
        esc = rng.choice(idx, size=len(dias), replace=True)
        ra = np.concatenate([a.get(dias[i], vazio) for i in esc]) if len(esc) else vazio
        rb = np.concatenate([b.get(dias[i], vazio) for i in esc]) if len(esc) else vazio
        if ra.size == 0 or rb.size == 0:
            continue  # sem as duas pontas não há Δ a medir
        deltas.append(float(ra.mean() - rb.mean()))

    arr = np.array(deltas, dtype=float)
    ic = (
        (float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5)))
        if arr.size
        else (float("nan"), float("nan"))
    )
    todos_a = np.concatenate(list(a.values())) if a else vazio
    todos_b = np.concatenate(list(b.values())) if b else vazio
    return Contraste(
        campo=campo,
        dias=len(dias),
        n_a=int(todos_a.size),
        n_b=int(todos_b.size),
        exp_a=float(todos_a.mean()),
        exp_b=float(todos_b.mean()),
        delta=float(todos_a.mean() - todos_b.mean()),
        ic95=ic,
        reamostragens_validas=int(arr.size),
    )


def carregar(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, fieldnames=COLUNAS))


QUATRO = {"ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"}


def main() -> None:
    linhas = carregar(CSV)
    a, b = "mean_reversion_h1 v1", "mean_reversion v10"
    for rotulo, sub in (
        ("16 mercados (h1) vs 4 (v10) — universos diferentes", linhas),
        ("só os 4 mercados que as duas correram", [l for l in linhas if l["symbol"] in QUATRO]),
    ):
        print(rotulo)
        for campo in ("r_net", "r_bruto"):
            c = contraste(sub, a, b, campo)
            print(
                f"  {c.campo:8s} | dias {c.dias:2d} | n_h1 {c.n_a:3d} | n_v10 {c.n_b:3d} | "
                f"exp_h1 {c.exp_a:+.4f} | exp_v10 {c.exp_b:+.4f} | delta {c.delta:+.4f} | "
                f"IC95 [{c.ic95[0]:+.4f}; {c.ic95[1]:+.4f}] | reamostragens {c.reamostragens_validas}"
            )


if __name__ == "__main__":
    main()
