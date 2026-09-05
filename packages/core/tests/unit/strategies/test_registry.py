"""Registry, frozen identity of the v1 parameter sets, and the JSONB round-trip.

``params_hash`` is what ties a shadow signal to the experiment that produced it
(SHADOW-LAB.md §1 and §6), so the golden hashes below are the identity of
``momentum_v1``/``volume_anomaly_v1`` v1. If one of them changes, the frozen
version changed: that is a new version and a new row, never an edit.

The mini JSON Schema checker here is a **test helper for the subset these
schemas use** (``type`` unions, ``pattern``, ``enum``, ``required``,
``additionalProperties``), not a general validator: it refuses any keyword it
does not implement, so it cannot silently pass something it did not check
(Astra, S1 design review, point 9).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.base import Strategy
from hunter_core.strategies.canonical import canonical_json, params_hash
from hunter_core.strategies.momentum_v1 import MOMENTUM_V1
from hunter_core.strategies.registry import DEFAULT_REGISTRY, StrategyRegistry
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1

from .test_momentum_v1 import context as momentum_context
from .test_volume_anomaly_v1 import context as volume_context

pytestmark = pytest.mark.unit

STRATEGIES = [MOMENTUM_V1, VOLUME_ANOMALY_V1]
_KNOWN_KEYWORDS = frozenset(
    {
        "$schema",
        "type",
        "properties",
        "required",
        "additionalProperties",
        "pattern",
        "enum",
        "description",
    }
)


def check(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    """Validate ``value`` against the supported subset, or raise ``AssertionError``."""
    unknown = set(schema) - _KNOWN_KEYWORDS
    assert not unknown, f"{path}: unsupported schema keywords {sorted(unknown)}"

    types = schema.get("type")
    if types is not None:
        allowed = [types] if isinstance(types, str) else list(types)
        matched = any(
            (name == "object" and isinstance(value, Mapping))
            or (name == "string" and isinstance(value, str))
            or (name == "integer" and isinstance(value, int) and not isinstance(value, bool))
            or (
                name == "number"
                and isinstance(value, (int, Decimal))
                and not isinstance(value, bool)
            )
            for name in allowed
        )
        assert matched, f"{path}: {value!r} is not one of {allowed}"
    if "enum" in schema:
        assert value in schema["enum"], f"{path}: {value!r} not in {schema['enum']}"
    if "pattern" in schema and isinstance(value, str):
        assert re.match(schema["pattern"], value), f"{path}: {value!r} !~ {schema['pattern']}"
    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, Any]", value)
        for name in schema.get("required", []):
            assert name in mapping, f"{path}: missing required {name}"
        properties: Mapping[str, Any] = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(mapping) - set(properties))
            assert not extra, f"{path}: unexpected {extra}"
        for name, item in mapping.items():
            if name in properties:
                check(item, properties[name], f"{path}.{name}")


# --------------------------------------------------------------------------- the helper itself


def test_the_schema_helper_rejects_what_it_should() -> None:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["a"],
        "properties": {"a": {"type": ["string", "integer"], "pattern": r"^[0-9]+$"}},
    }
    check({"a": 1}, schema)
    check({"a": "12"}, schema)
    for broken in ({}, {"a": 1, "b": 2}, {"a": "x"}, {"a": Decimal("1.5")}):
        with pytest.raises(AssertionError):
            check(broken, schema)


def test_the_schema_helper_refuses_keywords_it_does_not_implement() -> None:
    with pytest.raises(AssertionError, match="unsupported schema keywords"):
        check(1, {"type": "integer", "minimum": 0})


# --------------------------------------------------------------------------- registry


def test_get_resolves_key_and_version_exactly() -> None:
    assert DEFAULT_REGISTRY.get("momentum_v1", "v1") is MOMENTUM_V1
    assert DEFAULT_REGISTRY.get("volume_anomaly_v1", "v1") is VOLUME_ANOMALY_V1


def test_an_unknown_version_never_falls_back() -> None:
    with pytest.raises(KeyError, match="momentum_v1 v2"):
        DEFAULT_REGISTRY.get("momentum_v1", "v2")
    with pytest.raises(KeyError):
        DEFAULT_REGISTRY.get("breakout_v1", "v1")


def test_registering_the_same_version_twice_is_refused() -> None:
    registry = StrategyRegistry([MOMENTUM_V1])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(MOMENTUM_V1)


def test_all_is_ordered_and_complete() -> None:
    assert DEFAULT_REGISTRY.all() == (MOMENTUM_V1, VOLUME_ANOMALY_V1)


@pytest.mark.parametrize("strategy", STRATEGIES, ids=lambda s: s.key)
def test_every_registered_strategy_satisfies_the_protocol(strategy: Strategy) -> None:
    assert isinstance(strategy, Strategy)
    assert strategy.version == "v1"
    assert strategy.timeframe in {Timeframe.M5, Timeframe.M15}


# --------------------------------------------------------------------------- frozen parameters


@pytest.mark.parametrize("strategy", STRATEGIES, ids=lambda s: s.key)
def test_default_parameters_validate_against_the_declared_schema(strategy: Strategy) -> None:
    check(strategy.default_parameters, strategy.parameters_schema)


@pytest.mark.parametrize("strategy", STRATEGIES, ids=lambda s: s.key)
def test_the_canonical_wire_form_also_validates(strategy: Strategy) -> None:
    """What is persisted in ``strategy_versions.default_parameters`` is the
    canonical form, where every number is a normalised string — the schema has to
    describe that too, or the round-trip would fail validation."""
    wire = json.loads(canonical_json(strategy.default_parameters))

    check(wire, strategy.parameters_schema)


@pytest.mark.parametrize("strategy", STRATEGIES, ids=lambda s: s.key)
def test_the_jsonb_round_trip_keeps_the_hash_and_the_decision(strategy: Strategy) -> None:
    """typed -> JSONB -> typed must give the same ``params_hash`` *and* the same
    decision; otherwise a version reloaded from Postgres is a different experiment."""
    typed = strategy.default_parameters
    wire = json.loads(canonical_json(typed))

    assert params_hash(wire) == params_hash(typed)

    ctx = momentum_context() if strategy.key == MOMENTUM_V1.key else volume_context()
    assert strategy.evaluate(ctx, wire) == strategy.evaluate(ctx, typed)


def test_the_two_versions_do_not_share_an_identity() -> None:
    assert params_hash(MOMENTUM_V1.default_parameters) != params_hash(
        VOLUME_ANOMALY_V1.default_parameters
    )


@pytest.mark.parametrize(
    ("strategy", "expected"),
    [
        (MOMENTUM_V1, "40e1688e6b5f6385674cb47a81e542b215b320eb5643a1375f6401f5c41ac2f3"),
        (VOLUME_ANOMALY_V1, "fa5dce78173b2b9688578f7c96a5f37544eb504aa7b2227262ad296c32f63bb9"),
    ],
    ids=["momentum_v1", "volume_anomaly_v1"],
)
def test_the_params_hash_is_pinned(strategy: Strategy, expected: str) -> None:
    """Golden identity of the frozen v1 parameter sets."""
    assert params_hash(strategy.default_parameters) == expected
