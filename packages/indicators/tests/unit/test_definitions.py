"""The feature registry and ``feature_set_version`` — the identity of a vector."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from hunter_core.domain.enums import FeatureCategory
from hunter_indicators.features.context import (
    INPUT_ATR_STATE,
    INPUT_BOOK,
    INPUT_CANDLES,
    INPUT_DERIV_HISTORY,
    INPUT_FORMING,
    INPUT_FUNDING,
    INPUT_MARK,
    INPUT_OI,
    INPUT_TRADES,
    MarketContext,
)
from hunter_indicators.features.definitions import (
    FeatureDefinition,
    FeatureRegistry,
    feature_set_version,
)
from hunter_indicators.features.engine import DEFAULT_REGISTRY, default_definitions_rows
from hunter_indicators.features.state import FeatureState
from hunter_indicators.features.vector import FeatureValue

DEF_A = FeatureDefinition(
    key="return_5m",
    version=1,
    category=FeatureCategory.PRICE,
    inputs=(INPUT_CANDLES,),
    params={"minutes": 5},
    description="close over the close 5 final minutes earlier, as a fraction",
)
DEF_B = FeatureDefinition(
    key="relative_volume_1h",
    version=1,
    category=FeatureCategory.VOLUME,
    inputs=(INPUT_CANDLES,),
    params={"window_minutes": 60, "lookback_windows": 24, "statistic": "median"},
    description="volume of the last hour over the median of the 24 previous hours",
)


class TestFeatureSetVersion:
    def test_is_a_sha256_hex_digest(self) -> None:
        version = feature_set_version([DEF_A, DEF_B])
        assert len(version) == 64
        assert set(version) <= set("0123456789abcdef")

    def test_is_a_frozen_golden_vector(self) -> None:
        """Pinned: if the canonical form drifts, every historical snapshot's
        ``feature_set_version`` changes and stops matching what produced it.

        The digest is ``sha256`` of the canonical bytes, computed outside the
        code under test with
        ``printf '%s' '<json>' | sha256sum``, where ``<json>`` is exactly (one
        line, no spaces):
        ``[{"category":"price","inputs":["candles:1m"],"key":"return_5m",``
        ``"params":{"minutes":"5"},"version":"1"}]``
        """
        assert feature_set_version([DEF_A]) == (
            "ebfeebd74518efb4f00bbe00c91dd9ba0e762de819a546f534f4bebf8b8e35aa"
        )

    def test_ignores_the_order_the_definitions_are_given_in(self) -> None:
        assert feature_set_version([DEF_A, DEF_B]) == feature_set_version([DEF_B, DEF_A])

    def test_changes_when_a_version_changes(self) -> None:
        bumped = replace(DEF_A, version=2)
        assert feature_set_version([bumped, DEF_B]) != feature_set_version([DEF_A, DEF_B])

    def test_changes_when_a_parameter_changes(self) -> None:
        retuned = replace(DEF_A, params={"minutes": 15})
        assert feature_set_version([retuned]) != feature_set_version([DEF_A])

    def test_ignores_the_description(self) -> None:
        """Prose is documentation; it must not invalidate stored snapshots."""
        reworded = replace(DEF_A, description="outra prosa")
        assert feature_set_version([reworded]) == feature_set_version([DEF_A])

    def test_a_decimal_parameter_is_canonical(self) -> None:
        one = replace(DEF_A, params={"k": Decimal("1.50")})
        other = replace(DEF_A, params={"k": Decimal("1.5")})
        assert feature_set_version([one]) == feature_set_version([other])


class TestRegistry:
    def test_refuses_two_calculators_for_the_same_key(self) -> None:
        registry = FeatureRegistry()
        registry.register(_Calc(DEF_A))
        with pytest.raises(ValueError, match="return_5m"):
            registry.register(_Calc(replace(DEF_A, version=2)))

    def test_lists_definitions_sorted_by_key(self) -> None:
        registry = FeatureRegistry([_Calc(DEF_A), _Calc(DEF_B)])
        assert [d.key for d in registry.definitions()] == ["relative_volume_1h", "return_5m"]

    def test_version_covers_every_registered_definition(self) -> None:
        registry = FeatureRegistry([_Calc(DEF_A), _Calc(DEF_B)])
        assert registry.feature_set_version == feature_set_version([DEF_A, DEF_B])

    def test_get_is_exact(self) -> None:
        registry = FeatureRegistry([_Calc(DEF_A)])
        assert registry.get("return_5m").definition == DEF_A
        with pytest.raises(KeyError):
            registry.get("return_15m")


class TestDatabaseRow:
    def test_maps_to_the_feature_definitions_columns(self) -> None:
        row = DEF_B.as_row()
        assert row == {
            "name": "relative_volume_1h",
            "version": 1,
            "category": FeatureCategory.VOLUME,
            "parameters": {
                "lookback_windows": "24",
                "statistic": "median",
                "window_minutes": "60",
            },
            "description": "volume of the last hour over the median of the 24 previous hours",
            "inputs": ["candles:1m"],
        }


class _Calc:
    """A calculator that only exists to be registered."""

    def __init__(self, definition: FeatureDefinition) -> None:
        self._definition = definition

    @property
    def definition(self) -> FeatureDefinition:
        return self._definition

    def compute(
        self, ctx: MarketContext, state: FeatureState
    ) -> FeatureValue:  # pragma: no cover - registry only
        raise NotImplementedError


class TestTheRegisteredV1Set:
    """The identity of the shipped set, and the rows that seed it.

    Cross-review nice-to-have (a) and must-fix 1's half that belongs here: T2.1
    seeds ``feature_definitions`` and T2.5 upserts it, so both need one public
    call that yields exactly what this build computes — the ``inputs``
    vocabulary included.
    """

    def test_the_v1_digest_is_a_frozen_golden(self) -> None:
        """Recomputed outside the code under test: the 28 identities were
        re-serialised with a plain ``json.dumps(sort_keys=True,
        separators=(",", ":"))`` over ints rendered as strings and hashed with
        ``sha256sum``, giving the same digest. If this moves without a feature
        being added, removed or re-versioned, the canonical form drifted and
        every stored ``feature_snapshots.feature_set_version`` stopped matching
        what produced it."""
        assert len(DEFAULT_REGISTRY.keys()) == 28
        assert DEFAULT_REGISTRY.feature_set_version == (
            "a2b12fcdbd8431a1d5b731191007c1ae9b3e6542e08be176aa8a507b090cac51"
        )

    def test_default_definitions_rows_covers_the_whole_registry(self) -> None:
        rows = default_definitions_rows()
        assert len(rows) == 28
        names = [row["name"] for row in rows]
        assert len(set(names)) == 28
        assert names == sorted(names)
        assert names == list(DEFAULT_REGISTRY.keys())

    def test_every_row_has_exactly_the_table_columns(self) -> None:
        columns = {"name", "version", "category", "parameters", "description", "inputs"}
        for row in default_definitions_rows():
            assert set(row) == columns
            assert isinstance(row["category"], FeatureCategory)
            assert isinstance(row["inputs"], list)
            assert row["inputs"]
            assert isinstance(row["parameters"], dict)
            assert row["description"]

    def test_the_inputs_vocabulary_is_the_registry_one(self) -> None:
        """The seed must not invent input names: an ``inputs`` array that says
        ``candles`` where the engine says ``candles:1m`` would make the catalogue
        describe a different engine."""
        vocabulary = {
            INPUT_ATR_STATE,
            INPUT_BOOK,
            INPUT_CANDLES,
            INPUT_DERIV_HISTORY,
            INPUT_FORMING,
            INPUT_FUNDING,
            INPUT_MARK,
            INPUT_OI,
            INPUT_TRADES,
        }
        used = {name for row in default_definitions_rows() for name in row["inputs"]}
        assert used <= vocabulary

    def test_the_rows_are_a_copy_per_call(self) -> None:
        first, second = default_definitions_rows(), default_definitions_rows()
        assert first == second
        first[0]["description"] = "mutated"
        assert default_definitions_rows()[0]["description"] != "mutated"


class TestTheRegistryCachesItsIdentity:
    """T2.2b: the version is hashed once, and ``register`` is what invalidates it."""

    def test_registering_a_calculator_changes_the_version(self) -> None:
        registry = FeatureRegistry()
        empty = registry.feature_set_version
        registry.register(_Calc(DEF_A))
        first = registry.feature_set_version
        assert first != empty
        registry.register(_Calc(DEF_B))
        assert registry.feature_set_version != first
        assert registry.feature_set_version == feature_set_version([DEF_A, DEF_B])

    def test_the_version_is_computed_once_between_registrations(self) -> None:
        registry = FeatureRegistry([_Calc(DEF_A), _Calc(DEF_B)])
        seen = [registry.feature_set_version for _ in range(5)]
        assert len(set(seen)) == 1
        assert seen[0] == feature_set_version([DEF_A, DEF_B])
