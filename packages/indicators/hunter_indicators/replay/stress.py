"""A passada de estresse: os cenários declarados e a aritmética que eles impõem.

T3.36. O replay responde "o que teria acontecido"; esta passada responde **"o
que teria acontecido se o mundo fosse pior"** — que é o que o `backtest-expert`
chama de *beat ideas to death*: procurar a estratégia que **quebra menos**, não
a que lucra mais no papel.

Metade pura do estresse, como :mod:`hunter_indicators.replay.policies` é a
metade pura do EXP-0004: aqui ficam as **declarações** (cada cenário é
registrado com ``key``, ``version``, ``parameters``, ``description``,
``inputs`` — muda um fator, muda a versão, nunca se edita a antiga) e a
aritmética dos níveis. A tabela e o veredito estão em
:mod:`hunter_indicators.replay.stress_table`; folhear a entrada congelada com o
walker de produção é trabalho de ``hunter_strategy_worker.replay.stress``. Nada
aqui lê banco, relógio ou vela.

Duas famílias de cenário, e a diferença entre elas é o que cada um pode dizer:

- **reprecificação** (``StressKind.REWALK``): a **entrada continua congelada**
  (mesmo sinal, mesma barra de entrada, mesma decisão) e só o desfecho é
  recalculado, folheando as mesmas velas com custos, stop ou alvo diferentes.
  É comparação pareada por sinal;
- **recorte** (``StressKind.SUBSET``): nenhum número novo é calculado — os
  desfechos da base são reagregados sobre um subconjunto (um mercado de fora,
  metade da janela). Não há reprecificação e, por isso, também não há
  pareamento: é a mesma população, lida por partes.

O atraso de entrada é o único cenário que **não** é reprecificação pura: mover
a entrada uma barra à frente muda a barra de entrada, e daí em diante o
desfecho tem de ser recaminhado sobre as velas seguintes. Está declarado em
``entry_delay_bars`` justamente para que ninguém o leia como "mesma entrada com
outro preço" — o brief da T3.36 pede que se diga onde a reprecificação é
impossível.

Escala de stop e de alvo: as duas medem a distância **a partir do preço de
entrada hipotético do próprio cenário** (``P_entry``), nunca da referência da
decisão. Duas razões, declaradas antes de qualquer número: ``P_entry`` existe
para toda entrada (``reference_price`` é opcional, e o ``volume_anomaly_v1``
põe o stop na mínima da barra, não a 1,5 ATR da referência), e a geometria
congelada ``stop < P_entry < target1`` continua válida por construção para
qualquer fator positivo — de modo que **um cenário de parâmetro nunca recusa
uma entrada que a base admitiu**. O preço vai dito no relatório: o R do cenário
é normalizado pelo risco **novo** (``P_entry - stop_novo``), que é o que
"arriscar 25 % menos" significa.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from hunter_core.strategies.envelope import AssumedCosts

__all__ = [
    "BASE",
    "REWALK_SCENARIOS",
    "STRESS_VERSION",
    "StressAxis",
    "StressFamily",
    "StressKind",
    "StressScenario",
    "scenario",
    "stressed_costs",
    "stressed_levels",
]

STRESS_VERSION: Final = 1
"""Versão do conjunto de cenários. Mudar um fator é ``version`` nova do cenário
**e** desta constante: duas passadas com o mesmo rótulo e fatores diferentes
seriam incomparáveis, que é o que a SHADOW-LAB.md §1 proíbe."""

BASE: Final = "base"
_ONE: Final = Decimal(1)
_NO_PARAMETERS: Final[Mapping[str, str]] = MappingProxyType({})


class StressFamily(StrEnum):
    """A que pergunta o cenário responde — e qual veredito ele pode disparar."""

    BASE = "base"
    COSTS = "custos"
    """Custos e atrito de execução, o atraso de entrada incluído: os dois são
    fricção que o mercado impõe, não parâmetro que o pesquisador escolhe."""
    PARAMETERS = "parametros"
    MARKET = "mercado"
    TIME = "tempo"


class StressKind(StrEnum):
    """Como a linha foi produzida — reprecificação ou recorte."""

    REWALK = "reprecificacao"
    SUBSET = "recorte"


class StressAxis(StrEnum):
    """Em que R a linha foi medida — e por que existe um segundo eixo (T3.75).

    ``r_net`` é o eixo desta passada por construção: ele inclui a perna de
    funding. Mas ``funding_schedule_unknown`` não é uma dúvida sobre a operação
    e sim sobre a **cobertura de ``funding_rates``** — a tabela não tem
    assentamento nenhum perto daquela entrada, então nem a cadência do mercado
    pode ser lida. Descartar essas linhas fazia o denominador da tabela virar
    "a janela em que houve coleta de funding" com o rótulo de "a coorte
    inteira" (T3.62b §7.2: `base` com n = 300 de 798 e a primeira metade do
    calendário com n = 0, veredito `dependente de metade` como artefato).

    Nesse caso — e **só** nesse — a linha é medida em ``r_ex_funding``, que
    existe em 100 % dos desfechos e é o eixo que a própria régua K3 da
    ``SHADOW-LAB.md`` usa. Um agregado que contenha uma única linha assim é
    declarado ``r_ex_funding``: a média de um pool misto não pode reivindicar
    o eixo mais forte de que ela é feita em parte.
    """

    R_NET = "r_net"
    R_EX_FUNDING = "r_ex_funding"


@dataclass(frozen=True, slots=True)
class StressScenario:
    """Um cenário registrado. ``version`` sobe sempre que um fator muda."""

    key: str
    version: int
    description: str
    family: StressFamily
    kind: StressKind
    inputs: tuple[str, ...]
    parameters: Mapping[str, str] = _NO_PARAMETERS
    cost_multiplier: Decimal = _ONE
    stop_scale: Decimal = _ONE
    target_scale: Decimal = _ONE
    entry_delay_bars: int = 0

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("a scenario version starts at 1")
        if self.cost_multiplier <= 0 or self.stop_scale <= 0 or self.target_scale <= 0:
            raise ValueError("stress factors are strictly positive")
        if self.entry_delay_bars < 0:
            raise ValueError("the entry delay is never negative")

    @property
    def repriced(self) -> bool:
        """Se o desfecho cabe na **mesma** barra de entrada da coorte."""
        return self.entry_delay_bars == 0


_FROZEN_ENTRY: Final = ("signal_outcomes.meta", "candles:1m")

REWALK_SCENARIOS: Final[tuple[StressScenario, ...]] = (
    StressScenario(
        key=BASE,
        version=1,
        description="O que a coorte registrou: custos, stop, alvo e barra de entrada congelados.",
        family=StressFamily.BASE,
        kind=StressKind.REWALK,
        inputs=_FROZEN_ENTRY,
    ),
    StressScenario(
        key="custos_x2",
        version=1,
        description="Spread, slippage e taxa dobrados, nos dois lados.",
        family=StressFamily.COSTS,
        kind=StressKind.REWALK,
        inputs=_FROZEN_ENTRY,
        parameters={"cost_multiplier": "2"},
        cost_multiplier=Decimal(2),
    ),
    StressScenario(
        key="stop_x0.75",
        version=1,
        description="Stop a 0,75 da distância de risco original, medida de P_entry.",
        family=StressFamily.PARAMETERS,
        kind=StressKind.REWALK,
        inputs=_FROZEN_ENTRY,
        parameters={"stop_scale": "0.75"},
        stop_scale=Decimal("0.75"),
    ),
    StressScenario(
        key="stop_x1.25",
        version=1,
        description="Stop a 1,25 da distância de risco original, medida de P_entry.",
        family=StressFamily.PARAMETERS,
        kind=StressKind.REWALK,
        inputs=_FROZEN_ENTRY,
        parameters={"stop_scale": "1.25"},
        stop_scale=Decimal("1.25"),
    ),
    StressScenario(
        key="alvo_x0.75",
        version=1,
        description="Alvo a 0,75 da distância de recompensa original, medida de P_entry.",
        family=StressFamily.PARAMETERS,
        kind=StressKind.REWALK,
        inputs=_FROZEN_ENTRY,
        parameters={"target_scale": "0.75"},
        target_scale=Decimal("0.75"),
    ),
    StressScenario(
        key="alvo_x1.25",
        version=1,
        description="Alvo a 1,25 da distância de recompensa original, medida de P_entry.",
        family=StressFamily.PARAMETERS,
        kind=StressKind.REWALK,
        inputs=_FROZEN_ENTRY,
        parameters={"target_scale": "1.25"},
        target_scale=Decimal("1.25"),
    ),
    StressScenario(
        key="entrada_mais_1_barra",
        version=1,
        description="Entrada uma barra de 1 min à frente; horizonte contado da entrada nova.",
        family=StressFamily.COSTS,
        kind=StressKind.REWALK,
        inputs=_FROZEN_ENTRY,
        parameters={"entry_delay_bars": "1"},
        entry_delay_bars=1,
    ),
)

_BY_KEY: Final[Mapping[str, StressScenario]] = {s.key: s for s in REWALK_SCENARIOS}


def scenario(key: str) -> StressScenario:
    """O cenário registrado ``key``, ou ``KeyError``."""
    return _BY_KEY[key]


def stressed_costs(costs: AssumedCosts, spec: StressScenario) -> AssumedCosts:
    """A hipótese de custo do cenário. ``max_entry_delay_s`` **não** é multiplicado.

    O limite de atraso é regra de admissão da decisão (SHADOW-LAB.md §3), já
    exercida quando o sinal foi gravado; multiplicá-lo aqui reabriria entradas
    que a coorte recusou, e a população deixaria de ser a mesma.
    """
    if spec.cost_multiplier == _ONE:
        return costs
    with localcontext(CONTEXT):
        return costs.model_copy(
            update={
                "spread_bps": costs.spread_bps * spec.cost_multiplier,
                "slippage_bps": costs.slippage_bps * spec.cost_multiplier,
                "fee_bps": costs.fee_bps * spec.cost_multiplier,
            }
        )


def stressed_levels(
    *, entry: Decimal, stop: Decimal, target1: Decimal, spec: StressScenario
) -> tuple[Decimal, Decimal]:
    """``(stop, target1)`` do cenário, escalados a partir de ``entry``."""
    with localcontext(CONTEXT):
        return (
            entry - (entry - stop) * spec.stop_scale,
            entry + (target1 - entry) * spec.target_scale,
        )
