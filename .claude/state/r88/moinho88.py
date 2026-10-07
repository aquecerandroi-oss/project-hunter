"""R88 — o moinho (infra/research) sobre o D AGRUPADO, só descritivo pela emenda de 00:36Z.

O D decisório é o ajustado por conjunto (run88.py). Aqui roda o protocolo padrão para o relatório
canônico e a impressão digital; a permutação é linha a linha dentro do conjunto (não decisória).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))

from run88 import GRIDS, THR, load  # noqa: E402

from infra.research.protocol import run_hypothesis  # noqa: E402
from infra.research.report import render  # noqa: E402
from infra.research.spec import (  # noqa: E402
    DecisionPolicy,
    HypothesisSpec,
    InferencePlan,
    ObservabilityColumns,
    ObservabilityWaiver,
    PreRegistration,
)

PRE = (HERE / "prereg_frozen.md").read_text(encoding="utf-8")


def ts(x: object) -> datetime | None:
    if not x:
        return None
    s = str(x)
    if s[-3] in "+-" and ":" not in s[-6:]:
        s += ":00"
    return datetime.fromisoformat(s)


def rows_for(m: str) -> list[dict[str, object]]:
    out = []
    for r in load():
        if r["medida"] != m or r["cls"] != "measured":
            continue
        d = dict(r)
        d["t"] = ts(r["proposed_at"])
        d["as_of"] = ts(r["tape_as_of"]) or d["t"]
        d["computed_at"] = ts(r["tape_known_at"]) or d["as_of"]
        d["pnl_sol"] = r["pnl"]
        out.append(d)
    return out


def spec(m: str) -> HypothesisSpec:
    obs = (
        ObservabilityColumns("as_of", "computed_at")
        if m == "B"
        else ObservabilityWaiver("valor do pedigree_e2b gravado em reasons na transação da proposta (o que o portão leu)")
    )
    return HypothesisSpec(
        name=f"H-031 {m} — fatia do maior comprador (D agrupado, descritivo)",
        origin="Fila H-031; R88",
        loader=lambda: rows_for(m),
        decision_instant="t",
        outcome="y",
        variable="share_f",
        direction="low",
        observability=obs,
        inference=InferencePlan(cluster="mint", stratum="rs", block="day", thresholds=GRIDS[m], reps=10_000, seed=20261007),
        policy=DecisionPolicy(frozen_threshold=THR[m], minimum_effect=0.05),
        pre_registration=PreRegistration(
            prediction=PRE.split("- **previsão:**")[1].split("\n")[0][:600],
            refutation=PRE.split("- **refutação:**")[1].split("\n")[0][:600],
            decision_rule="emenda 00:36Z: D ajustado por conjunto decide (run88.py); este relatório é descritivo",
            registered_on="2026-10-07",
            threshold_policy="B: 0,35 da E2-b (16/09); A: quantil 2/3 da lista elegível congelada às 00:39:40Z",
        ),
        money_column="pnl_sol",
        assumptions=("r = pnl_sol / entry.sol_spent como persistido; fee_pct 1,25–1,75 %/perna no simulador",),
    )


if __name__ == "__main__":
    for m in ("A", "B"):
        print(render(run_hypothesis(spec(m))))
        print("\n" + "=" * 80 + "\n")
