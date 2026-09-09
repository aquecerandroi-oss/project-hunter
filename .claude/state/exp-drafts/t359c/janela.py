"""T3.59c — o Δ de expectancy que a janela de horas produz, com o dia como bloco.

Reusa ``.claude/state/exp-drafts/t342-blocos/blocos.py`` **sem alterar uma linha**,
exatamente como ``t352d/portao.py`` fez para o portão de regime: lá o subconjunto é
"atr_pct >= piso"; aqui a marca por decisão é "a filha com a janela de horas manteve
esta barra" (1) ou "a janela a removeu" (0), e o piso é 0,5. A pergunta é a mesma —
*o Δ entre a expectativa do subconjunto e a da população inteira se distingue de zero
quando dias inteiros são reamostrados com reposição?* — e o estimador tem de ser o
mesmo código, não um segundo com liberdade de discordar.

Contraste **transversal**: subconjunto contra população, dentro da mesma reamostragem.
O pareamento decisão a decisão é impossível por construção (as decisões removidas não
existem na filha) e o pareamento correto é por **(mercado, barra)** — que é o que a
`q11` faz e o que produz a coluna ``mantida`` deste CSV.

NumPy em memória; nada de Decimal (nada aqui é dinheiro persistido — PIPELINE §9).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "t342-blocos"))

from blocos import Decisao, contraste_por_piso  # noqa: E402

CSV = RAIZ / "t359c-decisoes.csv"
COLUNAS = ["braco", "classe", "dia", "symbol", "bar", "mantida", "r_net", "r_bruto"]
BRACOS = {
    "H1": "mean_reversion v12 (hours=12-15) vs v10",
    "H2": "momentum v12 (regime+hours=12-15) vs v11",
    "C1": "mean_reversion v13 (hours=13-16) vs v10",
    "C2": "momentum v13 (regime+hours=13-16) vs v11",
}


def carregar(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, fieldnames=COLUNAS))


def contraste(linhas: list[dict[str, str]], campo: str, *, com_extras: bool) -> None:
    dec = [
        Decisao(dia=l["dia"], atr_pct=float(l["mantida"]), r_net=float(l[campo]))
        for l in linhas
        if com_extras or l["classe"] == "pai"
    ]
    c = contraste_por_piso(dec, 0.5)
    rotulo = "com as extras da filha" if com_extras else "só a população do pai"
    print(
        f"  {campo:8s} | {rotulo:24s} | dias {c.dias:2d} | n_pai {c.n_pai:3d} | "
        f"n_filha {c.n_variante:3d} | exp_pai {c.exp_pai:+.4f} | exp_filha {c.exp_variante:+.4f} | "
        f"delta {c.delta:+.4f} | IC95 [{c.ic95[0]:+.4f}; {c.ic95[1]:+.4f}] | "
        f"reamostragens {c.reamostragens_validas}"
    )


def main() -> None:
    linhas = carregar(CSV)
    for braco, rotulo in BRACOS.items():
        sub = [l for l in linhas if l["braco"] == braco]
        print(f"{braco} — {rotulo}: {len(sub)} linhas")
        for campo in ("r_net", "r_bruto"):
            contraste(sub, campo, com_extras=False)
        contraste(sub, "r_net", com_extras=True)


if __name__ == "__main__":
    main()
