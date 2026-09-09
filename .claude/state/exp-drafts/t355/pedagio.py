"""A lente de pedágio (KB-0076) aplicada a cada padrão — T3.55b.

A identidade da KB-0076, verificada linha a linha em 4 472 desfechos do Lab:

    risco% = |entrada - stop| / entrada        custo_R = 0,0020 / risco%

Os 20 bps são a hipótese de custo do Lab (spread 2 + slippage 5/lado + fee
4/lado, ida e volta). O que este arquivo faz é perguntar, para cada padrão:
**a invalidação natural dele é larga o bastante para o pedágio caber?**

O R bruto por ocorrência usa saída por horizonte (4 barras), não stop-e-alvo:

    R_bruto = sinal * (C[i+4] - C[i]) / |entrada - stop|

**Isto não é backtest e não pretende ser.** Não há caminho intrabarra, então uma
ocorrência que teria batido o stop no meio do caminho aparece aqui pelo fechamento
da quarta barra. Um backtest de verdade reusa `Strategy`, `RiskEngine` e o
`PaperExecutionAdapter` — e esta task não escreve produção. O número serve para
uma pergunta só: quanto o padrão teria de acertar para pagar o pedágio que a
própria invalidação dele cobra.
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

import padroes_kb0080 as kb  # noqa: E402
from bootstrap_padroes import media_por_blocos  # noqa: E402
from padroes import NOMES, SINAL  # noqa: E402

CUSTO_BPS = 0.0020
HORIZONTE = 4


def main(
    sufixo: str = "", nomes: tuple[str, ...] = NOMES, sinal: dict[str, int] | None = None
) -> None:
    sinal = SINAL if sinal is None else sinal
    grupos: dict[tuple[str, str], list[dict[str, str]]] = {}
    with open(f"{AQUI}/ocorrencias{sufixo}.csv", newline="", encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            grupos.setdefault((linha["nome"], linha["tf"]), []).append(linha)

    print(
        f"custo assumido {CUSTO_BPS * 1e4:.0f} bps ida-e-volta | saida por horizonte "
        f"{HORIZONTE} barras | sem caminho intrabarra"
    )
    print(
        f"{'padrao':<16}{'tf':>5}{'n':>6}{'deg':>5}{'stop ATR':>10}{'risco%':>9}{'custo_R':>9}"
        f"{'R bruto':>9}{'R liq.':>9}{'IC baixo':>10}{'IC alto':>9}{'acerto%':>9}"
    )
    for tf in ("15m", "1h"):
        for nome in nomes:
            linhas = grupos.get((nome, tf), [])
            if not linhas:
                print(
                    f"{nome:<16}{tf:>5}{0:>6}{'-':>5}{'-':>10}{'-':>9}{'-':>9}{'-':>9}{'-':>9}"
                    f"{'-':>10}{'-':>9}{'-':>9}"
                )
                continue
            direcao = sinal[nome]
            todos = len(linhas)
            # Invalidação colada na entrada: `entrada == stop` (o enforcado fecha na
            # própria máxima). Risco zero não é risco pequeno, é uma operação que não
            # existe — sai da conta e é contada em separado, nunca virando NaN calado.
            linhas = [x for x in linhas if float(x["risco_frac"]) > 0]
            degenerados = todos - len(linhas)
            if not linhas:
                print(f"{nome:<16}{tf:>5}{todos:>6}{'stop=entrada em todas':>60}")
                continue
            stop_atr = [float(x["stop_atr"]) for x in linhas]
            risco = np.array([float(x["risco_frac"]) for x in linhas])
            atr_pct = np.array([float(x["atr_pct"]) for x in linhas])
            r_atr = np.array([float(x[f"r{HORIZONTE}"]) for x in linhas])
            dias = np.array([x["dia"] for x in linhas])
            bruto = direcao * r_atr * atr_pct / risco
            custo = CUSTO_BPS / risco
            liquido = bruto - custo
            media, ic = media_por_blocos(dias, liquido)
            print(
                f"{nome:<16}{tf:>5}{len(linhas):>6}{degenerados:>5}{median(stop_atr):>10.2f}"
                f"{median(risco) * 100:>9.3f}{median(custo):>9.3f}{bruto.mean():>9.3f}"
                f"{media:>9.3f}{ic[0]:>10.3f}{ic[1]:>9.3f}{(bruto > 0).mean() * 100:>9.1f}"
            )


if __name__ == "__main__":
    import sys as _sys

    if "--kb0080" in _sys.argv:
        main(sufixo="-a", nomes=kb.NOMES, sinal=kb.SINAL)
    else:
        main()
