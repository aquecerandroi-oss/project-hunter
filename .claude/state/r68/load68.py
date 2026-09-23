"""R68 — carregador de velas com guarda anti-look-ahead.

Regra (docs/PIPELINE.md §2): bar-features usam **só** velas `is_final`. Aqui, além
disso, nenhuma linha-fonte pode fechar depois do instante de decisão. A guarda é
`assert_causal`, e `Bars.take` é o único acesso a histórico que a aplica.
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HORIZONS = (1, 5, 15, 60, 240)


class LookAheadError(RuntimeError):
    """Uma feature tentou ler uma linha que fecha depois do instante de decisão."""


def assert_causal(
    source_close: np.ndarray, decision_instant: np.ndarray | int, what: str
) -> None:
    """Recusa qualquer fonte cujo fecho seja posterior ao instante de decisão.

    `source_close` e `decision_instant` em minutos de época (int). O fecho de uma
    barra é o instante em que ela passa a existir; ler uma barra que fecha *em*
    `decision_instant` é legítimo, ler uma que fecha depois é look-ahead.
    """
    src = np.asarray(source_close)
    dec = np.asarray(decision_instant)
    bad = src > dec
    if bool(np.any(bad)):
        i = int(np.argmax(bad))
        raise LookAheadError(
            f"{what}: fonte fecha em {int(src.ravel()[i])} > decisão "
            f"{int(np.broadcast_to(dec, src.shape).ravel()[i])} (minutos de época)"
        )


@dataclass(frozen=True)
class Bars:
    """Barras de horizonte `h` construídas a partir de velas 1 m `is_final`.

    `bucket_start` é o minuto de abertura; `close_time = bucket_start + h` é o
    instante de fecho **e** o instante de decisão de quem usa esta barra como
    última informação. `valid` já foi aplicado: só barras completas existem aqui.
    """

    symbol: str
    h: int
    bucket_start: np.ndarray  # int64, minutos de época
    close: np.ndarray
    high: np.ndarray
    low: np.ndarray
    volume: np.ndarray
    trade_count: np.ndarray
    taker_buy: np.ndarray

    @property
    def close_time(self) -> np.ndarray:
        return self.bucket_start + self.h

    def __len__(self) -> int:
        return int(self.bucket_start.size)

    def take(self, field: np.ndarray, idx: np.ndarray, decision_idx: np.ndarray) -> np.ndarray:
        """Lê `field[idx]` como feature para as decisões `decision_idx`, com guarda.

        É o **único** acesso a histórico usado pelos preditores. Um preditor que
        tente ler `idx = decision_idx + 1` levanta `LookAheadError`.
        """
        assert_causal(self.close_time[idx], self.close_time[decision_idx], f"{self.symbol}/h{self.h}")
        return field[idx]


def _dense(minutes: np.ndarray, values: np.ndarray, m0: int, n: int) -> np.ndarray:
    out = np.full(n, np.nan, dtype=np.float64)
    out[minutes - m0] = values
    return out


def aggregate(
    symbol: str,
    minutes: np.ndarray,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray,
    trade_count: np.ndarray,
    taker_buy: np.ndarray,
    h: int,
) -> Bars:
    """Agrega velas de 1 m em barras de `h` min numa grelha alinhada à época.

    Um bucket só existe se tiver as `h` velas (nenhuma interpolação, nenhum
    preenchimento). Buckets incompletos desaparecem.
    """
    order = np.argsort(minutes, kind="stable")
    minutes = minutes[order]
    m0 = int(minutes[0]) // h * h
    span = int(minutes[-1]) - m0 + 1
    n = int(np.ceil(span / h)) * h
    d_close = _dense(minutes, close[order], m0, n)
    d_high = _dense(minutes, high[order], m0, n)
    d_low = _dense(minutes, low[order], m0, n)
    d_vol = _dense(minutes, volume[order], m0, n)
    d_tc = _dense(minutes, trade_count[order], m0, n)
    d_tb = _dense(minutes, taker_buy[order], m0, n)
    k = n // h
    r_close = d_close.reshape(k, h)
    ok = ~np.isnan(r_close).any(axis=1)
    idx = np.flatnonzero(ok)
    return Bars(
        symbol=symbol,
        h=h,
        bucket_start=(m0 + h * idx).astype(np.int64),
        close=r_close[idx, -1],
        high=np.nanmax(d_high.reshape(k, h)[idx], axis=1),
        low=np.nanmin(d_low.reshape(k, h)[idx], axis=1),
        volume=d_vol.reshape(k, h)[idx].sum(axis=1),
        trade_count=d_tc.reshape(k, h)[idx].sum(axis=1),
        taker_buy=d_tb.reshape(k, h)[idx].sum(axis=1),
    )


def load_csv_gz(path: Path) -> dict[str, dict[str, np.ndarray]]:
    """Lê o export `symbol,minute,close,high,low,volume,trade_count,taker_buy`.

    `trade_count`/`taker_buy` vêm com -1 quando a coluna era NULL na base; aqui
    viram NaN, para que nenhum preditor os confunda com zero.
    """
    syms: list[str] = []
    rows: list[tuple[int, float, float, float, float, float, float]] = []
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as fh:  # type: ignore[operator]
        for line in fh:
            if not line.strip():
                continue
            p = line.rstrip("\n").split(",")
            syms.append(p[0])
            rows.append(
                (int(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5]), float(p[6]), float(p[7]))
            )
    sym_arr = np.array(syms)
    arr = np.array(rows, dtype=np.float64)
    out: dict[str, dict[str, np.ndarray]] = {}
    for s in np.unique(sym_arr):
        m = sym_arr == s
        a = arr[m]
        tc = a[:, 5].copy()
        tb = a[:, 6].copy()
        tc[tc < 0] = np.nan
        tb[tb < 0] = np.nan
        out[str(s)] = {
            "minute": a[:, 0].astype(np.int64),
            "close": a[:, 1],
            "high": a[:, 2],
            "low": a[:, 3],
            "volume": a[:, 4],
            "trade_count": tc,
            "taker_buy": tb,
        }
    return out


def bars_for(raw: dict[str, dict[str, np.ndarray]], h: int) -> dict[str, Bars]:
    return {
        s: aggregate(
            s, d["minute"], d["close"], d["high"], d["low"], d["volume"],
            d["trade_count"], d["taker_buy"], h,
        )
        for s, d in raw.items()
    }


def forward(bars: Bars) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Retorno close-to-close e MFE do horizonte seguinte, por índice de decisão.

    Devolve `(idx_decisao, ret, mfe)`. Um ponto só existe se a barra seguinte for
    a **contígua** na grelha (`bucket_start[i+1] == bucket_start[i] + h`); sem isso
    o desfecho não está medido e o ponto é censurado, nunca preenchido.
    """
    if len(bars) < 2:
        empty_i = np.zeros(0, dtype=np.int64)
        return empty_i, np.zeros(0), np.zeros(0)
    i = np.arange(len(bars) - 1)
    contiguous = bars.bucket_start[i + 1] == bars.bucket_start[i] + bars.h
    i = i[contiguous]
    ret = bars.close[i + 1] / bars.close[i] - 1.0
    mfe = bars.high[i + 1] / bars.close[i] - 1.0
    return i, ret, mfe
