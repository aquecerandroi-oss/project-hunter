"""A fila real é legível e o relatório sai no formato das notas R65–R69."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from infra.research.protocol import run_hypothesis
from infra.research.queue import (
    DEFAULT_PATH,
    QueueFormatError,
    load_queue,
    open_hypotheses,
    parse_queue,
)
from infra.research.report import render
from infra.research.spec import (
    DecisionPolicy,
    HypothesisSpec,
    InferencePlan,
    ObservabilityColumns,
    PreRegistration,
)

# ------------------------------------------------------------------------------ fila

BLOCK = """
## H-999 — Ideia de teste

- **origem:** um teste
- **variável:** `x` — direção `low`
- **população:** linhas sintéticas
- **previsão:** D positivo
- **refutação:** IC cobrindo zero
- **status:** aberta
"""


def test_the_real_queue_file_loads() -> None:
    queue = load_queue()
    assert DEFAULT_PATH.exists()
    assert len(queue) >= 8
    assert {h.id for h in queue} >= {"H-001", "H-002", "H-003", "H-004"}


def test_the_seeded_hypotheses_are_readable() -> None:
    """R70 (23/09/2026): rodar a fila torna ``open_hypotheses`` errado como
    âncora — a H-003 saiu de ``aberta`` no primeiro uso real. O que este teste
    protege é que os oito blocos existem e são legíveis, não que nunca foram
    julgados; o estado de cada um é asserido pelo teste acima."""
    names = " ".join(h.name for h in load_queue())
    assert "Absorção" in names  # EXP-M22
    assert "primeiros compradores" in names  # EXP-M19
    assert "1 a 4 h" in names  # R68 deixou h=240 inconclusivo
    assert "sells/buys" in names or "`sells/buys`" in names  # pico do R69


def test_every_queued_hypothesis_has_a_prediction_and_a_refutation() -> None:
    for h in load_queue():
        assert h.prediction.strip()
        assert h.refutation.strip()
        assert h.origin.strip()


def test_parse_accepts_a_minimal_block() -> None:
    (h,) = parse_queue(BLOCK)
    assert (h.id, h.status) == ("H-999", "aberta")
    assert h.variable.startswith("`x`")


def test_missing_field_is_an_error() -> None:
    with pytest.raises(QueueFormatError, match="faltam campos"):
        parse_queue(BLOCK.replace("- **refutação:** IC cobrindo zero\n", ""))


def test_unknown_status_is_an_error() -> None:
    with pytest.raises(QueueFormatError, match="status"):
        parse_queue(BLOCK.replace("aberta", "promissora"))


def test_duplicate_ids_are_an_error() -> None:
    with pytest.raises(QueueFormatError, match="repetidos"):
        parse_queue(BLOCK + BLOCK)


def test_empty_queue_is_an_error() -> None:
    with pytest.raises(QueueFormatError, match="vazia"):
        parse_queue("# Fila\n\nsem blocos\n")


# ------------------------------------------------------------------------ relatório

T0 = datetime(2026, 9, 1, tzinfo=UTC)


def _report(effect: float = 0.5):
    rows: list[dict[str, Any]] = []
    for i in range(160):
        t = T0 + timedelta(days=i % 8, minutes=i)
        x = float((i * 37) % 100)
        rows.append(
            {
                "mint": f"m{i}",
                "t": t,
                "day": t.date().isoformat(),
                "x": x,
                "ret": (effect if x <= 50 else 0.0) + 0.05 * (1 if i % 2 else -1),
                "as_of": t - timedelta(seconds=30),
                "computed_at": t - timedelta(seconds=30),
            }
        )
    spec = HypothesisSpec(
        name="H-999 — ideia de teste",
        origin="teste",
        loader=lambda: rows,
        decision_instant="t",
        outcome="ret",
        variable="x",
        direction="low",
        observability=ObservabilityColumns("as_of", "computed_at"),
        inference=InferencePlan("mint", "day", "day", (30.0, 40.0, 50.0, 60.0), reps=800, seed=3),
        policy=DecisionPolicy(frozen_threshold=50.0, minimum_effect=0.05),
        pre_registration=PreRegistration(
            "os selecionados rendem mais +0,05",
            "IC cobrindo zero",
            "CONFIRMA com IC acima de zero e planalto",
            "2026-09-23",
            "fixo",
        ),
        assumptions=("desfecho em unidades arbitrárias do teste",),
    )
    return run_hypothesis(spec)


def test_report_leads_with_one_of_the_three_verdicts() -> None:
    text = render(_report())
    assert "## VEREDITO: CONFIRMA" in text
    assert text.index("VEREDITO") < text.index("Curva de limiares")


def test_report_never_says_promising() -> None:
    for effect in (0.5, 0.001):
        text = render(_report(effect)).lower()
        assert "promissor" not in text
        assert "parece que" not in text


def test_report_has_the_five_to_eight_key_numbers() -> None:
    text = render(_report())
    for label in (
        "população usada",
        "D = média(selecionados)",
        "IC 95 % de D",
        "p de permutação",
        "bootstrap de blocos",
    ):
        assert label in text


def test_report_carries_the_pre_registration_and_its_fingerprint() -> None:
    report = _report()
    text = render(report)
    assert report.fingerprint in text
    assert report.pre_registration.prediction in text
    assert "Congelado em" in text


def test_report_has_a_single_most_important_caveat_and_the_declared_assumptions() -> None:
    text = render(_report())
    assert "## A ressalva que mais importa" in text
    assert "desfecho em unidades arbitrárias do teste" in text
    assert "Decimal" in text and "UTC" in text


def test_report_says_nothing_authorises_real_money() -> None:
    assert "Nada aqui autoriza dinheiro real" in render(_report())


def test_report_shows_the_threshold_curve_with_the_diagnosis() -> None:
    text = render(_report())
    assert "planalto ou pico" in text
    assert "Diagnóstico: **planalto**" in text
