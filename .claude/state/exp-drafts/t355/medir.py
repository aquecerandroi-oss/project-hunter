"""Varre `barras.csv` e escreve `universo.csv` + `ocorrencias.csv` — T3.55b.

Uma linha de `universo.csv` por barra **utilizável**: tem régua (`ATR[i-1]` e
`ATR[i]` existem) e tem futuro completo dentro da mesma corrida contígua
(`i + 16` existe). Uma linha de `ocorrencias.csv` por padrão detectado numa
barra utilizável.

Três recusas deliberadas:

- **corrida contígua, nunca costurada.** A exportação tem buracos (2 961 de 2 976
  baldes de 15 m; o coletor caiu). Emendar as pontas produziria uma barra vizinha
  que não é vizinha e um ATR que atravessa o buraco. A série de cada mercado é
  quebrada em corridas contíguas e cada corrida é varrida sozinha.
- **retorno futuro só quando ele existe inteiro.** As 16 últimas barras de cada
  corrida saem do estudo — do padrão **e** da baseline, senão a baseline media
  uma janela que o padrão não teve.
- **a régua do retorno é `ATR[i]`**, o ATR conhecido no fechamento da decisão;
  a régua do padrão é `ATR[i-n]` (`padroes.py` §4). São perguntas diferentes:
  "quanto o mercado andou" e "quão grande é esta barra".
"""

from __future__ import annotations

import csv
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

AQUI = "C:/dev/project-hunter/.claude/state/exp-drafts/t355"
for _p in (
    AQUI,
    "C:/dev/project-hunter/packages/core",
    "C:/dev/project-hunter/packages/indicators",
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from padroes import SINAL, Deteccao, varrer  # noqa: E402

from hunter_core.domain.enums import Timeframe  # noqa: E402
from hunter_core.strategies.aggregate import Bar  # noqa: E402
from hunter_core.strategies.indicators import CONTEXT  # noqa: E402
from hunter_indicators.patterns.scale import atr_series  # noqa: E402

PASSO = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1)}
TF = {"15m": Timeframe.M15, "1h": Timeframe.H1}
HORIZONTES = (1, 4, 16)
MAIOR = max(HORIZONTES)


def carregar(caminho: str) -> dict[tuple[str, str], list[Bar]]:
    series: dict[tuple[str, str], list[Bar]] = {}
    with open(caminho, newline="", encoding="utf-8") as fh:
        for linha in csv.DictReader(
            linha_bruta for linha_bruta in fh if linha_bruta.count(",") >= 7
        ):
            tf = linha["tf"]
            if tf not in PASSO:
                continue
            inicio = datetime.fromisoformat(linha["bucket"])
            series.setdefault((linha["symbol"], tf), []).append(
                Bar(
                    open_time=inicio,
                    close_time=inicio + PASSO[tf],
                    open=Decimal(linha["o"]),
                    high=Decimal(linha["h"]),
                    low=Decimal(linha["l"]),
                    close=Decimal(linha["c"]),
                    volume=Decimal(linha["v"]),
                )
            )
    for chave in series:
        series[chave].sort(key=lambda b: b.open_time)
    return series


def corridas(bars: list[Bar], passo: timedelta) -> list[list[Bar]]:
    """Quebra a série nos buracos: cada pedaço é contíguo por construção."""
    saida: list[list[Bar]] = []
    atual: list[Bar] = []
    for bar in bars:
        if atual and bar.open_time - atual[-1].open_time != passo:
            saida.append(atual)
            atual = []
        atual.append(bar)
    if atual:
        saida.append(atual)
    return saida


Varredor = Callable[[list[Bar], list[Decimal | None]], list[Deteccao]]


def main(varrer_fn: Varredor = varrer, sufixo: str = "") -> None:
    series = carregar(f"{AQUI}/barras.csv")
    universo = open(f"{AQUI}/universo{sufixo}.csv", "w", newline="", encoding="utf-8")
    ocorr = open(f"{AQUI}/ocorrencias{sufixo}.csv", "w", newline="", encoding="utf-8")
    wu = csv.writer(universo)
    wo = csv.writer(ocorr)
    wu.writerow(["symbol", "tf", "ts", "dia", "hora", "close", "atr_pct", "r1", "r4", "r16"])
    wo.writerow(
        [
            "symbol",
            "tf",
            "ts",
            "dia",
            "hora",
            "nome",
            "direcao",
            "barras",
            "entrada",
            "stop",
            "stop_atr",
            "risco_frac",
            "atr_pct",
            "r1",
            "r4",
            "r16",
        ]
    )
    n_bar = n_ocorr = n_corridas = 0
    for (symbol, tf), bars in sorted(series.items()):
        passo = PASSO[tf]
        for corrida in corridas(bars, passo):
            n_corridas += 1
            if len(corrida) < 20 + MAIOR:
                continue
            atr = list(atr_series(corrida, timeframe=TF[tf]))
            usavel: dict[int, tuple[Decimal, Decimal, Decimal, Decimal]] = {}
            for i in range(len(corrida) - MAIOR):
                escala = atr[i]
                if escala is None or escala <= 0:
                    continue
                fechamento = corrida[i].close
                if fechamento <= 0:
                    continue
                with localcontext(CONTEXT):
                    atr_pct = escala / fechamento
                    retornos = tuple(
                        (corrida[i + k].close - fechamento) / escala for k in HORIZONTES
                    )
                usavel[i] = (atr_pct, *retornos)  # type: ignore[assignment]
                ts = corrida[i].open_time
                wu.writerow(
                    [
                        symbol,
                        tf,
                        ts.isoformat(),
                        ts.date().isoformat(),
                        ts.hour,
                        fechamento,
                        f"{atr_pct:.10f}",
                        *[f"{r:.8f}" for r in retornos],
                    ]
                )
                n_bar += 1
            for d in varrer_fn(corrida, atr):
                if d.idx not in usavel:
                    continue
                atr_pct, r1, r4, r16 = usavel[d.idx]
                with localcontext(CONTEXT):
                    risco = abs(d.entrada - d.stop) / d.entrada
                ts = corrida[d.idx].open_time
                wo.writerow(
                    [
                        symbol,
                        tf,
                        ts.isoformat(),
                        ts.date().isoformat(),
                        ts.hour,
                        d.nome,
                        d.direcao,
                        d.barras,
                        d.entrada,
                        d.stop,
                        f"{d.stop_atr:.6f}",
                        f"{risco:.10f}",
                        f"{atr_pct:.10f}",
                        f"{r1:.8f}",
                        f"{r4:.8f}",
                        f"{r16:.8f}",
                    ]
                )
                n_ocorr += 1
    universo.close()
    ocorr.close()
    print(f"corridas {n_corridas} | barras usaveis {n_bar} | ocorrencias {n_ocorr}")
    print(f"sinais declarados: {len(SINAL)} padroes")


if __name__ == "__main__":
    main()
