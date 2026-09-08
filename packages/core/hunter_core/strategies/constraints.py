"""Faixa declarada de cada parâmetro — a trava que ``schema.py`` adiou para a M4.

``schema.py`` diz, e continua dizendo, que os fragmentos JSON Schema restringem
**forma e presença, nunca faixa**: ``minimum``/``maximum`` não valem para a forma
string do ``params_format = 1``, e um limite que só morde numa das duas
representações seria pior que nenhum. Enquanto só ``default_parameters`` escrito
no código rodava, isso bastava. ``infra/scripts/derive_variant.py`` (T3.26) mudou
o fato: agora um operador digita um valor no ``--set`` e ele vira uma versão
congelada. A revisão risk-engine-guardian de ``be3674a`` (A2) mostrou o buraco na
prática — ``atr_pct_min=-0.5``, ``stop_atr=0``, ``target_atr=-1.5``,
``rvol_min=-999999``, ``lookback_closes=-20``, ``horizon_s=-3600``,
``fee_bps=-100``, ``base_confidence=42`` e piso acima do teto passaram todos.

Nenhum deles chega na carteira (a variante nasce ``research_only``, e a ponte
recusa isso por nome), mas cada um é uma coorte congelada que **não pode ser
corrigida**: ou levanta exceção a cada barra, ou nunca dispara. O dano é de
pesquisa, e é permanente. Daí esta tabela.

**Por que aqui e não em ``schema.py``.** ``hunter_strategy_worker.code_ref``
congela cada versão com o digest do módulo da estratégia *mais o fecho transitivo
dos irmãos que ela importa* — e ``momentum_v1``/``volume_anomaly_v1`` importam
``schema``. Acrescentar uma linha que fosse em ``schema.py`` moveria o
``code_ref`` das duas, e toda versão já ativada na VPS (inclusive a linha
``paper``) viraria ``code_ref_mismatch``: o Lab inteiro emudeceria atrás de um
``/ready`` verde. Este módulo não é importado por estratégia nenhuma, então fica
**fora do fecho** de propósito — e um teste em
``services/strategy-worker/tests/test_constraints_outside_freeze.py`` mantém isso
verdadeiro. É também por isso que a tabela é indexada por ``Strategy.key``: ela
descreve um contrato congelado de fora dele, sem tocá-lo.

O que **não** está aqui: nada que a estratégia leia em tempo de avaliação. Isto é
uma checagem de porta de entrada (``derive_variant.py``), não um caminho quente.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Final

from hunter_core.strategies.base import Invalidation, assumed_costs

if TYPE_CHECKING:  # pragma: no cover - typing only
    from hunter_core.strategies.base import Strategy

__all__ = [
    "CONSTRAINTS",
    "PROBE_ATR",
    "PROBE_CLOSE",
    "Constraints",
    "check_ranges",
    "constraints_for",
]


@dataclass(frozen=True, slots=True)
class Constraints:
    """As faixas que uma versão desta estratégia declara sobre si mesma.

    Quatro regras, e nenhuma inventada por conveniência: cada nome abaixo está
    numa delas porque o código da estratégia depende do sinal dele (um
    ``stop_atr`` não positivo põe o stop em cima ou acima da referência e a
    geometria recusa *toda* barra), ou porque o objeto tipado que o parâmetro
    alimenta já o exige (``AssumedCosts.fee_bps`` é ``ge=0``).
    """

    positive: frozenset[str] = frozenset()
    """Estritamente ``> 0``."""

    non_negative: frozenset[str] = frozenset()
    """``>= 0``: um piso em zero é uma variante legítima ("sem porteiro")."""

    unit_interval: frozenset[str] = frozenset()
    """``0 < x <= 1`` — probabilidade declarada, não uma nota de 0 a 100."""

    ordered: tuple[tuple[str, str], ...] = ()
    """Pares ``(piso, teto)`` que a estratégia compara: ``piso < teto``,
    estrito. Igual já seria uma janela vazia, e vazia nunca dispara."""


_COSTS: Final = frozenset({"assumed_spread_bps", "slippage_bps", "fee_bps"})
"""Os três ``bps`` que ``AssumedCosts`` já declara ``ge=0`` — repetidos aqui
para que a recusa cite o parâmetro pelo nome antes do pydantic citar o campo."""

_COST_FIELDS: Final = _COSTS | {"max_entry_delay_s"}
"""Os quatro que :func:`hunter_core.strategies.base.assumed_costs` lê. A prova
tipada só roda quando o conjunto declara os quatro: um contrato que não os tem
não está quebrado, é outro contrato."""

CONSTRAINTS: Final[Mapping[str, Constraints]] = {
    "momentum_v1": Constraints(
        positive=frozenset(
            {
                "lookback_closes",
                "rvol_window",
                "atr_period",
                "atr_bars",
                "atr_pct_max",
                "stop_atr",
                "target_atr",
                "target2_atr",
                "target3_atr",
                "horizon_s",
                "max_entry_delay_s",
            }
        ),
        non_negative=frozenset({"rvol_min", "atr_pct_min", "return_min"}) | _COSTS,
        unit_interval=frozenset({"base_confidence"}),
        ordered=(
            ("atr_pct_min", "atr_pct_max"),
            ("target_atr", "target2_atr"),
            ("target2_atr", "target3_atr"),
        ),
    ),
    "volume_anomaly_v1": Constraints(
        positive=frozenset(
            {
                "volume_window",
                "volume_mult",
                "atr_period",
                "atr_bars",
                "return_max_atr",
                "target_atr",
                "horizon_s",
                "max_entry_delay_s",
            }
        ),
        non_negative=frozenset({"return_min"}) | _COSTS,
        unit_interval=frozenset({"base_confidence"}),
    ),
}
"""Uma entrada por ``Strategy.key`` deste build. Uma estratégia ausente não é um
erro: as regras universais de :func:`check_ranges` (sinal contra o pai, objetos
tipados) valem para todas, e inventar faixa para código que ninguém leu seria
pior que declarar que não há tabela."""

PROBE_CLOSE: Final = Decimal("100")
PROBE_ATR: Final = Decimal("1")
"""A barra sintética da prova de geometria: fechamento 100 e ATR 1, ou seja
ATR% = 1 %, dentro da faixa que ``momentum_v1`` congelou (0,3 % a 5 %). Números
declarados, não medidos — servem só para instanciar ``stop``/``target`` com o
mesmo cálculo da estratégia e ver se a ordem ``0 < stop < close < target`` se
mantém. Um ``stop_atr`` grande o bastante para furar o zero **nesta** barra
(``stop_atr >= 100``) é recusado por aqui; nenhuma variante plausível chega
perto (a 5 % de ATR, ``stop_atr = 20`` já zera o preço de verdade)."""


def constraints_for(strategy: Strategy) -> Constraints:
    """A tabela desta estratégia, ou uma vazia (só as regras universais valem)."""
    return CONSTRAINTS.get(strategy.key, Constraints())


def _number(value: Any) -> Decimal | None:
    """``value`` como ``Decimal`` finito, ou ``None`` se não for número nenhum.

    Aceita a forma string do ``params_format = 1`` e a tipada, porque as duas são
    o mesmo conjunto de parâmetros (``canonical.py``). Um ``bool`` é recusado
    como não-número de propósito: ``True`` é ``1`` em Python e não é um limiar.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _sign_regression(parent: Mapping[str, Any], params: Mapping[str, Any]) -> list[str]:
    """Todo parâmetro que era positivo no pai e ficou negativo na variante.

    A regra universal, valendo mesmo sem tabela: o pai é uma coorte que já rodou,
    então o sinal dele é evidência. Zero não conta como regressão — "desligar um
    porteiro" é uma variante de pesquisa legítima, e a tabela é quem diz quando
    não é.
    """
    problems: list[str] = []
    for name, before in parent.items():
        was, now = _number(before), _number(params.get(name))
        if was is None or now is None or not (was > 0 > now):
            continue
        problems.append(f"{name}={now} é negativo e o pai declara {was} (positivo)")
    return problems


def _table_rules(rules: Constraints, params: Mapping[str, Any]) -> list[str]:
    """As faixas declaradas, na ordem em que um humano as leria."""
    problems: list[str] = []
    for name in sorted(rules.positive):
        value = _number(params.get(name))
        if value is not None and value <= 0:
            problems.append(f"{name}={value} não é positivo")
    for name in sorted(rules.non_negative):
        value = _number(params.get(name))
        if value is not None and value < 0:
            problems.append(f"{name}={value} é negativo")
    for name in sorted(rules.unit_interval):
        value = _number(params.get(name))
        if value is not None and not 0 < value <= 1:
            problems.append(f"{name}={value} está fora de (0, 1]")
    for low, high in rules.ordered:
        floor, ceiling = _number(params.get(low)), _number(params.get(high))
        if floor is not None and ceiling is not None and floor >= ceiling:
            problems.append(f"{low}={floor} não é menor que {high}={ceiling}")
    return problems


def _typed_probe(strategy: Strategy, params: Mapping[str, Any]) -> list[str]:
    """Constrói, a seco, os objetos tipados que a estratégia constrói por barra.

    ``AssumedCosts`` é o genuinamente movido por parâmetro (``ge=0`` nos três
    ``bps``, ``gt=0`` em ``max_entry_delay_s``): se ele não instancia, a versão
    congelada levanta ``ValidationError`` a *cada* avaliação. ``Invalidation`` é
    construída sobre a geometria da barra de prova — o valor de ``level`` vem do
    stop que ``stop_atr``/``target_atr`` produzem — de modo que uma variante cuja
    geometria nunca fecha é recusada aqui, e não descoberta depois como uma
    coorte que só sabe responder ``REJECTED geometry``.

    Cada prova só roda quando o conjunto **declara** os parâmetros dela. Um
    conjunto sem os quatro custos não é um conjunto quebrado, é outro contrato
    (e o schema congelado é quem diz quais existem); e ``volume_anomaly_v1``
    não tem ``stop_atr`` de propósito — o stop dele é a mínima da barra, um dado,
    não um parâmetro —, então a prova de geometria não se aplica e não finge que
    sim.
    """
    problems: list[str] = []
    if _COST_FIELDS <= set(params):
        try:
            assumed_costs(params)
        except Exception as exc:  # pydantic ValidationError, TypeError, ValueError
            problems.append(f"AssumedCosts não instancia com estes parâmetros: {exc}")
    stop_atr, target_atr = _number(params.get("stop_atr")), _number(params.get("target_atr"))
    if stop_atr is None or target_atr is None:
        return problems
    stop = PROBE_CLOSE - stop_atr * PROBE_ATR
    target = PROBE_CLOSE + target_atr * PROBE_ATR
    if not 0 < stop < PROBE_CLOSE < target:
        problems.append(
            f"a geometria não fecha na barra de prova (fechamento {PROBE_CLOSE}, ATR "
            f"{PROBE_ATR}): stop {stop}, alvo {target} — a versão recusaria toda barra"
        )
        return problems
    try:
        Invalidation(kind="close_below", level=stop, timeframe=strategy.timeframe.value)
    except Exception as exc:  # pragma: no cover - a geometria acima já garante
        problems.append(f"Invalidation não instancia com estes parâmetros: {exc}")
    return problems


def check_ranges(
    strategy: Strategy, parent: Mapping[str, Any], params: Mapping[str, Any]
) -> list[str]:
    """Tudo que está fora da faixa em ``params``, como frases; ``[]`` se passa.

    Devolve uma lista em vez de levantar porque quem chama é um script de
    operação que já tem a sua própria recusa auditada (``Refused``) e escreve o
    motivo em ``system_events``: transformar isto em exceção obrigaria o script a
    traduzir de volta. Três camadas, todas sobre o conjunto **já canônico e já
    validado contra o schema congelado** — forma e presença não são problema
    daqui:

    1. regressão de sinal contra o pai (universal, sem tabela);
    2. as faixas declaradas em :data:`CONSTRAINTS` para esta estratégia;
    3. a construção a seco dos objetos tipados que ela monta por barra.
    """
    problems = _sign_regression(parent, params)
    problems.extend(_table_rules(constraints_for(strategy), params))
    problems.extend(_typed_probe(strategy, params))
    return problems
