"""Numeric parity: the ported geometry must equal the research package, exactly.

``hunter_core.strategies.tl_*`` is a **port** of ``hunter_indicators.patterns``
(T3.34, upstream commit ``db798b8``). The port exists because
``hunter_strategy_worker.code_ref`` freezes a strategy version over its own
module plus the closure of its **flat sibling modules**: geometry reached through
``hunter_indicators`` would sit outside the digest, so the version would stay
frozen at a hash that no longer covers the code producing its decisions.

Duplication is the price and this file is the receipt. Every value the strategy
reads — the ATR scale, the pivots, the lines, the channels and the events — is
computed twice, on the same bars, and compared as **exact ``Decimal`` equality**.
If a test here fails, the copy is the wrong one; the published figures of KB-0077
were drawn with the upstream and are not up for silent revision.

Two series, per the T3.34b brief. The exported CSV slices of
``.claude/state/design/trendlines/`` were not kept in the tree (only the PNGs
were), so the second series is the pseudo-random walk of the same T3.34 builders
over four seeds — declared substitute, not a real ETHUSDT slice: it is what the
brief names as the fallback, and it produces far more geometry (many pivots, both
line kinds, breakouts and retests) than the clean synthetic wave.

This is also the only test in ``packages/core`` that imports ``hunter_indicators``.
It is a *test-time* dependency, deliberate and one-directional: production code in
``hunter_core`` importing it would be the very cycle the port exists to avoid.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, localcontext
from typing import Any

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.tl_events import detect_events
from hunter_core.strategies.tl_lines import find_lines
from hunter_core.strategies.tl_pivots import atr_series, find_pivots
from hunter_core.strategies.tl_scan import TlParams, find_channels, tl_scan
from hunter_indicators.patterns.channels import find_channels as up_find_channels
from hunter_indicators.patterns.events import detect_events as up_detect_events
from hunter_indicators.patterns.pivots import find_pivots as up_find_pivots
from hunter_indicators.patterns.scale import atr_series as up_atr_series
from hunter_indicators.patterns.scan import PatternParams
from hunter_indicators.patterns.scan import scan as up_scan
from hunter_indicators.patterns.trendlines import find_lines as up_find_lines

from .tl_builders import bars as wave_bars
from .tl_builders import walk

pytestmark = pytest.mark.unit

ATR_PERIOD = 14
TF = Timeframe.M15

PARAMS = TlParams(retire_after_break=False)
"""``retire_after_break`` is the **one** rule the port adds (T3.34b), so parity is
asserted with it off. Its own behaviour is tested in ``test_tl_scan_retire``."""

UPSTREAM_PARAMS = PatternParams()


def walk_bars(seed: int, count: int = 240) -> tuple[Bar, ...]:
    # a deterministic fixture, not cryptography: the seed is part of the test
    rng = random.Random(seed)
    return walk([rng.randint(-12, 12) for _ in range(count)])


SERIES: dict[str, tuple[Bar, ...]] = {
    "wave-120": wave_bars(120),
    "wave-260": wave_bars(260),
    **{f"walk-{seed}": walk_bars(seed) for seed in (1, 7, 42, 2026)},
}


def _pivot_wire(pivot: Any) -> tuple[Any, ...]:
    return (pivot.index, str(pivot.kind), pivot.price, pivot.confirmed_at, pivot.prominence_atr)


def _line_wire(line: Any) -> tuple[Any, ...]:
    return (
        line.line_id,
        str(line.kind),
        line.origin,
        line.through,
        line.anchors,
        line.slope_per_bar,
        line.touches,
        line.first_idx,
        line.last_idx,
        line.valid_from_idx,
        line.violations,
        line.score,
    )


def _channel_wire(channel: Any) -> tuple[Any, ...]:
    return (
        _line_wire(channel.upper),
        _line_wire(channel.lower),
        channel.at_idx,
        channel.width_atr,
    )


def _event_wire(event: Any) -> tuple[Any, ...]:
    return (
        str(event.kind),
        event.line_id,
        event.index,
        event.origin_idx,
        str(event.direction),
        event.close,
        event.line_price,
        event.distance_atr,
    )


@dataclass(frozen=True, slots=True)
class Both:
    """The same window, computed by the copy and by the research package."""

    bars: tuple[Bar, ...]
    atr: tuple[Decimal | None, ...]
    up_atr: tuple[Decimal | None, ...]


def both(name: str) -> Both:
    series = SERIES[name]
    return Both(
        bars=series,
        atr=atr_series(series, period=ATR_PERIOD, timeframe=TF),
        up_atr=up_atr_series(series, period=ATR_PERIOD, timeframe=TF),
    )


@pytest.mark.parametrize("name", sorted(SERIES))
class TestParity:
    def test_the_atr_scale_is_the_same_decimal_bar_by_bar(self, name: str) -> None:
        """Not "close enough": the same object, digit for digit. The scale is the
        unit every threshold of the geometry is expressed in, so a difference of
        one ulp here moves pivots, tolerances, breakouts and the width of a
        channel all at once."""
        pair = both(name)

        assert pair.atr == pair.up_atr
        assert len(pair.atr) == len(pair.bars)
        assert pair.atr[ATR_PERIOD] is None  # the seed is not a reading
        assert pair.atr[ATR_PERIOD + 1] is not None

    def test_the_pivots_are_the_same(self, name: str) -> None:
        pair = both(name)

        mine = find_pivots(
            pair.bars, pair.atr, k=PARAMS.pivot_k, min_swing_atr=PARAMS.min_swing_atr
        )
        theirs = up_find_pivots(
            pair.bars, pair.up_atr, k=PARAMS.pivot_k, min_swing_atr=PARAMS.min_swing_atr
        )

        assert [_pivot_wire(p) for p in mine] == [_pivot_wire(p) for p in theirs]

    def test_the_lines_are_the_same_including_the_line_id(self, name: str) -> None:
        """``line_id`` is a sha256 over the canonical geometry, so equality here
        also proves the two agree on ``origin``/``through``/slope/anchors to the
        last digit — a drifted anchor would change the digest, not just a level."""
        pair = both(name)
        mine = find_lines(
            pair.bars,
            pair.atr,
            find_pivots(pair.bars, pair.atr, k=PARAMS.pivot_k, min_swing_atr=PARAMS.min_swing_atr),
        )
        theirs = up_find_lines(
            pair.bars,
            pair.up_atr,
            up_find_pivots(
                pair.bars, pair.up_atr, k=PARAMS.pivot_k, min_swing_atr=PARAMS.min_swing_atr
            ),
        )

        assert [_line_wire(line) for line in mine] == [_line_wire(line) for line in theirs]

    def test_the_channels_and_the_events_are_the_same(self, name: str) -> None:
        pair = both(name)
        pivots = find_pivots(
            pair.bars, pair.atr, k=PARAMS.pivot_k, min_swing_atr=PARAMS.min_swing_atr
        )
        lines = find_lines(pair.bars, pair.atr, pivots)
        up_pivots = up_find_pivots(
            pair.bars, pair.up_atr, k=PARAMS.pivot_k, min_swing_atr=PARAMS.min_swing_atr
        )
        up_lines = up_find_lines(pair.bars, pair.up_atr, up_pivots)

        assert [_channel_wire(c) for c in find_channels(lines, pair.atr)] == [
            _channel_wire(c) for c in up_find_channels(up_lines, pair.up_atr)
        ]
        assert [_event_wire(e) for e in detect_events(pair.bars, pair.atr, lines)] == [
            _event_wire(e) for e in up_detect_events(pair.bars, pair.up_atr, up_lines)
        ]

    def test_the_whole_scan_agrees_at_every_cut(self, name: str) -> None:
        """The property that matters to the strategy: it scans once per bar, so
        the two implementations have to agree on **every** cut, not only the last.
        Every eighth bar, which is ~30 cuts per series and keeps the O(pivots^2)
        line search from turning one parity file into a minute of CI."""
        series = SERIES[name]

        for cut in range(0, len(series), 8):
            mine = tl_scan(series, timeframe=TF, params=PARAMS, as_of=cut)
            theirs = up_scan(series, timeframe=TF, params=UPSTREAM_PARAMS, as_of=cut)
            assert mine.atr == theirs.atr, cut
            assert [_pivot_wire(p) for p in mine.pivots] == [
                _pivot_wire(p) for p in theirs.pivots
            ], cut
            assert [_line_wire(x) for x in mine.lines] == [_line_wire(x) for x in theirs.lines], cut
            assert [_channel_wire(c) for c in mine.channels] == [
                _channel_wire(c) for c in theirs.channels
            ], cut
            assert [_event_wire(e) for e in mine.events] == [
                _event_wire(e) for e in theirs.events
            ], cut


def test_the_two_parameter_records_declare_the_same_defaults() -> None:
    """A default that drifted apart would make the parity tests above compare two
    different questions and still pass. ``retire_after_break`` is the single key
    the port adds, and it is named here so adding another cannot be silent."""
    mine = TlParams().as_wire()
    theirs = UPSTREAM_PARAMS.as_wire()

    assert set(mine) - set(theirs) == {"retire_after_break"}
    assert set(theirs) - set(mine) == set()
    assert {k: v for k, v in mine.items() if k != "retire_after_break"} == theirs


def test_the_scan_with_volume_confirmation_agrees_too() -> None:
    """``rvol_min`` turns a quiet break into a non-event, and it is the gate
    ``trendline_breakout_v1`` uses. Same series, same ratios, both sides."""
    series = SERIES["walk-42"]
    ratios: Sequence[Decimal | None] = [
        None if index < 5 else Decimal(1) + Decimal(index % 7) / Decimal(4)
        for index in range(len(series))
    ]
    mine = tl_scan(
        series,
        timeframe=TF,
        params=TlParams(rvol_min=Decimal("1.5"), retire_after_break=False),
        rvol=ratios,
    )
    theirs = up_scan(
        series, timeframe=TF, params=PatternParams(rvol_min=Decimal("1.5")), rvol=ratios
    )

    assert [_event_wire(e) for e in mine.events] == [_event_wire(e) for e in theirs.events]
    assert mine.events != ()  # the comparison would be vacuous otherwise


def test_the_copy_survives_an_ambient_decimal_context_the_upstream_does_not() -> None:
    """The one declared divergence, proved rather than asserted in a docstring.

    A few divisions upstream run under the *ambient* decimal context (the pivot
    prominence, two branches of the bounce confirmation). The port wraps every
    operation in ``localcontext(CONTEXT)``, because a frozen strategy version
    whose numbers depend on what a library did to ``decimal.getcontext()`` is not
    frozen. Under the default context the two are identical — that is what every
    test above asserts; under a hostile one only the port still is.
    """
    series = SERIES["walk-7"]
    baseline = tl_scan(series, timeframe=TF, params=PARAMS)
    up_baseline = up_scan(series, timeframe=TF, params=UPSTREAM_PARAMS)

    with localcontext() as context:
        context.prec = 8
        context.rounding = ROUND_DOWN
        hostile = tl_scan(series, timeframe=TF, params=PARAMS)
        up_hostile = up_scan(series, timeframe=TF, params=UPSTREAM_PARAMS)

    assert [_pivot_wire(p) for p in hostile.pivots] == [_pivot_wire(p) for p in baseline.pivots]
    assert [_line_wire(x) for x in hostile.lines] == [_line_wire(x) for x in baseline.lines]
    assert [_event_wire(e) for e in hostile.events] == [_event_wire(e) for e in baseline.events]
    # and the upstream, on the same series, is the one that moves
    assert [_pivot_wire(p) for p in up_hostile.pivots] != [
        _pivot_wire(p) for p in up_baseline.pivots
    ]
