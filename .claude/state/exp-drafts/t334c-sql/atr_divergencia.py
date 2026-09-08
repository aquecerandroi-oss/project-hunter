"""T3.34c — as DUAS series de ATR de Wilder que a `trendline_breakout_v1` usa.

Ressalva 3 da revisao de c9691d0. Nao e bug: e uma consequencia declarada de
`atr_bars = 97` (a leitura oficial, que escala stop, risco e a porta de ATR%) e
`pattern_bars = 96` (a janela da geometria, onde `tl_pivots.atr_series` calcula a
sua PROPRIA serie para escalar a proeminencia dos pivos e as distancias dos
eventos). Sementes diferentes, um passo de suavizacao a mais numa delas.

Serie sintetica com valores conferidos a mao para que a divergencia seja um
numero e nao uma frase.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, getcontext

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.indicators import wilder_atr
from hunter_core.strategies.tl_pivots import atr_series

getcontext().prec = 28
STEP = timedelta(seconds=900)
T0 = datetime(2026, 8, 1, tzinfo=UTC)


def bars(n: int) -> list[Bar]:
    """Uma onda determinista: amplitude verdadeira conhecida, sem gaps."""
    out: list[Bar] = []
    close = Decimal("100")
    for i in range(n):
        swing = Decimal(1 + (i * 7) % 5)  # 1..5, ciclo de 5 barras
        high = close + swing
        low = close - swing
        open_time = T0 + i * STEP
        out.append(
            Bar(
                open_time=open_time,
                close_time=open_time + STEP,
                open=close,
                high=high,
                low=low,
                close=close + (swing if i % 2 else -swing) / 2,
                volume=Decimal(1000 + i),
            )
        )
        close = out[-1].close
    return out


def main() -> None:
    window = bars(97)
    oficial = wilder_atr(window, 14).value
    geometria = atr_series(window[-96:], period=14, timeframe=Timeframe.M15)[-1]
    assert oficial is not None and geometria is not None
    delta = (geometria - oficial) / oficial
    print(f"janela oficial      : {len(window)} barras  ATR = {oficial}")
    print(f"janela da geometria : {len(window[-96:])} barras  ATR = {geometria}")
    print(f"divergencia relativa: {delta:.6%}")
    print()
    # a mesma medida em cada uma das ultimas 20 barras, para dar ordem de grandeza
    piores: list[Decimal] = []
    for cut in range(97, 130):
        serie = bars(cut)
        a = wilder_atr(serie[-97:], 14).value
        b = atr_series(serie[-96:], period=14, timeframe=Timeframe.M15)[-1]
        assert a is not None and b is not None
        piores.append(abs((b - a) / a))
    print(f"33 cortes: divergencia relativa max = {max(piores):.6%} "
          f"min = {min(piores):.6%}")
    print()
    print("O QUE ISSO TOCA:")
    print("  ATR oficial (97 barras) -> stop_atr_max, max_risk_atr, atr_pct_min/max, alvo")
    print("  ATR da geometria (96)   -> min_swing_atr, tolerance_atr, break_atr,")
    print("                             bounce_atr, angle/level_bucket, distance_atr")
    print("Nenhum limiar e comparado entre as duas; a divergencia so desloca, por")
    print("uma fracao de por cento, QUAL barra fica de cada lado de um limiar.")


if __name__ == "__main__":
    main()
