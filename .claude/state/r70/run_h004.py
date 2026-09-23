"""R70 / H-004 — percentil de `sells/buys` dentro da coorte viva, pelo moinho.

Previsão e refutação copiadas **verbatim** de `obsidian/11-KNOWLEDGE/Fila de Hipoteses.md`.
O limiar (0,300 = mediana de `p_sb`) e a grelha (P20–P80 da mesma variável) foram
calculados olhando **só** a variável, nunca o desfecho.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from infra.research.protocol import run_hypothesis  # noqa: E402
from infra.research.report import render  # noqa: E402
from infra.research.spec import (  # noqa: E402
    DecisionPolicy,
    HypothesisSpec,
    InferencePlan,
    ObservabilityColumns,
    PreRegistration,
)
from load70 import h004_rows  # noqa: E402

DECISION_RULE = (
    "CONFIRMA com D>0, D≥MRE, IC 95 % inferior>0, p de permutação<0,05, braço "
    "selecionado lucrativo em nível e curva planalto. RESSALVA DO MOINHO: a fila "
    "pré-registou dois números diferentes — previsão +0,05 e barra de refutação +0,01 — "
    "e `DecisionPolicy` só tem um `minimum_effect`. Fixei `minimum_effect = +0,05` (o "
    "tamanho previsto) e a regra de refutação da fila (IC superior < +0,01) é lida à "
    "mão no relatório do estudo, sem tocar no moinho."
)

spec = HypothesisSpec(
    name="H-004 — percentil de sells/buys dentro da coorte viva",
    origin=(
        "R69 teste A — p=0,014 contra limiar BH de 0,0059 na família de 17; sobrevivente "
        "isolado, não confirmado. A variável absoluta está entre as 13 esgotadas do R65; "
        "o percentil dentro da coorte não está."
    ),
    loader=h004_rows,
    decision_instant="t",
    outcome="ret",
    variable="p_sb",
    direction="high",
    observability=ObservabilityColumns("as_of", "computed_at", "tape_as_of", strict=True),
    inference=InferencePlan(
        cluster="mint",
        stratum="dia",
        block="hora",
        thresholds=(0.1923, 0.2289, 0.2609, 0.3000, 0.3333, 0.3820, 0.4286),
        reps=10_000,
        seed=70,
    ),
    policy=DecisionPolicy(frozen_threshold=0.3000, minimum_effect=0.05),
    pre_registration=PreRegistration(
        prediction=(
            "metade alta do percentil rende mais +0,05 por SOL que a metade baixa, e a "
            "curva de limiares é planalto"
        ),
        refutation=(
            "limite superior do IC 95 % abaixo de +0,01 na população nova. Curva em pico "
            "é **não confirmação**"
        ),
        decision_rule=DECISION_RULE,
        registered_on="2026-09-23",
        threshold_policy=(
            "mediana de p_sb na população (0,300), calculada olhando só a variável e "
            "fixada antes de qualquer desfecho; grelha nos quantis P20–P80 da mesma "
            "variável (0,1923…0,4286)"
        ),
    ),
    money_column="pnl_sol",
    assumptions=(
        "ficha de 0,05 SOL; o custo de ida-e-volta do lado meme já está dentro de pnl_sol",
        "desfecho = pnl_sol / size_sol (SOL ganho por SOL arriscado), uma aposta por mint",
        "coorte viva mínima de 20 mints observáveis, como a fila pré-registou",
    ),
)

if __name__ == "__main__":
    print(render(run_hypothesis(spec)))
