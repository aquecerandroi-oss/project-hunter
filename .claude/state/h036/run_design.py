"""h036 — características operacionais do desenho da H-036 (antes de T0; usa só a VARIÂNCIA da coorte exposta).

Modelo: cada dia de calendário tem trades com prob. ``p_active``; um dia ativo é um dia sorteado da coorte exposta da v14
(com os seus trades e o seu choque comum), resíduos centrados (média 0) + θ; ``rate`` < 1 afina cada trade com essa
probabilidade (menos sinais por dia, mesmo choque do dia). Consultas em H/3, 2H/3 e H dias; fronteiras LD-OBF.
Regras de decisão = as do bloco H-036. Saída em design.txt.

uv run --no-sync python .claude/state/h036/run_design.py > .claude/state/h036/design.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import design  # noqa: E402
import measure  # noqa: E402

import cost_instrument as ci  # noqa: E402

ALPHA = 0.025
TS = (1 / 3, 2 / 3, 1.0)
MRE_CONFIRM = 0.05
DELTA = 0.10
SEED = 20261007


def pool() -> tuple[list[np.ndarray], float]:
    rows = [r for r in measure.build(measure.load()) if (r[0].strategy, r[0].version) == ("mean_reversion", "v14")
            and r[0].funding is not None]
    net = np.array([t.gross_r - t.funding_r - ci.cost_r(open_=lg.open, base=lg.base, risk=lg.risk,
                    c_in=ci.taker_in_resting_tp(lg, strict=True)[0], c_out=ci.taker_in_resting_tp(lg, strict=True)[1])
                    for t, lg, _ in rows])
    days = [t.day for t, _, _ in rows]
    centred = net - net.mean()
    by = [centred[[i for i, d in enumerate(days) if d == u]] for u in sorted(set(days))]
    return by, float(net.mean())


def _versions(by: list[np.ndarray], rate: float, rng: np.random.Generator, k: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """Para cada dia do pool, ``k`` versões afinadas (soma dos resíduos, contagem); com rate = 1, a própria."""
    s = np.zeros((len(by), k)); c = np.zeros((len(by), k))
    for j, x in enumerate(by):
        mask = rng.random((k, len(x))) < rate if rate < 1 else np.ones((k, len(x)), dtype=bool)
        s[j] = (mask * x).sum(axis=1); c[j] = mask.sum(axis=1)
    return s, c


def simulate(by: list[np.ndarray], *, theta: float, rate: float, horizon: int, p_active: float, n_sim: int,
             b: list[float], rng: np.random.Generator) -> dict[str, float]:
    """Vetorizado: toda estatística da decisão sai de somas por dia (média-razão, EP CR1, metades)."""
    vs, vc = _versions(by, rate, rng)
    pick = rng.integers(len(by), size=(n_sim, horizon)); ver = rng.integers(vs.shape[1], size=(n_sim, horizon))
    act = rng.random((n_sim, horizon)) < p_active
    cnt = np.where(act, vc[pick, ver], 0.0)
    sm = np.where(act, vs[pick, ver], 0.0) + theta * cnt
    looks = [int(round(horizon * t)) for t in TS]
    done = np.zeros(n_sim, dtype=bool)
    res = {"CONFIRMA": 0.0, "REFUTA": 0.0, "NÃO CONFIRMA": 0.0, "para_L1": 0.0, "para_L2": 0.0, "dias": 0.0,
           "trades": 0.0}
    for k, lk in enumerate(looks):
        S, C = sm[:, :lk], cnt[:, :lk]
        g = (C > 0).sum(axis=1)
        m = S.sum(axis=1) / C.sum(axis=1)
        resid2 = ((S - m[:, None] * C) ** 2).sum(axis=1)
        se = np.sqrt(g / (g - 1) * resid2) / C.sum(axis=1)
        h = lk // 2
        m1 = S[:, :h].sum(axis=1) / np.maximum(C[:, :h].sum(axis=1), 1)
        m2 = S[:, h:].sum(axis=1) / np.maximum(C[:, h:].sum(axis=1), 1)
        bt = np.array([design.t_boundary(b[k], int(x) - 1) for x in g])  # fronteira em t(G−1)
        conf = (m / se >= bt) & (m >= MRE_CONFIRM) & (m1 > 0) & (m2 > 0)
        final = k == len(looks) - 1
        stop_other = ~conf & ((m <= 0) | final)
        upper = m + np.array([design.t_quantile(0.975, int(x) - 1) for x in g]) * se
        for name, mask in (("CONFIRMA", conf), ("REFUTA", stop_other & (upper < DELTA)),
                           ("NÃO CONFIRMA", stop_other & (upper >= DELTA))):
            new = mask & ~done
            res[name] += new.sum()
            if k < 2:
                res[f"para_L{k + 1}"] += new.sum()
            res["dias"] += lk * new.sum()
            res["trades"] += C.sum(axis=1)[new].sum()
        done |= conf | stop_other
    return {key: v / n_sim for key, v in res.items()}


def main() -> None:
    b = design.boundaries(TS, alpha=ALPHA, n_sim=2_000_000, seed=SEED)
    print(f"fronteiras LD-OBF unilateral α={ALPHA} em t={TS}: " + " · ".join(f"{x:.3f}" for x in b))
    print("alfa acumulado: " + " · ".join(f"{design.obf_spent(t, ALPHA):.5f}" for t in TS))
    by, mean_obs = pool()
    n = sum(len(x) for x in by)
    print(f"pool: coorte exposta v14, {len(by)} dias, {n} trades, {n/len(by):.1f} trades/dia ativo; R médio ao custo "
          f"medido (B estrito) {mean_obs:+.3f} — só a VARIÂNCIA entra (resíduos centrados)")
    r_all = np.concatenate(by)
    sums = np.array([x.sum() for x in by]); cnt = np.array([len(x) for x in by])
    m, se = design.cluster_mean_se(r_all, np.concatenate([np.full(len(x), i) for i, x in enumerate(by)]))
    print(f"dp por trade {r_all.std(ddof=1):.3f} · EP agrupado por dia {se:.4f} em {len(by)} dias "
          f"(σ_dia equivalente {se*np.sqrt(len(by)):.3f})")
    rng = np.random.default_rng(SEED)
    print("\n| horizonte (dias corridos) | ritmo | θ (R/trade) | CONFIRMA | REFUTA (+0,10) | NÃO CONFIRMA | para em L1 | "
          "para em L2 | dias esperados | trades esperados |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for horizon in (182, 273):
        for rate, label in ((1.0, "8,5/dia ativo"), (0.5, "≈4,3/dia ativo")):
            for theta in (0.0, 0.03, 0.05, 0.10, 0.15):
                o = simulate(by, theta=theta, rate=rate, horizon=horizon, p_active=0.88, n_sim=20000, b=b, rng=rng)
                print(f"| {horizon} | {label} | {theta:+.2f} | {o['CONFIRMA']:.3f} | {o['REFUTA']:.3f} | "
                      f"{o['NÃO CONFIRMA']:.3f} | {o['para_L1']:.3f} | {o['para_L2']:.3f} | {o['dias']:.0f} | "
                      f"{o['trades']:.0f} |")


if __name__ == "__main__":
    main()
