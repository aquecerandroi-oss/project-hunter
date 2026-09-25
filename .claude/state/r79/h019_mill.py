# R79 — H-019 pelo moinho (complemento, enquadramento "piso": selecionados = acc > c1, o que o piso deixa passar).
# cd .claude/state/r79 && PYTHONPATH=C:/dev/project-hunter uv run --project C:/dev/project-hunter python h019_mill.py
import numpy as np

from h019 import accel, complete, first_per_mint, load, tertile_idx, ts
from infra.research.protocol import run_hypothesis
from infra.research.report import render
from infra.research.spec import (
    DecisionPolicy, HypothesisSpec, InferencePlan, ObservabilityColumns, PreRegistration,
)

ROWS = [r for r in first_per_mint([r for r in load() if r["has_tape"]]) if complete(r) and r["resolved"]]
X = np.array([accel(r["winj"]) for r in ROWS])
_, _, C1, _ = tertile_idx(X)
GRID = tuple(float(v) for v in np.quantile(X, (0.20, 0.25, 0.30, 1 / 3, 0.40, 0.45, 0.50)))


def loader() -> list[dict]:
    out = []
    for r in ROWS:
        out.append({
            "mint": r["mint"], "day": r["features_end_time"][:10], "hora": r["features_end_time"][:13],
            "t": ts(r["decided_at"]), "as_of": ts(r["derived_as_of"]), "computed_at": ts(r["derived_as_of"]),
            "tape_as_of": ts(r["max_recv"]) if r["max_recv"] else None,
            "acc": accel(r["winj"]), "ret": float(r["pnl_sol"]) / float(r["size_sol"]), "pnl_sol": r["pnl_sol"],
        })
    return out


spec = HypothesisSpec(
    name="H-019 — aceleração de compra (piso no tercil baixo)",
    origin="Fila de Hipoteses H-019; R79 (complemento da primária tercil × tercil)",
    loader=loader,
    decision_instant="t",
    outcome="ret",
    variable="acc",
    direction="high",
    observability=ObservabilityColumns("as_of", "computed_at", "tape_as_of"),
    inference=InferencePlan(cluster="mint", stratum="day", block="hora", thresholds=GRID, reps=10_000, seed=79),
    policy=DecisionPolicy(frozen_threshold=C1, minimum_effect=0.05),
    pre_registration=PreRegistration(
        prediction="o tercil baixo de aceleracao_compra rende menos -0,05 por SOL que o alto; aqui: o que o piso deixa passar rende +0,05 a mais que o bloqueado",
        refutation="limite superior do IC acima de -0,01; ou pico; ou o piso mata > 30 % das vencedoras; ou < 150 decisões",
        decision_rule="CONFIRMA com D>0, IC inferior>0, p<0,05, D>=MRE, patamar e nível positivo",
        registered_on="2026-09-25",
        threshold_policy="tercil 1/3 da amostra (posto), fixado antes de olhar desfechos",
    ),
    money_column="pnl_sol",
    assumptions=("r = pnl ÷ SOL gasto; real e papel juntos; custos já dentro do pnl registrado",),
)

if __name__ == "__main__":
    print(f"c1 = {C1:.4f}; grade = {tuple(round(g, 4) for g in GRID)}")
    print(render(run_hypothesis(spec)))
