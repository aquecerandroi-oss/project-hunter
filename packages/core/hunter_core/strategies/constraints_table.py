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
    "sweep_reclaim_v1": Constraints(
        positive=frozenset(
            "pivot_k min_swing_atr pivot_lookback_bars sweep_atr rvol_window atr_period "
            "atr_bars stop_buffer_atr risk_pct_min risk_atr_max target_r target2_r horizon_s "
            "max_entry_delay_s".split()
        ),
        non_negative=frozenset({"rvol_min"}) | _COSTS,
        unit_interval=frozenset({"base_confidence"}),
        # ``stop_buffer_atr`` é ``positive`` de propósito: folga zero põe o stop no
        # tick exato que a tese diz que é varrido. ``risk_pct_min`` tem teto de
        # 0,15 porque ele **é** o eixo ``stop_loss_pct`` desta versão e o C5 do
        # portão reprova acima disso — uma variante com 0,5 nunca operaria.
        bounded=(
            ("pivot_k", Decimal(1), Decimal(10)),
            ("risk_pct_min", Decimal("0.0001"), Decimal("0.15")),
        ),
        ordered=(("target_r", "target2_r"),),
    ),
    "trendline_breakout_v1": Constraints(
        positive=frozenset(
            "pattern_bars pivot_k min_swing_atr tolerance_atr break_atr bounce_atr retest_bars "
            "bounce_bars parallel_tol angle_bucket_atr level_bucket_atr max_anchors max_lines "
            "max_channels rvol_window atr_period atr_bars atr_pct_max stop_atr_max max_risk_atr "
            "target_r horizon_s max_entry_delay_s".split()
        ),
        non_negative=frozenset(
            {"rvol_min", "atr_pct_min", "max_violations_breakout", "max_violations_bounce"}
        )
        | _COSTS,
        unit_interval=frozenset({"base_confidence"}),
        # ``min_touches`` below 2 is not a loose threshold: ``find_lines`` raises,
        # so the version would explode on every bar instead of never firing. The
        # ceilings are structural sanity (a line cannot have more touches than the
        # anchors it is drawn from), declared and not measured. ``retire_after_break``
        # is 0/1 because ``schema.py`` — frozen inside the live closures — has no
        # boolean fragment and may not gain one.
        bounded=(
            ("min_touches", Decimal(2), Decimal(20)),
            ("min_touches_signal", Decimal(2), Decimal(20)),
            ("retire_after_break", Decimal(0), Decimal(1)),
        ),
        # ``stop_atr_max < max_risk_atr`` is the load-bearing pair: the stop sits at
        # ``min(pivot low, close - stop_atr_max*ATR)``, so risk is never under
        # ``stop_atr_max`` ATR, and a variant with the two inverted would answer
        # ``risk_too_wide`` to every bar it ever evaluated.
        ordered=(
            ("atr_pct_min", "atr_pct_max"),
            ("stop_atr_max", "max_risk_atr"),
            ("min_touches", "max_anchors"),
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
