# R78 — H-015: compra de outra carteira no slot real provada por SALDO DE TOKEN (emenda da Astra no veredito).
# Compra = dono ≠ curva ≠ criador com Δ token > 0 do mint; SOL = Δ lamports da curva na tx, repartido pelos
# compradores na proporção dos tokens (no create, a curva também recebe a compra inicial do criador).
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def others_sol_in_slot(txs: list[dict], creator: str) -> tuple[float | None, int]:
    """(SOL das compras de outras carteiras no slot, nº de compras) ou (None, 0) se alguma tx não abriu.
    txs[0] é o create: a curva é o dono com o maior ganho de lamports nele (recebe o SOL; com compra inicial
    do criador > 50 % da oferta, o maior Δ token é o criador — 8 casos reais)."""
    if not txs or any(not t.get("ok") for t in txs):
        return None, 0
    first = txs[0]["owners"]
    if not first:
        return None, 0
    curve = max(first, key=lambda o: o["lam"] if o["lam"] is not None else -1)["owner"]
    total, n = 0, 0
    for t in txs:
        if t.get("err"):
            continue
        buyers = [o for o in t["owners"] if o["owner"] != curve and o["tok"] > 0]
        others = [o for o in buyers if o["owner"] != creator]
        if not others:
            continue
        n += len(others)
        cl = next((o["lam"] for o in t["owners"] if o["owner"] == curve), None)
        if cl is not None and cl > 0:
            tok_all = sum(o["tok"] for o in buyers)
            total += cl * sum(o["tok"] for o in others) / tok_all
        else:  # sem Δ da curva legível: gasto do próprio comprador
            total += sum(-o["lam"] for o in others if o["lam"] is not None and o["lam"] < 0)
    return total / 1e9, n


def tok_cache() -> dict[str, dict]:
    with open(os.path.join(HERE, "cache", "tok.jsonl"), encoding="utf-8") as f:
        return {o["mint"]: o for o in map(json.loads, f) if o.get("ok")}
