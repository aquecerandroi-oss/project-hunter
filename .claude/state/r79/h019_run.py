# R79 — H-019: veredito. cd .claude/state/r79 && PYTHONIOENCODING=utf-8 uv run --project C:/dev/project-hunter python h019_run.py
from collections import Counter
from decimal import Decimal

import numpy as np

from h019 import accel, complete, extremes_idx, first_per_mint, load, peak_le_cost, tertile_idx, ts
from infra.research.resampling import cluster_bootstrap, permutation_p
from infra.research.stats import adjust_family

B, SEED = 10_000, 79
GRID = (0.20, 0.25, 0.30, 1 / 3, 0.40, 0.45, 0.50)
MRE = -0.05


def r_of(r: dict) -> float:
    return float(r["pnl_sol"]) / float(r["size_sol"])


def ctop(r: dict) -> bool | None:
    """comprou_no_topo (T4.92): perda e pico ≤ custo; sem marca → None."""
    pk = peak_le_cost(r)
    return None if pk is None else (pk and r_of(r) < 0)


def contrast(y: np.ndarray, lo: np.ndarray, hi: np.ndarray, mints: list[str], day: list[str], seed: int = SEED):
    idx = np.concatenate([lo, hi])
    sel = np.zeros(idx.size, dtype=bool)
    sel[: lo.size] = True
    yy = y[idx]
    ci = cluster_bootstrap(yy, sel, [mints[i] for i in idx], reps=B, seed=seed)
    p = permutation_p(yy, sel, [day[i] for i in idx], reps=B, seed=seed)
    return float(y[lo].mean() - y[hi].mean()), ci, p


def label(n: int, nl: int, nh: int, d: float, lo: float, hi: float, win_lo: float, plateau: bool, ct_ratio: float,
          cf_ok: bool) -> str:
    if n < 150:
        return f"LIMITE DE DADO ({n} < 150)"
    if min(nl, nh) < 20:
        return "CONTRASTE NÃO IDENTIFICÁVEL (< 20 num extremo)"
    if win_lo > 0.30:
        return f"REFUTA por (c): o piso mata {win_lo:.1%} das vencedoras (> 30 %)"
    if lo > -0.01:
        return "REFUTA pelo intervalo (IC inf de D > −0,01)"
    if d <= MRE and hi < 0:
        if not plateau:
            return "REFUTA por (b): pico, não patamar"
        if ct_ratio >= 1.5 and cf_ok:
            return "CONFIRMA"
        return "NÃO CONFIRMA (efeito principal sem as condições secundárias)"
    if hi > -0.01:
        return "NÃO CONFIRMA ((a) literal dispara; pela errata do R76 sozinha não refuta)"
    return "NÃO CONFIRMA"


def rate(flags: list[bool | None]) -> tuple[float, int, int]:
    k = [f for f in flags if f is not None]
    return (sum(k) / len(k) if k else float("nan")), sum(k), len(k)


def analyse(tag: str, pop: list[dict], key: str, c1_frozen: float | None = None, verbose: bool = True) -> dict:
    x = np.array([accel(r["winj"], key) for r in pop])
    y = np.array([r_of(r) for r in pop])
    mints = [r["mint"] for r in pop]
    day = [r["features_end_time"][:10] for r in pop]
    lo, hi, c1, c2 = tertile_idx(x)
    d, ci, p = contrast(y, lo, hi, mints, day)
    wins = y > 0
    win_lo = float(wins[lo].sum() / wins.sum())
    ct = [ctop(r) for r in pop]
    ctl, cth = rate([ct[i] for i in lo]), rate([ct[i] for i in hi])
    ct_ratio = ctl[0] / cth[0] if cth[0] > 0 else float("inf")
    curve, seen = [], set()
    for q in GRID:
        ql, qh, a, b = extremes_idx(x, q)
        part = (tuple(ql), tuple(qh))
        if part in seen or min(ql.size, qh.size) < 2:
            continue
        seen.add(part)
        dq, ciq, _ = contrast(y, ql, qh, mints, day, seed=SEED + int(q * 100))
        curve.append((q, a, b, ql.size, qh.size, dq, ciq.lo, ciq.hi))
    near = {round(q, 3): dq for q, _, _, _, _, dq, _, _ in curve}
    plateau = all(near.get(q, 0.0) <= MRE for q in (0.30, 0.40))
    out = dict(n=len(pop), c1=c1, c2=c2, nl=lo.size, nh=hi.size, ml=y[lo].mean(), mh=y[hi].mean(), d=d, ci=ci, p=p,
               win_lo=win_lo, wins=int(wins.sum()), ctl=ctl, cth=cth, ct_ratio=ct_ratio, curve=curve, plateau=plateau)
    if verbose:
        print(f"\n## {tag} — variável {key}: n = {len(pop)} | lanes {dict(Counter(r['lane'] for r in pop))}")
        print(f"   cortes q1/3 = {c1:.4f}, q2/3 = {c2:.4f}; baixo {lo.size}, alto {hi.size}; zeros {int((x == 0).sum())}")
        print(f"   média r: baixo {y[lo].mean():+.4f} (vitória {wins[lo].mean():.3f}, perda≥50% {np.mean(y[lo] <= -0.5):.3f})"
              f" | meio {np.delete(y, np.concatenate([lo, hi])).mean():+.4f} | alto {y[hi].mean():+.4f}"
              f" (vitória {wins[hi].mean():.3f}, perda≥50% {np.mean(y[hi] <= -0.5):.3f}) | todos {y.mean():+.4f}")
        print(f"   D (baixo − alto) = {d:+.4f} IC95 [{ci.lo:+.4f}, {ci.hi:+.4f}] (bootstrap por mint {B}, inválidas {ci.invalid:.3f})"
              f" | p perm (estrato dia) {p:.4f}")
        print(f"   (c) vencedoras no tercil baixo: {int(wins[lo].sum())}/{int(wins.sum())} = {win_lo:.1%}")
        print(f"   comprou_no_topo: baixo {ctl[1]}/{ctl[2]} = {ctl[0]:.3f} | alto {cth[1]}/{cth[2]} = {cth[0]:.3f} | razão {ct_ratio:.2f}")
        print("   curva (baixo ≤ Q(q) × alto > Q(1−q)):")
        for q, a, b, nl, nh, dq, l_, h_ in curve:
            print(f"     q {q:.3f}: ≤ {a:.3f} (n {nl}) × > {b:.3f} (n {nh}): D {dq:+.4f} [{l_:+.4f}, {h_:+.4f}]")
        print(f"   patamar (q 0,30 e 0,40 com D ≤ −0,05): {plateau}")
    return out


def counterfactual(rows: list[dict], c1: float, key: str) -> None:
    real = [r for r in rows if r["lane"] == "real" and complete(r) and r["resolved"]]
    blocked = [r for r in real if accel(r["winj"], key) <= c1]
    pn = [Decimal(r["pnl_sol"]) for r in blocked]
    gains = sum((v for v in pn if v > 0), Decimal(0))
    losses = sum((v for v in pn if v < 0), Decimal(0))
    tot = sum((Decimal(r["pnl_sol"]) for r in real), Decimal(0))
    print(f"\n## Contrafactual real ({key}, piso acc > {c1:.4f}): {len(real)} posições reais com fita completa, Σ {tot:+.4f} SOL")
    print(f"   bloqueadas {len(blocked)}: perdas evitadas {losses:+.4f} SOL, ganhos mortos {gains:+.4f} SOL →"
          f" Δ SOL = {-(gains + losses):+.4f}; vencedoras mortas {sum(v > 0 for v in pn)}/{sum(Decimal(r['pnl_sol']) > 0 for r in real)}")
    for r in sorted(blocked, key=lambda r: r["features_end_time"]):
        print(f"     {r['features_end_time'][:19]} {r['symbol'][:12]:12} {r['rs']:10} acc {accel(r['winj'], key):.3f}"
              f" pnl {Decimal(r['pnl_sol']):+.4f} {r['exit_reason']}{'  ← VENCEDORA' if Decimal(r['pnl_sol']) > 0 else ''}")


def guards(pop: list[dict]) -> None:
    late = [r for r in pop if r["max_recv"] and ts(r["max_recv"]) > ts(r["tape_as_of"])]
    mism = [r for r in pop if ts(r["derived_as_of"]) != ts(r["tape_as_of"])]
    after = [r for r in pop if ts(r["tape_as_of"]) > ts(r["decided_at"])]
    lag = np.array([(ts(r["recorded_at"]) - ts(r["tape_as_of"])).total_seconds() for r in pop])
    print(f"\n## Guardas: troca da fatia recebida depois do as_of {len(late)}; derived.as_of ≠ as_of {len(mism)};"
          f" fita depois da aprovação {len(after)}; gravação − as_of p50 {np.median(lag):.2f} s, máx {lag.max():.2f} s")


def main() -> None:
    rows = load()
    fp = first_per_mint([r for r in rows if r["has_tape"]])
    pop = [r for r in fp if complete(r) and r["resolved"]]
    guards(pop)
    res = {k: analyse("PRIMÁRIA", pop, k) for k in ("buy_sol", "buys")}
    fam = adjust_family([res["buy_sol"]["p"], res["buys"]["p"]])
    print(f"\n## Holm (família SOL, contagem): p {fam.p} → Holm {tuple(round(v, 4) for v in fam.holm_adjusted)}")
    for k in ("buy_sol", "buys"):
        s = res[k]
        cf_real = [r for r in rows if r["lane"] == "real" and complete(r) and r["resolved"]]
        blocked = [Decimal(r["pnl_sol"]) for r in cf_real if accel(r["winj"], k) <= s["c1"]]
        cf_ok = -sum((v for v in blocked if v < 0), Decimal(0)) > sum((v for v in blocked if v > 0), Decimal(0))
        print(f"   → {k}: {label(s['n'], s['nl'], s['nh'], s['d'], s['ci'].lo, s['ci'].hi, s['win_lo'], s['plateau'], s['ct_ratio'], cf_ok)}"
              f" (piso bloqueia mais perdas que ganhos nas reais: {cf_ok})")
    for k in ("buy_sol", "buys"):
        counterfactual(rows, res[k]["c1"], k)
    imm = first_per_mint([r for r in rows if r["has_tape"] and r["rs"] != "recuo_v1/1"])
    analyse("s1 — sem recuo_v1 (só entrada imediata)", [r for r in imm if complete(r) and r["resolved"]], "buy_sol")
    analyse("s2 — só reais", [r for r in pop if r["lane"] == "real"], "buy_sol")
    analyse("s3 — gaps = 0", [r for r in fp if complete(r, no_gaps=True) and r["resolved"]], "buy_sol")
    for dday in ("2026-09-24", "2026-09-25"):
        analyse(f"s4 — dia {dday}", [r for r in pop if r["features_end_time"].startswith(dday)], "buy_sol")


if __name__ == "__main__":
    main()
