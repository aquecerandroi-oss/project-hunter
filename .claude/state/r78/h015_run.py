# R78 — H-015: veredito. PYTHONIOENCODING=utf-8 uv run --project C:/dev/project-hunter python h015_run.py
import csv
import json
import os
from collections import Counter, defaultdict

import numpy as np

from h015 import coordinated_dump, tertiles
from h015_tok import others_sol_in_slot, tok_cache
from h015_var import resolved
from h018 import _ts

HERE = os.path.dirname(os.path.abspath(__file__))
OUR = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"  # carteira da mesa (R76 load.py)
BUY_MIN_LAMPORTS = 2_500_000  # gasto do pagador além da taxa > 0,0025 SOL (acima do aluguel de ATA ~0,00204) = compra
B = 10_000
GRID = (0.50, 0.60, 2 / 3, 0.75, 0.85)


def cov() -> dict[str, dict]:
    with open(os.path.join(HERE, "cache", "cov.jsonl"), encoding="utf-8") as f:
        return {o["mint"]: o for o in map(json.loads, f) if o.get("ok")}


def chain_sol(c: dict, creator: str) -> tuple[float | None, int]:
    """v1 (h015_v1.txt; substituído pela prova por saldo de token, h015_tok). SOL gasto (≈, inclui aluguel/gorjeta) por pagadores ≠ criador no slot real; None se alguma tx não abriu."""
    if any(not t.get("ok") for t in c["txs"]) or c["others_in_slot"] > len(c["txs"]):
        return None, 0
    buys = [-(t["payer_delta"] + t["fee"]) for t in c["txs"] if t["payer"] != creator and -(t["payer_delta"] + t["fee"]) > BUY_MIN_LAMPORTS]
    return sum(buys) / 1e9, len(buys)


def sells() -> dict[str, list]:
    d: dict[str, list] = defaultdict(list)
    with open(os.path.join(HERE, "cache", "h015_sells.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d[r["mint"]].append((_ts(r["block_time"]), int(r["slot"]), r["trader"]))
    return d


def build(desk: bool = False, strict: bool = False, var: str = "tape") -> tuple[list[dict], Counter]:
    rows, why = resolved(desk, strict)
    cv, tk, sl, out = cov(), tok_cache(), sells(), []
    for r in rows:
        c = cv.get(r["mint"])
        if c is None or not c.get("create_listed"):
            why["cov_missing"] += 1
            continue
        t = tk.get(r["mint"])
        cs, nb = (None, 0) if t is None else others_sol_in_slot(t["txs"], r["creator"])
        r["chain"], r["chain_buys"] = cs, nb
        if var == "tape" and r["how"] == "absent_zero" and (cs is None or nb > 0):
            why["zero_ambiguous"] += 1  # Astra must-fix 1: a chain mostra compra de outra carteira no slot real
            continue
        if var == "chain":
            if cs is None:
                why["chain_unreadable"] += 1
                continue
            r["x"] = cs
        r["r"] = float(r["pnl_sol"]) / float(r["size_sol"])
        r["dump"], r["worst"] = coordinated_dump(sl.get(r["mint"], []), _ts(r["entry_at"]), OUR)
        r["has_sells"] = r["mint"] in sl
        out.append(r)
    return out, why


def boot(a: np.ndarray, b: np.ndarray, seed: int = 15) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, len(a), (B, len(a)))
    ib = rng.integers(0, len(b), (B, len(b)))
    ds = a[ia].mean(1) - b[ib].mean(1)
    return float(a.mean() - b.mean()), *np.percentile(ds, [2.5, 97.5]).tolist()


def label(n: int, nl: int, nh: int, d: float, lo: float, hi: float, dump_ratio: float, win_hi: float) -> str:
    if n < 150:
        return f"LIMITE DE DADO ({n} < 150)"
    if min(nl, nh) < 20:
        return "CONTRASTE NÃO IDENTIFICÁVEL (< 20 num extremo)"
    if win_hi > 0.30:
        return f"REFUTA por (c): teto mata {win_hi:.0%} das vencedoras"
    if lo > -0.01:
        return "REFUTA (IC inf > −0,01)"
    if hi > -0.01:
        return "NÃO CONFIRMA ((a) literal dispara; o intervalo não exclui o efeito)"
    if d <= -0.05 and dump_ratio >= 2:
        return "CONFIRMA a principal (patamar a verificar)"
    return "NÃO CONFIRMA"


def report(tag: str, rows: list[dict], why: Counter) -> None:
    x = np.array([r["x"] for r in rows])
    y = np.array([r["r"] for r in rows])
    dmp = np.array([r["dump"] for r in rows], dtype=float)
    lo_i, hi_i, (c1, c2) = tertiles(list(x))
    print(f"\n## {tag}: n = {len(rows)} | exclusões {dict(why)}")
    print(f"   cortes q1/3 = {c1:.4f}, q2/3 = {c2:.4f} SOL; baixo {len(lo_i)}, alto {len(hi_i)}; zeros {int((x == 0).sum())};"
          f" mints sem venda em meme_trades nos 300 s: {sum(not r['has_sells'] for r in rows)}")
    if len(rows) < 150 or min(len(lo_i), len(hi_i)) < 2:
        print("   ", label(len(rows), len(lo_i), len(hi_i), 0, 0, 0, 0, 0))
        return
    a, b = y[hi_i], y[lo_i]
    d, lo, hi = boot(a, b)
    da, db = dmp[hi_i].mean(), dmp[lo_i].mean()
    dd, dlo, dhi = boot(dmp[hi_i], dmp[lo_i], seed=16)
    wins = y > 0
    win_hi = float(wins[hi_i].sum() / wins.sum())
    ratio = da / db if db > 0 else float("inf")
    print(f"   alto: média r {a.mean():+.4f} (n {len(a)}), perda≥50% {np.mean(a <= -0.5):.3f}, despejo {da:.3f} | baixo: média {b.mean():+.4f}"
          f" (n {len(b)}), perda≥50% {np.mean(b <= -0.5):.3f}, despejo {db:.3f}")
    print(f"   D (alto − baixo) = {d:+.4f} IC95 [{lo:+.4f}, {hi:+.4f}] | despejo alto−baixo {dd:+.3f} [{dlo:+.3f}, {dhi:+.3f}],"
          f" razão {ratio:.2f} | (c) vencedoras no alto {int(wins[hi_i].sum())}/{int(wins.sum())} = {win_hi:.1%}")
    print(f"   → {label(len(rows), len(lo_i), len(hi_i), d, lo, hi, ratio, win_hi)}")
    for name, idx in (("baixo", lo_i), ("alto", hi_i)):
        print(f"   composição {name}: lanes {dict(Counter(rows[i]['lane'] for i in idx))}; portas {dict(Counter(rows[i]['rs'] for i in idx))}")
    parts, seen = [], set()
    for q in GRID:
        cut = float(np.quantile(x, q))
        idx = tuple(i for i, v in enumerate(x) if v > cut)
        if idx in seen or len(idx) < 2:
            continue
        seen.add(idx)
        dq = y[list(idx)].mean() - b.mean()
        parts.append(f"q{q:.3f} (> {cut:.3f}, n {len(idx)}): D {dq:+.4f}")
    print(f"   grade (partições distintas {len(parts)}): " + " · ".join(parts))


def main() -> None:
    rows, why = build()
    report("PRIMÁRIA — pista inteira, variável da fita, zeros provados por saldo de token na chain", rows, why)
    m = [r for r in rows if r["how"] == "match" and r["chain"] is not None]
    if m:
        tv, cvv = np.array([r["x"] for r in m]), np.array([r["chain"] for r in m])
        rk = lambda v: np.argsort(np.argsort(v))  # noqa: E731
        print(f"\n   concordância fita × chain nos {len(m)} 'match': Spearman {np.corrcoef(rk(tv), rk(cvv))[0, 1]:.3f};"
              f" chain > fita + 0,5 SOL em {int((cvv > tv + 0.5).sum())}; mediana chain − fita {np.median(cvv - tv):+.4f} SOL")
    report("SENSIBILIDADE — só reason null", *build(strict=True))
    report("SENSIBILIDADE — porta da mesa (fluxo_e_holders)", *build(desk=True))
    report("SENSIBILIDADE — variável lida da chain (oráculo retrospectivo)", *build(var="chain"))


if __name__ == "__main__":
    main()
