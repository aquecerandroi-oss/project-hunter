"""Jitter de parâmetros — bloco 2 (REPLICATION.md §4.2).

O conjunto derivado tem de continuar sendo um conjunto **válido** contra o schema
congelado do pai: mesmos nomes, mesmos tipos, mesma forma canônica (sem
expoente), e nada de numérico fora de ±15 %. A validação contra
``validate_parameters`` (que mora no strategy-worker) é provada em
``services/strategy-worker/tests/test_replicate_strategy_version.py``; aqui a
prova é sobre a forma e sobre o determinismo.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.momentum_v1 import MOMENTUM_V1
from hunter_indicators.replication.jitter import JITTER_PCT, jitter_parameters

DECIMAL_PATTERN = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")


def _frozen() -> tuple[dict[str, Any], dict[str, Any]]:
    """Os parâmetros e o schema congelados como o banco os devolve: JSON canônico
    (``params_format = 1``), em que **todo número é string normalizada**."""
    params: dict[str, Any] = json.loads(canonical_json(dict(MOMENTUM_V1.default_parameters)))
    schema: dict[str, Any] = json.loads(canonical_json(dict(MOMENTUM_V1.parameters_schema)))
    return params, schema


class TestJitterParameters:
    def test_every_numeric_moves_inside_the_declared_band(self) -> None:
        params, schema = _frozen()
        result = jitter_parameters(params, schema, seed=20260908)
        assert set(result.parameters) == set(params)
        for name, value in result.parameters.items():
            original = params[name]
            if not DECIMAL_PATTERN.fullmatch(str(original)):
                assert value == original, name
                continue
            before, after = Decimal(str(original)), Decimal(str(value))
            if before == 0:
                assert after == 0, name
                continue
            ratio = after / before
            # ±15 % mais a margem do arredondamento de um inteiro pequeno
            assert Decimal("0.8") <= ratio <= Decimal("1.2"), f"{name}: {before} -> {after}"

    def test_non_numeric_parameters_are_untouched(self) -> None:
        params, schema = _frozen()
        result = jitter_parameters(params, schema, seed=1)
        assert result.parameters["atr_timeframe"] == params["atr_timeframe"] == "15m"
        assert "atr_timeframe" in result.untouched

    def test_zero_stays_zero(self) -> None:
        params, schema = _frozen()
        assert params["return_min"] == "0"
        for seed in range(10):
            result = jitter_parameters(params, schema, seed=seed)
            assert result.parameters["return_min"] == "0"

    def test_the_output_keeps_the_canonical_string_form(self) -> None:
        params, schema = _frozen()
        result = jitter_parameters(params, schema, seed=7)
        for name, value in result.parameters.items():
            if name == "atr_timeframe":
                continue
            assert isinstance(value, str), name
            assert DECIMAL_PATTERN.fullmatch(value), f"{name} = {value!r}"

    def test_integers_stay_integers_and_never_reach_zero(self) -> None:
        params, schema = _frozen()
        result = jitter_parameters(params, schema, seed=42)
        for name in ("lookback_closes", "rvol_window", "atr_period", "horizon_s"):
            value = Decimal(result.parameters[name])
            assert value == value.to_integral_value(), name
            assert value >= 1, name

    def test_a_small_positive_integer_never_falls_to_zero(self) -> None:
        schema = {
            "type": "object",
            "properties": {"window": {"type": ["string", "integer"], "pattern": r"^-?[0-9]+$"}},
        }
        for seed in range(50):
            result = jitter_parameters({"window": "1"}, schema, seed=seed)
            assert result.parameters["window"] == "1"

    def test_the_same_seed_derives_the_same_sibling(self) -> None:
        params, schema = _frozen()
        first = jitter_parameters(params, schema, seed=5)
        second = jitter_parameters(params, schema, seed=5)
        other = jitter_parameters(params, schema, seed=6)
        assert first.parameters == second.parameters
        assert other.parameters != first.parameters

    def test_typed_values_come_back_typed(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "window": {"type": "integer"},
                "threshold": {"type": "number"},
            },
        }
        result = jitter_parameters({"window": 96, "threshold": Decimal("1.5")}, schema, seed=3)
        assert isinstance(result.parameters["window"], int)
        assert isinstance(result.parameters["threshold"], Decimal)

    def test_bounds_declared_by_the_schema_are_respected(self) -> None:
        schema = {
            "type": "object",
            "properties": {"threshold": {"type": "number", "minimum": 1.45, "maximum": 1.55}},
        }
        for seed in range(30):
            value = jitter_parameters({"threshold": "1.5"}, schema, seed=seed).parameters[
                "threshold"
            ]
            assert Decimal("1.45") <= Decimal(str(value)) <= Decimal("1.55")

    def test_booleans_are_never_numbers(self) -> None:
        schema = {"type": "object", "properties": {"enabled": {"type": "boolean"}}}
        result = jitter_parameters({"enabled": True}, schema, seed=1)
        assert result.parameters["enabled"] is True
        assert result.untouched == ("enabled",)

    def test_a_frozen_name_is_not_moved(self) -> None:
        params, schema = _frozen()
        result = jitter_parameters(params, schema, seed=9, frozen=("fee_bps",))
        assert result.parameters["fee_bps"] == params["fee_bps"]
        assert "fee_bps" in result.untouched

    def test_the_record_of_the_derivation_is_complete(self) -> None:
        params, schema = _frozen()
        result = jitter_parameters(params, schema, seed=2026)
        moved = {change.name for change in result.changes}
        assert moved.isdisjoint(result.untouched)
        assert moved | set(result.untouched) == set(params)
        assert result.pct == JITTER_PCT
        payload = result.to_jsonable()
        assert payload["seed"] == 2026
        assert payload["pct"] == "0.15"
