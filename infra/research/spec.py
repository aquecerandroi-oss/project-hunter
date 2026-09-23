"""O contrato de uma hipótese: população, plano de inferência e política de decisão.

Separado em três peças por sugestão da Astra (revisão de desenho da T4.87): misturar
"o que eu meço", "como eu infiro" e "o que eu decido" num único saco foi o que fez cada
estudo R65–R69 reinventar a regra. `HypothesisSpec` é a dataclass congelada que o
operador escreve; as três peças são campos dela.

**Pré-registo não é opcional.** `run_hypothesis` recusa correr sem previsão escrita,
regra de refutação, regra de decisão, data de registo e política de limiar. O
`fingerprint` é o sha256 desse texto: se alguém reescrever a previsão depois de ver os
números, a impressão digital no relatório antigo deixa de bater.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta

from infra.research.stats import check_grid

Row = Mapping[str, object]
Loader = Callable[[], Sequence[Row]]


class PreRegistrationError(RuntimeError):
    """A hipótese chegou ao moinho sem previsão ou sem regra de refutação."""


@dataclass(frozen=True)
class PreRegistration:
    """Escrito **antes** de ver qualquer número. Sem isto o moinho recusa correr."""

    prediction: str
    """O que afirmo, com sinal e tamanho. Ex.: 'ret médio dos selecionados supera o
    resto em ≥ +0,05 SOL por SOL arriscado'."""

    refutation: str
    """O que me faz abandonar a hipótese. Ex.: 'IC 95 % do contraste inteiramente
    abaixo de +0,01'."""

    decision_rule: str
    """A regra congelada, em palavras, que o veredito automático implementa."""

    registered_on: str
    """Data ISO em que este texto foi congelado."""

    threshold_policy: str
    """Proveniência do limiar: 'fixo, congelado no pré-registo', 'mediana da amostra
    escolhida antes de olhar desfechos', 'percentil móvel dos 3 dias anteriores'…"""


@dataclass(frozen=True)
class ObservabilityColumns:
    """Colunas com os instantes de observabilidade de cada linha de feature (R69)."""

    as_of: str
    computed_at: str
    tape_as_of: str | None = None
    lag: timedelta = timedelta(0)
    strict: bool = True
    """`True`: uma linha que usaria o futuro é defeito do export e levanta
    `LookAheadError`. `False`: a linha é censurada e contada no relatório."""


@dataclass(frozen=True)
class ObservabilityWaiver:
    """Sem colunas de instantes. O motivo entra no relatório como ressalva.

    Uma dispensa **não certifica** causalidade; declara que a guarda não correu.
    """

    reason: str


Observability = ObservabilityColumns | ObservabilityWaiver


@dataclass(frozen=True)
class InferencePlan:
    """Como se infere: o que é trocável, quantas reamostragens, com que semente."""

    cluster: str
    """Coluna do cluster de reamostragem (mint, mercado). Linhas do mesmo cluster
    partilham destino; reamostrar linhas independentes subestima o erro (R65)."""

    stratum: str | None = None
    """Coluna do estrato da permutação (dia). Sem ela, um dia bom vira 'sinal'."""

    block: str | None = None
    """Coluna do bloco temporal (dia/hora) para o bootstrap de blocos (R68/R69).
    Reportado ao lado do bootstrap de cluster, nunca em vez dele."""

    thresholds: tuple[float, ...] = ()
    """Grelha da varredura planalto-vs-pico. Congelada no pré-registo."""

    reps: int = 10_000
    seed: int = 0


@dataclass(frozen=True)
class DecisionPolicy:
    """O que conta como CONFIRMA, REFUTA e sem potência. Congelado antes de correr."""

    frozen_threshold: float
    minimum_effect: float
    """MRE — ganho mínimo economicamente relevante (R68 E1.9c). Na unidade do desfecho."""

    require_plateau: bool = True
    """Regra da casa (KB-0149 §5, item 26). Desligável **no pré-registo** quando o
    efeito é legitimamente descontínuo (variável booleana, degrau real) — e o motivo
    tem de estar escrito em `PreRegistration.decision_rule`."""

    require_positive_level: bool = True
    """CONFIRMA exige que o braço selecionado seja lucrativo em nível, não só melhor
    que o resto: 'perder menos' não é vantagem para a mesa (achado da Astra)."""

    min_per_side: int = 20
    min_clusters: int = 8
    """Abaixo disto o IC não tem réplicas independentes que o sustentem e o veredito
    é 'sem potência', nunca REFUTA."""


@dataclass(frozen=True)
class Split:
    """Divisão temporal treino/teste com purga, na unidade da própria coluna."""

    column: str
    train_until: str
    """Linhas com `column <= train_until` são treino (comparação de strings ISO)."""

    purge: int = 0
    """Quantas unidades a seguir à fronteira são descartadas, para que nenhum rótulo
    do treino termine dentro do teste (R68 E1.6a)."""


@dataclass(frozen=True)
class HypothesisSpec:
    """Uma hipótese pronta para o moinho. Tudo offline: `loader` lê export/CSV."""

    name: str
    origin: str
    loader: Loader
    decision_instant: str
    outcome: str
    variable: str
    direction: str
    """'low' = valores baixos da variável são os selecionados; 'high' = os altos."""

    observability: Observability
    inference: InferencePlan
    policy: DecisionPolicy
    pre_registration: PreRegistration | None = None
    split: Split | None = None
    money_column: str | None = None
    """Coluna de dinheiro somada em `Decimal` para o relatório. Nunca entra na
    estatística (que roda em float) — só no total publicado."""

    assumptions: tuple[str, ...] = field(default_factory=tuple)
    """Suposições numéricas declaradas antes de correr (custos, tamanho da ficha…)."""


_REQUIRED = ("prediction", "refutation", "decision_rule", "registered_on", "threshold_policy")


def check_pre_registration(spec: HypothesisSpec) -> PreRegistration:
    """Devolve o pré-registo ou levanta. É a primeira coisa que `run_hypothesis` faz."""
    pre = spec.pre_registration
    if pre is None:
        raise PreRegistrationError(
            f"{spec.name}: sem pré-registo. Escreva previsão, refutação, regra de decisão, "
            "data e política de limiar antes de olhar para qualquer número."
        )
    blank = [f for f in _REQUIRED if not str(getattr(pre, f, "")).strip()]
    if blank:
        raise PreRegistrationError(f"{spec.name}: pré-registo incompleto — em branco: {blank}")
    if spec.direction not in ("low", "high"):
        raise ValueError(
            f"{spec.name}: direction deve ser 'low' ou 'high', veio {spec.direction!r}"
        )
    check_grid(spec.inference.thresholds)
    obs = spec.observability
    if isinstance(obs, ObservabilityColumns) and obs.lag < timedelta(0):
        raise ValueError(f"{spec.name}: atraso negativo ({obs.lag}) adiantaria a guarda")
    if isinstance(obs, ObservabilityWaiver) and not obs.reason.strip():
        raise PreRegistrationError(
            f"{spec.name}: dispensa da guarda sem motivo escrito. A dispensa não "
            "certifica causalidade — declara que a guarda não correu, e porquê."
        )
    return pre


def fingerprint(spec: HypothesisSpec) -> str:
    """sha256 (12 hex) de **tudo** o que muda a conclusão.

    Inclui o plano de inferência (cluster, estrato, bloco, grelha, semente), o split, a
    observabilidade e as suposições, não só a previsão: a Astra reproduziu impressões
    digitais idênticas depois de acrescentar um split e de trocar o cluster de `mint`
    para `day`, o que permitiria mudar a inferência depois de ver o resultado mantendo
    a mesma identidade publicada.
    """
    pre = spec.pre_registration
    parts = [
        spec.name,
        spec.decision_instant,
        spec.outcome,
        spec.variable,
        spec.direction,
        repr(spec.observability),
        repr(spec.inference),
        repr(spec.policy),
        repr(spec.split),
        repr(spec.money_column),
        repr(spec.assumptions),
        "" if pre is None else "|".join(str(getattr(pre, f)) for f in _REQUIRED),
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:12]
