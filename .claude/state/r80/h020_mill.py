# R80 — H-020 pelo moinho (complemento: selecionados = reuso 0, direção low, limiar congelado 0,5).
# cd .claude/state/r80 && PYTHONPATH=C:/dev/project-hunter PYTHONIOENCODING=utf-8 uv run --project C:/dev/project-hunter python h020_mill.py
from h020 import enrich
from infra.research.protocol import run_hypothesis
from infra.research.report import render
from infra.research.spec import DecisionPolicy, HypothesisSpec, InferencePlan, ObservabilityColumns, PreRegistration
from r80 import LOOKBACK, TokenIndex, first_per_mint, load_pop, load_tokens, r_of, resolved

IDX = TokenIndex(load_tokens())


def loader() -> list[dict]:
    out = []
    for r in first_per_mint(load_pop()):
        if not resolved(r):
            continue
        e = enrich(r, IDX)
        if not e["legible"]:
            continue
        T = e["T"]
        used = [c for c, _m, _o in IDX.matched(r["mint"], T)]
        last = max(used) if used else T - LOOKBACK
        out.append({"mint": r["mint"], "day": e["day"], "hora": T.strftime("%Y-%m-%d %H"), "t": T,
                    "as_of": last, "computed_at": T, "tape_as_of": last,
                    "reuso": float(e["reuse"]), "ret": r_of(r), "pnl_sol": r["pnl_sol"]})
    return out


spec = HypothesisSpec(
    name="H-020 — reuso do link de X/Twitter nas 24 h anteriores (o filtro deixa passar reuso = 0)",
    origin="Fila de Hipoteses H-020; R80 (complemento da primária A × B)",
    loader=loader, decision_instant="t", outcome="ret", variable="reuso", direction="low",
    observability=ObservabilityColumns("as_of", "computed_at", "tape_as_of"),
    inference=InferencePlan(cluster="mint", stratum="day", block="hora", thresholds=(0.5, 1.5, 2.5, 4.5), reps=10_000, seed=80),
    policy=DecisionPolicy(frozen_threshold=0.5, minimum_effect=0.05),
    pre_registration=PreRegistration(
        prediction="reuso >= 1 rende menos -0,05 por SOL que reuso = 0; aqui: o que o filtro deixa passar rende +0,05 a mais",
        refutation="IC sup acima de -0,01; ou o filtro mata > 30 % das vencedoras; ou < 30 com reuso >= 1; ou legível < 60 %",
        decision_rule="CONFIRMA com D>0, IC inferior>0, p<0,05, D>=MRE, patamar e nível positivo",
        registered_on="2026-09-26",
        threshold_policy="reuso >= 1 (qualquer reuso), fixado no pré-registo",
    ),
    money_column="pnl_sol",
    assumptions=("r = pnl ÷ SOL gasto; real e papel juntos; custos já dentro do pnl registrado",
                 "link de X/Twitter tratado como metadado da criação (observação posterior não é antecipação)"),
)

if __name__ == "__main__":
    print(render(run_hypothesis(spec)))
