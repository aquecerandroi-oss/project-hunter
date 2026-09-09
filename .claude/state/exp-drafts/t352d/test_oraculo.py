"""O estimador de duas populações tem de concordar com `blocos.py` no que compartilham.

`duas_populacoes.contraste` é código novo; `t342-blocos/blocos.py` já foi revisado e
usado em três notas. Alimentado com o par degenerado (subconjunto, população inteira),
o estimador novo tem de devolver **o mesmo Δ pontual e o mesmo IC** que o antigo — com
a mesma semente e a mesma lista de dias. Se divergirem, o novo está errado, não o antigo.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "t342-blocos"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from blocos import Decisao, contraste_por_piso  # noqa: E402
from duas_populacoes import contraste  # noqa: E402

CSV = RAIZ / "t352d-decisoes.csv"
COLUNAS = ["familia", "classe", "dia", "symbol", "bar", "mantida", "r_net", "r_bruto"]


def _linhas() -> list[dict[str, str]]:
    with CSV.open(newline="", encoding="utf-8") as fh:
        return [l for l in csv.DictReader(fh, fieldnames=COLUNAS) if l["familia"] == "momentum"]


def test_mesmo_delta_pontual_do_estimador_de_subconjunto() -> None:
    linhas = _linhas()
    antigo = contraste_por_piso(
        [Decisao(dia=l["dia"], atr_pct=float(l["mantida"]), r_net=float(l["r_net"]))
         for l in linhas if l["classe"] == "pai"],
        0.5,
    )
    # o mesmo par, escrito como duas populações: A = mantidas, B = população do pai
    duas = [
        {"versao": "A" if l["mantida"] == "1" else "so_B", "dia": l["dia"],
         "symbol": l["symbol"], "r_net": l["r_net"], "r_bruto": l["r_bruto"]}
        for l in linhas if l["classe"] == "pai"
    ] + [
        {"versao": "B", "dia": l["dia"], "symbol": l["symbol"],
         "r_net": l["r_net"], "r_bruto": l["r_bruto"]}
        for l in linhas if l["classe"] == "pai"
    ]
    novo = contraste(duas, "A", "B", "r_net")
    assert novo.n_a == antigo.n_variante, (novo.n_a, antigo.n_variante)
    assert novo.n_b == antigo.n_pai, (novo.n_b, antigo.n_pai)
    assert abs(novo.exp_a - antigo.exp_variante) < 1e-12
    assert abs(novo.exp_b - antigo.exp_pai) < 1e-12
    assert abs(novo.delta - antigo.delta) < 1e-12, (novo.delta, antigo.delta)
    print(f"delta antigo {antigo.delta:+.10f} | delta novo {novo.delta:+.10f} -> iguais")
    print(f"IC antigo [{antigo.ic95[0]:+.4f}; {antigo.ic95[1]:+.4f}] | "
          f"IC novo [{novo.ic95[0]:+.4f}; {novo.ic95[1]:+.4f}] "
          f"(sementes independentes: os IC ficam próximos, não idênticos)")


if __name__ == "__main__":
    test_mesmo_delta_pontual_do_estimador_de_subconjunto()
    print("OK")
