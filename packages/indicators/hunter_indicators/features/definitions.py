"""``FeatureDefinition``, the registry, and ``feature_set_version``.

Every calculator publishes a definition (PIPELINE.md §2) and the version of the
whole set is the ordered hash of those definitions. Two rules make the hash
mean something:

- **a formula change is a new ``version``**, never an edit of the old one — the
  old number stays reproducible next to the snapshots that were computed with
  it;
- the hash is built from :func:`hunter_core.strategies.canonical.canonical_json`
  (``params_format = 1``), so ``Decimal("1.50")`` and ``1.5`` are the same
  parameter and the digest does not depend on the ambient decimal context or on
  the order the calculators happened to register in.

The **description is deliberately excluded** from the hash: rewording prose
must not invalidate every stored ``feature_snapshots.feature_set_version``,
while the key, version, category, inputs and parameters are what actually
decide the number a feature produces.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from hunter_core.domain.enums import FeatureCategory
from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.features.context import MarketContext
from hunter_indicators.features.state import FeatureState
from hunter_indicators.features.vector import FeatureValue

EMPTY_PARAMS: Mapping[str, object] = MappingProxyType({})
"""A definition without parameters — an immutable default a frozen dataclass accepts."""

LIVE_SUFFIX = "_live"
"""A feature whose window includes the candle still forming carries this suffix.

Book and trade features do **not**: they never read a candle, and they carry
their own observation timestamp and coverage in the vector's provenance
(agreed with Astra, T2.2 design review, must-fix 3b).
"""


def _freeze(params: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(params))


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    """What ``feature_definitions`` stores, and what the set hash is built from."""

    key: str
    version: int
    category: FeatureCategory
    inputs: tuple[str, ...]
    description: str
    params: Mapping[str, object] = EMPTY_PARAMS

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("a feature version starts at 1")
        if not self.inputs:
            raise ValueError(f"{self.key} declares no inputs")
        object.__setattr__(self, "params", _freeze(self.params))

    @property
    def is_live(self) -> bool:
        return self.key.endswith(LIVE_SUFFIX)

    def identity(self) -> dict[str, Any]:
        """Everything that decides the number — what the set hash covers."""
        return {
            "key": self.key,
            "version": self.version,
            "category": self.category.value,
            "inputs": sorted(self.inputs),
            "params": dict(self.params),
        }

    def as_row(self) -> dict[str, Any]:
        """The ``feature_definitions`` row (the column is ``name``, not ``key``)."""
        parameters: Any = canonical_params(self.params)
        return {
            "name": self.key,
            "version": self.version,
            "category": self.category,
            "parameters": parameters,
            "description": self.description,
            "inputs": list(self.inputs),
        }


def canonical_params(params: Mapping[str, object]) -> dict[str, Any]:
    """``params`` in the canonical JSON shape that goes to JSONB."""
    import json

    decoded: Any = json.loads(canonical_json(dict(params)))
    return dict(decoded)


def feature_set_version(definitions: Iterable[FeatureDefinition]) -> str:
    """SHA-256 of the ordered canonical identities of ``definitions``."""
    ordered = sorted((d.identity() for d in definitions), key=lambda d: (d["key"], d["version"]))
    return hashlib.sha256(canonical_json(ordered)).hexdigest()


@runtime_checkable
class FeatureCalculator(Protocol):
    """One feature, computed from a cut context and the state carried forward.

    Two deviations from the sketch in ``docs/ARCHITECTURE.md`` §6
    (``compute(ctx) -> dict[str, float]``), both recorded in
    ``.claude/state/notes-T2.2.md``: a value that is persisted and compared
    against thresholds is a ``Decimal`` carrying its own quality and reason (so
    "no data" is never a zero), and the anchored ATR checkpoint is passed
    explicitly instead of being recomputed per window.
    """

    @property
    def definition(self) -> FeatureDefinition: ...

    def compute(self, ctx: MarketContext, state: FeatureState) -> FeatureValue: ...


class FeatureRegistry:
    """The calculators of one build — one per key, no "latest" resolution."""

    def __init__(self, calculators: Sequence[FeatureCalculator] = ()) -> None:
        self._by_key: dict[str, FeatureCalculator] = {}
        for calculator in calculators:
            self.register(calculator)

    def register(self, calculator: FeatureCalculator) -> None:
        key = calculator.definition.key
        if key in self._by_key:
            raise ValueError(f"{key} is already registered (one calculator per key)")
        self._by_key[key] = calculator

    def get(self, key: str) -> FeatureCalculator:
        try:
            return self._by_key[key]
        except KeyError:
            raise KeyError(f"no feature registered as {key}") from None

    def all(self) -> tuple[FeatureCalculator, ...]:
        return tuple(self._by_key[key] for key in sorted(self._by_key))

    def definitions(self) -> tuple[FeatureDefinition, ...]:
        return tuple(calculator.definition for calculator in self.all())

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_key))

    @property
    def feature_set_version(self) -> str:
        return feature_set_version(self.definitions())


__all__ = [
    "LIVE_SUFFIX",
    "FeatureCalculator",
    "FeatureDefinition",
    "FeatureRegistry",
    "canonical_params",
    "feature_set_version",
]
