"""O moinho de ponta a ponta sobre séries sintéticas com desfecho conhecido."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from infra.research.guards import LookAheadError
from infra.research.protocol import run_hypothesis
from infra.research.spec import (
    DecisionPolicy,
    HypothesisSpec,
    InferencePlan,
    ObservabilityColumns,
    ObservabilityWaiver,
    PreRegistration,
    PreRegistrationError,
    Split,
)

T0 = datetime(2026, 9, 1, tzinfo=UTC)

PRE = PreRegistration(
    prediction="o braço selecionado rende mais +0,05 por unidade que o resto",
    refutation="IC 95 % do contraste inteiramente abaixo de +0,01",
    decision_rule="CONFIRMA se D>0, IC inferior>0, p<0,05, D>=MRE e planalto",
    registered_on="2026-09-23",
    threshold_policy="fixo, congelado no pré-registo",
)


def _rows(
    n_clusters: int = 120,
    effect: float = 0.5,
    *,
    noise: float = 0.05,
    cheat: bool = False,
    missing_every: int = 0,
) -> list[dict[str, Any]]:
    """Linhas sintéticas: `x <= 50` rende `effect`, o resto rende 0."""
    rows: list[dict[str, Any]] = []
    for i in range(n_clusters):
        t = T0 + timedelta(days=i % 10, minutes=i)
        x = float((i * 37) % 100)
        y = (effect if x <= 50 else 0.0) + noise * (1.0 if i % 2 else -1.0)
        as_of = t + timedelta(seconds=1) if cheat else t - timedelta(seconds=30)
        rows.append(
            {
                "mint": f"m{i}",
                "t": t,
                "day": t.date().isoformat(),
                "x": None if missing_every and i % missing_every == 0 else x,
                "ret": y,
                "pnl_sol": Decimal(str(round(y / 20, 6))),
                "feat_as_of": as_of,
                "feat_computed_at": as_of,
                "feat_tape_as_of": as_of,
            }
        )
    return rows


def _spec(rows: list[dict[str, Any]], **over: Any) -> HypothesisSpec:
    base: dict[str, Any] = {
        "name": "H-teste",
        "origin": "teste sintético",
        "loader": lambda: rows,
        "decision_instant": "t",
        "outcome": "ret",
        "variable": "x",
        "direction": "low",
        "observability": ObservabilityColumns("feat_as_of", "feat_computed_at", "feat_tape_as_of"),
        "inference": InferencePlan(
            cluster="mint",
            stratum="day",
            thresholds=(20.0, 30.0, 40.0, 50.0, 60.0, 70.0),
            reps=1500,
            seed=1,
        ),
        "policy": DecisionPolicy(frozen_threshold=50.0, minimum_effect=0.05),
        "pre_registration": PRE,
        "money_column": "pnl_sol",
    }
    base.update(over)
    return HypothesisSpec(**base)


# ------------------------------------------------------------------- pré-registo


def test_refuses_to_run_without_a_prediction() -> None:
    with pytest.raises(PreRegistrationError, match="sem pré-registo"):
        run_hypothesis(_spec(_rows(), pre_registration=None))


def test_refuses_an_incomplete_pre_registration() -> None:
    incomplete = PreRegistration(PRE.prediction, "   ", PRE.decision_rule, "2026-09-23", "fixo")
    with pytest.raises(PreRegistrationError, match="incompleto"):
        run_hypothesis(_spec(_rows(), pre_registration=incomplete))


def test_fingerprint_changes_when_the_prediction_is_rewritten() -> None:
    a = run_hypothesis(_spec(_rows(40)))
    rewritten = PreRegistration(
        "na verdade eu previa o contrário", PRE.refutation, PRE.decision_rule, "2026-09-23", "fixo"
    )
    b = run_hypothesis(_spec(_rows(40), pre_registration=rewritten))
    assert a.fingerprint != b.fingerprint


# ----------------------------------------------------------------- anti-antecipação


def test_a_cheating_variable_is_caught_end_to_end() -> None:
    """A feature é observada 1 s DEPOIS da decisão: o moinho recusa o estudo inteiro."""
    with pytest.raises(LookAheadError, match="as_of"):
        run_hypothesis(_spec(_rows(cheat=True)))


def test_non_strict_guard_censors_instead_of_raising() -> None:
    rows = _rows(60) + _rows(20, cheat=True)
    spec = _spec(
        rows,
        observability=ObservabilityColumns(
            "feat_as_of", "feat_computed_at", "feat_tape_as_of", strict=False
        ),
    )
    report = run_hypothesis(spec)
    assert report.refused_by_guard == 20
    assert report.n_used == 60


def test_censored_rows_do_not_change_the_honest_result() -> None:
    honest = run_hypothesis(_spec(_rows(60)))
    spec = _spec(
        _rows(60) + _rows(20, cheat=True),
        observability=ObservabilityColumns(
            "feat_as_of", "feat_computed_at", "feat_tape_as_of", strict=False
        ),
    )
    assert run_hypothesis(spec).contrast.d == pytest.approx(honest.contrast.d)


def test_a_waiver_is_carried_into_the_caveats() -> None:
    report = run_hypothesis(
        _spec(_rows(60), observability=ObservabilityWaiver("export sem relógios"))
    )
    assert any("guarda não correu" in c for c in report.caveats)


# ----------------------------------------------------------------------- veredito


def test_confirms_a_planted_effect() -> None:
    report = run_hypothesis(_spec(_rows(200, effect=0.5)))
    assert report.verdict == "CONFIRMA"
    assert report.contrast.d == pytest.approx(0.5, abs=0.05)
    assert report.shape.form == "planalto"


def test_refutes_an_effect_below_the_minimum_relevant_one() -> None:
    """Efeito real de +0,001 com amostra grande: REFUTA vantagem ≥ MRE, não 'refuta tudo'."""
    report = run_hypothesis(_spec(_rows(400, effect=0.001, noise=0.002)))
    assert report.verdict == "REFUTA"
    assert any("MRE" in r for r in report.reasons)


def test_no_power_is_never_a_refutation() -> None:
    report = run_hypothesis(_spec(_rows(12)))
    assert report.verdict == "NÃO CONFIRMA"
    assert any("potência" in r or "insuficiente" in r for r in report.reasons)


def test_too_few_clusters_is_never_a_refutation() -> None:
    rows = _rows(60)
    for r in rows:
        r["mint"] = "único"
    report = run_hypothesis(_spec(rows, policy=DecisionPolicy(50.0, 0.05, min_clusters=8)))
    assert report.verdict == "NÃO CONFIRMA"
    assert any("réplicas" in r for r in report.reasons)


def test_does_not_confirm_when_the_selected_arm_still_loses_money() -> None:
    """Perder menos que o resto não é vantagem para a mesa (achado da Astra)."""
    rows = _rows(200, effect=0.5)
    for r in rows:
        r["ret"] = float(r["ret"]) - 0.9  # os dois braços passam a perder
    report = run_hypothesis(_spec(rows))
    assert report.verdict == "NÃO CONFIRMA"
    assert any("nível" in r for r in report.reasons)
    assert (
        run_hypothesis(
            _spec(rows, policy=DecisionPolicy(50.0, 0.05, require_positive_level=False))
        ).verdict
        == "CONFIRMA"
    )


def test_plateau_gate_can_be_switched_off_only_in_the_policy() -> None:
    rows = _rows(200, effect=0.5)
    strict = _spec(rows, inference=InferencePlan("mint", "day", thresholds=(50.0,), reps=1500))
    assert run_hypothesis(strict).verdict == "NÃO CONFIRMA"
    loose = _spec(
        rows,
        inference=InferencePlan("mint", "day", thresholds=(50.0,), reps=1500),
        policy=DecisionPolicy(50.0, 0.05, require_plateau=False),
    )
    assert run_hypothesis(loose).verdict == "CONFIRMA"


def test_verdict_is_always_one_of_three_labels() -> None:
    for n, eff in ((200, 0.5), (400, 0.001), (12, 0.5)):
        assert run_hypothesis(_spec(_rows(n, effect=eff))).verdict in (
            "CONFIRMA",
            "NÃO CONFIRMA",
            "REFUTA",
        )


# ------------------------------------------------------------------- contabilidade


def test_missing_variable_is_censored_not_selected() -> None:
    report = run_hypothesis(_spec(_rows(120, missing_every=4)))
    assert report.censored_variable == 30
    assert report.n_used == 90


def test_money_total_is_decimal_and_exact() -> None:
    rows = _rows(60)
    report = run_hypothesis(_spec(rows))
    assert isinstance(report.money_total, Decimal)
    assert report.money_total == sum((Decimal(str(r["pnl_sol"])) for r in rows), Decimal(0))


def test_split_reports_the_test_slice() -> None:
    report = run_hypothesis(_spec(_rows(200), split=Split("day", "2026-09-06", purge=1)))
    assert report.out_of_sample is not None
    assert report.out_of_sample.n_selected > 0
    assert report.out_of_sample.label.startswith("teste")


def test_purge_drops_the_boundary_days() -> None:
    no_purge = run_hypothesis(_spec(_rows(200), split=Split("day", "2026-09-06")))
    purged = run_hypothesis(_spec(_rows(200), split=Split("day", "2026-09-06", purge=2)))
    assert purged.purged > 0 and no_purge.purged == 0
    assert purged.out_of_sample is not None and no_purge.out_of_sample is not None
    assert purged.out_of_sample.n_selected < no_purge.out_of_sample.n_selected
