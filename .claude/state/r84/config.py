"""R84 — constantes congeladas (notes-R84.md §1–§2) e carregamento do dado real."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from panel import load_csv

HERE = Path(__file__).parent
CACHE = HERE / "cache"
EPOCH = dt.date(1970, 1, 1)
AS_OF_DAY = (dt.date(2026, 9, 28) - EPOCH).days  # vela de 28/09 em formação: fora
LAST_T_DAY = (dt.date(2026, 9, 14) - EPOCH).days

E1 = {"AEUR", "AUD", "BFUSD", "BKRW", "BUSD", "DAI", "EUR", "EURI", "FDUSD", "GBP", "KGST", "PAX", "RLUSD", "SUSD",
      "TUSD", "U", "USD1", "USDC", "USDE", "USDP", "USDS", "USDSB", "USDSOLD", "UST", "USTC", "XUSD",
      # da lista congelada, sem par no dado (inofensivos):
      "USDD", "PYUSD", "USDB", "BRL", "TRY", "RUB", "BIDR", "IDRT", "BVND", "NGN", "UAH", "ZAR", "ARS", "PLN", "RON",
      "JPY", "MXN", "COP", "CZK", "VAI", "LUSD", "GUSD", "HUSD"}
_LEV_BASES = ["1INCH", "AAVE", "ADA", "BCH", "BNB", "BTC", "DOT", "EOS", "ETH", "FIL", "LINK", "LTC", "SUSHI", "SXP",
              "TRX", "UNI", "XLM", "XRP", "XTZ", "YFI"]
E2 = ({b + s for b in _LEV_BASES for s in ("UP", "DOWN")} | {b + s for b in ("BNB", "EOS", "ETH", "XRP") for s in ("BULL", "BEAR")}
      | {"BULL", "BEAR", "INTWB", "KORUB", "MUUB", "MVLLB", "SNXXB", "SOXLB", "SOXSB", "TQQQB", "SQQQB"})
E3 = {"WBTC", "WBETH", "BETH", "BNSOL"}
EXCLUDED = E1 | E2 | E3


def day_iso(d: int) -> str:
    return (EPOCH + dt.timedelta(days=int(d))).isoformat()


def trading_symbols(all_status: bool = False) -> list[str]:
    ei = json.loads((CACHE / "exchange_info.json").read_text(encoding="utf-8"))["symbols"]
    return [s["symbol"] for s in ei if s["quoteAsset"] == "USDT" and (all_status or s["status"] == "TRADING")]


def load_rows() -> list[tuple[str, int, float, float, float]]:
    """Velas finais (abertura < AS_OF), sem duplicata (símbolo, dia)."""
    seen: dict[tuple[str, int], tuple[str, int, float, float, float]] = {}
    for r in load_csv(CACHE / "candles_1d.csv"):
        if r[1] < AS_OF_DAY:
            seen.setdefault((r[0], r[1]), r)
    return list(seen.values())


# Continuidade oficial documentada (catálogo oldAssetCode→newAssetCode ou renomeação 1:1 da Binance) com razão
# conferida pela abertura do novo = fecho do antigo × razão (notes §4). Só as que tocaram o universo com posição
# possível (fim de série nas 3 semanas finais dentro do top-20); as demais nunca estiveram no universo no fim.
# (símbolo antigo, símbolo novo, unidades antigas por unidade nova)
LINKS: tuple[tuple[str, str, float], ...] = (
    ("BCHABCUSDT", "BCHUSDT", 1.0),  # 2019-11-28: BCHABC renomeado BCH; abertura 220,08 = fecho 220,08
    ("ERDUSDT", "EGLDUSDT", 1000.0),  # 2020-09-03: 1 000 ERD = 1 EGLD; 0,01971 × 1 000 = 19,71
    ("LENDUSDT", "AAVEUSDT", 100.0),  # 2020-10-15: 100 LEND = 1 AAVE; 0,51431 × 100 = 51,43
    ("BNXUSDT", "FORMUSDT", 1.0),  # 2025-03-19: BNX → FORM (catálogo); 1,7819 = 1,7819
    ("TONUSDT", "GRAMUSDT", 1.0),  # 2026-07-02: TON → GRAM (catálogo); 1,600 = 1,600
)


def apply_links(rows, trading: set[str], links=LINKS):
    """Série antiga continua com as velas do novo símbolo (preço ÷ razão, volume em USDT igual) depois do seu fim."""
    trading = set(trading)
    by_sym: dict[str, list] = {}
    for r in rows:
        by_sym.setdefault(r[0], []).append(r)
    for old, new, ratio in links:
        if old not in by_sym or new not in by_sym:
            continue
        last_old = max(r[1] for r in by_sym[old])
        by_sym[old] = by_sym[old] + [(old, d, o / ratio, c / ratio, v) for _, d, o, c, v in by_sym[new] if d > last_old]
        del by_sym[new]
        if new in trading:
            trading.add(old)
    return [r for rs in by_sym.values() for r in rs], trading
