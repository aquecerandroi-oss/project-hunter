"""Wilder ATR with an anchored checkpoint — hand-computed, gap-aware.

The series is built so the arithmetic can be checked by hand:

* bars 0..14 all print ``high=101, low=99, close=100`` -> every true range is
  ``max(2, |101-100|, |99-100|) = 2``;
* the 14 true ranges of bars 1..14 average to the seed ``28/14 = 2``, which is
  **not** published (a seed is not an ATR);
* bar 15 prints ``high=110, low=100, close=105`` -> ``TR = max(10, 10, 0) = 10``
  and the first published value is ``(2*13 + 10)/14 = 36/14 = 18/7``;
* ``atr_pct`` divides by that bar's close: ``(18/7)/105 = 6/245 =
  0.024489795918367...``.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_indicators.features.atr import (
    ATR_METHOD,
    ATR_ORIGIN,
    ATR_PERIOD,
    AtrCheckpoint,
    advance,
    advance_from_context,
    atr_percent,
    bootstrap,
)
from hunter_indicators.features.context import build_context
from hunter_indicators.features.vector import Reason
from packages.indicators.tests.factories import EXCHANGE, MINUTE, ORIGIN, SYMBOL, series

STEP = timedelta(minutes=15)
EIGHTEEN_SEVENTHS = Decimal(18) / Decimal(7)


def _bar(index: int, high: str, low: str, close: str, open_: str | None = None) -> Bar:
    start = ORIGIN + index * STEP
    return Bar(
        open_time=start,
        close_time=start + STEP,
        open=Decimal(open_ or close),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("1"),
    )


def _flat_bars(count: int) -> list[Bar]:
    return [_bar(i, "101", "99", "100") for i in range(count)]


def _series_16() -> list[Bar]:
    return [*_flat_bars(15), _bar(15, "110", "100", "105")]


class TestGate:
    def test_the_seed_is_never_published_as_an_atr(self) -> None:
        result = bootstrap(_flat_bars(15), period=14)
        assert result.checkpoint is not None
        assert result.checkpoint.seed == Decimal("2")
        assert result.checkpoint.value is None  # 15 bars: seed complete, no smoothing yet

    def test_the_first_value_appears_on_the_sixteenth_bar(self) -> None:
        result = bootstrap(_series_16(), period=14)
        checkpoint = result.checkpoint
        assert checkpoint is not None
        assert checkpoint.value == EIGHTEEN_SEVENTHS
        assert checkpoint.bars_seen == 16
        assert checkpoint.seed_anchor == ORIGIN + 14 * STEP
        assert checkpoint.origin_bar_open == ORIGIN

    def test_fourteen_bars_are_not_enough(self) -> None:
        result = bootstrap(_flat_bars(14), period=14)
        assert result.checkpoint is not None
        assert result.checkpoint.seed is None
        assert result.checkpoint.value is None

    def test_atr_percent_uses_the_matching_close(self) -> None:
        checkpoint = bootstrap(_series_16(), period=14).checkpoint
        assert checkpoint is not None
        pct = atr_percent(checkpoint)
        assert pct is not None
        assert pct.quantize(Decimal("0.000000000001")) == Decimal("0.024489795918")

    def test_a_non_positive_close_has_no_percentage(self) -> None:
        bars = [*_series_16(), _bar(16, "1", "0", "0")]
        checkpoint = bootstrap(bars, period=14).checkpoint
        assert checkpoint is not None
        assert atr_percent(checkpoint) is None


class TestCheckpointAdvances:
    def test_the_anchor_does_not_move_as_the_window_rolls(self) -> None:
        """The whole point of the checkpoint: a rolling window must not reseed."""
        first = bootstrap(_series_16(), period=14).checkpoint
        assert first is not None
        later = advance(first, [_bar(16, "106", "104", "105")]).checkpoint
        assert later is not None
        assert later.origin_bar_open == first.origin_bar_open
        assert later.seed == first.seed
        assert later.seed_anchor == first.seed_anchor

    def test_one_smoothing_step_is_exact(self) -> None:
        checkpoint = bootstrap(_series_16(), period=14).checkpoint
        assert checkpoint is not None
        # bar 16: high=107, low=105, close=106, previous close 105
        # TR = max(2, |107-105|, |105-105|) = 2
        # ATR = ((18/7)*13 + 2)/14 = (234/7 + 2)/14 = (248/7)/14 = 248/98 = 124/49
        #     = 2.530612244897959183673469387755...
        after = advance(checkpoint, [_bar(16, "107", "105", "106")]).checkpoint
        assert after is not None
        assert after.value is not None
        assert after.value.quantize(Decimal("1E-20")) == Decimal("2.53061224489795918367")
        # the recursion is a chain of 28-digit steps, not the closed form: the two
        # differ in the 28th significant digit, and the chain is what is frozen.
        assert after.value == Decimal("2.530612244897959183673469387")

    def test_a_duplicate_bar_does_not_advance_the_recursion(self) -> None:
        checkpoint = bootstrap(_series_16(), period=14).checkpoint
        assert checkpoint is not None
        bar = _bar(16, "107", "105", "106")
        once = advance(checkpoint, [bar]).checkpoint
        assert once is not None
        twice = advance(once, [bar])
        assert twice.skipped == 1
        assert twice.checkpoint is not None
        assert twice.checkpoint.value == once.value

    def test_an_older_bar_never_rewinds_the_state(self) -> None:
        checkpoint = bootstrap(_series_16(), period=14).checkpoint
        assert checkpoint is not None
        result = advance(checkpoint, [_bar(3, "101", "99", "100")])
        assert result.skipped == 1
        assert result.checkpoint == checkpoint

    def test_a_missing_bar_stops_the_advance_with_a_gap(self) -> None:
        checkpoint = bootstrap(_series_16(), period=14).checkpoint
        assert checkpoint is not None
        result = advance(checkpoint, [_bar(17, "107", "105", "106")])
        assert result.reason is Reason.GAP
        assert result.checkpoint is checkpoint  # unchanged: no silent jump

    def test_bars_are_folded_in_chronological_order(self) -> None:
        seeded = bootstrap(_series_16(), period=14).checkpoint
        assert seeded is not None
        bars = [_bar(17, "108", "106", "107"), _bar(16, "107", "105", "106")]
        shuffled = advance(seeded, bars).checkpoint
        ordered = advance(seeded, list(reversed(bars))).checkpoint
        assert shuffled == ordered


class TestSerialisation:
    def test_a_checkpoint_survives_a_round_trip(self) -> None:
        checkpoint = bootstrap(_series_16(), period=14).checkpoint
        assert checkpoint is not None
        restored = AtrCheckpoint.from_wire(checkpoint.as_wire())
        assert restored == checkpoint
        assert restored.value == EIGHTEEN_SEVENTHS  # no precision lost through the wire

    def test_the_wire_form_declares_method_and_origin(self) -> None:
        checkpoint = bootstrap(_series_16(), period=14).checkpoint
        assert checkpoint is not None
        wire = checkpoint.as_wire()
        assert wire["method"] == ATR_METHOD == "wilder_v1"
        assert wire["origin"] == ATR_ORIGIN == "anchored_checkpoint_v1"
        assert wire["period"] == ATR_PERIOD == 14

    def test_a_checkpoint_of_another_period_is_refused(self) -> None:
        checkpoint = bootstrap(_series_16(), period=14).checkpoint
        assert checkpoint is not None
        with pytest.raises(ValueError, match="period"):
            advance(checkpoint, [_bar(16, "107", "105", "106")], period=7)


class TestFromContext:
    def _ctx(self, minutes: int):
        closes = [Decimal("100")] * minutes
        return build_context(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=ORIGIN + minutes * MINUTE,
            candles=series(closes),
        )

    def test_bootstraps_on_the_first_call_and_then_only_advances(self) -> None:
        ctx = self._ctx(16 * 15)
        first = advance_from_context(ctx, None)
        assert first.checkpoint is not None
        assert first.checkpoint.bars_seen == 16
        wider = self._ctx(17 * 15)
        second = advance_from_context(wider, first.checkpoint)
        assert second.checkpoint is not None
        assert second.checkpoint.bars_seen == 17
        assert second.checkpoint.origin_bar_open == first.checkpoint.origin_bar_open

    def test_a_gap_re_anchors_and_says_so(self) -> None:
        ctx = self._ctx(16 * 15)
        seeded = advance_from_context(ctx, None).checkpoint
        assert seeded is not None
        # minute 245 never arrived: the bar 240-255 cannot be built, so the next
        # complete bar the context can offer starts at 255 — one bar past the
        # checkpoint's 225, i.e. a hole in the recursion, not a continuation.
        candles = series([Decimal("100")] * (19 * 15))
        holed = [*candles[:245], *candles[246:]]
        ctx2 = build_context(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=ORIGIN + 19 * 15 * MINUTE,
            candles=holed,
        )
        result = advance_from_context(ctx2, seeded)
        assert result.checkpoint is not None
        assert result.checkpoint.origin_reason == "gap_rebuild"
        assert result.checkpoint.origin_bar_open != seeded.origin_bar_open

    def test_warmup_without_a_single_complete_bar(self) -> None:
        result = advance_from_context(self._ctx(10), None)
        assert result.checkpoint is None
        assert result.reason is Reason.WARMUP

    def test_the_timeframe_is_part_of_the_checkpoint(self) -> None:
        checkpoint = advance_from_context(self._ctx(16 * 15), None).checkpoint
        assert checkpoint is not None
        assert checkpoint.timeframe is Timeframe.M15
