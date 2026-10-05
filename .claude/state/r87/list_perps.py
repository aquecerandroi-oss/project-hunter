"""R87 passo 0 — só nomes e datas (nenhum preço, nenhum funding): que perpétuos USDT-M existem/existiram.

Saídas: cache/um_klines_symbols.txt, cache/um_funding_symbols.txt (pastas do arquivo público data.binance.vision,
inclui deslistados) e cache/fapi_exchange_info.json (cadastro de hoje, com onboardDate e deliveryDate).
"""

import json
import sys
import urllib.request
from pathlib import Path

R84 = Path(__file__).resolve().parent.parent / "r84"
sys.path.insert(0, str(R84))
from list_symbols import list_prefixes  # noqa: E402

CACHE = Path(__file__).parent / "cache"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "hunter-research-r87"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main() -> None:
    CACHE.mkdir(exist_ok=True)
    for kind, prefix in (("klines", "data/futures/um/monthly/klines/"), ("funding", "data/futures/um/monthly/fundingRate/")):
        syms = sorted({p.rstrip("/").split("/")[-1] for p in list_prefixes(prefix)})
        (CACHE / f"um_{kind}_symbols.txt").write_text("\n".join(syms) + "\n", encoding="utf-8")
        print(f"{prefix}: {len(syms)} pastas; terminam em USDT: {sum(1 for s in syms if s.endswith('USDT'))}")
    info = get("https://fapi.binance.com/fapi/v1/exchangeInfo")
    (CACHE / "fapi_exchange_info.json").write_bytes(info)
    ei = json.loads(info)["symbols"]
    perp = [s for s in ei if s.get("contractType") == "PERPETUAL" and s["quoteAsset"] == "USDT"]
    print(f"fapi exchangeInfo: {len(ei)} símbolos; perpétuos USDT: {len(perp)}; status: "
          + str({st: sum(1 for s in perp if s['status'] == st) for st in {s['status'] for s in perp}}))


if __name__ == "__main__":
    main()
