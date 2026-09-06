"""«Por que estamos olhando isso?» — deterministic pt-BR, no LLM anywhere.

Every sentence is a versioned template (``explanation_v1``) filled from the
**decomposition and nothing else**, so the text and the number can never disagree:
if a component is not in the decomposition it has no sentence, and the values a
sentence shows are the ones that were summed.

Determinism is the whole point (``docs/plans/M2.md``, decision 7): the same
result produces the same bytes, so the sentence a person read yesterday can be
reproduced today, after the weights and the baselines have moved on. Numbers are
formatted with a comma, as Portuguese writes them, at the same precision the
decomposition stores.

Each sentence carries its ``codigo`` and its ``valores`` next to the text: the UI
may re-render it, and a future translation is a new template version, never an
edit of this one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, localcontext
from typing import Any

from hunter_core.domain.enums import OpportunityStatus, TradeDirection
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.opportunity.model import (
    ComponentKind,
    ComponentScore,
    ScoreResult,
)

EXPLANATION_VERSION = "explanation_v1"

LABELS: Mapping[str, str] = {
    "momentum": "Momentum",
    "volume": "Volume",
    "liquidity": "Liquidez (spread)",
    "order_flow": "Fluxo de ordens",
    "derivatives": "Derivativos",
    "market_regime": "Regime de mercado",
    "anomalies": "Anomalias",
    "agent_consensus": "Consenso de agentes",
    "external_intelligence": "Inteligência externa",
}

DIRECTIONS: Mapping[str, str] = {
    TradeDirection.LONG.value: "long",
    TradeDirection.SHORT.value: "short",
    TradeDirection.NEUTRAL.value: "sem direção",
}


def _num(value: Decimal | None, decimals: int) -> str:
    """``1234.5`` -> ``1234,5000``. No thousands separator: it is a number to be
    read next to the stored one, not typography.

    Under the frozen context like everything else that rounds: formatting
    ``100.0000`` with an ambient ``prec = 6`` raised ``InvalidOperation`` and took
    the whole explanation down with it (Astra, T2.4 diff review, must-fix 2).
    """
    if value is None:
        return "—"
    with localcontext(CONTEXT):
        quantum = Decimal(1).scaleb(-decimals)
        return f"{value.quantize(quantum)}".replace(".", ",")


def _sentence(code: str, text: str, values: Mapping[str, Any]) -> dict[str, Any]:
    return {"codigo": code, "texto": text, "valores": dict(sorted(values.items()))}


def _score_sentence(result: ScoreResult) -> dict[str, Any]:
    if not result.eligible or result.score is None:
        return _sentence(
            "sem_evidencia",
            "Sem evidência utilizável neste ciclo: nenhum componente de mercado pôde ser lido "
            f"({result.reason}). O último score continua exibido com carimbo de atraso.",
            {"motivo": result.reason},
        )
    # "Silence" and "a perfect standoff" are different sentences because they are
    # different facts: with no directional vote there is no agreement to report,
    # and printing "concordância 0" claimed a contradiction nobody observed
    # (cross review, must-fix 1).
    agreement = (
        "sem evidência direcional"
        if result.agreement is None
        else f"concordância {_num(result.agreement, 4)}"
    )
    return _sentence(
        "score",
        f"Score {_num(result.score, 2)} de 100, confiança {_num(result.confidence, 4)}, "
        f"direção {DIRECTIONS[result.direction.value]}, {agreement}.",
        {
            "score": result.score,
            "confianca": result.confidence,
            "direcao": result.direction.value,
            "concordancia": result.agreement,
            "motivo_direcao": result.direction_reason,
        },
    )


def _component_sentence(component: ComponentScore) -> dict[str, Any]:
    label = LABELS.get(component.name, component.name)
    if component.available and component.normalized is not None:
        text = (
            f"{label}: {_num(component.normalized, 4)} de 100 (peso {_num(component.weight, 2)}) "
            f"contribuiu {_num(component.contribution, 4)} pontos"
        )
        if component.kind is ComponentKind.MAD:
            text += f", com {component.used} de {component.expected} entradas"
        return _sentence(
            "componente",
            text + ".",
            {
                "componente": component.name,
                "normalizado": component.normalized,
                "peso": component.weight,
                "contribuicao": component.contribution,
                "entradas_usadas": component.used,
                "entradas_esperadas": component.expected,
            },
        )
    return _sentence(
        "componente_indisponivel",
        f"{label} sem dado utilizável ({component.reason}): o peso "
        f"{_num(component.weight, 2)} não foi redistribuído, a confiança caiu.",
        {"componente": component.name, "peso": component.weight, "motivo": component.reason},
    )


def _anomaly_sentence(component: ComponentScore) -> dict[str, Any]:
    active = [entry for entry in component.inputs if entry.available]
    if not component.available:
        return _sentence(
            "anomalias_desconhecidas",
            f"Anomalias não puderam ser lidas ({component.reason}).",
            {"motivo": component.reason},
        )
    if not active:
        return _sentence("sem_anomalias", "Nenhuma anomalia ativa elegível.", {})
    listed = "; ".join(
        f"{entry.feature} (severidade {_num(entry.severity, 2)})"
        for entry in sorted(active, key=lambda item: (-(item.severity or Decimal(0)), item.feature))
    )
    return _sentence(
        "anomalias",
        f"{len(active)} anomalia(s) ativa(s): {listed}.",
        {
            "quantidade": len(active),
            "tipos": [entry.feature for entry in active],
        },
    )


def _regime_sentence(component: ComponentScore) -> dict[str, Any]:
    if not component.available:
        return _sentence(
            "regime_indisponivel",
            f"Regime indisponível ({component.reason}): componente sem contribuição.",
            {"motivo": component.reason},
        )
    detail = component.detail
    return _sentence(
        "regime",
        f"Regime {detail.get('regime')} (tendência {detail.get('trend')}, volatilidade "
        f"{detail.get('volatility')}) frente a "
        f"{DIRECTIONS[str(detail.get('direction_input'))]}: {_num(component.normalized, 4)}.",
        {
            "regime": detail.get("regime"),
            "tendencia": detail.get("trend"),
            "volatilidade": detail.get("volatility"),
            "direcao_avaliada": detail.get("direction_input"),
            "normalizado": component.normalized,
        },
    )


def _stage_sentences(result: ScoreResult) -> list[dict[str, Any]]:
    early = result.early_movement
    if early.e == 0:
        text = (
            f"Estágio {early.stage} publicado: nenhum ajuste de Early-Movement."
            if early.reason is None
            else f"Sem estágio publicado ({early.reason}): nenhum ajuste de Early-Movement."
        )
        sentences = [
            _sentence(
                "estagio", text, {"estagio": early.stage, "e": early.e, "motivo": early.reason}
            )
        ]
    else:
        verb = "somou" if early.e > 0 else "subtraiu"
        sentences = [
            _sentence(
                "estagio",
                f"Estágio {early.stage} publicado (direção {early.stage_direction}) {verb} "
                f"{_num(abs(early.contribution), 4)} pontos.",
                {
                    "estagio": early.stage,
                    "direcao_estagio": early.stage_direction,
                    "e": early.e,
                    "contribuicao": early.contribution,
                },
            )
        ]
    if (
        early.e != 0
        and result.direction is not TradeDirection.NEUTRAL
        and early.stage_direction not in {result.direction.value, TradeDirection.NEUTRAL.value}
    ):
        sentences.append(
            _sentence(
                "estagio_divergente",
                f"Atenção: o estágio publicado aponta {early.stage_direction} e a direção do "
                f"score é {result.direction.value}; o fator de estágio não muda com isso.",
                {
                    "direcao_estagio": early.stage_direction,
                    "direcao_score": result.direction.value,
                },
            )
        )
    return sentences


def explain(
    result: ScoreResult,
    *,
    status: OpportunityStatus | None = None,
) -> dict[str, Any]:
    """``opportunities.explanation`` — built from the decomposition, in pt-BR."""
    scored = sorted(
        (item for item in result.components if item.kind is ComponentKind.MAD),
        key=lambda item: (-item.contribution, item.name),
    )
    sentences: list[dict[str, Any]] = [_score_sentence(result)]
    if status is not None:
        sentences.append(_sentence("status", f"Status {status.value}.", {"status": status.value}))
    sentences.extend(_component_sentence(component) for component in scored)
    for component in result.components:
        if component.kind is ComponentKind.ANOMALIES:
            sentences.append(_anomaly_sentence(component))
        elif component.kind is ComponentKind.REGIME:
            sentences.append(_regime_sentence(component))
    sentences.extend(_stage_sentences(result))
    return {
        "version": EXPLANATION_VERSION,
        "idioma": "pt-BR",
        "gerado_de": {
            "scorer": result.versions.get("scorer"),
            "components": result.versions.get("components"),
            "weights_version": result.weights_version,
            "observation_ts": result.observation_ts,
        },
        "resumo": sentences[0]["texto"],
        "frases": sentences,
        "componentes": [
            {
                "nome": component.name,
                "rotulo": LABELS.get(component.name, component.name),
                "normalizado": component.normalized,
                "peso": component.weight,
                "contribuicao": component.contribution,
                "disponivel": component.available,
                "motivo": component.reason,
            }
            for component in sorted(result.components, key=lambda item: item.name)
        ],
        "early_movement": result.early_movement.as_wire(),
    }


def sentences_of(explanation: Mapping[str, Any]) -> Sequence[str]:
    """The texts alone — what a panel prints, in order."""
    frases: Any = explanation["frases"]
    return [str(item["texto"]) for item in frases]


__all__ = ["EXPLANATION_VERSION", "LABELS", "explain", "sentences_of"]
