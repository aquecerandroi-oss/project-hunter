"""R84 passo 1 — lista TODOS os símbolos do arquivo público (sem preço) e o exchangeInfo de hoje.

Saídas: cache/archive_symbols.txt (todas as pastas de data/spot/monthly/klines/), cache/exchange_info.json.
"""

import json
import re
import urllib.request
from pathlib import Path

CACHE = Path(__file__).parent / "cache"
BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "hunter-research-r84"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def list_prefixes(prefix: str) -> list[str]:
    out: list[str] = []
    marker = ""
    while True:
        url = f"{BUCKET}?delimiter=/&prefix={prefix}" + (f"&marker={marker}" if marker else "")
        xml = get(url).decode()
        pre = re.findall(r"<Prefix>([^<]+)</Prefix>", xml)
        got = [p for p in pre if p != prefix]
        out += got
        if "<IsTruncated>true</IsTruncated>" not in xml or not got:
            break
        marker = got[-1]
    return out


def main() -> None:
    CACHE.mkdir(exist_ok=True)
    pre = list_prefixes("data/spot/monthly/klines/")
    syms = sorted({p.rstrip("/").split("/")[-1] for p in pre})
    (CACHE / "archive_symbols.txt").write_text("\n".join(syms) + "\n", encoding="utf-8")
    info = get("https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT")
    (CACHE / "exchange_info.json").write_bytes(info)
    usdt = [s for s in syms if s.endswith("USDT") and len(s) > 4]
    print(f"pastas no arquivo: {len(syms)}; terminam em USDT: {len(usdt)}")
    ei = json.loads(info)["symbols"]
    print(f"exchangeInfo: {len(ei)} símbolos; status: "
          + str({st: sum(1 for s in ei if s['status'] == st) for st in {s['status'] for s in ei}}))


if __name__ == "__main__":
    main()
