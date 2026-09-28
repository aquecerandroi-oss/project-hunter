"""R84 — inventário INDEPENDENTE de pares: cópias históricas (Wayback Machine) de endpoints de cadastro da Binance.

Extrai só NOMES de símbolo (e o status, quando o endpoint tem), nunca preço. Saída: cache/wayback/<ts>_<slug>.txt
(uma linha "SYMBOL STATUS" por par terminado em USDT) e cache/wayback_manifest.csv.
"""

import csv
import json
import re
import time
import urllib.request
from pathlib import Path

CACHE = Path(__file__).parent / "cache"
OUT = CACHE / "wayback"
URLS = [
    "www.binance.com/exchange/public/product",
    "api.binance.com/api/v1/exchangeInfo",
    "www.binance.com/api/v1/exchangeInfo",
    "api.binance.com/api/v3/exchangeInfo",
    "www.binance.com/api/v3/exchangeInfo",
    "api1.binance.com/api/v3/exchangeInfo",
    "www.binance.com/exchange-api/v1/public/asset-service/product/get-products",
    "api.binance.com/api/v1/ticker/24hr",
    "api.binance.com/api/v3/ticker/24hr",
    "www.binance.com/api/v1/ticker/24hr",
    "api.binance.com/api/v3/ticker/price",
    "www.binance.com/api/v1/ticker/allPrices",
]


def get(url: str, tries: int = 5) -> bytes:
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hunter-research-r84"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception:  # noqa: BLE001 — rede do arquivo é instável; tenta de novo
            if a == tries - 1:
                raise
            time.sleep(5 * (a + 1))
    raise AssertionError


def snapshots(url: str) -> list[str]:
    q = f"http://web.archive.org/cdx/search/cdx?url={url}&output=txt&fl=timestamp&filter=statuscode:200&collapse=timestamp:6"
    return get(q).decode().split()


def symbols_with_status(text: str) -> dict[str, str]:
    """{símbolo: status ou '?'} — só os que terminam em USDT; nenhum número de preço é lido."""
    out: dict[str, str] = {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    items = []
    if isinstance(data, dict):
        items = data.get("symbols") or data.get("data") or []
    elif isinstance(data, list):
        items = data
    for it in items:
        if not isinstance(it, dict):
            continue
        sym = it.get("symbol") or it.get("s")
        if isinstance(sym, str) and sym.endswith("USDT") and len(sym) > 4:
            out[sym] = str(it.get("status") or it.get("st") or "?")
    if not out:  # formato inesperado: cai para regex só de nomes
        for sym in re.findall(r'"(?:symbol|s)"\s*:\s*"([^"]+USDT)"', text):
            out.setdefault(sym, "?")
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for url in URLS:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", url)[:60]
        for ts in snapshots(url):
            dest = OUT / f"{ts}_{slug}.txt"
            if not dest.exists():
                try:
                    raw = get(f"http://web.archive.org/web/{ts}id_/https://{url}").decode("utf-8", "replace")
                except Exception as e:  # noqa: BLE001
                    rows.append([ts, url, "erro", str(e)[:80]])
                    continue
                syms = symbols_with_status(raw)
                dest.write_text("".join(f"{s} {st}\n" for s, st in sorted(syms.items())), encoding="utf-8")
                time.sleep(1.5)
            n = len(dest.read_text(encoding="utf-8").splitlines())
            rows.append([ts, url, "ok", n])
    with (CACHE / "wayback_manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "url", "estado", "pares_usdt"])
        w.writerows(rows)
    print(f"{sum(1 for r in rows if r[2] == 'ok')} cópias ok, {sum(1 for r in rows if r[2] != 'ok')} com erro")


if __name__ == "__main__":
    main()
