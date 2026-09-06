"""Window selection: contiguity, warm-up vs gap, coverage — no silent short windows."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import OrderSide, Timeframe
from hunter_core.domain.market import NormalizedCandle
from hunter_indicators.features.context import (
    MarketContext,
    SourceEntry,
    TapeTrade,
    build_context,
)
from hunter_indicators.features.vector import Reason
from hunter_indicators.features.windows import bars_15m, tail_minutes, trades_between
from packages.indicators.tests.factories import EXCHANGE, MINUTE, ORIGIN, SYMBOL, candle, series

AS_OF = ORIGIN + timedelta(minutes=60, seconds=20)


def _ctx(candles: Sequence[NormalizedCandle], as_of: datetime = AS_OF) -> MarketContext:
    return build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=as_of, candles=candles)


def _closes(n: int) -> list[Decimal]:
    return [Decimal(100 + i) for i in range(n)]


class TestTailMinutes:
    def test_returns_exactly_the_requested_minutes(self) -> None:
        window = tail_minutes(_ctx(series(_closes(60))), 5)
        assert window.available
        assert [c.close for c in window.candles] == [Decimal(155 + i) for i in range(5)]

    def test_warmup_when_history_does_not_reach_back(self) -> None:
        window = tail_minutes(_ctx(series(_closes(4))), 5)
        assert window.reason is Reason.WARMUP
        assert window.candles == ()

    def test_gap_when_a_minute_is_missing_inside_the_window(self) -> None:
        candles = series(_closes(60))
        holed = [*candles[:57], *candles[58:]]  # minute 57 never arrived
        assert tail_minutes(_ctx(holed), 5).reason is Reason.GAP
        assert tail_minutes(_ctx(holed), 2).available  # the tail after the hole is intact

    def test_a_hole_outside_the_window_does_not_matter(self) -> None:
        candles = series(_closes(60))
        holed = [*candles[:10], *candles[11:]]
        assert tail_minutes(_ctx(holed), 5).available

    def test_the_forming_candle_is_only_included_on_request(self) -> None:
        forming = candle(
            ORIGIN + 60 * MINUTE,
            close=Decimal("999"),
            is_final=False,
            event_ts=AS_OF,
        )
        ctx = _ctx([*series(_closes(60)), forming])
        assert tail_minutes(ctx, 5).forming is None
        live = tail_minutes(ctx, 5, include_forming=True)
        assert live.forming is not None
        assert live.forming.close == Decimal("999")

    def test_asking_for_the_forming_candle_without_one_is_unavailable(self) -> None:
        window = tail_minutes(_ctx(series(_closes(60))), 5, include_forming=True)
        assert window.reason is Reason.MISSING_INPUT

    def test_no_candles_at_all_is_missing_input(self) -> None:
        assert tail_minutes(_ctx([]), 5).reason is Reason.MISSING_INPUT


class TestBars15m:
    def test_builds_complete_utc_bars_only(self) -> None:
        window = bars_15m(_ctx(series(_closes(60))))
        assert window.available
        assert len(window.bars) == 4
        assert window.bars[0].open_time == ORIGIN
        assert window.bars[-1].close_time == ORIGIN + 60 * MINUTE
        assert window.timeframe is Timeframe.M15

    def test_a_partial_bucket_is_never_emitted(self) -> None:
        window = bars_15m(_ctx(series(_closes(70)), as_of=ORIGIN + timedelta(minutes=70)))
        assert len(window.bars) == 4
        assert window.bars[-1].close_time == ORIGIN + 60 * MINUTE

    def test_the_longest_contiguous_tail_is_used(self) -> None:
        candles = series(_closes(60))
        holed = [*candles[:20], *candles[21:]]  # hole at minute 20
        window = bars_15m(_ctx(holed))
        assert len(window.bars) == 2
        assert window.bars[0].open_time == ORIGIN + 30 * MINUTE

    def test_warmup_below_one_full_bar(self) -> None:
        window = bars_15m(_ctx(series(_closes(10)), as_of=ORIGIN + 10 * MINUTE))
        assert window.reason is Reason.WARMUP

    def test_ohlc_folds_the_minutes(self) -> None:
        closes = [Decimal(100 + i) for i in range(15)]
        window = bars_15m(_ctx(series(closes), as_of=ORIGIN + 15 * MINUTE))
        bar = window.bars[0]
        assert bar.open == Decimal("100")
        assert bar.close == Decimal("114")
        assert bar.high == Decimal("114")
        assert bar.low == Decimal("100")
        assert bar.volume == Decimal("150")


class TestTradesBetween:
    def _tape(self, seconds: list[int]) -> SourceEntry[tuple[TapeTrade, ...]]:
        trades = tuple(
            TapeTrade(
                ts=AS_OF - timedelta(seconds=s),
                price=Decimal("100"),
                qty=Decimal("1"),
                side=OrderSide.BUY,
                trade_id=str(s),
            )
            for s in sorted(seconds, reverse=True)
        )
        return SourceEntry(
            value=trades,
            ts=trades[-1].ts,
            covers_from=trades[0].ts,
            covered_until=AS_OF,
            truncated=False,
        )

    def test_slices_the_half_open_window(self) -> None:
        tape = self._tape([120, 90, 30, 10, 0])
        window = trades_between(tape, AS_OF - timedelta(seconds=60), AS_OF)
        assert window.available
        assert [t.trade_id for t in window.trades] == ["30", "10", "0"]

    def test_coverage_must_be_proven(self) -> None:
        tape = self._tape([30, 10])  # the tape only starts 30 s ago
        window = trades_between(tape, AS_OF - timedelta(seconds=60), AS_OF)
        assert window.reason is Reason.INSUFFICIENT_COVERAGE

    def test_a_missing_tape_is_missing_input(self) -> None:
        window = trades_between(
            SourceEntry(reason="missing_input"), AS_OF - timedelta(seconds=60), AS_OF
        )
        assert window.reason is Reason.MISSING_INPUT


class TestCoverageProof:
    """Astra, T2.2 diff review, must-fix 3: an old trade does not prove the
    collector was still listening during the window."""

    def _entry(
        self, seconds: list[int], covered_until: datetime | None = None
    ) -> SourceEntry[tuple[TapeTrade, ...]]:
        trades = tuple(
            TapeTrade(
                ts=AS_OF - timedelta(seconds=s),
                price=Decimal("100"),
                qty=Decimal("1"),
                side=OrderSide.BUY,
                trade_id=str(s),
            )
            for s in sorted(seconds, reverse=True)
        )
        return SourceEntry(
            value=trades,
            ts=trades[-1].ts,
            covers_from=trades[0].ts,
            covered_until=covered_until,
        )

    def test_an_empty_window_without_proof_is_not_a_zero(self) -> None:
        tape = self._entry([600, 500])  # the tape stops long before the window
        window = trades_between(tape, AS_OF - timedelta(seconds=60), AS_OF)
        assert window.reason is Reason.INSUFFICIENT_COVERAGE

    def test_an_empty_window_with_proof_is_a_zero(self) -> None:
        tape = self._entry([600, 500], covered_until=AS_OF)
        window = trades_between(tape, AS_OF - timedelta(seconds=60), AS_OF)
        assert window.available
        assert window.trades == ()

    def test_a_reconnection_does_not_prove_the_window_either(self) -> None:
        """Astra, T2.2 round 2: a trade at the end of the window says the collector
        came back, not that nothing was missed while it was away."""
        tape = self._entry([660, 5])  # 11 min ago, then one right before the cut
        window = trades_between(tape, AS_OF - timedelta(seconds=60), AS_OF)
        assert window.reason is Reason.INSUFFICIENT_COVERAGE

    def test_a_non_empty_window_still_needs_the_proof(self) -> None:
        tape = self._entry([120, 30, 10], covered_until=AS_OF)
        window = trades_between(tape, AS_OF - timedelta(seconds=60), AS_OF)
        assert window.available
        assert [t.trade_id for t in window.trades] == ["30", "10"]
