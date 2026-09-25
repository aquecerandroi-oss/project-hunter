# R78 — prova de compra por saldo de token (emenda da Astra no veredito). Roda DENTRO de hunter-meme-worker-1.
# Chave só de os.environ; nunca impressa. Item "mint|sig1,sig2,..." (todas as tx do slot real, INCLUINDO o create).
# Por tx: deltas de token deste mint por dono e o delta de lamports de cada dono que é conta da transação.
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
            return None, "rpc:" + str(j["error"].get("code"))
        return j.get("result"), 200
    return None, "retries"


def amounts(bals, mint):
    out = {}
    for b in bals or []:
        if b.get("mint") == mint:
            out[b.get("owner")] = out.get(b.get("owner"), 0) + int(b["uiTokenAmount"]["amount"])
    return out


for item in ITEMS:
    mint, sigs = item.split("|")
    txs = []
    for s in sigs.split(","):
        tx, st = rpc("getTransaction", [s, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        if tx is None:
            txs.append({"sig": s, "ok": False, "status": st})
            continue
        meta = tx.get("meta") or {}
        la = meta.get("loadedAddresses") or {}
        keys = list(tx["transaction"]["message"]["accountKeys"]) + list(la.get("writable") or []) + list(la.get("readonly") or [])
        pre_t, post_t = amounts(meta.get("preTokenBalances"), mint), amounts(meta.get("postTokenBalances"), mint)
        owners = set(pre_t) | set(post_t)
        pre, post = meta.get("preBalances") or [], meta.get("postBalances") or []
        rows = []
        for o in owners:
            k = keys.index(o) if o in keys else None
            lam = post[k] - pre[k] if k is not None and k < len(pre) and k < len(post) else None
            rows.append({"owner": o, "tok": post_t.get(o, 0) - pre_t.get(o, 0), "lam": lam})
        txs.append({"sig": s, "ok": True, "err": meta.get("err") is not None, "payer": keys[0], "owners": rows})
    print(json.dumps({"mint": mint, "ok": True, "txs": txs}), flush=True)
print(json.dumps({"_stats": stats}), flush=True)
