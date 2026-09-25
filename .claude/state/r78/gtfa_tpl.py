# R78 — prova de cobertura do slot de criação. Roda DENTRO de hunter-meme-worker-1 (`python -`), sem gravar nada.
# Chave só de os.environ; nunca impressa. Por item "mint|slot_real|create_sig":
#   getTransactionsForAddress(mint, asc, signatures, succeeded, limit 100) → assinaturas no slot real (sem o create);
#   para cada uma, getTransaction(json) → pagador, variação de SOL do pagador (lamports, com taxa) e erro.
import json
import os
import time
import urllib.parse

import httpx

ITEMS = __ITEMS__
RPS = __RPS__
_u = urllib.parse.urlparse(os.environ["SOLANA_RPC_URL"])
KEY = dict(urllib.parse.parse_qsl(_u.query)).get("api-key", "")
RPC = f"{_u.scheme}://{_u.hostname}/"
c = httpx.Client(timeout=30.0)
stats = {"calls": 0, "http429": 0, "errors": 0, "non200": 0}
last = [0.0]


def rpc(method, params):
    for attempt in range(4):
        dt = time.monotonic() - last[0]
        if dt < 1.0 / RPS:
            time.sleep(1.0 / RPS - dt)
        last[0] = time.monotonic()
        stats["calls"] += 1
        try:
            r = c.post(RPC, params={"api-key": KEY}, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        except Exception:  # nunca imprime a URL
            stats["errors"] += 1
            time.sleep(1 + attempt)
            continue
        if r.status_code == 429:
            stats["http429"] += 1
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code != 200:
            stats["non200"] += 1
            return None, r.status_code
        j = r.json()
        if "error" in j:
            return None, "rpc:" + str(j["error"].get("code")) + ":" + str(j["error"].get("message"))[:120]
        return j.get("result"), 200
    return None, "retries"


for item in ITEMS:
    mint, slot, csig = item.split("|")
    slot = int(slot)
    res, st = rpc("getTransactionsForAddress", [mint, {"transactionDetails": "signatures", "sortOrder": "asc",
                  "limit": 100, "filters": {"status": "succeeded"}}])
    if res is None:
        print(json.dumps({"mint": mint, "ok": False, "status": st}), flush=True)
        continue
    data = res.get("data") or []
    first_slot = data[0].get("slot") if data else None
    in_slot = [d["signature"] for d in data if d.get("slot") == slot and d.get("signature") != csig]
    txs = []
    for s in in_slot[:60]:
        tx, st2 = rpc("getTransaction", [s, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        if tx is None:
            txs.append({"sig": s, "ok": False, "status": st2})
            continue
        meta = tx.get("meta") or {}
        keys = tx["transaction"]["message"]["accountKeys"]
        pre, post = meta.get("preBalances") or [0], meta.get("postBalances") or [0]
        txs.append({"sig": s, "ok": True, "payer": keys[0], "payer_delta": post[0] - pre[0], "fee": meta.get("fee")})
    print(json.dumps({"mint": mint, "ok": True, "n_listed": len(data), "first_slot": first_slot,
                      "create_listed": any(d.get("signature") == csig for d in data), "others_in_slot": len(in_slot),
                      "txs": txs}), flush=True)
print(json.dumps({"_stats": stats}), flush=True)
