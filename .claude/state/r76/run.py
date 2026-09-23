"""R76 — H-014: cobertura, tercis, moinho, patamar, despejo, contrafactual e proxy. Lê `rows.json`.

Sinal dos quadros: D = média(tercil baixo) − média(tercil alto); a previsão é D ≥ +0,05 (baixo rende mais).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from infra.research.protocol import run_hypothesis  # noqa: E402
from infra.research.report import render  # noqa: E402
from infra.research.resampling import cluster_bootstrap  # noqa: E402
from infra.research.spec import (  # noqa: E402
    DecisionPolicy, HypothesisSpec, InferencePlan, ObservabilityWaiver, PreRegistration,
)
from infra.research.stats import adjust_family, plateau_or_spike, threshold_curve  # noqa: E402

HERE = Path(__file__).resolve().parent
REPS, SEED, MIN_SIDE = 10_000, 76, 20
GRID_Q = (0.20, 0.25, 1 / 3, 0.40, 0.50)
PRE = PreRegistration(
    prediction=("o tercil alto de rede_financiadora_pct rende menos −0,05 por SOL que o baixo (IC 95 % bootstrap "
                "por mint inteiramente abaixo de zero) e tem taxa de despejo coordenado ≥ 2× a do tercil baixo; "
                "patamar em dois limiares vizinhos; no contrafactual das reais, um teto bloqueia ≥ 3 das 6 piores e "
                "mata ≤ 20 % das vencedoras"),
    refutation=("limite superior do IC acima de −0,01 por SOL; ou a curva é pico e não patamar; ou o teto que "
                "bloqueia as piores mata > 30 % das vencedoras; ou financiador resolvido em < 60 % das compradoras "
                "pré-decisão (limite de dado, não resultado). ERRATA (Astra, antes do contraste): a cláusula (a) "
                "literal só não-confirma; refutação pelo intervalo = limite superior de D(baixo−alto) < +0,01"),
    decision_rule=("moinho sobre os tercis extremos: CONFIRMA com D(baixo−alto)>0, D≥MRE 0,05, IC inferior>0, "
                   "p<0,05, braço baixo lucrativo em nível, planalto; rótulo final pela regra das notas §0.4b-4"),
    registered_on="2026-09-23",
    threshold_policy="limiar = máximo do tercil baixo (quantil 1/3, empates juntos), fixado antes dos desfechos",
)


def tercile_masks(vals: list[float]) -> tuple[list[bool], list[bool]]:
    """Baixo = v ≤ q(1/3); alto = v > q(2/3). Empates ficam juntos (a fronteira é um valor)."""
    v = np.asarray(vals, dtype=float)
    q1, q2 = np.quantile(v, 1 / 3), np.quantile(v, 2 / 3)
    return [bool(x <= q1) for x in v], [bool(x > q2) for x in v]


def wilson(k: int, n: int) -> str:
    if n == 0:
        return "—"
    p, z = k / n, 1.96
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return f"{p:.1%} [{max(0, c - h):.1%}–{min(1, c + h):.1%}]"


def cuts(rows, var: str) -> tuple[float, float]:
    """Cortes dos tercis na população ELEGÍVEL com a variável, ANTES de filtrar pelo desfecho (Astra, R76)."""
    v = np.asarray([r[var] for r in rows if r.get(var) is not None], dtype=float)
    return float(np.quantile(v, 1 / 3)), float(np.quantile(v, 2 / 3))


def contrast(rows, var: str, out: str, seed: int, cut: tuple[float, float] | None = None) -> dict:
    q1, q2 = cut if cut is not None else cuts(rows, var)
    ok = [r for r in rows if r.get(var) is not None and r.get(out) is not None]
    if len(ok) < 3 * MIN_SIDE:
        return {"n": len(ok), "note": "sem potência"}
    sub = [r for r in ok if r[var] <= q1 or r[var] > q2]
    m = np.array([r[var] <= q1 for r in sub])
    y = np.array([r[out] for r in sub], dtype=float)
    res = {"n": len(ok), "n_lo": int(m.sum()), "n_hi": int((~m).sum()), "cut_lo": q1, "cut_hi": q2}
    if res["n_lo"] < MIN_SIDE or res["n_hi"] < MIN_SIDE:
        return res | {"note": "contraste não identificável (< 20 por lado)"}
    iv = cluster_bootstrap(y, m, [r["mint"] for r in sub], reps=REPS, seed=seed)
    dmp = np.array([float(bool(r["dump"])) for r in sub])
    ivd = cluster_bootstrap(dmp, ~m, [r["mint"] for r in sub], reps=REPS, seed=seed + 1)  # alto − baixo
    lo_rows = [r for r, s in zip(sub, m, strict=True) if s]
    hi_rows = [r for r, s in zip(sub, m, strict=True) if not s]
    return res | {"mean_lo": float(y[m].mean()), "mean_hi": float(y[~m].mean()), "D": float(y[m].mean() - y[~m].mean()),
                  "ci": (iv.lo, iv.hi), "p_le0": iv.p_le0, "dump_diff_ci": (ivd.lo, ivd.hi),
                  "dump_lo": (sum(bool(r["dump"]) for r in lo_rows), len(lo_rows)),
                  "dump_hi": (sum(bool(r["dump"]) for r in hi_rows), len(hi_rows)),
                  "big_lo": (sum(1 for r in lo_rows if r[out] <= -0.5), len(lo_rows)),
                  "big_hi": (sum(1 for r in hi_rows if r[out] <= -0.5), len(hi_rows)),
                  "lo_rows": lo_rows, "hi_rows": hi_rows}


def fmt(c: dict, label: str) -> str:
    if "D" not in c:
        return f"| {label} | {c['n']} | {c.get('n_lo', '—')} / {c.get('n_hi', '—')} | — | — | — | {c.get('note')} | — |"
    dl, dh = c["dump_lo"], c["dump_hi"]
    return (f"| {label} | {c['n']} | {c['n_lo']} / {c['n_hi']} | ≤ q⅓ {c['cut_lo']:.4f} / > q⅔ {c['cut_hi']:.4f}"
            f" | {c['mean_lo']:+.4f} / {c['mean_hi']:+.4f} | **{c['D']:+.4f}** | [{c['ci'][0]:+.4f}, {c['ci'][1]:+.4f}]"
            f" | {dl[0]}/{dl[1]} vs {dh[0]}/{dh[1]} |")


def moinho(rows, var: str, name: str, seed: int) -> tuple[str, float | None]:
    q1, q2 = cuts(rows, var)  # cortes na elegível inteira, antes da censura do desfecho
    ok = [r for r in rows if r.get(var) is not None and r.get("sim_ret") is not None]
    data = [dict(r, decided_at=datetime.fromisoformat(r["decided_at"])) for r in ok if r[var] <= q1 or r[var] > q2]
    thr = q1
    spec = HypothesisSpec(
        name=name, origin="perda real SIMFTR 23/09/2026 (73 vendedoras num slot)", loader=lambda: data,
        decision_instant="decided_at", outcome="sim_ret", variable=var, direction="low",
        observability=ObservabilityWaiver(reason=(
            "variável = compradoras com block_time < decisão (oráculo retrospetivo de meme_trades, R73) e "
            "financiamento com block_time < decisão (Helius); a guarda de chegada não se aplica ao oráculo")),
        inference=InferencePlan(cluster="mint", stratum="dia", block="hora", thresholds=(float(thr),),
                                reps=REPS, seed=seed),
        policy=DecisionPolicy(frozen_threshold=float(thr), minimum_effect=0.05, require_plateau=False),
        pre_registration=PRE, money_column=None,
        assumptions=("desfecho = simulate_current do R72 (1,15×/10 %/300 s, 2,23 %, pouso +1,6 s)",
                     "censura: buraco > 60 s até ao pouso; uma decisão por mint, real > papel > mais antiga",
                     "patamar avaliado fora do moinho (grelha de quantis, partições distintas)"),
    )
    rep = run_hypothesis(spec)
    return render(rep), rep.contrast.p_perm


def plateau(rows, var: str) -> list[str]:
    allv = np.array([r[var] for r in rows if r.get(var) is not None])  # grelha na elegível, antes da censura
    ok = [r for r in rows if r.get(var) is not None and r.get("sim_ret") is not None]
    grid, seen = [], set()
    for q in GRID_Q:
        t = float(np.quantile(allv, q))
        part = tuple(allv <= t)
        if part in seen:
            continue
        seen.add(part)
        grid.append(t)
    grid = sorted(set(grid))
    out = [f"Grelha pedida: quantis {[round(q, 3) for q in GRID_Q]} → limiares com partições distintas: "
           f"{[round(g, 4) for g in grid]}", ""]
    if len(grid) < 3:
        return out + ["**Patamar não avaliável**: menos de 3 partições distintas (empates colapsam a grelha)."]
    curve = threshold_curve([r[var] for r in ok], [r["sim_ret"] for r in ok], [r["mint"] for r in ok], grid,
                            direction="low", reps=REPS, seed=SEED + 500)
    out += ["| limiar (≤) | n sel | n resto | D (sel − resto) | IC 95 % |", "|---:|---:|---:|---:|---|"]
    for c in curve:
        ci = f"[{c.ci.lo:+.4f}, {c.ci.hi:+.4f}]" if c.evaluable else "—"
        d = f"{c.d:+.4f}" if c.evaluable else "—"
        out.append(f"| {c.threshold:.4f} | {c.n_selected} | {c.n_rest} | {d} | {ci} |")
    sh = plateau_or_spike(curve)
    return out + ["", f"Forma (regra do moinho): **{sh.form}** — {sh.detail}"]


if __name__ == "__main__":
    print("use report.py")
