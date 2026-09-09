"""Controles e poder: o "nada" da tabela principal é um nada medido? — T3.55b.

Um resultado nulo só vale se a máquina que o produziu conseguisse ver alguma
coisa. Duas provas, no dado real, com o mesmo bootstrap e a mesma baseline:

- **controle positivo (trapaça deliberada)**: um "padrão" que olha a barra
  seguinte. Não existe, não é implementável e é exatamente o vazamento que os
  estudos de candlestick cometem sem perceber. Tem de acender.
- **controle positivo raro**: a mesma trapaça restrita a `n` comparável ao de um
  padrão de verdade (~600 em 15 m, ~150 em 1 h) — mostra que o poder existe no
  tamanho de amostra que os padrões realmente têm.
- **controle negativo**: marca sorteada com o mesmo `n`. Tem de ficar em zero.

Depois, a **resolução**: metade da largura do IC95 de cada padrão, convertida em
R pela distância de stop natural dele, ao lado do `custo_R` que essa mesma
distância cobra. Se a resolução for menor que o custo, o estudo tinha poder para
enxergar uma vantagem que pagasse o pedágio — e não enxergou.
"""

from __future__ import annotations

import csv
import sys
from statistics import median

import numpy as np

AQUI = "C:/dev/project-hunter/.claude/state/exp-drafts/t355"
for _p in (AQUI, "C:/dev/project-hunter/.claude/state/exp-drafts/t342-blocos"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bootstrap_padroes import contraste_rapido  # noqa: E402
from estatistica import TFS, carregar_marcas, carregar_universo, residuo_pareado  # noqa: E402
from padroes import NOMES, SINAL  # noqa: E402

HORIZONTE = 4
CUSTO_BPS = 0.0020


def main() -> None:
    universos = carregar_universo()
    marcas = carregar_marcas(universos)
    rng = np.random.default_rng(20260909)

    print("A. controles (horizonte 4 barras, mesma baseline pareada)")
    print(f"{'controle':<22}{'tf':>5}{'n':>7}{'delta':>10}{'IC baixo':>11}{'IC alto':>10}{'p':>9}")
    for tf in TFS:
        u = universos[tf]
        r = u.r[HORIZONTE]
        alvo = int(marcas[("martelo", tf)].sum())
        futuro = u.r[1] > 0
        indices_bons = np.flatnonzero(r > 0)
        raro = np.zeros(r.size, dtype=bool)
        raro[rng.choice(indices_bons, size=alvo, replace=False)] = True
        aleatorio = np.zeros(r.size, dtype=bool)
        aleatorio[rng.choice(r.size, size=alvo, replace=False)] = True
        for rotulo, marca in (
            ("trapaca_futuro", futuro),
            ("trapaca_rara", raro),
            ("aleatorio", aleatorio),
        ):
            res = residuo_pareado(u, r, marca, 1)
            c = contraste_rapido(rotulo, u.dia, res, marca)
            print(
                f"{rotulo:<22}{tf:>5}{c.n_variante:>7}{c.delta:>10.4f}"
                f"{c.ic95[0]:>11.4f}{c.ic95[1]:>10.4f}{c.p_valor:>9.4f}"
            )

    risco_mediano: dict[tuple[str, str], float] = {}
    stop_mediano: dict[tuple[str, str], float] = {}
    grupos: dict[tuple[str, str], list[dict[str, str]]] = {}
    with open(f"{AQUI}/ocorrencias.csv", newline="", encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            grupos.setdefault((linha["nome"], linha["tf"]), []).append(linha)
    for chave, linhas in grupos.items():
        validos = [x for x in linhas if float(x["risco_frac"]) > 0]
        if validos:
            risco_mediano[chave] = median(float(x["risco_frac"]) for x in validos)
            stop_mediano[chave] = median(float(x["stop_atr"]) for x in validos)

    print()
    print("B. resolucao contra pedagio (horizonte 4 barras)")
    print(
        f"{'padrao':<16}{'tf':>5}{'n':>6}{'meia largura ATR':>18}{'stop ATR':>10}"
        f"{'resolucao R':>13}{'custo_R':>9}{'ve o suficiente?':>18}"
    )
    for tf in TFS:
        u = universos[tf]
        for nome in NOMES:
            marca = marcas[(nome, tf)]
            if not marca.any() or (nome, tf) not in risco_mediano:
                continue
            res = residuo_pareado(u, u.r[HORIZONTE], marca, SINAL[nome])
            c = contraste_rapido(f"{nome}|{tf}", u.dia, res, marca)
            meia = (c.ic95[1] - c.ic95[0]) / 2
            resolucao = meia / stop_mediano[(nome, tf)]
            custo = CUSTO_BPS / risco_mediano[(nome, tf)]
            print(
                f"{nome:<16}{tf:>5}{c.n_variante:>6}{meia:>18.4f}"
                f"{stop_mediano[(nome, tf)]:>10.2f}{resolucao:>13.3f}{custo:>9.3f}"
                f"{('sim' if resolucao < custo else 'nao'):>18}"
            )


if __name__ == "__main__":
    main()
