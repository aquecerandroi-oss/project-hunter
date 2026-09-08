"""The pattern features have definitions — and are not in the live set yet."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_indicators.features.engine import DEFAULT_REGISTRY
from hunter_indicators.patterns.definitions import PATTERN_DEFINITIONS, pattern_features
from hunter_indicators.patterns.scan import scan
from packages.indicators.tests.patterns.builders import bars, resistance_price, support_price

pytestmark = pytest.mark.unit


def test_every_pattern_feature_declares_name_version_inputs_and_description() -> None:
    for definition in PATTERN_DEFINITIONS:
        row = definition.as_row()
        assert row["name"].startswith("trendline_")
        assert row["version"] == 1
        assert row["inputs"] == ["candles:15m"]
        assert row["description"]


def test_the_live_feature_set_has_not_moved() -> None:
    """T3.34 must not change ``feature_set_version`` — T3.34b does, on purpose."""
    live = set(DEFAULT_REGISTRY.keys())
    assert {definition.key for definition in PATTERN_DEFINITIONS} & live == set()


def test_the_features_read_the_distances_off_the_drawing() -> None:
    series = bars(52)
    result = scan(series, timeframe=Timeframe.M15)
    close = series[51].close

    values = pattern_features(result, close)

    scale = result.atr[51]
    assert scale is not None
    assert values["trendline_support_touches"] == Decimal(4)
    assert values["trendline_resistance_touches"] == Decimal(3)
    assert values["trendline_resistance_distance_atr"] == (resistance_price(51) - close) / scale
    assert values["trendline_support_distance_atr"] == (close - support_price(51)) / scale
    width = values["trendline_channel_width_atr"]
    assert width is not None and width == (resistance_price(51) - support_price(51)) / scale


def test_without_a_line_the_answer_is_none_and_never_zero() -> None:
    series = bars(30)
    result = scan(series, timeframe=Timeframe.M15)
    assert result.lines == ()

    values = pattern_features(result, series[29].close)

    assert set(values.values()) == {None}
