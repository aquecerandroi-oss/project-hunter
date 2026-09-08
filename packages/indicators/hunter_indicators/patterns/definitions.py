"""The five numbers a strategy reads off the drawing — with their definitions.

PIPELINE.md §2: every feature is a :class:`FeatureDefinition` (name, version,
parameters, description, inputs), and *a formula change is a new version, never
an edit of the old one*. So the pattern features have their definitions from
day one, parameterised by the exact :class:`PatternParams` that produced them —
a distance of "0.4 ATR to the resistance" means nothing without the tolerance
and the pivot window that drew that resistance.

**They are deliberately not in** ``features.engine.DEFAULT_REGISTRY``.
``feature_set_version`` is the ordered hash of the active set and stamps every
``feature_snapshots`` row already written; adding five keys here would move it
for the whole running system on the day a *drawing* package landed. T3.34b
wires them, on purpose, in a change whose only content is that move — and
``tests/patterns/test_definitions.py`` holds the line meanwhile.
"""

from __future__ import annotations

from decimal import Decimal

from hunter_core.domain.enums import FeatureCategory
from hunter_indicators.features.definitions import FeatureDefinition
from hunter_indicators.patterns.scan import PatternScan
from hunter_indicators.patterns.trendlines import LineKind

__all__ = [
    "PATTERN_DEFINITIONS",
    "pattern_features",
]

_INPUTS = ("candles:15m",)

PATTERN_DEFINITIONS: tuple[FeatureDefinition, ...] = (
    FeatureDefinition(
        key="trendline_resistance_distance_atr",
        version=1,
        category=FeatureCategory.PRICE,
        inputs=_INPUTS,
        description=(
            "Distance from the close to the best-scoring valid resistance line, "
            "in ATRs; negative once price is above it."
        ),
    ),
    FeatureDefinition(
        key="trendline_support_distance_atr",
        version=1,
        category=FeatureCategory.PRICE,
        inputs=_INPUTS,
        description=(
            "Distance from the close to the best-scoring valid support line, in "
            "ATRs; negative once price is below it."
        ),
    ),
    FeatureDefinition(
        key="trendline_resistance_touches",
        version=1,
        category=FeatureCategory.PRICE,
        inputs=_INPUTS,
        description="Number of confirmed pivot highs on that resistance line.",
    ),
    FeatureDefinition(
        key="trendline_support_touches",
        version=1,
        category=FeatureCategory.PRICE,
        inputs=_INPUTS,
        description="Number of confirmed pivot lows on that support line.",
    ),
    FeatureDefinition(
        key="trendline_channel_width_atr",
        version=1,
        category=FeatureCategory.PRICE,
        inputs=_INPUTS,
        description=(
            "Width of the best parallel channel at the cut, in ATRs; absent when "
            "no support/resistance pair is parallel enough."
        ),
    ),
)

_KEYS = tuple(definition.key for definition in PATTERN_DEFINITIONS)


def pattern_features(result: PatternScan, close: Decimal) -> dict[str, Decimal | None]:
    """The five values at ``result.as_of`` — ``None`` where there is no line.

    ``None`` is the answer, never zero: "no resistance line" and "the close is
    exactly on the resistance line" are different states, and a detector that
    collapses them would fire on an empty chart. ``close`` is passed in because
    a :class:`PatternScan` keeps the geometry, not the bars.
    """
    values: dict[str, Decimal | None] = dict.fromkeys(_KEYS)
    scale = result.atr[result.as_of] if result.as_of < len(result.atr) else None
    if scale is None or scale <= 0:
        return values
    for kind, distance_key, touches_key in (
        (LineKind.RESISTANCE, _KEYS[0], _KEYS[2]),
        (LineKind.SUPPORT, _KEYS[1], _KEYS[3]),
    ):
        line = next((item for item in result.lines if item.kind is kind), None)
        if line is None:
            continue
        level = line.projected(result.as_of)
        gap = level - close if kind is LineKind.RESISTANCE else close - level
        values[distance_key] = gap / scale
        values[touches_key] = Decimal(line.touches)
    if result.channels:
        values[_KEYS[4]] = result.channels[0].width_atr
    return values
