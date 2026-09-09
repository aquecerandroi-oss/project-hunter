"""T3.54 — quanto custa encurtar a janela de ATR de 97 barras para as 24 que o
orcamento de contexto do worker (SHADOW_CONTEXT_MINUTES = 1560 min = 26 h)
permite a uma versao que decide em 1 h.

O peso da semente decai como (13/14)^(bars-1-period): 0,26 % em 97 barras,
51,3 % em 24. A pergunta empirica e se isso move o NIVEL do ATR% medido.
Mesma serie de barras.csv, mesmo wilder_atr congelado.
"""

from __future__ import annotations

import sys
from decimal import Decimal

sys.path.insert(0, "C:/dev/project-hunter/packages/core")
sys.path.insert(0, "C:/dev/project-hunter/.claude/state/exp-drafts/t354")

from hunter_core.strategies.indicators import atr_percent, median, wilder_atr  # noqa: E402
from medir_atr import STEP, load  # noqa: E402

ATR_PERIOD = 14


def readings(bars: list[object], step: object, atr_bars: int) -> list[Decimal]:
    out: list[Decimal] = []
    for end in range(atr_bars - 1, len(bars)):
        window = bars[end - atr_bars + 1 : end + 1]
        if window[-1].open_time - window[0].open_time != step * (atr_bars - 1):  # type: ignore[attr-defined]
            continue
        atr = wilder_atr(window, ATR_PERIOD)  # type: ignore[arg-type]
        if atr is None:
            continue
        pct = atr_percent(atr, window[-1].close)  # type: ignore[attr-defined]
        if pct is not None:
            out.append(pct)
    return out


def main() -> None:
    series = load("C:/dev/project-hunter/.claude/state/exp-drafts/t354/barras.csv")
    symbols = sorted({s for s, tf in series if tf == "1h"})
    print("mercado      ATR%1h(97b)  ATR%1h(24b)  24b/97b   n97/n24")
    print("-" * 58)
    ratios: list[Decimal] = []
    for symbol in symbols:
        bars = series[(symbol, "1h")]
        long = median(readings(bars, STEP["1h"], 97))
        short = median(readings(bars, STEP["1h"], 24))
        assert long is not None and short is not None
        ratios.append(short / long)
        print(
            f"{symbol:<12} {long * 100:>10.4f}   {short * 100:>10.4f}   "
            f"{short / long:>6.4f}   "
            f"{len(readings(bars, STEP['1h'], 97))}/{len(readings(bars, STEP['1h'], 24))}"
        )
    ordered = sorted(ratios)
    print()
    print(
        f"razao 24b/97b: min {ordered[0]:.4f}  p50 {ordered[len(ordered) // 2]:.4f}  "
        f"max {ordered[-1]:.4f}"
    )
    print(f"peso da semente: 97 barras = {(Decimal(13) / 14) ** 82:.5f}   "
          f"24 barras = {(Decimal(13) / 14) ** 9:.5f}")


if __name__ == "__main__":
    main()
