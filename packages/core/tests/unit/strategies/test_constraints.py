"""``hunter_core.strategies.constraints`` — a faixa que o schema congelado não diz.

O caso de teste é o da revisão risk-engine-guardian de ``be3674a`` (A2): nove
sondas que ``derive_variant.py`` **aceitou** e congelou como versões de pesquisa
que nunca disparariam ou levantariam exceção a cada barra. Cada uma delas aparece
aqui pelo nome, com o valor exato da revisão.

Os conjuntos são os contratos congelados de verdade (``MOMENTUM_V1``,
``VOLUME_ANOMALY_V1``) na forma de fio do ``params_format = 1`` — toda string —,
porque é assim que eles voltam do JSONB e é sobre isso que a checagem roda.

Run: ``uv run pytest packages/core/tests/unit/strategies/test_constraints.py -q``
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from hunter_core.strategies.breakout_v1 import BREAKOUT_V1
from hunter_core.strategies.constraints import (
    CONSTRAINTS,
    PROBE_ATR,
    PROBE_CLOSE,
    Constraints,
    check_ranges,
    constraints_for,
)
from hunter_core.strategies.momentum_v1 import MOMENTUM_V1
from hunter_core.strategies.registry import DEFAULT_REGISTRY
from hunter_core.strategies.session_orb_v1 import SESSION_ORB_V1
from hunter_core.strategies.trendline_breakout_v1 import TRENDLINE_BREAKOUT_V1
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1

pytestmark = pytest.mark.unit


def _wire(strategy: Any) -> dict[str, Any]:
    """``default_parameters`` como o JSONB devolve: todo número virou string."""
    return {name: str(value) for name, value in strategy.default_parameters.items()}


MOMENTUM = _wire(MOMENTUM_V1)
VOLUME = _wire(VOLUME_ANOMALY_V1)
BREAKOUT = _wire(BREAKOUT_V1)
SESSION_ORB = _wire(SESSION_ORB_V1)
TRENDLINE = _wire(TRENDLINE_BREAKOUT_V1)


def _variant(parent: dict[str, Any], **overrides: str) -> dict[str, Any]:
    return {**parent, **overrides}


class TestTheFrozenContractsPassTheirOwnCheck:
    """A trava é inútil se recusa o que já está em produção."""

    def test_momentum_v1_passes_against_itself(self) -> None:
        assert check_ranges(MOMENTUM_V1, MOMENTUM, MOMENTUM) == []

    def test_volume_anomaly_v1_passes_against_itself(self) -> None:
        assert check_ranges(VOLUME_ANOMALY_V1, VOLUME, VOLUME) == []

    def test_breakout_v1_passes_against_itself(self) -> None:
        assert check_ranges(BREAKOUT_V1, BREAKOUT, BREAKOUT) == []

    def test_session_orb_v1_passes_against_itself(self) -> None:
        assert check_ranges(SESSION_ORB_V1, SESSION_ORB, SESSION_ORB) == []

    def test_trendline_breakout_v1_passes_against_itself(self) -> None:
        assert check_ranges(TRENDLINE_BREAKOUT_V1, TRENDLINE, TRENDLINE) == []

    def test_the_variant_that_actually_shipped_passes(self) -> None:
        """``momentum v4``: piso de custo em ``atr_pct_min`` (KB-0008, EXP-0006)."""
        assert check_ranges(MOMENTUM_V1, MOMENTUM, _variant(MOMENTUM, atr_pct_min="0.0089")) == []

    def test_every_strategy_this_build_carries_has_a_table(self) -> None:
        """Uma estratégia sem entrada só ganha as regras universais — legítimo,
        mas não deve acontecer por esquecimento com as duas que existem."""
        registered = {strategy.key for strategy in DEFAULT_REGISTRY.all()}

        assert registered <= set(CONSTRAINTS), sorted(registered - set(CONSTRAINTS))
        assert {MOMENTUM_V1.key, VOLUME_ANOMALY_V1.key, BREAKOUT_V1.key} <= registered


class TestTrendlineBreakoutV1Ranges:
    """T3.34b: as faixas da versão de linhas de tendência.

    Duas delas carregam peso de verdade e não são decoração:

    - ``min_touches`` abaixo de 2 **levanta** em ``find_lines`` ("a line needs at
      least two points"), então a variante não ficaria fraca, ficaria quebrada a
      cada barra;
    - ``stop_atr_max < max_risk_atr`` é o par que faz a versão existir: o stop é
      ``min(pivô de baixa, fechamento − stop_atr_max·ATR)``, logo o risco nunca é
      menor que ``stop_atr_max`` ATR. Invertido, **toda** barra sairia
      ``risk_too_wide`` e a coorte inteira só saberia dizer uma palavra.
    """

    @pytest.mark.parametrize(
        ("override", "fragment"),
        [
            ({"min_touches": "1"}, "min_touches=1 está fora de [2, 20]"),
            ({"min_touches_signal": "1"}, "min_touches_signal=1 está fora de [2, 20]"),
            ({"break_atr": "0"}, "break_atr=0 não é positivo"),
            ({"bounce_atr": "-0.5"}, "bounce_atr=-0.5 não é positivo"),
            ({"target_r": "0"}, "target_r=0 não é positivo"),
            ({"pattern_bars": "0"}, "pattern_bars=0 não é positivo"),
            ({"tolerance_atr": "0"}, "tolerance_atr=0 não é positivo"),
            ({"rvol_min": "-1.5"}, "rvol_min=-1.5 é negativo"),
            ({"max_violations_bounce": "-1"}, "max_violations_bounce=-1 é negativo"),
            ({"base_confidence": "42"}, "base_confidence=42 está fora de (0, 1]"),
            ({"retire_after_break": "2"}, "retire_after_break=2 está fora de [0, 1]"),
            (
                {"atr_pct_min": "0.06", "atr_pct_max": "0.05"},
                "atr_pct_min=0.06 não é menor que atr_pct_max=0.05",
            ),
            (
                {"stop_atr_max": "3.5"},
                "stop_atr_max=3.5 não é menor que max_risk_atr=3.0",
            ),
            (
                {"stop_atr_max": "3", "max_risk_atr": "3"},
                "stop_atr_max=3 não é menor que max_risk_atr=3",
            ),
            (
                {"min_touches": "40", "min_touches_signal": "40"},
                "min_touches=40 não é menor que max_anchors=20",
            ),
        ],
    )
    def test_a_variant_out_of_range_is_refused_by_name(
        self, override: dict[str, str], fragment: str
    ) -> None:
        problems = check_ranges(TRENDLINE_BREAKOUT_V1, TRENDLINE, _variant(TRENDLINE, **override))

        assert fragment in problems, problems

    def test_the_geometry_probe_does_not_apply_and_does_not_pretend_to(self) -> None:
        """Não há ``stop_atr``/``target_atr``: o stop desta versão é estrutural (o
        pivô de baixa), um dado, não um múltiplo. A prova a seco de geometria
        simplesmente não se aplica — e ``check_ranges`` não inventa uma."""
        problems = check_ranges(
            TRENDLINE_BREAKOUT_V1, TRENDLINE, _variant(TRENDLINE, stop_atr_max="1.9")
        )

        assert problems == []
        assert "stop_atr" not in TRENDLINE
        assert "target_atr" not in TRENDLINE

    def test_the_declared_defaults_are_the_ones_the_module_freezes(self) -> None:
        assert TRENDLINE["mode"] == "both"
        assert TRENDLINE["pattern_bars"] == "96"
        assert TRENDLINE["min_touches"] == TRENDLINE["min_touches_signal"] == "3"
        assert TRENDLINE["break_atr"] == TRENDLINE["bounce_atr"] == "0.5"
        assert TRENDLINE["tolerance_atr"] == "0.25"
        assert TRENDLINE["stop_atr_max"] == "2.0"
        assert TRENDLINE["max_risk_atr"] == "3.0"
        assert TRENDLINE["target_r"] == "2.0"
        assert TRENDLINE["atr_pct_min"] == "0.005"
        assert TRENDLINE["horizon_s"] == "28800"
        # a correção do §5 do brief: 0 recusaria todo rompimento que existe
        assert TRENDLINE["max_violations_breakout"] == "1"
        assert TRENDLINE["max_violations_bounce"] == "2"


class TestBreakoutV1Ranges:
    """T3.33a: as faixas que a versão de compressão declara sobre si mesma."""

    @pytest.mark.parametrize(
        ("override", "fragment"),
        [
            ({"squeeze_max": "0"}, "squeeze_max=0 não é positivo"),
            ({"squeeze_max": "-0.75"}, "squeeze_max=-0.75 não é positivo"),
            ({"stop_atr": "0"}, "stop_atr=0 não é positivo"),
            ({"squeeze_window_bars": "0"}, "squeeze_window_bars=0 não é positivo"),
            ({"breakout_highs": "-20"}, "breakout_highs=-20 não é positivo"),
            ({"rvol_min": "-1.5"}, "rvol_min=-1.5 é negativo"),
            ({"atr_pct_min": "-0.005"}, "atr_pct_min=-0.005 é negativo"),
            ({"base_confidence": "42"}, "base_confidence=42 está fora de (0, 1]"),
            (
                {"atr_pct_min": "0.06", "atr_pct_max": "0.05"},
                "atr_pct_min=0.06 não é menor que atr_pct_max=0.05",
            ),
            (
                {"squeeze_window_bars": "32"},
                "squeeze_window_bars=32 não é menor que squeeze_baseline_bars=32",
            ),
            (
                {"squeeze_window_bars": "40"},
                "squeeze_window_bars=40 não é menor que squeeze_baseline_bars=32",
            ),
            (
                {"target_atr": "5"},
                "target_atr=5 não é menor que target2_atr=4",
            ),
        ],
    )
    def test_a_variant_out_of_range_is_refused_by_name(
        self, override: dict[str, str], fragment: str
    ) -> None:
        problems = check_ranges(BREAKOUT_V1, BREAKOUT, _variant(BREAKOUT, **override))

        assert fragment in problems, problems

    def test_a_geometry_that_never_closes_is_caught_by_the_dry_probe(self) -> None:
        """``stop_atr``/``target_atr`` são declarados, então a barra de prova
        (fechamento 100, ATR 1) roda e recusa a variante antes de congelá-la."""
        problems = check_ranges(BREAKOUT_V1, BREAKOUT, _variant(BREAKOUT, stop_atr="100"))

        assert any("geometria não fecha" in problem for problem in problems)

    def test_the_declared_defaults_are_the_ones_the_module_freezes(self) -> None:
        assert BREAKOUT["squeeze_max"] == "0.75"
        assert BREAKOUT["squeeze_window_bars"] == "8"
        assert BREAKOUT["squeeze_baseline_bars"] == "32"
        assert BREAKOUT["stop_atr"] == "1.25"
        assert BREAKOUT["target_atr"] == "2.5"
        assert BREAKOUT["atr_pct_min"] == "0.005"


class TestSessionOrbV1Ranges:
    """T3.33c: a versão que trouxe a regra ``bounded`` — uma hora UTC fora de
    0..23 não é um limiar frouxo, é uma versão congelada que nunca dispara."""

    @pytest.mark.parametrize(
        ("override", "fragment"),
        [
            ({"session_us_open_h": "24"}, "session_us_open_h=24 está fora de [0, 23]"),
            ({"session_us_open_h": "99"}, "session_us_open_h=99 está fora de [0, 23]"),
            ({"session_europe_open_h": "-1"}, "session_europe_open_h=-1 está fora de [0, 23]"),
            ({"session_europe_open_h": "-1"}, "session_europe_open_h=-1 é negativo"),
            ({"session_window_bars": "48"}, "session_window_bars=48 está fora de [1, 24]"),
            ({"session_window_bars": "0"}, "session_window_bars=0 não é positivo"),
            ({"target_r": "0"}, "target_r=0 não é positivo"),
            ({"base_confidence": "42"}, "base_confidence=42 está fora de (0, 1]"),
            (
                {"range_risk_atr_min": "2.5"},
                "range_risk_atr_min=2.5 não é menor que range_risk_atr_max=2.5",
            ),
            (
                {"range_risk_atr_min": "3"},
                "range_risk_atr_min=3 não é menor que range_risk_atr_max=2.5",
            ),
            (
                {"session_asia_open_h": "8"},
                "session_asia_open_h=8 não é menor que session_europe_open_h=7",
            ),
            (
                {"session_europe_open_h": "13"},
                "session_europe_open_h=13 não é menor que session_us_open_h=13",
            ),
            (
                {"range_bars": "20"},
                "range_bars=20 não é menor que session_window_bars=20",
            ),
        ],
    )
    def test_a_variant_out_of_range_is_refused_by_name(
        self, override: dict[str, str], fragment: str
    ) -> None:
        problems = check_ranges(SESSION_ORB_V1, SESSION_ORB, _variant(SESSION_ORB, **override))

        assert fragment in problems, problems

    @pytest.mark.parametrize(
        ("name", "hour"), [("session_us_open_h", "23"), ("session_asia_open_h", "0")]
    )
    def test_the_two_ends_of_the_declared_day_are_accepted(self, name: str, hour: str) -> None:
        """A faixa é inclusiva: 0 e 23 são horas UTC legítimas."""
        assert (
            check_ranges(SESSION_ORB_V1, SESSION_ORB, _variant(SESSION_ORB, **{name: hour})) == []
        )

    def test_the_geometry_probe_does_not_apply_and_does_not_pretend_to(self) -> None:
        """Não há ``stop_atr``: o stop é a mínima da faixa, um dado. A prova de
        geometria de ``_typed_probe`` fica de fora, como já fica na
        ``volume_anomaly_v1`` — inventar uma seria inventar um contrato."""
        problems = check_ranges(SESSION_ORB_V1, SESSION_ORB, SESSION_ORB)

        assert problems == []
        assert "stop_atr" not in SESSION_ORB

    def test_the_declared_defaults_are_the_ones_the_module_freezes(self) -> None:
        assert SESSION_ORB["session_asia_open_h"] == "0"
        assert SESSION_ORB["session_europe_open_h"] == "7"
        assert SESSION_ORB["session_us_open_h"] == "13"
        assert SESSION_ORB["range_bars"] == "4"
        assert SESSION_ORB["session_window_bars"] == "20"
        assert SESSION_ORB["rvol_min"] == "1.3"
        assert SESSION_ORB["range_risk_atr_min"] == "1"
        assert SESSION_ORB["range_risk_atr_max"] == "2.5"
        assert SESSION_ORB["target_r"] == "2"


class TestTheBoundedRuleItself:
    """A regra nova, isolada da estratégia que a pediu."""

    def test_a_bound_only_bites_the_parameter_it_names(self) -> None:
        rules = Constraints(bounded=(("hour", Decimal(0), Decimal(23)),))

        assert rules.bounded[0][0] == "hour"

    def test_an_absent_parameter_is_not_out_of_range(self) -> None:
        """Ausência é problema do schema congelado, não da faixa."""
        assert check_ranges(SESSION_ORB_V1, SESSION_ORB, {}) == []

    def test_a_bound_is_inclusive_on_both_ends(self) -> None:
        low = _variant(SESSION_ORB, session_asia_open_h="0")
        high = _variant(SESSION_ORB, session_window_bars="24")

        assert check_ranges(SESSION_ORB_V1, SESSION_ORB, low) == []
        assert check_ranges(SESSION_ORB_V1, SESSION_ORB, high) == []


class TestTheProbesFromTheReview:
    """As nove sondas de ``review-T3.26-risk.md``, uma a uma."""

    @pytest.mark.parametrize(
        ("override", "fragment"),
        [
            ({"atr_pct_min": "-0.5"}, "atr_pct_min"),
            ({"stop_atr": "0"}, "stop_atr"),
            ({"stop_atr": "-2"}, "stop_atr"),
            ({"target_atr": "-1.5"}, "target_atr"),
            ({"rvol_min": "-999999"}, "rvol_min"),
            ({"lookback_closes": "-20"}, "lookback_closes"),
            ({"horizon_s": "-3600"}, "horizon_s"),
            ({"fee_bps": "-100"}, "fee_bps"),
            ({"base_confidence": "42"}, "base_confidence"),
        ],
    )
    def test_the_probe_is_refused_and_the_message_names_the_parameter(
        self, override: dict[str, str], fragment: str
    ) -> None:
        problems = check_ranges(MOMENTUM_V1, MOMENTUM, _variant(MOMENTUM, **override))
        assert problems, f"{override} passou"
        assert any(fragment in problem for problem in problems)

    def test_a_floor_above_its_ceiling_is_refused(self) -> None:
        """``atr_pct_min >= atr_pct_max``: a janela é vazia e nada dispara —
        a inversão declarada que a revisão nomeia."""
        problems = check_ranges(
            MOMENTUM_V1, MOMENTUM, _variant(MOMENTUM, atr_pct_min="0.06", atr_pct_max="0.05")
        )
        assert any("não é menor que" in problem for problem in problems)

    def test_equal_floor_and_ceiling_is_refused_too(self) -> None:
        problems = check_ranges(
            MOMENTUM_V1, MOMENTUM, _variant(MOMENTUM, atr_pct_min="0.05", atr_pct_max="0.05")
        )
        assert any("atr_pct_min" in problem for problem in problems)


class TestTheUniversalSignRule:
    """Vale sem tabela nenhuma: o sinal do pai é evidência."""

    def test_a_negative_where_the_parent_is_positive_is_refused(self) -> None:
        problems = check_ranges(
            VOLUME_ANOMALY_V1,
            VOLUME,
            _variant(VOLUME, volume_mult="-4"),
        )
        assert any("o pai declara" in problem for problem in problems)

    def test_it_fires_for_a_strategy_with_no_table_at_all(self) -> None:
        class Unknown:
            key = "nao_registrada_v1"
            version = "v1"
            timeframe = MOMENTUM_V1.timeframe

        parent = {"limiar": "3"}
        assert constraints_for(Unknown()) == Constraints()  # type: ignore[arg-type]
        problems = check_ranges(Unknown(), parent, {"limiar": "-3"})  # type: ignore[arg-type]
        assert problems == ["limiar=-3 é negativo e o pai declara 3 (positivo)"]

    def test_zero_is_not_a_sign_regression(self) -> None:
        """Desligar um porteiro é variante legítima; é a tabela que diz quando
        não é (``return_min`` já era zero e pode continuar zero)."""
        assert check_ranges(VOLUME_ANOMALY_V1, VOLUME, _variant(VOLUME, return_min="0")) == []


class TestTheTypedProbe:
    def test_a_cost_that_assumed_costs_refuses_is_named_as_such(self) -> None:
        problems = check_ranges(MOMENTUM_V1, MOMENTUM, _variant(MOMENTUM, max_entry_delay_s="0"))
        assert any("max_entry_delay_s" in problem for problem in problems)
        assert any("AssumedCosts" in problem for problem in problems)

    def test_a_stop_at_the_reference_never_closes_the_geometry(self) -> None:
        """``stop_atr = 0`` põe o stop **em** cima do fechamento: a estratégia
        exige ``0 < stop < close < target1`` e recusaria toda barra."""
        problems = check_ranges(MOMENTUM_V1, MOMENTUM, _variant(MOMENTUM, stop_atr="0"))
        assert any("geometria não fecha" in problem for problem in problems)

    def test_the_probe_bar_is_the_declared_one(self) -> None:
        """Números declarados, não medidos: fechamento 100 e ATR 1 (ATR% = 1 %,
        dentro da faixa congelada do ``momentum_v1``)."""
        assert (PROBE_CLOSE, PROBE_ATR) == (100, 1)
        assert PROBE_ATR / PROBE_CLOSE > float(MOMENTUM["atr_pct_min"])
        assert PROBE_ATR / PROBE_CLOSE < float(MOMENTUM["atr_pct_max"])


class TestWhatItDeliberatelyDoesNotJudge:
    def test_a_timeframe_string_is_left_to_the_schema(self) -> None:
        """Forma e presença continuam sendo trabalho do JSON Schema; esta
        camada não olha ``atr_timeframe`` e não finge olhar."""
        assert check_ranges(MOMENTUM_V1, MOMENTUM, _variant(MOMENTUM, atr_timeframe="30m")) == []

    def test_a_boolean_is_not_read_as_a_number(self) -> None:
        """``True`` é ``1`` em Python e não é um limiar: fica de fora em vez de
        virar um "positivo" silencioso."""
        assert check_ranges(MOMENTUM_V1, {"x": True}, {"x": False}) == []
