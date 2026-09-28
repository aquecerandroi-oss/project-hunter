"""R83 / H-023 — o contraste congelado (notes-R83.md §2 + emenda §2b) sobre o moinho. Lê desfechos.

cd .claude/state/r83 && PYTHONPATH=C:/dev/project-hunter uv run --project C:/dev/project-hunter python run.py > h023.txt
(R83_OUT=out_synth.csv usa os desfechos sintéticos de `smoke_synthetic.py`.)
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from fractions import Fraction

import numpy as np
from h023 import CACHE, GRID, assign_extremes, fila_label, guarded, load_features, read_csv
from stats83 import boot_p_two_sided, distinct, episode_perm_p

from infra.research.protocol import run_hypothesis
from infra.research.report import render
from infra.research.resampling import block_bootstrap, cluster_bootstrap, permutation_p
from infra.research.spec import (
    DecisionPolicy,
    HypothesisSpec,
    InferencePlan,
    ObservabilityColumns,
    PreRegistration,
)
from infra.research.stats import CurvePoint, adjust_family, plateau_or_spike
from infra.research.verdict import _no_power

REPS, SEED, MRE = 10_000, 83, 0.05
Row = dict[str, object]
POLICY = DecisionPolicy(frozen_threshold=0.5, minimum_effect=MRE, require_plateau=False,
                        require_positive_level=True, min_per_side=20, min_clusters=8)


def with_outcomes(rows: list[Row]) -> list[Row]:
    out = {r["signal_id"]: r for r in read_csv(CACHE / os.environ.get("R83_OUT", "out.csv"))}
    joined = []
    for r in rows:
        o = out.get(str(r["signal_id"]))
        assert o is not None, r["signal_id"]
        joined.append(dict(r, y=float(o["r_multiple"]) if o["r_multiple"] else None,
                           y_exf=float(o["r_ex_funding"]) if o["r_ex_funding"] else None,
                           result=o["result"], stratum=f"{r['strategy']}|{r['day']}"))
    return joined


def arms(rows: Sequence[Row], var: str, q: Fraction, group: str, outcome: str) -> list[Row]:
    """Linhas de baixo ∪ alto (cortes com a população que tem desfecho e variável), com `alto` 1/0."""
    usable = [r for r in rows if r[outcome] is not None and r[var] is not None]
    labels = assign_extremes(usable, var, q, group)
    return [dict(r, alto=1 if lab == "alto" else 0) for r, lab in zip(usable, labels, strict=True)
            if lab in ("alto", "baixo")]


def quick(rows: Sequence[Row], outcome: str = "y", seed: int = SEED) -> dict[str, float]:
    y = np.array([r[outcome] for r in rows], float)
    sel = np.array([r["alto"] == 1 for r in rows])
    ci = cluster_bootstrap(y, sel, [r["market"] for r in rows], reps=REPS, seed=seed)
    blk = block_bootstrap(y, sel, [r["day"] for r in rows], reps=REPS, seed=seed)
    p = permutation_p(y, sel, [r["stratum"] for r in rows], reps=REPS, seed=seed)
    return {"n_alto": int(sel.sum()), "n_baixo": int((~sel).sum()), "alto": float(y[sel].mean()),
            "baixo": float(y[~sel].mean()), "d": float(y[sel].mean() - y[~sel].mean()), "lo": ci.lo, "hi": ci.hi,
            "blo": blk.lo, "bhi": blk.hi, "p": p, "mk": ci.groups}


def fmt(tag: str, s: dict[str, float]) -> str:
    return (f"{tag}: alto {s['n_alto']} × baixo {s['n_baixo']} | alto {s['alto']:+.4f} baixo {s['baixo']:+.4f} | "
            f"D {s['d']:+.4f} IC mercado [{s['lo']:+.4f}, {s['hi']:+.4f}] ({s['mk']} mercados) | "
            f"IC dia [{s['blo']:+.4f}, {s['bhi']:+.4f}] | p linha {s['p']:.4f}")


def curve(rows: Sequence[Row], var: str, group: str = "strategy") -> list[CurvePoint]:
    pts = []
    for j, q in enumerate(GRID):
        a = arms(rows, var, q, group, "y")
        y = np.array([r["y"] for r in a], float)
        sel = np.array([r["alto"] == 1 for r in a])
        ci = cluster_bootstrap(y, sel, [r["market"] for r in a], reps=REPS, seed=SEED + 10 + j)
        pts.append(CurvePoint(float(q), int(sel.sum()), int((~sel).sum()),
                              float(y[sel].mean() - y[~sel].mean()), ci, True))
    return pts


def mill(rows: Sequence[Row], var: str) -> tuple[str, object]:
    a = arms(rows, var, Fraction(1, 3), "strategy", "y")
    spec = HypothesisSpec(
        name=f"H-023 — {var} na continuação (tercil alto − baixo, dentro da estratégia)",
        origin="KB-0004 (George & Hwang), Strategy Backlog item 8, Dicionário item 1",
        loader=lambda: a,
        decision_instant="t", outcome="y", variable="alto", direction="high",
        observability=ObservabilityColumns("as_of", "computed_at", strict=False),
        inference=InferencePlan(cluster="market", stratum="stratum", block=None, thresholds=(), reps=REPS, seed=SEED),
        policy=POLICY,
        pre_registration=PreRegistration(
            prediction="nos sinais de continuação o tercil mais perto da máxima de 24 h rende ≥ +0,05 R líquido "
                       "a mais que o mais longe, IC 95 % bootstrap por mercado acima de zero, com patamar",
            refutation="IC sup < +0,01 R → REFUTA pelo tamanho; efeito oposto sustentado (IC sup < −0,01) → REFUTA; "
                       "a leitura literal 'IC inf < −0,01' sozinha dá NÃO CONFIRMA (errata do R76); pico → NÃO CONFIRMA",
            decision_rule="rótulo externo (h023.fila_label): guardas de potência do moinho; CONFIRMA com D ≥ 0,05, "
                          "IC inf > 0, p do portão (máx. de episódios e bootstrap por mercado) < 0,05, Holm ≤ 0,05, "
                          "alto > 0 em nível e patamar em partições distintas da grade q ∈ {1/5..1/2}; "
                          "require_plateau desligado no moinho porque sobre o indicador a curva é degenerada",
            registered_on="2026-09-27",
            threshold_policy="tercis de posto dentro de cada estratégia (stats.terciles), cortes pela variável só, "
                             "antes de ler desfechos; limiar 0,5 sobre o indicador separa alto de baixo",
        ),
        assumptions=("R = signal_outcomes.r_multiple (R_net: fee 4 bps, spread 2 bps, derrapagem 5 bps + funding)",
                     "feature reconstruída das velas com a fórmula de produção (price.py:106), validada 337/337"),
    )
    report = run_hypothesis(spec)
    return render(report), report


def gate_p(a: Sequence[Row], outcome: str = "y", seed: int = SEED) -> tuple[float, float, float]:
    """(p de episódios, p bilateral do bootstrap por mercado, o maior dos dois) — emenda §2b.2."""
    y = np.array([r[outcome] for r in a], float)
    sel = np.array([r["alto"] == 1 for r in a])
    ep = [f"{r['strategy']}|{r['market']}|{r['obs']}" for r in a]
    p_ep = episode_perm_p(y, sel, ep, [r["stratum"] for r in a], reps=REPS, seed=seed)
    p_bt = boot_p_two_sided(y, sel, [r["market"] for r in a], reps=REPS, seed=seed + 1)
    return p_ep, p_bt, max(p_ep, p_bt)


def composition(a: Sequence[Row]) -> str:
    c = Counter((r["strategy"], "alto" if r["alto"] else "baixo") for r in a)
    return ", ".join(f"{s} {c[(s, 'alto')]}/{c[(s, 'baixo')]}" for s in sorted({k[0] for k in c}))


def tercile_means(rows: Sequence[Row], var: str, outcome: str = "y") -> dict[str, tuple[int, float]]:
    usable = [r for r in rows if r[outcome] is not None and r[var] is not None]
    g: dict[str, list[float]] = defaultdict(list)
    for r, lb in zip(usable, assign_extremes(usable, var, Fraction(1, 3)), strict=True):
        g[str(lb)].append(float(r[outcome]))  # type: ignore[arg-type]
    return {k: (len(v), round(float(np.mean(v)), 4)) for k, v in sorted(g.items())}


def one_per_bar(rows: Sequence[Row]) -> list[Row]:
    """Uma decisão por (estratégia, mercado, obs): a versão de menor número."""
    best: dict[tuple[object, ...], Row] = {}
    for r in sorted(rows, key=lambda r: (int(str(r["version"]).lstrip("v")), str(r["signal_id"]))):
        best.setdefault((r["strategy"], r["market"], r["obs"]), r)
    return list(best.values())


def primary(cont: list[Row]) -> None:
    third = Fraction(1, 3)
    res = {}
    for var in ("d_high", "d_low"):
        print(f"\n## 1. Continuação — {var} pelo moinho (saída mecânica; o rótulo H-023 é o do §6)")
        text, rep = mill(cont, var)
        print(text)
        a = arms(cont, var, third, "strategy", "y")
        p_ep, p_bt, p_gate = gate_p(a)
        print(fmt(f"{var} conferência (mesmas linhas)", quick(a)))
        print(f"{var}: p episódios {p_ep:.4f} | p bootstrap mercado {p_bt:.4f} | p do portão {p_gate:.4f} | "
              f"p linha a linha (moinho, descritivo) {rep.contrast.p_perm:.4f}")  # type: ignore[attr-defined]
        print(f"{var} composição (alto/baixo):", composition(a))
        pts = curve(cont, var)
        for p in pts:
            print(f"  {var} q={p.threshold:.3f}: {p.n_selected}×{p.n_rest} D {p.d:+.4f} "
                  f"IC [{p.ci.lo:+.4f}, {p.ci.hi:+.4f}]")
        dist = distinct(pts)
        shape = plateau_or_spike(dist)
        print(f"  {var} partições distintas {len(dist)} de {len(pts)} — forma: {shape}")
        res[var] = (rep, p_gate, shape)
    fam = adjust_family([res["d_high"][1], res["d_low"][1]])
    print(f"\nHolm {{d_high, d_low}} sobre o p do portão: {fam.p} → {fam.holm_adjusted} sobrevive {fam.holm_survives}")
    print("\n## 2. Tercis (n, média R_net) na continuação")
    for var in ("d_high", "d_low"):
        print(var, tercile_means(cont, var))
    print("\n## 6. Rótulo H-023 (regra congelada §2.7 + §2b.3)")
    n = len([r for r in cont if r["y"] is not None and r["d_high"] is not None])
    for i, var in enumerate(("d_high", "d_low")):
        rep, p_gate, shape = res[var]
        c = rep.contrast  # type: ignore[attr-defined]
        blocked = _no_power(c, POLICY)
        lab, why = fila_label(n=n, rho_max=0.385 if var == "d_high" else 0.0, d=c.d, lo=c.ci.lo, hi=c.ci.hi,
                              p=p_gate, p_holm=fam.holm_adjusted[i], level_alto=c.mean_selected, shape=shape.form)
        tag = "H-023 (continuação, d_high)" if var == "d_high" else "secundária d_low (mesma regra, leitura)"
        print(tag + ":", "NÃO CONFIRMA (guarda de potência: " + blocked + ")" if blocked else lab, "|", "; ".join(why))


def sensitivities(cont: list[Row], cont_no_guard: list[Row]) -> None:
    third = Fraction(1, 3)
    print("\n## 4. Sensibilidades (descritivas; não mudam o rótulo)")
    prim = arms(cont, "d_high", third, "strategy", "y")
    sens: list[tuple[str, Callable[[], list[Row]], str]] = [
        ("r_ex_funding, mesmas linhas e cortes da primária", lambda: prim, "y_exf"),
        ("r_ex_funding, cortes recalculados em todos", lambda: arms(cont, "d_high", third, "strategy", "y_exf"),
         "y_exf"),
        ("sem a guarda de persistência", lambda: arms(cont_no_guard, "d_high", third, "strategy", "y"), "y"),
        ("só prospectiva", lambda: arms([r for r in cont if r["prospective"]], "d_high", third, "strategy", "y"), "y"),
        ("só replay", lambda: arms([r for r in cont if not r["prospective"]], "d_high", third, "strategy", "y"), "y"),
        ("só momentum", lambda: arms([r for r in cont if r["strategy"] == "momentum"], "d_high", third, "strategy",
                                     "y"), "y"),
        ("só volume_anomaly", lambda: arms([r for r in cont if r["strategy"] == "volume_anomaly"], "d_high", third,
                                           "strategy", "y"), "y"),
        ("só momentum v3 (paper)", lambda: arms([r for r in cont if r["sv"] == "momentum/v3"], "d_high", third,
                                               "strategy", "y"), "y"),
        ("tercis do agregado", lambda: arms([dict(r, all="x") for r in cont], "d_high", third, "all", "y"), "y"),
        ("tercis por versão", lambda: arms(cont, "d_high", third, "sv", "y"), "y"),
        ("uma por (estratégia, mercado, barra)", lambda: arms(one_per_bar(cont), "d_high", third, "strategy", "y"),
         "y"),
    ]
    for tag, f, out in sens:
        print(fmt(tag, quick(f(), out)))
    mom = [r for r in cont if r["strategy"] == "momentum" and r["y"] is not None]
    kb = [dict(r, alto=1 if r["d_high"] >= -0.005 else 0) for r in mom]  # type: ignore[operator]
    print(fmt("KB-0004 d_high ≥ −0,005 × resto (momentum)", quick(kb)))
    for s in ("momentum", "volume_anomaly"):
        print(f"tercis d_high {s}:", tercile_means([r for r in cont if r["strategy"] == s], "d_high"))


def descriptive(rev: list[Row], oth: list[Row]) -> None:
    third = Fraction(1, 3)
    print("\n## 5. Reversão (sem sinal previsto), v14 e outras — descritivo")
    groups = (("reversão", rev),
              ("mean_reversion (só a estratégia)", [r for r in rev if r["strategy"] == "mean_reversion"]),
              ("mean_reversion v14 (spot/1)", [r for r in rev if r["sv"] == "mean_reversion/v14"]), ("outras", oth))
    for tag, pop_ in groups:
        for var in ("d_high", "d_low"):
            a = arms(pop_, var, third, "strategy", "y")
            p_ep, p_bt, _ = gate_p(a)
            print(fmt(f"{tag} {var}", quick(a)) + f" | p ep {p_ep:.4f} p bt {p_bt:.4f}")
        print(f"  {tag} tercis d_high:", tercile_means(pop_, "d_high"))
    pts = distinct(curve(rev, "d_high"))
    print("reversão curva d_high (q, D, IC):",
          [(round(p.threshold, 3), round(p.d, 4), round(p.ci.lo, 4), round(p.ci.hi, 4)) for p in pts],
          plateau_or_spike(pts).form)


def main() -> None:
    pop, cnt = load_features()
    kept, refused = guarded(pop)
    cnt["recusadas_guarda"] = refused
    rows = with_outcomes(kept)
    print("# R83 / H-023 — contraste (desenho congelado em notes-R83.md §2 + emenda §2b)")
    print("população:", dict(cnt))
    by_state = Counter((r["family"], r["result"], r["y"] is not None) for r in rows)
    for k in sorted(by_state):
        print("  estado", k, by_state[k])
    cont = [r for r in rows if r["family"] == "continuacao"]
    primary(cont)
    no_guard = [r for r in with_outcomes(pop) if r["family"] == "continuacao"]
    sensitivities(cont, no_guard)
    descriptive([r for r in rows if r["family"] == "reversao"], [r for r in rows if r["family"] == "outras"])


if __name__ == "__main__":
    main()
