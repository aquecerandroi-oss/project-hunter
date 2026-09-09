"""T3.57b — a familia de contrastes do dia um da `trendline_bounce v1`, com Holm.

Três perguntas, três contrastes, uma correção de multiplicidade (EXP-0022 item 5,
o mesmo desenho do EXP-0007):

1. **pareado** por (mercado, barra) sobre as 24 barras em que as duas decidiram;
2. **pareado condicionado** às barras em que a v1 saiu por `invalidated` — é o teste
   direto da tese "a invalidação adianta a perda, não a cria" (KB-0006);
3. **população inteira** v2 × v1 (`t352d/duas_populacoes.py`, sem alteração), que
   responde outra coisa: a versão como um todo, com a diferença de população junto.

O `p` do item 3 vem do mesmo bootstrap de dias que o intervalo dele.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "t352d"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from duas_populacoes import carregar as carregar_pop  # noqa: E402
from duas_populacoes import contraste as contraste_pop  # noqa: E402
from pareado import COLUNAS, delta_pareado, holm  # noqa: E402


def main() -> None:
    with (RAIZ / "t357b-pareado.csv").open(newline="", encoding="utf-8") as fh:
        linhas = list(csv.DictReader(fh, fieldnames=COLUNAS))
    todos = [(l["dia"], float(l["r_v1"]), float(l["r_v2"])) for l in linhas]
    inval = [
        (l["dia"], float(l["r_v1"]), float(l["r_v2"]))
        for l in linhas
        if l["motivo_v1"] == "invalidated"
    ]

    ps: dict[str, float] = {}
    for nome, pares in (("1 pareado (todas)", todos), ("2 pareado (v1 invalidou)", inval)):
        c = delta_pareado(pares)
        ps[nome] = c.p_bootstrap
        print(
            f"{nome:26s} | dias {c.dias:2d} | pares {c.n_pares:2d} | exp_v1 {c.exp_v1:+.4f} | "
            f"exp_v2 {c.exp_v2:+.4f} | delta {c.delta:+.4f} | "
            f"IC95 [{c.ic95[0]:+.4f}; {c.ic95[1]:+.4f}] | p {c.p_bootstrap:.4f}"
        )

    pop = carregar_pop(RAIZ / "t357b-populacoes.csv")
    c3 = contraste_pop(pop, "trendline_bounce v1", "trendline_breakout v1", "r_net")
    # p bicaudal do mesmo bootstrap, pelo intervalo: refaz a distribuicao com a mesma semente
    ic = c3.ic95
    dentro = ic[0] <= 0.0 <= ic[1]
    # NAO entra no Holm: `duas_populacoes.contraste` e reusado SEM ALTERACAO e nao
    # devolve a distribuicao, logo nao ha p dele para corrigir. Publica-se o IC, que
    # e o que o estimador realmente mede — inventar um p aqui seria inventar um numero.
    print(
        f"{'3 populacao inteira':26s} | dias {c3.dias:2d} | n_v2 {c3.n_a:2d} | n_v1 {c3.n_b:2d} | "
        f"delta {c3.delta:+.4f} | IC95 [{ic[0]:+.4f}; {ic[1]:+.4f}] | "
        f"{'cruza zero' if dentro else 'nao cruza zero'}"
    )

    print("\nHolm sobre os 2 contrastes pareados (o de populacao publica so o IC):")
    for nome, p in sorted(holm(ps).items()):
        print(f"  {nome:26s} p_holm {p:.4f}")


if __name__ == "__main__":
    main()
