"""R87 passo 1 — velas diárias dos perpétuos USDⓈ-M candidatos e o histórico de funding liquidado (API pública).

Candidatos = perpétuo do mesmo ativo (BASEUSDT, 1000BASE, 1000000BASE, 1MBASE) de toda série à vista do R84 que
chega ao top-40 de volume em alguma segunda desde 2019-09-09 (feasibility.py). Inclui contratos deslistados
(`SETTLING`): a API serve velas e funding deles. Nada de chave, nada de base. Idempotente por símbolo.

Saídas: cache/perp_1d/<SYM>.csv (open_ms,open,high,low,close,quote_volume) e cache/funding/<SYM>.csv
(funding_ms,rate). Não imprime preço nem taxa — só contagens.
"""

from __future__ import annotations

import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / "cache"
START_MS = 1567296000000  # 2019-09-01T00:00Z
FAPI = "https://fapi.binance.com/fapi/v1/"


def get(path: str, params: dict[str, object]) -> list:
    url = FAPI + path + "?" + urllib.parse.urlencode(params)
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hunter-research-r87"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 400:
                return []  # símbolo inexistente
            if e.code in (418, 429):
                time.sleep(60 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"falhou {url}")


def klines(sym: str, path: str = "klines") -> list[list[str]]:
    out, start = [], START_MS
    while True:
        data = get(path, {"symbol": sym, "interval": "1d", "startTime": start, "limit": 1500})
        out += [[str(k[0]), k[1], k[2], k[3], k[4], k[7]] for k in data]
        if len(data) < 1500:
            return out
        start = int(data[-1][0]) + 1
        time.sleep(0.3)


def funding(sym: str) -> list[list[str]]:
    out, start = [], START_MS
    while True:
        data = get("fundingRate", {"symbol": sym, "startTime": start, "limit": 1000})
        out += [[str(x["fundingTime"]), x["fundingRate"]] for x in data]
        time.sleep(0.65)  # 500 pedidos / 5 min por IP neste endpoint
        if len(data) < 1000:
            return out
        start = int(data[-1]["fundingTime"]) + 1


def write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    tmp.replace(path)


def main(which: str) -> None:
    syms = (CACHE / "perp_candidates.txt").read_text(encoding="utf-8").split()
    if len(sys.argv) > 2 and sys.argv[2] == "rev":  # segundo processo, do fim para o começo (mesmo limite por IP)
        syms = syms[::-1]
    folder = CACHE / {"klines": "perp_1d", "mark": "mark_1d", "funding": "funding"}[which]
    folder.mkdir(exist_ok=True)
    empty = 0
    for n, sym in enumerate(syms, 1):
        dest = folder / f"{sym}.csv"
        if dest.exists():
            continue
        if which in ("klines", "mark"):
            rows = klines(sym, "klines" if which == "klines" else "markPriceKlines")
            write(dest, ["open_ms", "open", "high", "low", "close", "quote_volume"], rows)
        else:
            rows = funding(sym)
            write(dest, ["funding_ms", "rate"], rows)
        empty += not rows
        if n % 25 == 0:
            print(f"{which}: {n}/{len(syms)} (vazios {empty})", flush=True)
    print(f"{which}: fim, {len(syms)} símbolos, vazios nesta rodada {empty}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
