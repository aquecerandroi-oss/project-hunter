"""R84 passo 2 — baixa velas 1d de TODOS os 750 pares USDT (inclui deslistados) e grava cache/candles_1d.csv.

Fonte por vela: arquivo mensal `data.binance.vision` para meses ≤ 2026-08; `GET /api/v3/klines` para 2026-09 (e para
listagens que ainda não têm arquivo mensal). Só dado público, sem chave. Zips ficam em cache/zips/ (idempotente).
"""

import csv
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from list_symbols import BUCKET
from list_symbols import get as _get


def get(url: str) -> bytes:
    """GET com até 6 tentativas (handshake TLS do S3 às vezes expira com 16–24 conexões)."""
    for attempt in range(6):
        try:
            return _get(url)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if attempt == 5:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("inalcançável")

CACHE = Path(__file__).parent / "cache"
ZIPS = CACHE / "zips"
DATA = "https://data.binance.vision/"
API_FROM_MS = 1788220800000  # 2026-09-01T00:00Z
LAST_MONTHLY = "2026-08"


def usdt_symbols() -> tuple[list[str], dict[str, str]]:
    arch = set((CACHE / "archive_symbols.txt").read_text(encoding="utf-8").split())
    ei = json.loads((CACHE / "exchange_info.json").read_text(encoding="utf-8"))["symbols"]
    status = {s["symbol"]: s["status"] for s in ei if s["quoteAsset"] == "USDT"}
    syms = sorted({s for s in arch if s.endswith("USDT") and len(s) > 4} | set(status))
    return syms, status


def list_keys(sym: str) -> list[str]:
    keys: list[str] = []
    marker = ""
    prefix = f"data/spot/monthly/klines/{sym}/1d/"
    while True:
        url = f"{BUCKET}?prefix={urllib.parse.quote(prefix)}" + (f"&marker={urllib.parse.quote(marker)}" if marker else "")
        xml = get(url).decode()
        got = [k for k in re.findall(r"<Key>([^<]+)</Key>", xml) if k.endswith(".zip")]
        keys += got
        if "<IsTruncated>true</IsTruncated>" not in xml or not got:
            return keys
        marker = got[-1]


def fetch_zip(key: str) -> Path:
    dest = ZIPS / key.split("/")[-1]
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    for attempt in range(5):
        try:
            dest.write_bytes(get(DATA + urllib.parse.quote(key)))
            return dest
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"falhou {key}")


def parse_zip(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as z:
        name = z.namelist()[0]
        text = z.read(name).decode()
    rows = []
    for r in csv.reader(io.StringIO(text)):
        if not r or not r[0].strip().isdigit():
            continue  # cabeçalho ocasional
        t = int(r[0])
        if t > 10**14:  # microssegundos (arquivo spot desde 2025)
            t //= 1000
        rows.append([str(t), r[1], r[2], r[3], r[4], r[7]])
    return rows


def api_klines(sym: str, start_ms: int) -> list[list[str]]:
    out: list[list[str]] = []
    while True:
        q = urllib.parse.urlencode({"symbol": sym, "interval": "1d", "startTime": start_ms, "limit": 1000})
        try:
            data = json.loads(get(f"https://api.binance.com/api/v3/klines?{q}"))
        except urllib.error.HTTPError as e:
            if e.code == 400:
                return out  # símbolo inválido hoje
            raise
        for k in data:
            out.append([str(k[0]), k[1], k[2], k[3], k[4], k[7]])
        if len(data) < 1000:
            return out
        start_ms = int(data[-1][0]) + 1
        time.sleep(0.2)


def main() -> None:
    ZIPS.mkdir(parents=True, exist_ok=True)
    syms, status = usdt_symbols()
    with ThreadPoolExecutor(8) as ex:
        keys_by = dict(zip(syms, ex.map(list_keys, syms), strict=True))
    all_keys = [k for ks in keys_by.values() for k in ks if k[-11:-4] <= LAST_MONTHLY]
    print(f"{len(syms)} símbolos; {sum(1 for v in keys_by.values() if v)} com arquivo mensal; {len(all_keys)} zips")
    with ThreadPoolExecutor(12) as ex:
        paths = list(ex.map(fetch_zip, all_keys))
    rows: list[list[str]] = []
    for key, p in zip(all_keys, paths, strict=True):
        sym = key.split("/")[4]
        rows += [[sym, *r, "archive"] for r in parse_zip(p)]
    api_syms = [s for s in syms if s in status]
    for s in api_syms:
        start = API_FROM_MS if keys_by.get(s) else 0
        rows += [[s, *r, "api"] for r in api_klines(s, start)]
        time.sleep(0.05)
    with (CACHE / "candles_1d.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "open_ms", "open", "high", "low", "close", "quote_volume", "source"])
        w.writerows(rows)
    print(f"{len(rows)} velas gravadas")


if __name__ == "__main__":
    main()
