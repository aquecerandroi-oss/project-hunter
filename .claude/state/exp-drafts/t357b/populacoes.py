"""T3.57b — contraste de população inteira v2 × v1, reusando `t352d/duas_populacoes.py`
**sem alterar uma linha** (só o CSV muda). São duas grades de decisão sobre o mesmo
calendário e o mesmo universo de 4 mercados; o dia continua sendo o bloco."""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "t352d"))

from duas_populacoes import carregar, contraste  # noqa: E402

CSV = RAIZ / "t357b-populacoes.csv"


def main() -> None:
    linhas = carregar(CSV)
    a, b = "trendline_bounce v1", "trendline_breakout v1"
    for campo in ("r_net", "r_bruto"):
        c = contraste(linhas, a, b, campo)
        print(
            f"  {c.campo:8s} | dias {c.dias:2d} | n_v2 {c.n_a:3d} | n_v1 {c.n_b:3d} | "
            f"exp_v2 {c.exp_a:+.4f} | exp_v1 {c.exp_b:+.4f} | delta {c.delta:+.4f} | "
            f"IC95 [{c.ic95[0]:+.4f}; {c.ic95[1]:+.4f}] | reamostragens {c.reamostragens_validas}"
        )


if __name__ == "__main__":
    main()
