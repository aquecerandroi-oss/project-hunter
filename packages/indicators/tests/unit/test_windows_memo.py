"""The per-context derivation memo: computed once, never shared, never stale.

The memo is the whole of T2.2b's performance claim, so what is asserted here is
the **number of derivations**, not a wall-clock time: a timing assertion on a
shared CI box is a coin toss, while "the minute array is built once per context"
is exactly the property that turned 17 rebuilds into 1 and cannot regress
silently.

Its safety argument is equally testable, and each paragraph below is one test:

- the memo lives *inside* the context (``init=False``), so it dies with it: no
  process-wide dictionary, no eviction policy, nothing to leak between ticks or
  between markets;
- everything it derives is a function of ``final_candles`` and ``as_of``, both
  immutable on a frozen context whose candle list is normalised to a tuple, so a
  cached entry can never disagree with the context that owns it;
- ``dataclasses.replace`` produces a *fresh* memo instead of inheriting the old
  one, which is what keeps a re-cut context from reading windows of another cut.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_indicators.features import compute_features
from hunter_indicators.features.context import MarketContext, build_context
from hunter_indicators.features.windows import bars_15m, tail_minutes
from packages.indicators.tests.factories import EXCHANGE, MINUTE, ORIGIN, SYMBOL, series

if TYPE_CHECKING:
    from hunter_core.domain.market import NormalizedCandle

pytestmark = pytest.mark.unit


def _closes(n: int) -> list[Decimal]:
    return [Decimal(100) + Decimal(index % 37) / Decimal(10) for index in range(n)]


def _ctx(candles: Sequence[NormalizedCandle], as_of: datetime) -> MarketContext:
    return build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=as_of, candles=candles)


def _full(minutes: int = 400) -> MarketContext:
    return _ctx(series(_closes(minutes)), ORIGIN + minutes * MINUTE)


class _Counter:
    """A spy that keeps the wrapped function's behaviour byte for byte."""

    def __init__(self, target: object, name: str, monkeypatch: pytest.MonkeyPatch) -> None:
        original = getattr(target, name)
        self.calls = 0

        def wrapper(*args: object, **kwargs: object) -> object:
            self.calls += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(target, name, wrapper)


class TestOneDerivationPerContext:
    def test_the_minute_array_is_built_once_however_many_windows_ask(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from hunter_indicators.features import windows

        spy = _Counter(windows, "_minutes_of", monkeypatch)
        ctx = _full()
        for count in (2, 5, 16, 31, 61, 241):
            assert tail_minutes(ctx, count).available
        assert spy.calls == 1, "the epoch minutes of one context are derived once"

    def test_a_whole_vector_derives_the_minutes_once_and_the_bars_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from hunter_indicators.features import windows

        minutes = _Counter(windows, "_minutes_of", monkeypatch)
        bars = _Counter(windows, "_bars_15m", monkeypatch)
        ctx = _full(1500)
        result = compute_features(ctx)
        assert result.vector.values, "the vector must actually have been computed"
        # 17 minute rebuilds and 3 aggregations per vector were the measured
        # ceiling of T2.5 (.claude/state/notes-T2.2.md section 16).
        assert bars.calls == 1
        assert minutes.calls == 1, "the 15m tail reuses a slice of the same array"

    def test_a_second_vector_over_the_same_context_derives_nothing_again(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from hunter_indicators.features import windows

        ctx = _full(1500)
        first = compute_features(ctx)
        bars = _Counter(windows, "_bars_15m", monkeypatch)
        minutes = _Counter(windows, "_minutes_of", monkeypatch)
        second = compute_features(ctx, first.state)
        assert bars.calls == 0
        assert minutes.calls == 0
        assert second.vector.values.keys() == first.vector.values.keys()


class TestTheMemoCannotLeakOrGoStale:
    def test_two_equal_contexts_do_not_share_a_memo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No process-wide cache: an equal context is still a different object.

        This is what rules out a global ``{(id(ctx), as_of): ...}`` map, whose
        keys CPython recycles as soon as a context is collected.
        """
        from hunter_indicators.features import windows

        candles = series(_closes(400))
        as_of = ORIGIN + 400 * MINUTE
        spy = _Counter(windows, "_minutes_of", monkeypatch)
        first, second = _ctx(candles, as_of), _ctx(candles, as_of)
        assert first == second
        tail_minutes(first, 30)
        tail_minutes(second, 30)
        assert spy.calls == 2

    def test_replace_starts_from_an_empty_memo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from hunter_indicators.features import windows

        ctx = _full(400)
        assert tail_minutes(ctx, 100).available
        spy = _Counter(windows, "_minutes_of", monkeypatch)
        shorter = dataclasses.replace(ctx, final_candles=ctx.final_candles[:50])
        window = tail_minutes(shorter, 100)
        assert spy.calls == 1, "replace() must not inherit the derivation of the old candles"
        assert not window.available, "50 minutes cannot answer a 100-minute window"

    def test_a_warm_memo_does_not_survive_a_cut_moved_backwards(self) -> None:
        """Re-cutting still revalidates: the memo cannot smuggle a later candle in."""
        ctx = _full(400)
        assert bars_15m(ctx).available
        with pytest.raises(ValueError, match="after the cut"):
            dataclasses.replace(ctx, as_of=ORIGIN + 100 * MINUTE)

    def test_the_candle_list_is_frozen_into_a_tuple(self) -> None:
        """A caller's list must not be able to invalidate a derivation later.

        ``frozen=True`` protects the *binding*, not the object bound: without
        this normalisation an ``append`` after the first window would leave the
        memo describing candles the context no longer has (Astra, T2.2b design
        review).
        """
        candles = series(_closes(60))
        ctx = MarketContext(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=ORIGIN + 60 * MINUTE,
            final_candles=tuple(candles),
        )
        assert isinstance(ctx.final_candles, tuple)
        mutable = list(candles)
        from_list = MarketContext(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=ORIGIN + 60 * MINUTE,
            final_candles=mutable,  # type: ignore[arg-type]
        )
        assert isinstance(from_list.final_candles, tuple)
        assert tail_minutes(from_list, 60).available
        mutable.clear()
        assert tail_minutes(from_list, 60).available, "the context kept its own tuple"


class TestTheMemoChangesNoAnswer:
    @pytest.mark.parametrize("count", [1, 2, 14, 15, 16, 60, 300, 1440])
    def test_windows_agree_with_a_memo_cold_and_warm(self, count: int) -> None:
        ctx = _full(1500)
        cold = tail_minutes(ctx, count)
        tail_minutes(ctx, 7)  # warms the memo with a different question
        warm = tail_minutes(ctx, count)
        assert [c.open_time for c in cold.candles] == [c.open_time for c in warm.candles]
        assert [c.close for c in cold.candles] == [c.close for c in warm.candles]
        assert cold.reason is warm.reason

    def test_a_hole_still_shortens_only_the_windows_it_touches(self) -> None:
        candles = series(_closes(400))
        holed = [*candles[:390], *candles[391:]]
        ctx = _ctx(holed, ORIGIN + 400 * MINUTE)
        assert tail_minutes(ctx, 9).available
        assert tail_minutes(ctx, 10).reason is not None
        # and the 15m bars, whose usable prefix ends before the hole, still exist
        assert bars_15m(ctx).available

    def test_the_bar_tail_is_not_the_candle_tail(self) -> None:
        """A hole inside the partial 15m bucket must not erase complete bars.

        The contiguous tail of ``final_candles`` and the contiguous tail of the
        candles usable for complete 15-minute bars are two different numbers,
        and one memo entry may not answer for both (Astra, T2.2b design review).
        """
        candles = series(_closes(130))
        holed = [*candles[:126], *candles[127:]]  # hole inside the partial 120-130 bucket
        ctx = _ctx(holed, ORIGIN + 130 * MINUTE)
        assert tail_minutes(ctx, 3).available, "the tail after the hole is three minutes"
        assert tail_minutes(ctx, 5).reason is not None
        bars = bars_15m(ctx)
        assert bars.available, "the complete bars end before the hole and are untouched"
        assert bars.bars[-1].close_time == ORIGIN + timedelta(minutes=120)
        assert len(bars.bars) == 8
