"""A tabela de faixas por estratégia e a dataclass que a descreve (T3.33c, revisão).

Extraída de ``constraints.py`` quando ele bateu o teto de 350 linhas: cada
estratégia nova acrescenta uma entrada aqui, e as regras (``check_ranges``,
``constraints_for``) ficam lá. Fora do fecho do ``code_ref`` de qualquer
estratégia, como ``constraints.py`` — ``test_constraints_outside_freeze`` prova.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

__all__ = ["CONSTRAINTS", "Constraints", "_COST_FIELDS"]


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

    bounded: tuple[tuple[str, Decimal, Decimal], ...] = ()
    """Faixas ``(nome, piso, teto)`` **inclusivas** do domínio: uma hora UTC fora
    de 0..23 não é um limiar frouxo, é uma versão que nunca dispara. Separada de
    ``ordered`` porque ali os dois lados são parâmetros, aqui nenhum é."""

    ordered: tuple[tuple[str, str], ...] = ()
    """Pares ``(piso, teto)`` que a estratégia compara: ``piso < teto``,
    estrito. Igual já seria uma janela vazia, e vazia nunca dispara."""


_SESSION_HOURS: Final = ("session_asia_open_h", "session_europe_open_h", "session_us_open_h")
"""As três horas de abertura da ``session_orb_v1``, na ordem declarada: a mesma
lista responde pela faixa 0..23 e pela ordem asia < europe < us."""

_COSTS: Final = frozenset({"assumed_spread_bps", "slippage_bps", "fee_bps"})
"""Os três ``bps`` que ``AssumedCosts`` já declara ``ge=0`` — repetidos aqui
para que a recusa cite o parâmetro pelo nome antes do pydantic citar o campo."""

_COST_FIELDS: Final = _COSTS | {"max_entry_delay_s"}
"""Os quatro que :func:`hunter_core.strategies.base.assumed_costs` lê. A prova
tipada só roda quando o conjunto declara os quatro: um contrato que não os tem
não está quebrado, é outro contrato."""

CONSTRAINTS: Final[Mapping[str, Constraints]] = {
    "breakout_v1": Constraints(
        positive=frozenset(
            {
                "squeeze_window_bars",
                "squeeze_baseline_bars",
                "squeeze_max",
                "breakout_highs",
                "rvol_window",
                "atr_period",
                "atr_bars",
                "atr_pct_max",
                "stop_atr",
                "target_atr",
                "target2_atr",
                "horizon_s",
                "max_entry_delay_s",
            }
        ),
        non_negative=frozenset({"rvol_min", "atr_pct_min"}) | _COSTS,
        unit_interval=frozenset({"base_confidence"}),
        ordered=(
            ("atr_pct_min", "atr_pct_max"),
            ("squeeze_window_bars", "squeeze_baseline_bars"),
            ("target_atr", "target2_atr"),
        ),
    ),
    "mean_reversion_v1": Constraints(
        positive=frozenset(
            {
                "trend_sma_bars",
                "zscore_bars",
                "zscore_depth_min",
                "atr_period",
                "atr_bars",
                "atr_pct_max",
                "stop_atr",
                "target_atr",
                "target2_atr",
                "horizon_s",
                "max_entry_delay_s",
            }
        ),
        non_negative=frozenset({"atr_pct_min"}) | _COSTS,
        unit_interval=frozenset({"base_confidence"}),
        ordered=(("atr_pct_min", "atr_pct_max"), ("target_atr", "target2_atr")),
    ),
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
    "session_orb_v1": Constraints(
        positive=frozenset(
            "range_bars session_window_bars rvol_window atr_period atr_bars atr_pct_max "
            "range_risk_atr_min range_risk_atr_max target_r target2_r horizon_s "
            "max_entry_delay_s".split()
        ),
        non_negative=frozenset({*_SESSION_HOURS, "rvol_min", "atr_pct_min"}) | _COSTS,
        unit_interval=frozenset({"base_confidence"}),
        bounded=(
            *((hour, Decimal(0), Decimal(23)) for hour in _SESSION_HOURS),
            ("session_window_bars", Decimal(1), Decimal(24)),
        ),
        ordered=(
            ("atr_pct_min", "atr_pct_max"),
            ("range_risk_atr_min", "range_risk_atr_max"),
            ("target_r", "target2_r"),
            ("session_asia_open_h", "session_europe_open_h"),
            ("session_europe_open_h", "session_us_open_h"),
            ("range_bars", "session_window_bars"),
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
