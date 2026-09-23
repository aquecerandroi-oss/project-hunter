# R76 — resolvedor de financiador. Roda DENTRO de um contêiner existente (`python -`), sem gravar nada.
# Lê a chave só de os.environ; nunca a imprime (nem a URL). Saída: uma linha JSON por carteira no stdout.
#   gtfa     : getTransactionsForAddress asc, jsonParsed (10 créditos) -> `source` da 1.ª instrução do
#              System Program (externa ou interna) que envia SOL à carteira (revisão da Astra).
#   xfers    : getTransfersByAddress (10 créditos/página) -> destinatários distintos de SOL nativo enviado
#              pelo financiador ANTES de um corte (item "financiador|corte_unix"), até 15 páginas.
#   fundedby : Wallet API /v1/wallet/<w>/funded-by (100 créditos) — só para validar o gtfa.
#   sigs     : getSignaturesForAddress(limit=1000) (1 crédito) — nº de assinaturas (proxy de serviço).
#   identity : POST /v1/wallet/batch-identity (100 créditos por lote de até 100).
import json
import os
import time
import urllib.parse

import httpx

WALLETS = __WALLETS__
MODE = "__MODE__"
RPS = __RPS__
_u = urllib.parse.urlparse(os.environ["SOLANA_RPC_URL"])
KEY = dict(urllib.parse.parse_qsl(_u.query)).get("api-key", "")
RPC = f"{_u.scheme}://{_u.hostname}/"
API = "https://api.helius.xyz"
c = httpx.Client(timeout=30.0)
stats = {"calls": 0, "http429": 0, "errors": 0, "non200": 0}
_last = [0.0]


def pace():
    dt = time.monotonic() - _last[0]
    if dt < 1.0 / RPS:
        time.sleep(1.0 / RPS - dt)
    _last[0] = time.monotonic()


def req(fn):
    for attempt in range(4):
        pace()
        stats["calls"] += 1
        try:
            r = fn()
        except Exception:  # erro de rede: conta e tenta de novo; nunca imprime a URL
            stats["errors"] += 1
            time.sleep(1 + attempt)
            continue
        if r.status_code == 429:
            stats["http429"] += 1
            if stats["http429"] > 30:
                print(json.dumps({"_abort": "429", "_stats": stats}), flush=True)
                raise SystemExit(3)
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code != 200:
            stats["non200"] += 1
        return r
    return None


def rpc(method, params):
    r = req(lambda: c.post(RPC, params={"api-key": KEY},
                           json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}))
    if r is None or r.status_code != 200:
        return None, (None if r is None else r.status_code)
    j = r.json()
    if "error" in j:
        return None, "rpc:" + str(j["error"].get("code")) + ":" + str(j["error"].get("message"))[:160]
    return j.get("result"), 200


def keys_of(tx):
    msg = tx["transaction"]["message"]
    ks = [k if isinstance(k, str) else k.get("pubkey") for k in msg["accountKeys"]]
    la = (tx.get("meta") or {}).get("loadedAddresses") or {}
    return ks + list(la.get("writable") or []) + list(la.get("readonly") or [])


_SYS = {"transfer": ("source", "destination"), "transferWithSeed": ("source", "destination"),
        "createAccount": ("source", "newAccount"), "createAccountWithSeed": ("source", "newAccount")}


def _ordered_ixs(tx):
    """Instruções na ordem de execução: a externa i, depois as internas do índice i."""
    outer = tx["transaction"]["message"].get("instructions") or []
    inner = {g.get("index"): g.get("instructions") or [] for g in ((tx.get("meta") or {}).get("innerInstructions") or [])}
    for i, ix in enumerate(outer):
        yield ix
        yield from inner.get(i, [])


def first_incoming(tx, w):
    """1.ª instrução do System Program (transfer/createAccount e variantes com seed) com destino = w."""
    for ix in _ordered_ixs(tx):
        p = ix.get("parsed") if isinstance(ix, dict) else None
        if ix.get("program") != "system" or not isinstance(p, dict):
            continue
        roles = _SYS.get(p.get("type"))
        info = p.get("info") or {}
        if roles and info.get(roles[1]) == w and info.get(roles[0]) and info.get(roles[0]) != w:
            return info.get(roles[0]), int(info.get("lamports") or 0), p.get("type")
    return None


def gtfa100(w):
    """Igual ao gtfa, com limit 100 (mesmo custo: 10 créditos por até 100 transações devolvidas)."""
    return gtfa(w, 100)


def gtfa(w, limit=10):
    """Financiador = `source` da 1.ª transferência de SOL (System Program) dirigida a w, na ordem da cadeia.

    Revisão da Astra (R76): a 'maior queda de lamports' da transação não identifica o remetente quando há
    várias transferências; agora lê-se a instrução (externa ou interna). Sem ela nas 10 primeiras
    transações: `truncated` (busca truncada, NÃO ausência de financiamento) — fica não resolvida.
    O campo `drop_funder` (heurística antiga) fica só como diagnóstico de concordância.
    """
    res, st = rpc("getTransactionsForAddress", [w, {
        "transactionDetails": "full", "sortOrder": "asc", "limit": limit, "encoding": "jsonParsed",
        "filters": {"status": "succeeded"}, "maxSupportedTransactionVersion": 1}])
    if res is None:
        return {"w": w, "ok": False, "status": st}
    data = res.get("data") or []
    for tx in data:
        hit = first_incoming(tx, w)
        if hit is None:
            continue
        meta = tx.get("meta") or {}
        ks = keys_of(tx)
        pre, post = meta.get("preBalances") or [], meta.get("postBalances") or []
        n = min(len(pre), len(post), len(ks))
        drops = sorted(((pre[k] - post[k], ks[k]) for k in range(n) if ks[k] != w and pre[k] > post[k]),
                       reverse=True)
        return {"w": w, "ok": True, "method": "ix", "funder": hit[0], "amount_lamports": hit[1], "ix_type": hit[2],
                "fee_payer": ks[0] if ks else None, "drop_funder": drops[0][1] if drops else None,
                "slot": tx.get("slot"), "block_time": tx.get("blockTime"),
                "sig": (tx["transaction"].get("signatures") or [None])[0], "n_seen": len(data)}
    return {"w": w, "ok": False, "status": "truncated" if len(data) >= limit else "no_system_transfer_in",
            "n_seen": len(data)}


def fundedby(w):
    r = req(lambda: c.get(f"{API}/v1/wallet/{w}/funded-by", headers={"X-Api-Key": KEY}))
    if r is None or r.status_code != 200:
        return {"w": w, "ok": False, "status": None if r is None else r.status_code}
    j = r.json()
    return {"w": w, "ok": True, "funder": j.get("funder"), "funderName": j.get("funderName"),
            "funderType": j.get("funderType"), "amount_lamports": int(j.get("amountRaw") or 0),
            "slot": j.get("slot"), "block_time": j.get("timestamp"), "sig": j.get("signature")}


def xfers(item):
    """Destinatários distintos de SOL nativo enviado antes do corte; para ao passar de 1 000 ou esgotar.

    Devolve, por destinatário, o 1.º `blockTime` visto (para avaliar cortes mais cedo sem nova chamada),
    `exhausted` (histórico anterior ao corte esgotado) e `oldest` (limite do que foi lido).
    """
    f, cut = item.split("|")
    cut = int(cut)
    first = {}
    token, pages, oldest, exhausted = None, 0, None, False
    while pages < 15:
        cfg = {"direction": "out", "mint": "So11111111111111111111111111111111111111111", "solMode": "separate",
               "limit": 100, "sortOrder": "desc", "filters": {"blockTime": {"lt": cut}}}
        if token:
            cfg["paginationToken"] = token
        res, st = rpc("getTransfersByAddress", [f, cfg])
        pages += 1
        if res is None:
            return {"w": item, "ok": False, "status": st, "pages": pages}
        for t in res.get("data") or []:
            to, bt = t.get("toUserAccount"), t.get("blockTime")
            if to and to != f and bt is not None:
                first[to] = min(first.get(to, bt), bt)
                oldest = bt if oldest is None else min(oldest, bt)
        token = res.get("paginationToken")
        if not token or not (res.get("data") or []):
            exhausted = True
            break
        if len(first) > 1000:
            break
    return {"w": item, "ok": True, "funder": f, "cut": cut, "pages": pages, "distinct": len(first),
            "exhausted": exhausted, "oldest": oldest, "first_bt": sorted(first.values())}


def sigs(w):
    res, st = rpc("getSignaturesForAddress", [w, {"limit": 1000}])
    if res is None:
        return {"w": w, "ok": False, "status": st}
    bts = [s.get("blockTime") for s in res if s.get("blockTime")]
    return {"w": w, "ok": True, "n_sigs": len(res), "newest": max(bts) if bts else None,
            "oldest": min(bts) if bts else None}


def identity(batch):
    r = req(lambda: c.post(f"{API}/v1/wallet/batch-identity", headers={"X-Api-Key": KEY},
                           json={"addresses": batch}))
    if r is None or r.status_code != 200:
        return [{"w": w, "ok": False, "status": None if r is None else r.status_code} for w in batch]
    j = r.json()
    items = j if isinstance(j, list) else (j.get("results") or j.get("data") or j.get("identities") or [])
    got = {}
    for it in items:
        if isinstance(it, dict):
            a = it.get("address") or it.get("wallet")
            if a:
                got[a] = it
    return [{"w": w, "ok": True, "name": (got.get(w) or {}).get("name"),
             "category": (got.get(w) or {}).get("category"), "type": (got.get(w) or {}).get("type"),
             "tags": (got.get(w) or {}).get("tags"), "found": w in got} for w in batch]


if MODE == "identity":
    for i in range(0, len(WALLETS), 100):
        for o in identity(WALLETS[i:i + 100]):
            print(json.dumps(o), flush=True)
else:
    fn = {"gtfa": gtfa, "gtfa100": gtfa100, "fundedby": fundedby, "sigs": sigs, "xfers": xfers}[MODE]
    for w in WALLETS:
        try:
            print(json.dumps(fn(w)), flush=True)
        except SystemExit:
            raise
        except Exception as e:
            stats["errors"] += 1
            print(json.dumps({"w": w, "ok": False, "status": "exc:" + type(e).__name__}), flush=True)
print(json.dumps({"_stats": stats, "mode": MODE}), flush=True)
