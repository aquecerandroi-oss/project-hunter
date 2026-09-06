"""The pt-BR explanation: deterministic, generated from the decomposition."""

from __future__ import annotations

import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import (
    AnomalyType,
    OpportunityStage,
    OpportunityStatus,
    TradeDirection,
)
from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.anomalies import AnomalyState
from hunter_indicators.opportunity import (
    EXPLANATION_VERSION,
    ScoreResult,
    explain,
    score_opportunity,
)
from hunter_indicators.opportunity.explanation import sentences_of
from packages.indicators.tests.scoring import anomaly
from packages.indicators.tests.unit.test_opportunity_scorer import FULL_VALUES, context


def explanation(
    values: dict[str, str] | None = None,
    *,
    stage: OpportunityStage = OpportunityStage.NONE,
    anomalies: Sequence[AnomalyState] = (),
    degraded_keys: tuple[str, ...] = (),
) -> tuple[ScoreResult, dict[str, Any]]:
    result = score_opportunity(
        context(values, stage=stage, anomalies=anomalies, degraded_keys=degraded_keys)
    )
    return result, explain(result, status=OpportunityStatus.WATCHING)


class TestDeterminism:
    def test_the_same_result_produces_the_same_bytes(self) -> None:
        first = explain(score_opportunity(context(stage=OpportunityStage.EARLY)))
        second = explain(score_opportunity(context(stage=OpportunityStage.EARLY)))
        assert canonical_json(first) == canonical_json(second)

    def test_it_is_versioned(self) -> None:
        _result, text = explanation()
        assert text["version"] == EXPLANATION_VERSION
        assert text["idioma"] == "pt-BR"

    def test_no_sentence_is_empty_and_all_carry_a_code(self) -> None:
        _result, text = explanation()
        for sentence in text["frases"]:
            assert sentence["texto"].strip()
            assert sentence["codigo"]


class TestItMatchesTheDecomposition:
    def test_every_number_in_a_sentence_is_the_stored_one(self) -> None:
        result, text = explanation()
        assert result.score is not None
        assert f"Score {str(result.score).replace('.', ',')}" in text["resumo"]
        momentum = next(item for item in text["componentes"] if item["nome"] == "momentum")
        assert momentum["contribuicao"] == result.component("momentum").contribution
        assert momentum["normalizado"] == result.component("momentum").normalized

    def test_a_component_without_data_says_the_weight_was_not_redistributed(self) -> None:
        values = {key: value for key, value in FULL_VALUES.items() if key != "spread_pct"}
        _result, text = explanation(values)
        sentence = next(
            item for item in text["frases"] if item["valores"].get("componente") == "liquidity"
        )
        assert sentence["codigo"] == "componente_indisponivel"
        assert "não foi redistribuído" in sentence["texto"]

    def test_the_components_are_listed_by_contribution(self) -> None:
        _result, text = explanation()
        scored = [
            item["valores"]["componente"]
            for item in text["frases"]
            if item["codigo"] == "componente"
        ]
        assert scored[0] in {"momentum", "volume"}
        assert scored[-1] == "liquidity"


class TestWhatItSays:
    def test_the_anomalies_are_named_with_their_severity(self) -> None:
        _result, text = explanation(anomalies=[anomaly(AnomalyType.VOLUME_SPIKE, "80")])
        sentence = next(item for item in text["frases"] if item["codigo"] == "anomalias")
        assert "VOLUME_SPIKE (severidade 80,00)" in sentence["texto"]

    def test_no_anomaly_is_said_out_loud(self) -> None:
        _result, text = explanation()
        assert "Nenhuma anomalia ativa elegível." in sentences_of(text)

    def test_the_regime_sentence_carries_the_pair_and_the_side_it_judged(self) -> None:
        _result, text = explanation()
        sentence = next(item for item in text["frases"] if item["codigo"] == "regime")
        assert "tendência bull" in sentence["texto"]
        assert "volatilidade normal" in sentence["texto"]
        assert sentence["valores"]["direcao_avaliada"] == "long"

    def test_the_stage_sentence_says_what_it_added(self) -> None:
        _result, text = explanation(stage=OpportunityStage.EARLY)
        sentence = next(item for item in text["frases"] if item["codigo"] == "estagio")
        assert "somou 10,0000 pontos" in sentence["texto"]
        _result, penalised = explanation(stage=OpportunityStage.EXTENDED)
        sentence = next(item for item in penalised["frases"] if item["codigo"] == "estagio")
        assert "subtraiu 10,0000 pontos" in sentence["texto"]

    def test_a_stage_published_on_the_other_side_is_never_claimed_as_agreement(self) -> None:
        """Astra, T2.4 design review, item 6: an EARLY confirmed long while the
        score points short is reported as a divergence, not as "EARLY short"."""
        from packages.indicators.tests.scoring import stage_decision

        ctx = context(
            {**FULL_VALUES, "momentum_15m": "-2", "momentum_acceleration": "-2"},
        )
        short = score_opportunity(
            type(ctx)(
                market_id=ctx.market_id,
                vector=ctx.vector,
                projection=ctx.projection,
                config=ctx.config,
                profile=ctx.profile,
                stage=stage_decision(OpportunityStage.EARLY, direction=TradeDirection.LONG),
                regime=ctx.regime,
                anomalies=[],
            )
        )
        text = explain(short)
        assert short.direction is TradeDirection.SHORT
        divergence = next(item for item in text["frases"] if item["codigo"] == "estagio_divergente")
        assert "aponta long" in divergence["texto"]
        assert "score é short" in divergence["texto"]

    def test_an_ineligible_sample_explains_why_there_is_no_new_score(self) -> None:
        result = score_opportunity(context(degraded_keys=tuple(FULL_VALUES)))
        text = explain(result)
        assert text["frases"][0]["codigo"] == "sem_evidencia"
        assert "carimbo de atraso" in text["resumo"]

    def test_numbers_are_written_the_way_portuguese_writes_them(self) -> None:
        _result, text = explanation()
        assert "," in text["resumo"]
        assert "." not in text["resumo"].split("confiança")[1].split(",")[0]


def test_the_explanation_survives_json_without_losing_a_sentence() -> None:
    _result, text = explanation()
    decoded = json.loads(canonical_json(text))
    assert len(decoded["frases"]) == len(text["frases"])
    # canonical_json writes a number as its normalised decimal string
    assert Decimal(decoded["componentes"][0]["peso"]) == text["componentes"][0]["peso"]
