"""R83 — passo cego: população, censura, guarda, redundância e cortes. Nenhum valor de desfecho é lido.

cd .claude/state/r83 && uv run --project C:/dev/project-hunter python blind.py > blind.txt
"""

from __future__ import annotations

from collections import Counter, defaultdict
from fractions import Fraction

import numpy as np
from h023 import assign_extremes, load_features

from infra.research.guards import Instants, check_observable

FEATS = ("ret15", "ret60", "ret240", "mom15", "atr_pct", "env_ret15", "env_z15", "env_rvol")


def ranks(x: np.ndarray) -> np.ndarray:
    """Postos médios (empates recebem a média), como `scipy.stats.rankdata`."""
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x), float)
    r[order] = np.arange(1, len(x) + 1)
    _, inv, cnt = np.unique(x, return_inverse=True, return_counts=True)
    sums = np.bincount(inv, weights=r)
    return (sums / cnt)[inv]


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = ranks(np.asarray(a, float)), ranks(np.asarray(b, float))
    return float(np.corrcoef(ra, rb)[0, 1])


def rho_table(rows, var: str) -> dict[str, tuple[float, int]]:
    out = {}
    for f in FEATS:
        pairs = [(r[var], r[f]) for r in rows if r[var] is not None and r[f] is not None]
        if len(pairs) >= 30:
            a, b = zip(*pairs, strict=True)
            out[f] = (spearman(list(a), list(b)), len(pairs))
    return out


def main() -> None:
    pop, cnt = load_features()
    print("# R83 passo cego — sem desfechos")
    print("export:", dict(cnt))
    guard = Counter()
    kept = []
    for r in pop:
        why = check_observable(Instants(r["as_of"], r["computed_at"]), r["t"], str(r["signal_id"]))
        if why is None:
            kept.append(r)
        else:
            guard["recusada_" + ("prosp" if r["prospective"] else "replay")] += 1
    print("guarda (check_observable, t = emitted_at):", dict(guard), "mantidas", len(kept))
    lag = [(r["t"] - r["obs"]).total_seconds() for r in pop if r["prospective"]]
    print(f"emitted_at − obs (prospectiva) s: mediana {np.median(lag):.2f} p99 {np.percentile(lag, 99):.2f}")

    print("\n## contagens por família / estratégia (perp, terminal, dedup, pós-guarda)")
    tab = defaultdict(Counter)
    for r in kept:
        key = (r["family"], r["strategy"])
        tab[key]["n"] += 1
        tab[key]["com_R"] += r["has_r"]
        tab[key]["com_feature"] += r["d_high"] is not None
        tab[key]["R_e_feature"] += r["has_r"] and r["d_high"] is not None
        tab[key]["prosp"] += r["prospective"]
        if r["window_reason"]:
            tab[key]["aus_" + r["window_reason"]] += 1
    for key in sorted(tab):
        print(key, dict(tab[key]))
    fam = Counter()
    for r in kept:
        if r["has_r"] and r["d_high"] is not None:
            fam[r["family"]] += 1
    print("R e feature por família:", dict(fam))
    reasons = Counter(r["r_net_reason"] for r in kept if not r["has_r"])
    print("R nulo, motivo (top):", reasons.most_common(4))

    print("\n## versões (R e feature)")
    sv = Counter(r["sv"] for r in kept if r["has_r"] and r["d_high"] is not None)
    print(dict(sorted(sv.items())))
    mk = Counter((r["family"], r["market"]) for r in kept if r["has_r"] and r["d_high"] is not None)
    for f in ("continuacao", "reversao", "outras"):
        print(f, "mercados:", sum(1 for (ff, _m) in mk if ff == f))

    print("\n## redundância: Spearman ρ de d_high (e d_low) contra as features do envelope/reconstruídas")
    for f in ("continuacao", "reversao", "outras"):
        rows = [r for r in kept if r["family"] == f and r["has_r"]]
        for var in ("d_high", "d_low"):
            t = rho_table(rows, var)
            print(f, var, {k: (round(v[0], 3), v[1]) for k, v in t.items()})
        print(f, "ρ(d_high, d_low) =", round(rho_table([dict(r, ret15=r["d_low"]) for r in rows], "d_high")
                                              .get("ret15", (float("nan"), 0))[0], 3))
    for s in ("momentum", "volume_anomaly", "mean_reversion"):
        rows = [r for r in kept if r["strategy"] == s and r["has_r"]]
        t = rho_table(rows, "d_high")
        print(s, "d_high", {k: (round(v[0], 3), v[1]) for k, v in t.items()})

    print("\n## distribuição de d_high e cortes dos tercis (dentro de cada estratégia)")
    for s in sorted({r["strategy"] for r in kept}):
        xs = np.array([r["d_high"] for r in kept if r["strategy"] == s and r["has_r"] and r["d_high"] is not None])
        if xs.size == 0:
            continue
        q = np.percentile(xs, [0, 10, 33.3, 50, 66.7, 90, 100])
        print(s, xs.size, "quantis d_high:", np.round(q, 4).tolist(),
              "retenção de d_high >= -0,005:", round(float((xs >= -0.005).mean()), 3))
    for f in ("continuacao", "reversao"):
        rows = [r for r in kept if r["family"] == f and r["has_r"] and r["d_high"] is not None]
        lab = assign_extremes(rows, "d_high", Fraction(1, 3))
        print(f, "tercis:", dict(Counter(lab)))


if __name__ == "__main__":
    main()
