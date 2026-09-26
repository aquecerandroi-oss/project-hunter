# R81 — spec do moinho para H-021 (enquadramento "teto": selecionados = distância ≤ c2, o que o teto deixa passar).
from __future__ import annotations

from collections.abc import Callable

from infra.research.spec import DecisionPolicy, HypothesisSpec, InferencePlan, ObservabilityColumns, PreRegistration


def build_spec(loader: Callable[[], list[dict]], *, threshold: float, grid: tuple[float, ...], reps: int = 10_000,
               name_suffix: str = "", extra_assumptions: tuple[str, ...] = ()) -> HypothesisSpec:
    return HypothesisSpec(
        name=f"H-021 E EXPLORATÓRIA (não é veredito) — distância do suporte de 5 min (o teto deixa passar dist <= c2){name_suffix}",
        origin="Fila de Hipoteses H-021; R81 (complemento da primária tercil alto × tercil baixo)",
        loader=loader, decision_instant="t", outcome="ret", variable="dist", direction="low",
        observability=ObservabilityColumns("as_of", "computed_at", "tape_as_of"),
        inference=InferencePlan(cluster="mint", stratum="day", block="hora", thresholds=grid, reps=reps, seed=81),
        policy=DecisionPolicy(frozen_threshold=threshold, minimum_effect=0.05),
        pre_registration=PreRegistration(
            prediction="o tercil alto de distancia_do_suporte rende menos -0,05 por SOL que o baixo; aqui: o que o teto deixa passar rende +0,05 a mais que o bloqueado",
            refutation="IC sup acima de -0,01; ou pico; ou o teto mata > 30 % das vencedoras; ou < 150 decisões com 5 min de fita",
            decision_rule="EXPLORATÓRIO: o rótulo mecânico do moinho NÃO é veredito da H-021 (concluída por limite de dado) nem autoriza braço",
            registered_on="2026-09-26",
            threshold_policy="tercil 2/3 da amostra (posto), fixado antes de olhar desfechos",
        ),
        money_column="pnl_sol",
        assumptions=("r = pnl ÷ SOL gasto; real e papel juntos; custos já dentro do pnl registrado",) + extra_assumptions,
    )
