# R81 — H-021: rótulo pela letra (limite de dado) + análise EXPLORATÓRIA E (janela truncada no nascimento).
# NÃO RODADO no R81: a Astra e eu decidimos não abrir desfechos da E (notas §2–§4) — instrumento com
# identificação aberta (slot de criação, lacunas do arquivo, ordem no último slot, fill × marginal).
# Se alguém rodar, o resultado é EXPLORATÓRIO: não produz veredito, CONFIRMA nem braço.
# cd .claude/state/r81 && PYTHONPATH=C:/dev/project-hunter PYTHONIOENCODING=utf-8 uv run --project C:/dev/project-hunter python h021.py
from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal

import numpy as np

from infra.research.resampling import cluster_bootstrap, permutation_p
from infra.research.stats import adjust_family
from r81 import (comprou_no_topo, covered, first_per_mint, load_first, load_pop, load_trades, r_of, resolved,
                 structure, ts)

B, SEED, MRE = 10_000, 81, -0.05
GRID = (0.20, 0.25, 0.30, 1 / 3, 0.40, 0.45, 0.50)
TOL = timedelta(seconds=5)
POP, FIRST, TRADES = load_pop(), load_first(), load_trades()


def covered_e(r: dict) -> tuple[bool, int | None]:
    """E: o arquivo cobre a janela [T−300, T) truncada no nascimento. Devolve (coberto, slot de criação)."""
    T, c = ts(r["decided_at"]), ts(r["tok_created_at"])
    fb, fs = FIRST.get(r["mint"], (None, None))
    if fb is None or c is None or fb > max(T - timedelta(seconds=300), c + TOL):
        return False, None
    return True, (fs if fb <= c + TOL else None)


def enrich(r: dict) -> dict | None:
    ok, cs = covered_e(r)
    if not ok:
        return None
    T = ts(r["decided_at"])
    tt = TRADES.get((r["mint"], T), [])
    s = structure(tt, T, cs)
    if s is None:
        return None
    k = structure(tt, T, cs, received_before_decision=True)
    return dict(r, T=T, day=str(T.date()), s=s, k=k, dist=s.dist, ctop=comprou_no_topo(r),
                win=Decimal(r["pnl_sol"]) > 0, pnl=Decimal(r["pnl_sol"]))


def contrast(y, sel, rows, seed=SEED):
    ci = cluster_bootstrap(y, sel, [r["mint"] for r in rows], reps=B, seed=seed)
    p = permutation_p(y, sel, [r["day"] for r in rows], reps=B, seed=seed)
    return float(y[sel].mean() - y[~sel].mean()), ci, p


def rate(flags):
    k = [f for f in flags if f is not None]
    return (sum(k) / len(k) if k else float("nan")), sum(k), len(k)


def tertiles(tag: str, rows: list[dict], x: np.ndarray, verbose: bool = True) -> dict:
    """Tercis de posto: alto > q2/3 × baixo ≤ q1/3; D = média r(alto) − média r(baixo)."""
    y = np.array([r_of(r) for r in rows])
    c1, c2 = np.quantile(x, [1 / 3, 2 / 3])
    lo, hi = x <= c1, x > c2
    sub = [r for r, m in zip(rows, lo | hi) if m]
    d, ci, p = contrast(y[lo | hi], hi[lo | hi], sub)
    wins = y > 0
    win_hi = float(wins[hi].sum() / wins.sum()) if wins.sum() else float("nan")
    ct = [r["ctop"] for r in rows]
    cth, ctl = rate([c for c, m in zip(ct, hi) if m]), rate([c for c, m in zip(ct, lo) if m])
    # não avaliável (nan) sem denominador; ambos zero não é concentração (Astra, must-fix 5)
    ratio = (cth[0] / ctl[0] if ctl[0] > 0 else (float("inf") if cth[0] > 0 else float("nan"))) if np.isfinite(cth[0]) and np.isfinite(ctl[0]) else float("nan")
    curve, seen = [], set()
    for q in GRID:
        a, b = np.quantile(x, [q, 1 - q])
        ql, qh = x <= a, x > b
        key = (tuple(np.flatnonzero(ql)), tuple(np.flatnonzero(qh)))
        if key in seen or min(ql.sum(), qh.sum()) < 2:
            continue
        seen.add(key)
        m = ql | qh
        dq, ciq, _ = contrast(y[m], qh[m], [r for r, k in zip(rows, m) if k], seed=SEED + int(q * 100))
        curve.append((q, a, b, int(ql.sum()), int(qh.sum()), dq, ciq.lo, ciq.hi))
    near = {round(q, 3): dq for q, *_, dq, _l, _h in curve}
    plateau = all(near.get(q, 0.0) <= MRE for q in (0.30, 0.40))
    if verbose:
        print(f"\n## {tag}: n {len(rows)} | lanes {dict(Counter(r['lane'] for r in rows))} | cortes q1/3 {c1:.4f} q2/3 {c2:.4f}")
        print(f"   média r: baixo {y[lo].mean():+.4f} (n {int(lo.sum())}, vitória {wins[lo].mean():.3f}) | meio {y[~(lo | hi)].mean():+.4f}"
              f" | alto {y[hi].mean():+.4f} (n {int(hi.sum())}, vitória {wins[hi].mean():.3f}) | todos {y.mean():+.4f}")
        print(f"   D (alto − baixo) = {d:+.4f} IC95 [{ci.lo:+.4f}, {ci.hi:+.4f}] | p perm (dia) {p:.4f}")
        print(f"   (c) vencedoras no tercil alto: {int(wins[hi].sum())}/{int(wins.sum())} = {win_hi:.1%}")
        print(f"   comprou_no_topo: alto {cth[1]}/{cth[2]} = {cth[0]:.3f} | baixo {ctl[1]}/{ctl[2]} = {ctl[0]:.3f} | razão {ratio:.2f}")
        for q, a, b, nl, nh, dq, l_, h_ in curve:
            print(f"     q {q:.3f}: baixo ≤ {a:.4f} (n {nl}) × alto > {b:.4f} (n {nh}): D {dq:+.4f} [{l_:+.4f}, {h_:+.4f}]")
        print(f"   patamar (q 0,30 e 0,40 com D ≤ −0,05): {plateau}")
    return dict(n=len(rows), c1=c1, c2=c2, d=d, ci=ci, p=p, win_hi=win_hi, ratio=ratio, plateau=plateau,
                nl=int(lo.sum()), nh=int(hi.sum()))


def boolean(tag: str, rows: list[dict], key: str) -> dict:
    R = [r for r in rows if getattr(r["s"], key) is not None]
    y = np.array([r_of(r) for r in R])
    sel = np.array([bool(getattr(r["s"], key)) for r in R])
    d, ci, p = contrast(y, sel, R)
    ct = [r["ctop"] for r in R]
    ca, cb = rate([c for c, m in zip(ct, sel) if m]), rate([c for c, m in zip(ct, sel) if not m])
    print(f"\n## {tag} ({key}): n {len(R)} (True {int(sel.sum())} / False {int((~sel).sum())}) | média r True {y[sel].mean():+.4f}"
          f" False {y[~sel].mean():+.4f} | D (True − False) {d:+.4f} [{ci.lo:+.4f}, {ci.hi:+.4f}] p {p:.4f}"
          f" | comprou_no_topo True {ca[0]:.3f} False {cb[0]:.3f}")
    return dict(d=d, ci=ci, p=p)


def counterfactual(c2: float) -> dict:
    real = [r for r in POP if r["lane"] == "real" and r["status"] == "closed" and r["pnl_sol"]]
    ev = [(r, enrich(r)) for r in real]
    tot = sum((Decimal(r["pnl_sol"]) for r in real), Decimal(0))
    blocked = [e for _, e in ev if e is not None and e["dist"] > c2]
    loss = sum((e["pnl"] for e in blocked if e["pnl"] < 0), Decimal(0))
    gain = sum((e["pnl"] for e in blocked if e["pnl"] > 0), Decimal(0))
    wins = [r for r in real if Decimal(r["pnl_sol"]) > 0]
    killed = [e for e in blocked if e["pnl"] > 0]
    print(f"\n## Contrafactual contábil (teto dist > {c2:.4f}): {len(real)} posições reais fechadas (Σ {tot:+.4f} SOL),"
          f" com variável {sum(e is not None for _, e in ev)} (as sem variável passam)")
    print(f"   bloqueadas {len(blocked)}: perda evitada {loss:+.4f}, ganho morto {gain:+.4f} → Δ {-(loss + gain):+.4f} SOL;"
          f" vencedoras mortas {len(killed)}/{len(wins)} = {(len(killed) / len(wins)) if wins else float('nan'):.1%}")
    for e in sorted(killed, key=lambda e: e["T"]):
        print(f"     morta: {e['symbol']} {e['pnl']:+.4f} ({e['day']}, dist {e['dist']:.3f}, {e['rs']}, {e['exit_reason']})")
    print("   piores bloqueadas:", "; ".join(f"{e['symbol']} {e['pnl']:+.4f} (dist {e['dist']:.2f}, {e['exit_reason']})"
                                           for e in sorted(blocked, key=lambda e: e["pnl"])[:8]))
    return dict(delta=-(loss + gain), killed=(len(killed) / len(wins)) if wins else float("nan"))  # sem vencedoras: não avaliável


def main() -> None:
    fp = [r for r in first_per_mint(POP) if resolved(r)]
    lit = [r for r in fp if covered(FIRST.get(r["mint"], (None, None))[0], ts(r["decided_at"]))]
    print(f"# LETRA DO BLOCO: 1.ª por mint resolvidas {len(fp)}; com 5 min de fita arquivada antes de T: {len(lit)}"
          f" → {'LIMITE DE DADO (< 150)' if len(lit) < 150 else 'segue'}")
    print("\n# EXPLORATÓRIA E (não é veredito): janela [T−300, T) truncada no nascimento")
    P = [e for e in (enrich(r) for r in fp) if e is not None]
    P.sort(key=lambda e: e["T"])
    print("rule sets", Counter(e["rs"] for e in P).most_common(), "| séries", Counter(e["series"] for e in P))
    x = np.array([e["dist"] for e in P])
    prim = tertiles("E primária: distancia_do_suporte", P, x)
    fh = boolean("E secundária", P, "higher_lows")
    ro = boolean("E secundária", P, "breakout")
    fam = adjust_family([prim["p"], fh["p"], ro["p"]])
    print(f"\n## Holm {{dist, fundos, rompimento}}: p {tuple(round(v, 4) for v in fam.p)} → {tuple(round(v, 4) for v in fam.holm_adjusted)}")
    cf = counterfactual(prim["c2"])
    print("\n## regra do R79 aplicada à E (SÓ DESCRITIVA — a E não produz veredito):")
    ci = prim["ci"]
    if prim["win_hi"] > 0.30:
        print(f"   (c) dispararia: {prim['win_hi']:.1%} das vencedoras no tercil alto")
    if ci.lo > -0.01:
        print("   o intervalo excluiria o efeito previsto (IC inf > −0,01)")
    print(f"   D ≤ −0,05 e IC sup < 0: {prim['d'] <= MRE and ci.hi < 0}; patamar {prim['plateau']}; comprou_no_topo ≥ 1,5×: {prim['ratio'] >= 1.5};"
          f" Δ contrafactual > 0: {cf['delta'] > 0}; mata ≤ 20 %: {cf['killed'] <= 0.20}; Holm < 0,05: {fam.holm_adjusted[0] < 0.05}")

    print("\n# SENSIBILIDADES (descritivas)")
    K = [e for e in P if e["k"] is not None]
    tertiles(f"s1 só trocas recebidas antes de T (com valor em {len(K)} de {len(P)})", K, np.array([e["k"].dist for e in K]))
    pr = np.array([float(e["s"].price_t) for e in P])
    b1, b2 = np.quantile(pr, [1 / 3, 2 / 3])
    for i, (a, b) in enumerate(((-np.inf, b1), (b1, b2), (b2, np.inf))):
        S = [e for e, v in zip(P, pr) if a < v <= b]
        tertiles(f"s2 dentro do tercil {i + 1} de preço na decisão (controle de progresso)", S, np.array([e["dist"] for e in S]))
    Rr = [e for e in P if e["lane"] == "real"]
    tertiles("s3 só reais", Rr, np.array([e["dist"] for e in Rr]))
    Nr = [e for e in P if e["rs"] != "recuo_v1/1"]
    tertiles("s4 sem recuo_v1", Nr, np.array([e["dist"] for e in Nr]))
    for ser in ("meme_event_gate_v1", "meme_features_15s_v1"):
        S = [e for e in P if e["series"] == ser]
        tertiles(f"s5 só {ser}", S, np.array([e["dist"] for e in S]))
    Pp = [e for e in P if e["p_dist"]]
    tertiles(f"s6 produção distance_to_support_pct (n {len(Pp)})", Pp, np.array([float(e["p_dist"]) for e in Pp]))
    for half, S in (("12–21/09", [e for e in P if e["day"] < "2026-09-22"]), ("22–26/09", [e for e in P if e["day"] >= "2026-09-22"])):
        tertiles(f"s7 período {half}", S, np.array([e["dist"] for e in S]))


if __name__ == "__main__":
    main()
