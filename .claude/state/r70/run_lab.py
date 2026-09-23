"""R70 / H-005 a H-008 — as hipóteses sobre as decisões do Lab, pelo moinho.

Previsões e refutações **verbatim** da fila. Limiares e grelhas fixados olhando só as
distribuições das variáveis (nunca os desfechos) e escritos em `threshold_policy`.

Dois desvios declarados, porque a fila pediu uma população que o banco não tem:

* **H-005/H-008** — `momentum_15m` e `return_4h` **não existem** no envelope
  (`agent_signals.supporting_features`) de nenhum dos 7 728 sinais terminais da janela.
  Existem no `feature_snapshots` do minuto da decisão, com instantes próprios; é essa a
  população que corre, e a diferença aparece como suposição declarada.
* **H-006** — a fila pré-registou "tercil alto contra tercil baixo"; o moinho contrasta
  **selecionados contra o resto**. O limiar congelado é o corte do tercil superior, e o
  resto inclui o tercil do meio — contraste conservador, nunca inflacionado.
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
    ObservabilityWaiver,
    PreRegistration,
)
from load70 import h005_rows, h006_rows, h007_rows, h008_envelope_rows, h008_snapshot_rows  # noqa: E402

MILL_NOTE = (
    "RESSALVA DO MOINHO: a fila pré-registou dois números — o tamanho previsto e uma "
    "barra de refutação menor — e `DecisionPolicy` só tem um `minimum_effect`. Fixei "
    "`minimum_effect` = tamanho previsto; a barra de refutação da fila é lida à mão no "
    "relatório, sem tocar no moinho."
)
RULE = (
    "CONFIRMA com D>0, D≥MRE, IC 95 % inferior>0, p de permutação<0,05, braço "
    "selecionado lucrativo em nível e curva planalto. "
)

SNAP = ObservabilityColumns("snap_as_of", "snap_computed_at", "snap_tape", strict=True)

H005 = HypothesisSpec(
    name="H-005 — piso de impulso recente (momentum_15m <= 2,0)",
    origin="Strategy Backlog item 7 · KB-0002 — nunca medido neste recorte",
    loader=h005_rows,
    decision_instant="t",
    outcome="r",
    variable="mom15",
    direction="low",
    observability=SNAP,
    inference=InferencePlan(
        cluster="mercado",
        stratum="dia",
        thresholds=(0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0),
        reps=10_000,
        seed=70,
    ),
    policy=DecisionPolicy(frozen_threshold=2.0, minimum_effect=0.10),
    pre_registration=PreRegistration(
        prediction="decisões com `momentum_15m` ≤ 2,0 rendem mais +0,10 R que as demais",
        refutation=(
            "limite superior do IC 95 % abaixo de +0,02 R. O efeito sumir ao estratificar "
            "por ATR% é **não confirmação**"
        ),
        decision_rule=RULE + MILL_NOTE,
        registered_on="2026-09-23",
        threshold_policy=(
            "limiar 2,0 fixo, vindo do item 7 do backlog (escolha experimental K=2), "
            "nunca ajustado aos dados; grelha 0,5…4,0 em torno dele, fixada antes de "
            "olhar desfechos"
        ),
    ),
    assumptions=(
        "desfecho = r_multiple do `signal_outcomes` terminal (a unidade R da própria mesa)",
        "`momentum_15m` do `feature_snapshots` do minuto da decisão — NÃO está no "
        "envelope do sinal; é o desvio declarado desta corrida",
        "momentum_15m é retorno de 15 min dividido por atr_14_pct (unidade: ATRs)",
    ),
)

H006 = HypothesisSpec(
    name="H-006 — desequilíbrio agressor na barra do sinal",
    origin="Strategy Backlog item 11 · KB-0014 — cobertura de 100 % medida, utilidade nunca medida",
    loader=h006_rows,
    decision_instant="t",
    outcome="ret_net",
    variable="taker_imb",
    direction="high",
    observability=ObservabilityColumns("bar_close", "bar_recv", None, strict=True),
    inference=InferencePlan(
        cluster="mercado",
        stratum="dia",
        block="bloco3d",
        thresholds=(0.45, 0.50, 0.55, 0.5898, 0.65, 0.70),
        reps=10_000,
        seed=70,
    ),
    policy=DecisionPolicy(frozen_threshold=0.5898, minimum_effect=0.0010),
    pre_registration=PreRegistration(
        prediction=(
            "o tercil alto rende ≥ +0,10 % líquido por operação acima do tercil baixo, ao "
            "custo medido de 0,14 %"
        ),
        refutation="limite superior do IC 95 % abaixo do MRE",
        decision_rule=(
            RULE + "DESVIO DECLARADO: a fila pede tercil alto contra tercil baixo e o "
            "moinho contrasta selecionados contra o resto; o limiar congelado é o corte "
            "do tercil superior e o resto inclui o tercil do meio — o contraste medido é "
            "menor que o pré-registado, nunca maior."
        ),
        registered_on="2026-09-23",
        threshold_policy=(
            "corte do tercil superior de `taker_imbalance_5m` (P66,7 = 0,5898), calculado "
            "olhando só a variável e fixado antes de qualquer desfecho"
        ),
    ),
    assumptions=(
        "custo de ida-e-volta 0,14 % (R68), já subtraído do desfecho",
        "desfecho = lado × (exit_price / virtual_entry − 1) − 0,0014",
        "taker_imbalance_5m = Σ taker_buy_volume ÷ Σ volume das 5 velas de 1 min "
        "`is_final` que fecham antes da decisão; menos de 5 barras é ausente",
    ),
)

H007 = HypothesisSpec(
    name="H-007 — teto de volume relativo (exaustão)",
    origin="Strategy Backlog item 12 · KB-0015 — nenhum edge prometido; o valor 12 é exploratório",
    loader=h007_rows,
    decision_instant="t",
    outcome="r",
    variable="env_vr5",
    direction="low",
    observability=ObservabilityWaiver(
        "o envelope do sinal guarda `volume_ratio_5m` sem instante próprio "
        "(`source_ts` nulo); o valor é o que a estratégia usou para decidir, gravado "
        "com o sinal, mas a guarda de instantes não pôde correr sobre ele"
    ),
    inference=InferencePlan(
        cluster="mercado",
        stratum="dia",
        thresholds=(8.0, 10.0, 12.0, 14.0, 16.0),
        reps=10_000,
        seed=70,
    ),
    policy=DecisionPolicy(frozen_threshold=12.0, minimum_effect=0.10),
    pre_registration=PreRegistration(
        prediction=(
            "decisões com `volume_ratio_5m` ≤ 12 rendem mais +0,10 R que as acima de 12, "
            "com planalto entre 8 e 16"
        ),
        refutation=(
            "limite superior do IC 95 % abaixo de +0,02 R. Curva em pico é **não confirmação**"
        ),
        decision_rule=RULE + MILL_NOTE,
        registered_on="2026-09-23",
        threshold_policy="limiar 12 fixo, vindo do item 12 do backlog; grelha 8…16 como a fila pediu",
    ),
    assumptions=(
        "população restrita ao piso de volume da mesa (volume_ratio_5m ≥ 4×), para o "
        "contraste ser sobre o teto e não sobre o piso",
        "desfecho = r_multiple do `signal_outcomes` terminal",
    ),
)


def _h008(loader, name: str, extra: str) -> HypothesisSpec:
    return HypothesisSpec(
        name=name,
        origin="Strategy Backlog item 6 · KB-0001 — transferência de horizonte não demonstrada",
        loader=loader,
        decision_instant="t",
        outcome="r",
        variable="ret4h" if loader is h008_snapshot_rows else "env_ret4h",
        direction="high",
        observability=SNAP
        if loader is h008_snapshot_rows
        else ObservabilityWaiver("o envelope do sinal não carrega instantes por feature"),
        inference=InferencePlan(
            cluster="mercado",
            stratum="dia",
            thresholds=(-0.02, -0.01, 0.0, 0.01, 0.02, 0.03),
            reps=10_000,
            seed=70,
        ),
        policy=DecisionPolicy(frozen_threshold=0.0, minimum_effect=0.10),
        pre_registration=PreRegistration(
            prediction="decisões com `return_4h` > 0 rendem mais +0,10 R que as demais",
            refutation=(
                "limite superior do IC 95 % abaixo de +0,02 R. Fração censurada acima de "
                "20 % invalida o estudo (população diferente), não refuta nada"
            ),
            decision_rule=RULE + MILL_NOTE,
            registered_on="2026-09-23",
            threshold_policy="limiar 0 fixo (o sinal do retorno de 4 h), como a fila pré-registou",
        ),
        assumptions=("desfecho = r_multiple do `signal_outcomes` terminal", extra),
    )


H008_ENV = _h008(
    h008_envelope_rows,
    "H-008 — portão de tendência de 4 h (população verbatim: envelope do sinal)",
    "população verbatim da fila: `return_4h` presente no envelope do sinal",
)
H008_SNAP = _h008(
    h008_snapshot_rows,
    "H-008 — portão de tendência de 4 h (desvio declarado: feature_snapshots)",
    "desvio declarado: `return_4h` do `feature_snapshots` do minuto da decisão",
)

SPECS = {
    "H-005": H005,
    "H-006": H006,
    "H-007": H007,
    "H-008-envelope": H008_ENV,
    "H-008-snapshot": H008_SNAP,
}

if __name__ == "__main__":
    which = sys.argv[1]
    print(render(run_hypothesis(SPECS[which])))
