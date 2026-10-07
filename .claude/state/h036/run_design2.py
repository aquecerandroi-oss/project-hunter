"""h036 — emenda: características operacionais do procedimento EMENDADO, pela própria função de decisão
(``decision.decide``), com calibração de ALPHA_FINAL e P_REF. Saída em design2.txt.

Pool: coorte EXPOSTA da v14 (25 dias com trade). R primário = todo a mercado ao custo medido; estresse = idem com o
pior spread de saída e +2 bp por perna. O R primário é centrado (média 0) e recebe +θ; o custo extra do estresse
(primário − estresse, ≥ 0) entra como foi medido. Entra a forma da distribuição (assimetria, caudas, tamanho dos dias,
associação entre quantidade e retorno), não só a variância (Astra must-fix 4). Cenários de informação:
S1 ritmo constante 8,5/dia ativo · S2 constante ≈4,3 · S3 caindo 1→0,25 · S4 subindo 0,25→1 (pouca informação cedo) ·
S5 choques persistentes (blocos de 5 dias consecutivos do pool, ritmo S1). 88 % dos dias de calendário com trade.
O que NÃO entra: interrupção operacional (encerra em LIMITE), mudança de regime além do pool, cobertura (testada à parte).

uv run --no-sync python .claude/state/h036/run_design2.py > .claude/state/h036/design2.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import cost_instrument as ci  # noqa: E402
import decision as dc  # noqa: E402
import measure  # noqa: E402

H = 273
LOOKS = (91, 182, 273)
P_ACTIVE = 0.88
SEED = 20261007
NSIM = 20_000


def pool() -> tuple[list[np.ndarray], list[np.ndarray], float]:
    rows = [r for r in measure.build(measure.load()) if (r[0].strategy, r[0].version) == ("mean_reversion", "v14")
            and r[0].funding is not None]
    prim, extra, days = [], [], []
    for t, lg, e in rows:
        sc = measure.scen_costs(lg, e)
        base = t.gross_r - t.funding_r
        prim.append(base - sc["A_taker"])
        extra.append(sc["A_stress"] - sc["A_taker"])
        days.append(t.day)
    p, x = np.array(prim), np.array(extra)
    order = sorted(set(days))
    idx = [[i for i, d in enumerate(days) if d == u] for u in order]
    return [p[i] - p.mean() for i in idx], [x[i] for i in idx], float(p.mean())


def _rate(scn: str) -> np.ndarray:
    lin = np.linspace(0, 1, H)
    return {"S1": np.ones(H), "S2": np.full(H, 0.5), "S3": 1 - 0.75 * lin, "S4": 0.25 + 0.75 * lin,
            "S5": np.ones(H)}[scn]


def paths(res: list[np.ndarray], ext: list[np.ndarray], scn: str, rng: np.random.Generator
          ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(c, soma dos resíduos, soma do custo extra) por caminho × dia; θ entra depois (s = r + θ·c)."""
    npool = len(res)
    if scn == "S5":
        starts = rng.integers(npool, size=(NSIM, -(-H // 5)))
        pick = ((starts[:, :, None] + np.arange(5)) % npool).reshape(NSIM, -1)[:, :H]
    else:
        pick = rng.integers(npool, size=(NSIM, H))
    act = rng.random((NSIM, H)) < P_ACTIVE
    rate = _rate(scn)
    c = np.zeros((NSIM, H)); r = np.zeros((NSIM, H)); x = np.zeros((NSIM, H))
    for j in range(npool):  # afina cada trade com a probabilidade do dia (mesmo choque do dia)
        where = np.argwhere(act & (pick == j))
        if len(where) == 0:
            continue
        keep = rng.random((len(where), len(res[j]))) < rate[where[:, 1]][:, None]
        c[where[:, 0], where[:, 1]] = keep.sum(axis=1)
        r[where[:, 0], where[:, 1]] = keep @ res[j]
        x[where[:, 0], where[:, 1]] = keep @ ext[j]
    return c, r, x


def run(c: np.ndarray, r: np.ndarray, x: np.ndarray, theta: float, *, alpha_final: float, p_ref: float
        ) -> dict[str, float]:
    s = r + theta * c
    t = s - x
    ok = np.ones(NSIM, dtype=bool)
    done = np.zeros(NSIM, dtype=bool)
    out = {k: 0.0 for k in ("CONFIRMA", "REFUTA", "NÃO CONFIRMA", "LIMITE", "L1", "L2", "dias")}
    for k, lk in enumerate(LOOKS):
        v = dc.decide(c[:, :lk], s[:, :lk], t[:, :lk], look=k, coverage_ok=ok, alpha_final=alpha_final, p_ref=p_ref)
        new = (v != dc.CONTINUA) & ~done
        for code in (dc.CONFIRMA, dc.REFUTA, dc.NAO_CONFIRMA, dc.LIMITE):
            out[dc.NOMES[code]] += float((new & (v == code)).sum())
        if k < 2:
            out[f"L{k + 1}"] += float(new.sum())
        out["dias"] += lk * float(new.sum())
        done |= new
    return {key: val / NSIM for key, val in out.items()}


def main() -> None:
    res, ext, mean_obs = pool()
    print(f"pool: {len(res)} dias, {sum(len(v) for v in res)} trades; R médio exposto todo a mercado {mean_obs:+.3f} "
          f"(centrado a 0); custo extra do estresse médio {np.concatenate(ext).mean():.3f} R")
    sums = np.array([v.sum() for v in res])
    z = (sums - sums.mean()) / sums.std(ddof=1)
    print(f"assimetria das somas diárias de resíduos {np.mean(z**3):+.2f} (negativa = dias de perda coletiva)")
    rng = np.random.default_rng(SEED)
    sims = {s: paths(res, ext, s, rng) for s in ("S1", "S2", "S3", "S4", "S5")}
    print("\n### calibração (θ = 0 → alfa; θ = +0,10 → REFUTA indevido)")
    for af in (0.024, 0.020, 0.016):
        a = {s: run(*sims[s], 0.0, alpha_final=af, p_ref=0.975)["CONFIRMA"] for s in sims}
        print(f"ALPHA_FINAL {af}: alfa simulado " + " · ".join(f"{s} {v:.4f}" for s, v in a.items()))
    for pr in (0.975, 0.99, 0.995):
        b = {s: run(*sims[s], 0.10, alpha_final=0.024, p_ref=pr)["REFUTA"] for s in sims}
        print(f"P_REF {pr}: P(REFUTA | θ=+0,10) " + " · ".join(f"{s} {v:.4f}" for s, v in b.items()))
    af, pr = float(sys.argv[1]) if len(sys.argv) > 1 else dc.ALPHA_FINAL, float(sys.argv[2]) if len(sys.argv) > 2 \
        else dc.P_REF
    print(f"\n### procedimento com ALPHA_FINAL {af}, P_REF {pr} (EP Monte Carlo ≈ 0,0011 em 0,025; ≈ 0,003 em 0,5)")
    print("| cenário | θ | CONFIRMA | REFUTA | NÃO CONFIRMA | LIMITE | para em L1 | para em L2 | dias esperados |")
    print("|---|---|---|---|---|---|---|---|---|")
    for s in sims:
        for th in (0.0, 0.03, 0.05, 0.10, 0.15):
            o = run(*sims[s], th, alpha_final=af, p_ref=pr)
            print(f"| {s} | {th:+.2f} | {o['CONFIRMA']:.3f} | {o['REFUTA']:.3f} | {o['NÃO CONFIRMA']:.3f} | "
                  f"{o['LIMITE']:.3f} | {o['L1']:.3f} | {o['L2']:.3f} | {o['dias']:.0f} |")


if __name__ == "__main__":
    main()
