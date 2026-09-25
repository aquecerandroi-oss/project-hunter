# R78 — resolvedor do slot de criação. Roda DENTRO de hunter-meme-worker-1 (`python -`), sem gravar nada.
# Chave só de os.environ; nunca impressa (nem a URL). Uma linha JSON por assinatura no stdout.
import json
import os
import time
import urllib.parse

import httpx

SIGS = __SIGS__
RPS = __RPS__
_u = urllib.parse.urlparse(os.environ["SOLANA_RPC_URL"])
KEY = dict(urllib.parse.parse_qsl(_u.query)).get("api-key", "")
RPC = f"{_u.scheme}://{_u.hostname}/"
c = httpx.Client(timeout=30.0)
stats = {"calls": 0, "http429": 0, "errors": 0, "non200": 0}
last = 0.0
PARAMS = {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}
for sig in SIGS:
    out = {"sig": sig, "status": None}
    for attempt in range(4):
        dt = time.monotonic() - last
        if dt < 1.0 / RPS:
            time.sleep(1.0 / RPS - dt)
        last = time.monotonic()
        stats["calls"] += 1
        try:
            r = c.post(RPC, params={"api-key": KEY},
                       json={"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, PARAMS]})
        except Exception:  # erro de rede: conta e tenta de novo; nunca imprime a URL
            stats["errors"] += 1
            time.sleep(1 + attempt)
            continue
        if r.status_code == 429:
            stats["http429"] += 1
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code != 200:
            stats["non200"] += 1
            out["status"] = r.status_code
            break
        j = r.json()
        if "error" in j:
            out["status"] = "rpc:" + str(j["error"].get("code"))
            break
        res = j.get("result")
        if res is None:
            out["status"] = "not_found"
            break
        out.update(status="ok", slot=res.get("slot"), block_time=res.get("blockTime"),
                   err=None if (res.get("meta") or {}).get("err") is None else "tx_err")
        break
    print(json.dumps(out), flush=True)
print(json.dumps({"_stats": stats}), flush=True)
