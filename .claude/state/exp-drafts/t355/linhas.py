"""Distância de cada barra às linhas de tendência vivas — T3.55b, recorte condicional.

Usa `hunter_indicators.patterns.scan` **congelado**, com `DEFAULT_PARAMS` (T3.34),
exatamente como `infra/scripts/render_operations.py` §3: janela de 96 baldes
contíguos terminando na barra, corte aplicado uma vez no topo (`as_of = 95`).
Nenhuma vela posterior participa.

Duas escolhas declaradas:

- **a régua é o ATR de dentro da varredura** (`scan.atr[95]`), não o ATR da corrida
  longa. A recursão de Wilder recomeça na janela de 96, então os dois números
  diferem um pouco; a tolerância que decide "encostou na linha" tem de ser a mesma
  régua que desenhou a linha.
- **as 95 primeiras barras de cada corrida não têm varredura** e saem do recorte
  condicional (ficam no contraste principal). Encolher a janela para elas seria
  uma segunda geometria com o mesmo nome.

Uso: `uv run python linhas.py 15m [A|B]` — um timeframe por chamada e, em 15 m,
metade dos mercados por chamada (7 ms por barra × 45 360 barras estoura o teto de
5 min por comando desta sessão). As metades são disjuntas por índice par/ímpar do
nome ordenado e são concatenadas na leitura.
"""

from __future__ import annotations

import csv
import sys
import time
from decimal import Decimal

AQUI = "C:/dev/project-hunter/.claude/state/exp-drafts/t355"
for _p in (
    AQUI,
    "C:/dev/project-hunter/packages/core",
    "C:/dev/project-hunter/packages/indicators",
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from medir import MAIOR, PASSO, TF, carregar, corridas  # noqa: E402

from hunter_indicators.patterns.scan import DEFAULT_PARAMS, scan  # noqa: E402

JANELA = 96


def main() -> None:
    tf = sys.argv[1]
    parte = sys.argv[2] if len(sys.argv) > 2 else ""
    series = carregar(f"{AQUI}/barras.csv")
    simbolos = sorted({s for s, _ in series})
    metade = {s for k, s in enumerate(simbolos) if (k % 2 == 0) == (parte == "A")}
    aceitos = set(simbolos) if not parte else metade
    saida = open(
        f"{AQUI}/linhas-{tf}{parte and '-' + parte}.csv", "w", newline="", encoding="utf-8"
    )
    escritor = csv.writer(saida)
    escritor.writerow(["symbol", "tf", "ts", "n_linhas", "dist_sup", "dist_res"])
    t0 = time.perf_counter()
    n = com_linha = 0
    for (symbol, tf_atual), bars in sorted(series.items()):
        if tf_atual != tf or symbol not in aceitos:
            continue
        for corrida in corridas(bars, PASSO[tf]):
            for i in range(JANELA - 1, len(corrida) - MAIOR):
                janela = corrida[i - JANELA + 1 : i + 1]
                s = scan(janela, timeframe=TF[tf], params=DEFAULT_PARAMS, as_of=JANELA - 1)
                escala = s.atr[JANELA - 1]
                if escala is None or escala <= 0:
                    continue
                barra = corrida[i]
                melhor: dict[str, Decimal | None] = {"support": None, "resistance": None}
                for linha in s.lines:
                    alvo = barra.low if linha.kind.value == "support" else barra.high
                    d = abs(alvo - linha.projected(JANELA - 1)) / escala
                    atual = melhor[linha.kind.value]
                    if atual is None or d < atual:
                        melhor[linha.kind.value] = d
                escritor.writerow(
                    [
                        symbol,
                        tf,
                        barra.open_time.isoformat(),
                        len(s.lines),
                        "" if melhor["support"] is None else f"{melhor['support']:.6f}",
                        "" if melhor["resistance"] is None else f"{melhor['resistance']:.6f}",
                    ]
                )
                n += 1
                com_linha += 1 if s.lines else 0
    saida.close()
    seg = time.perf_counter() - t0
    print(
        f"{tf}: {n} barras varridas, {com_linha} com ao menos uma linha, {seg:.1f} s "
        f"({seg / max(n, 1) * 1000:.1f} ms/barra)"
    )


if __name__ == "__main__":
    main()
