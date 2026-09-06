"""``WeightProfile``: the active ``opportunity_weights`` row, parsed.

Its own module because it is the one shape in the scorer that comes from
**outside the build** — a row of the database, published and frozen — and because
``model.py`` is at the 350-line budget (``infra/scripts/check_file_size.py``).

Every accessor raises rather than defaults. A scorer that invented a weight, a
magnitude or a rounding mode would decide with numbers nobody published, and the
score it produced could not be explained by the version it names.

The same doctrine covers the **precision**: the quanta this package rounds with
are module constants of ``model.py`` (two decimals for the score, four for the
confidence and for every component), so a profile that publishes 3/6/6 does not
get 3/6/6 — it gets 2/4/4 under a ``weights_version`` claiming otherwise, and the
replay of that row would compare numbers of different shapes. Refusing is the
only honest answer, exactly as with ``rounding`` (cross review, must-fix 2).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any

from hunter_indicators.opportunity.model import (
    COMPONENT_QUANTUM,
    CONFIDENCE_QUANTUM,
    SCORE_QUANTUM,
)


def _decimals(quantum: Decimal) -> int:
    return -int(quantum.as_tuple().exponent)


def _published_decimals(key: str, value: Any) -> int:
    """``value`` as a whole number of decimal places, or a refusal.

    ``int(2.5)`` truncates to 2, so a profile publishing 2.5 used to pass the
    check *and* be reported as agreeing with this build (Astra, cross review of
    these fixes). A count of decimal places is a whole number or it is nothing.
    """
    try:
        published = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(
            f"the profile publishes {key}={value!r}, which is not a number of decimals"
        ) from exc
    if published != published.to_integral_value():
        raise ValueError(
            f"the profile publishes {key}={value!r}: a count of decimal places is a whole number"
        )
    return int(published)


IMPLEMENTED_PRECISION: Mapping[str, int] = MappingProxyType(
    {
        "score_decimals": _decimals(SCORE_QUANTUM),
        "confidence_decimals": _decimals(CONFIDENCE_QUANTUM),
        "component_decimals": _decimals(COMPONENT_QUANTUM),
    }
)
"""Derived from the quanta themselves, so the check and the arithmetic cannot
drift apart: changing a quantum changes what a profile is allowed to publish."""


@dataclass(frozen=True, slots=True)
class WeightProfile:
    """The active ``opportunity_weights`` row, parsed. Never a default in code."""

    version: str
    components: Mapping[str, Decimal]
    early_movement_magnitude: Decimal
    early_movement_values: tuple[int, ...]
    score_decimals: int
    confidence_decimals: int
    component_decimals: int
    components_frozen: bool = False

    @classmethod
    def from_weights(cls, weights: Mapping[str, Any], *, version: str) -> WeightProfile:
        components: Mapping[str, Any] = weights["components"]
        early: Mapping[str, Any] = weights["early_movement"]
        precision: Mapping[str, Any] = weights["precision"]
        if str(precision["rounding"]) != "ROUND_HALF_EVEN":
            raise ValueError(
                f"the profile asks for {precision['rounding']!r}; this build rounds "
                "ROUND_HALF_EVEN under hunter_core.strategies.numeric.CONTEXT"
            )
        for key, implemented in IMPLEMENTED_PRECISION.items():
            published = _published_decimals(key, precision[key])
            if published != implemented:
                raise ValueError(
                    f"the profile asks for {key}={published}; this build quantises at "
                    f"{implemented} decimals and would store a number that does not have "
                    f"the precision {version} claims"
                )
        return cls(
            version=version,
            components=MappingProxyType(
                {name: Decimal(str(value)) for name, value in components.items()}
            ),
            early_movement_magnitude=Decimal(str(early["magnitude"])),
            early_movement_values=tuple(int(value) for value in early["values"]),
            score_decimals=_published_decimals("score_decimals", precision["score_decimals"]),
            confidence_decimals=_published_decimals(
                "confidence_decimals", precision["confidence_decimals"]
            ),
            component_decimals=_published_decimals(
                "component_decimals", precision["component_decimals"]
            ),
            components_frozen=bool(weights.get("components_frozen", False)),
        )

    def weight_of(self, name: str) -> Decimal:
        """The weight of ``name``; an unknown component raises rather than defaults."""
        try:
            return self.components[name]
        except KeyError as exc:  # pragma: no cover - guarded by the contract test
            raise KeyError(
                f"{name} has no weight in profile {self.version}: a component the active "
                "vector does not name cannot be scored"
            ) from exc

    @property
    def total_weight(self) -> Decimal:
        return sum(self.components.values(), Decimal(0))


__all__ = ["IMPLEMENTED_PRECISION", "WeightProfile"]
