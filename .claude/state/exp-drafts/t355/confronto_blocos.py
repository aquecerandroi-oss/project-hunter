"""Confronto literal com `t342-blocos/blocos.py` sobre o dado real — T3.55b.

`test_bootstrap.py` já prova a identidade numérica em população sintética. Aqui a
mesma prova roda sobre as populações reais que a nota publica: se um número da
tabela vier do atalho e não bater com o `blocos.py` original, é o `blocos.py` que
vale. Só os contrastes de menor p entram (cada chamada de `blocos.py` concatena a
população inteira 10 000 vezes e custa alguns segundos).
"""

from __future__ import annotations

import sys
import time

AQUI = "C:/dev/project-hunter/.claude/state/exp-drafts/t355"
for _p in (AQUI, "C:/dev/project-hunter/.claude/state/exp-drafts/t342-blocos"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from blocos import contraste_por_piso  # noqa: E402
from bootstrap_padroes import PISO, como_decisoes, contraste_rapido  # noqa: E402
from estatistica import carregar_marcas, carregar_universo, residuo_pareado  # noqa: E402
from padroes import SINAL  # noqa: E402

ALVOS = (
    ("tres_soldados", "1h", 1),
    ("marubozu_baixa", "1h", 1),
    ("enforcado", "15m", 4),
    ("doji", "15m", 1),
)


def main() -> None:
    universos = carregar_universo()
    marcas = carregar_marcas(universos)
    print(
        f"{'contraste':<24}{'fonte':<10}{'n_var':>7}{'exp_pai':>10}{'exp_var':>10}"
        f"{'delta':>10}{'IC baixo':>11}{'IC alto':>10}{'seg':>7}"
    )
    for nome, tf, k in ALVOS:
        u = universos[tf]
        marca = marcas[(nome, tf)]
        res = residuo_pareado(u, u.r[k], marca, SINAL[nome])
        chave = f"{nome}|{tf}|h{k}"

        t0 = time.perf_counter()
        rapido = contraste_rapido(chave, u.dia, res, marca, seed=20260909)
        t_rapido = time.perf_counter() - t0

        t0 = time.perf_counter()
        lento = contraste_por_piso(
            como_decisoes(u.dia, res, marca), PISO, reamostragens=10_000, seed=20260909
        )
        t_lento = time.perf_counter() - t0

        for rotulo, c, seg in (("atalho", rapido, t_rapido), ("blocos.py", lento, t_lento)):
            print(
                f"{chave:<24}{rotulo:<10}{c.n_variante:>7}{c.exp_pai:>10.5f}"
                f"{c.exp_variante:>10.5f}{c.delta:>10.5f}{c.ic95[0]:>11.5f}"
                f"{c.ic95[1]:>10.5f}{seg:>7.1f}"
            )
        iguais = (
            abs(rapido.delta - lento.delta) < 1e-12
            and abs(rapido.ic95[0] - lento.ic95[0]) < 1e-12
            and abs(rapido.ic95[1] - lento.ic95[1]) < 1e-12
        )
        print(f"{'':<24}{'identicos' if iguais else 'DIVERGEM':<10}")


if __name__ == "__main__":
    main()
