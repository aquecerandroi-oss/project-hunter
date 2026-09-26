# R80 — H-020: contraste pré-registrado, golpe por grupo, contrafactual real, sensibilidades.
# cd .claude/state/r80 && PYTHONPATH=C:/dev/project-hunter PYTHONIOENCODING=utf-8 uv run --project C:/dev/project-hunter python h020.py
from __future__ import annotations

from collections import Counter
from decimal import Decimal

import numpy as np

from infra.research.resampling import cluster_bootstrap, permutation_p
from infra.research.stats import adjust_family
from r80 import TokenIndex, first_per_mint, golpe_ficha, golpe_raw, load_pop, load_tokens, peak_le_cost, r_of, resolved, ts

B, SEED, MRE, COV = 10_000, 80, -0.05, 0.60


def sellers_of(r: dict) -> int | None:
    """Máx. vendedores distintos num slot na posse; sem nenhuma troca na janela = desconhecido."""
    if not r["trades_in_hold"] or int(r["trades_in_hold"]) == 0:
        return None
    return int(r["sellers_slot"]) if r["sellers_slot"] else 0


def enrich(r: dict, idx: TokenIndex) -> dict:
    T = ts(r["decided_at"])
    pnl = Decimal(r["pnl_sol"]) if r["pnl_sol"] else None
    s = sellers_of(r) if r["exit_at"] else None
    pk = peak_le_cost(r)
    cov, cov_k = idx.coverage(T), idx.coverage(T, known_only=True)
    reu, reu_k = idx.reuse(r["mint"], T), idx.reuse(r["mint"], T, known_only=True)
    return dict(
        r, T=T, day=str(T.date()), pnl=pnl, sellers=s, cov=cov, cov_k=cov_k, reuse=reu, reuse_k=reu_k,
        has_tw=idx.has_twitter(r["mint"]), kind=idx.kind(r["mint"]), key=idx.key(r["mint"]),
        legible=reu is not None and cov is not None and cov >= COV,
        legible_k=reu_k is not None and cov_k is not None and cov_k >= COV,
        g_raw=None if pnl is None else golpe_raw(pnl=pnl, exit_reason=r["exit_reason"] or None, sellers=s),
        g_ficha=None if pnl is None else golpe_ficha(pnl=pnl, peak_le_cost=pk, exit_reason=r["exit_reason"] or None, sellers=s),
    )


def contrast(rows: list[dict], sel: np.ndarray, *, cluster: str = "mint", seed: int = SEED) -> tuple:
    y = np.array([r_of(r) for r in rows])
    if sel.sum() == 0 or (~sel).sum() == 0:
        return float("nan"), None, float("nan"), y
    ci = cluster_bootstrap(y, sel, [r[cluster] or r["mint"] for r in rows], reps=B, seed=seed)
    p = permutation_p(y, sel, [r["day"] for r in rows], reps=B, seed=seed)
    return float(y[sel].mean() - y[~sel].mean()), ci, p, y


def rate(flags: list[bool | None]) -> tuple[float, int, int]:
    k = [f for f in flags if f is not None]
    return (sum(k) / len(k) if k else float("nan")), sum(k), len(k)


def golpe_ok(ga: float, gb: float) -> bool:
    """Taxa de golpe A ≥ 2× B; ambas zero (ou não finitas) não é evidência (adendo §2.1, Astra)."""
    if not (np.isfinite(ga) and np.isfinite(gb)):
        return False
    return ga > 0 and ga >= 2 * gb


def fmt_ci(ci) -> str:
    return "—" if ci is None else f"[{ci.lo:+.4f}, {ci.hi:+.4f}]"


def line(tag: str, rows: list[dict], sel: np.ndarray, **kw) -> dict:
    d, ci, p, y = contrast(rows, sel, **kw)
    wins = y > 0
    wa = int(wins[sel].sum())
    ga, gb = rate([r["g_raw"] for r, s in zip(rows, sel) if s]), rate([r["g_raw"] for r, s in zip(rows, sel) if not s])
    fa, fb = rate([r["g_ficha"] for r, s in zip(rows, sel) if s]), rate([r["g_ficha"] for r, s in zip(rows, sel) if not s])
    print(f"{tag}: n {len(rows)} (A {int(sel.sum())} / B {int((~sel).sum())}) | média r A {y[sel].mean():+.4f} B {y[~sel].mean():+.4f}"
          f" | D {d:+.4f} {fmt_ci(ci)} p {p:.3f} | vencedoras em A {wa}/{int(wins.sum())} = {wa / max(1, wins.sum()):.1%}"
          f" | golpe literal A {ga[1]}/{ga[2]} = {ga[0]:.1%} B {gb[1]}/{gb[2]} = {gb[0]:.1%}"
          f" | golpe ficha A {fa[0]:.1%} B {fb[0]:.1%}")
    return {"d": d, "ci": ci, "p": p, "win_a": wa / max(1, wins.sum()), "ga": ga, "gb": gb, "n_a": int(sel.sum())}


def main() -> None:
    idx = TokenIndex(load_tokens())
    pop = load_pop()
    P = [enrich(r, idx) for r in first_per_mint(pop) if resolved(r)]
    L = sorted([r for r in P if r["legible"]], key=lambda r: r["T"])
    print(f"P resolvidas {len(P)}; legíveis {len(L)} = {len(L) / len(P):.1%}; reuso>=1 {sum(r['reuse'] >= 1 for r in L)}")
    print("lanes", Counter(r["lane"] for r in L), "séries", Counter(r["series"] for r in L))
    print("rule sets", Counter(r["rs"] for r in L).most_common())
    print("golpe literal conhecido em", sum(r["g_raw"] is not None for r in L), "de", len(L))

    print("\n== primária: reuso >= 1 (A) × reuso = 0 (B) ==")
    sel = np.array([r["reuse"] >= 1 for r in L])
    prim = line("reuso>=1", L, sel)
    print("\n== secundária: sem_social (A) × com link (B) ==")
    sel2 = np.array([r["has_tw"] is False for r in L])
    sec = line("sem_social", L, sel2)
    fam = adjust_family([prim["p"], sec["p"]])
    print(f"Holm {{reuso, sem_social}}: {fam.holm_adjusted[0]:.3f} · {fam.holm_adjusted[1]:.3f}")

    print("\n== forma: D por limiar de reuso ==")
    for k in (1, 2, 3, 5, 10):
        line(f"reuso>={k}", L, np.array([r["reuse"] >= k for r in L]))

    print("\n== sensibilidades (descritivas) ==")
    Lk = [r for r in P if r["legible_k"]]
    line("s1 known_only", Lk, np.array([r["reuse_k"] >= 1 for r in Lk]))
    Lkp = [r for r in Lk if r["legible"]]
    line("s1b mesmas linhas do s1, reuso primário", Lkp, np.array([r["reuse"] >= 1 for r in Lkp]))
    Lnk = [r for r in L if not r["legible_k"]]
    line("s1c legíveis que o s1 perde (identidade própria ou universo vistos depois de T)", Lnk, np.array([r["reuse"] >= 1 for r in Lnk]))
    Lt = [r for r in L if r["has_tw"]]
    line("s2 só com link", Lt, np.array([r["reuse"] >= 1 for r in Lt]))
    for kind in ("profile", "post"):
        Lx = [r for r in L if r["has_tw"] is False or r["kind"] == kind]
        line(f"s3 tipo {kind} (A = {kind} com reuso; B = reuso 0)", Lx, np.array([r["reuse"] >= 1 for r in Lx]))
    Lr = [r for r in L if r["lane"] == "real"]
    line("s4 só reais", Lr, np.array([r["reuse"] >= 1 for r in Lr]))
    Ln = [r for r in L if not r["rs"].startswith("recuo")]
    line("s5 sem recuo_v1", Ln, np.array([r["reuse"] >= 1 for r in Ln]))
    for a, b in (("2026-09-16", "2026-09-22"), ("2026-09-23", "2026-09-27")):
        Ld = [r for r in L if a <= r["day"] < b]  # fim exclusivo (não houve decisão em 22/09)
        line(f"s6 {a} a {b} (exclusivo)", Ld, np.array([r["reuse"] >= 1 for r in Ld]))
    Lc = [r for r in L if r["cov"] >= 0.85]
    line("s7 cobertura>=0,85", Lc, np.array([r["reuse"] >= 1 for r in Lc]))
    line("s8 cluster = chave social", L, sel, cluster="key")

    print("\n== contrafactual real (todas as posições reais da porta) ==")
    R = [enrich(r, idx) for r in pop if r["lane"] == "real" and r["status"] == "closed" and r["pnl_sol"]]
    for tag, legk, reuk in (("primária", "legible", "reuse"), ("known_only", "legible_k", "reuse_k")):
        blocked = [r for r in R if r[legk] and r[reuk] >= 1]
        tot = sum((r["pnl"] for r in R), Decimal(0))
        loss = sum((r["pnl"] for r in blocked if r["pnl"] < 0), Decimal(0))
        gain = sum((r["pnl"] for r in blocked if r["pnl"] > 0), Decimal(0))
        wins = [r for r in R if r["pnl"] > 0]
        killed = [r for r in blocked if r["pnl"] > 0]
        print(f"[{tag}] {len(R)} reais (Σ {tot:+.4f} SOL), legíveis {sum(r[legk] for r in R)}, bloqueadas {len(blocked)}: "
              f"perda evitada {loss:+.4f}, ganho morto {gain:+.4f} → Δ {-(loss + gain):+.4f} SOL; "
              f"vencedoras mortas {len(killed)}/{len(wins)} = {len(killed) / max(1, len(wins)):.1%}")
        for r in sorted(killed, key=lambda r: r["T"]):
            print(f"    morta: {r['symbol']} {r['pnl']:+.4f} ({r['day']}, reuso {r[reuk]}, {r['kind']}, {r['key']})")
        worst = sorted(blocked, key=lambda r: r["pnl"])[:8]
        print("    piores bloqueadas:", "; ".join(f"{r['symbol']} {r['pnl']:+.4f} ({r['exit_reason']}, reuso {r[reuk]}, {r['kind']})" for r in worst))
        if tag == "primária":
            cf = {"delta": -(loss + gain), "killed": len(killed) / max(1, len(wins)), "gain": gain, "loss": loss}

    print("\n== rótulo (regra §2 + adendo §2.1) ==")
    ga, gb = prim["ga"][0], prim["gb"][0]
    g_ok = golpe_ok(ga, gb)
    ci = prim["ci"]
    if len(L) / len(P) < 0.60:
        lab = "LIMITE DE DADO (legível < 60 %)"
    elif prim["n_a"] < 30:
        lab = "LIMITE DE DADO (< 30 com reuso >= 1)"
    elif prim["win_a"] > 0.30:
        lab = f"REFUTA por (c): {prim['win_a']:.1%} das vencedoras com reuso >= 1 (> 30 %)"
    elif ci.lo > -0.01:
        lab = "REFUTA pelo intervalo (IC inf de D > −0,01)"
    elif prim["d"] <= MRE and ci.hi < 0:
        ok = g_ok and cf["delta"] > 0 and cf["killed"] <= 0.20 and fam.holm_adjusted[0] < 0.05
        lab = "CONFIRMA" if ok else "NÃO CONFIRMA (efeito principal sem as condições secundárias)"
    elif ci.hi > -0.01:
        lab = "NÃO CONFIRMA ((a) literal dispara; pela errata do R76 sozinha não refuta)"
    else:
        lab = "NÃO CONFIRMA"
    print(f"golpe literal A/B = {ga:.1%} / {gb:.1%} (≥ 2×? {g_ok}); contrafactual Δ {cf['delta']:+.4f}, mata {cf['killed']:.1%}; Holm {fam.holm_adjusted[0]:.3f}")
    print("RÓTULO:", lab)


if __name__ == "__main__":
    main()
