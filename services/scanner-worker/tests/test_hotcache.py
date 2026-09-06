"""The decode caches: the same answer as the loaders, without decoding twice.

They exist for one measured reason (notes-T2.5 sections 22 and 25): advancing a
market re-validated 1500 msgpack candle rows and 2000 trade rows on every tick,
29 ms and 14 ms of the ~45 ms a market cost in the container. The rows
themselves barely change -- one candle head rewritten per second, one new candle
per minute, a handful of trades -- so the decoded object of an *unchanged row*
is reusable.

What these tests defend is not the speed, it is the equivalence: for every
input the loader accepts, the cache must return exactly what the loader
returns, including the entries the loader refuses. The cache is keyed by the
raw row, so it can only ever answer for bytes it was given.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from hunter_core.domain.market import NormalizedCandle
from hunter_indicators.features.context import SourceEntry
from hunter_indicators.features.hotstate import decode_candles, decode_trades
from hunter_scanner_worker.hotcache import CandleCache, HotCache, TapeCache

from .builders import (
    EXCHANGE,
    ORIGIN,
    bad_side_trade_row,
    candle,
    candle_rows,
    corrupt_trade_row,
    series,
    trade_rows,
)

pytestmark = pytest.mark.unit

SYMBOL = "SYM000USDT"


def rows_of(minutes: int, *, start: datetime = ORIGIN) -> list[bytes]:
    return candle_rows(series(minutes, start=start, symbol=SYMBOL))


def values(entry: SourceEntry[tuple[NormalizedCandle, ...]]) -> tuple[NormalizedCandle, ...]:
    return entry.value or ()


def test_the_cache_answers_exactly_what_the_loader_answers() -> None:
    """Every shape the loader has an opinion about, compared entry by entry."""
    forming = candle(
        ORIGIN + timedelta(minutes=10),
        is_final=False,
        event_ts=ORIGIN + timedelta(minutes=10, seconds=30),
        symbol=SYMBOL,
    )
    cases: list[tuple[str, list[bytes], int]] = [
        ("empty", [], 1500),
        ("one minute", rows_of(1), 1500),
        ("ten minutes", rows_of(10), 1500),
        ("with a forming head", [*candle_rows([forming]), *rows_of(10)], 1500),
        ("truncated", rows_of(10), 10),
        ("full buffer", rows_of(1500), 1500),
    ]
    for name, rows, limit in cases:
        cache = CandleCache()
        assert cache.decode(rows, limit) == decode_candles(rows, limit), name


def test_an_unchanged_row_is_never_decoded_twice() -> None:
    cache = CandleCache()
    rows = rows_of(1500)
    first = cache.decode(rows, 1500)
    assert cache.decoded == 1500

    second = cache.decode(rows, 1500)
    assert cache.decoded == 1500, "a second pass over the same rows decodes nothing"
    assert first == second
    # The very same objects: the context keeps them for a whole tick, so
    # rebuilding equal-but-distinct candles would be pure allocation.
    assert values(first)[0] is values(second)[0]


def test_a_rewritten_row_is_decoded_again_and_the_old_one_is_dropped() -> None:
    """The forming minute is rewritten by every tick: one decode, not 1500."""
    cache = CandleCache()
    base = series(1499, symbol=SYMBOL)
    forming_at = ORIGIN + timedelta(minutes=1499)
    first = candle(
        forming_at, is_final=False, event_ts=forming_at + timedelta(seconds=10), symbol=SYMBOL
    )
    updated = candle(
        forming_at, is_final=False, event_ts=forming_at + timedelta(seconds=40), symbol=SYMBOL
    )
    cache.decode([*candle_rows([first]), *candle_rows(base)], 1500)
    assert cache.decoded == 1500

    entry = cache.decode([*candle_rows([updated]), *candle_rows(base)], 1500)
    assert cache.decoded == 1501, "only the rewritten row is decoded again"
    assert len(cache) == 1500, "the row Redis replaced does not stay resident"
    assert values(entry)[-1].event_ts == updated.event_ts


def test_a_row_redis_dropped_leaves_the_cache_with_it() -> None:
    """The answer is built from the rows received, so a shorter list is shorter.

    Astra's counterexample to a merge-based window: the key is deleted and
    recreated holding only the head minute. A cache that *unioned* the new rows
    into what it remembered would keep 1499 candles Redis no longer has.
    """
    cache = CandleCache()
    cache.decode(rows_of(1500), 1500)
    assert len(cache) == 1500

    entry = cache.decode(rows_of(1, start=ORIGIN + timedelta(minutes=1499)), 1500)
    assert len(values(entry)) == 1
    assert len(cache) == 1, "what the list lost, the cache loses"


def test_an_emptied_list_empties_the_cache() -> None:
    cache = CandleCache()
    cache.decode(rows_of(10), 1500)
    entry = cache.decode([], 1500)
    assert entry == decode_candles([], 1500)
    assert len(cache) == 0


def test_the_resident_size_follows_the_buffer_not_the_history() -> None:
    """A market running for hours holds 1500 rows, and a new minute costs one.

    The rows are written once and re-read, exactly as Redis holds them: the
    market-worker packs a candle when it arrives (``hot_state_candles``), so the
    bytes of a minute already in the buffer do not change until that minute is
    rewritten.
    """
    cache = CandleCache()
    newest_first = candle_rows(series(1520, symbol=SYMBOL))
    for pushed in range(1500, 1521):
        head = len(newest_first) - pushed
        cache.decode(newest_first[head : head + 1500], 1500)
    assert len(cache) == 1500
    assert cache.decoded == 1520, "twenty new minutes cost twenty decodes"


def test_the_resident_cost_of_one_market_is_measured_not_estimated() -> None:
    """The price of the reuse, in bytes, asserted so a regression is visible.

    Measured on this machine: 3.4 MiB per market for a full 1500-minute buffer
    (2357 B per candle, of which 311 B are the raw row kept as the key), so
    674 MiB for the 200 markets of the joint M2 decision and 1.3 GiB at the
    ``max_markets = 400`` guard rail. That is the number the window decision is
    written against (notes-T2.5 section 24) -- the ceiling here has ~25% of head
    room over it, and exists so nobody has to re-derive it after a model change.
    """
    import gc
    import tracemalloc

    rows = rows_of(1500)
    gc.collect()
    tracemalloc.start()
    try:
        before = tracemalloc.take_snapshot()
        cache = CandleCache()
        entry = cache.decode(rows, 1500)
        gc.collect()
        after = tracemalloc.take_snapshot()
        resident = sum(item.size_diff for item in after.compare_to(before, "filename"))
    finally:
        tracemalloc.stop()

    assert len(values(entry)) == 1500
    per_candle = resident / 1500
    assert per_candle < 3000, f"{per_candle:.0f} B per resident candle"
    assert cache.row_bytes / 1500 < 400


# --- the tape ---------------------------------------------------------------
#
# Same technique, second measured bottleneck: with ``TRADES_MAXLEN = 2000`` the
# scanner re-decoded two thousand trade rows on every tick -- 14 ms per market
# in the container, measured next to the 0.5 ms the warm candle cache costs
# (notes-T2.5 section 25). The tape is append-only (``hot_state_trades``:
# LPUSH + LTRIM), so an old row is byte-identical until it falls off the end.


def test_the_tape_cache_answers_exactly_what_the_loader_answers() -> None:
    cut = ORIGIN + timedelta(minutes=5)
    good = trade_rows(30, until=cut)
    corrupt = corrupt_trade_row()
    future = trade_rows(3, until=cut + timedelta(minutes=1))
    cases: list[tuple[str, list[bytes], int]] = [
        ("empty", [], 2000),
        ("thirty trades", good, 2000),
        ("truncated", good, 30),
        ("a corrupt row", [corrupt, *good], 2000),
        ("only after the cut", list(future[:2]), 2000),
        ("all corrupt", [corrupt], 2000),
    ]
    for name, rows, limit in cases:
        cache = TapeCache()
        assert cache.decode(rows, cut, limit) == decode_trades(rows, cut, limit), name


def test_the_tape_reuses_the_rows_that_did_not_move() -> None:
    cut = ORIGIN + timedelta(minutes=5)
    rows = trade_rows(200, until=cut)
    cache = TapeCache()
    cache.decode(rows, cut, 2000)
    assert cache.decoded == 200

    arrived = trade_rows(3, until=cut + timedelta(seconds=1))
    later = cut + timedelta(seconds=2)
    entry = cache.decode([*arrived, *rows[:-3]], later, 2000)
    assert cache.decoded == 203, "three trades arrived, three rows decoded"
    assert len(cache) == 200, "and the three that fell off the end are gone"
    assert entry == decode_trades([*arrived, *rows[:-3]], later, 2000)


def test_a_cut_in_the_past_hides_the_newest_trades_without_dropping_them() -> None:
    """The cut is applied at assembly, not at decode: the same cached rows have
    to answer for two different cuts, because ``as_of`` moves every tick."""
    cut = ORIGIN + timedelta(minutes=5)
    rows = trade_rows(60, until=cut)
    cache = TapeCache()
    full = cache.decode(rows, cut, 2000)
    earlier = cut - timedelta(seconds=10)
    partial = cache.decode(rows, earlier, 2000)

    assert cache.decoded == 60, "the second cut decodes nothing new"
    assert partial == decode_trades(rows, earlier, 2000)
    assert len(partial.value or ()) < len(full.value or ())


# --- the windows carried between ticks --------------------------------------


MINUTES = series(216, symbol=SYMBOL)
"""Built once and shared: the cache carries a window when the minute history is
*the same candles*, which is what the decode cache hands it in production."""


def _context(as_of: datetime, *, forming: bool, minutes: int = 200):
    from hunter_indicators.features.context import build_context

    candles = MINUTES[:minutes]
    extra = (
        [
            candle(
                candles[-1].close_time,
                is_final=False,
                event_ts=as_of,
                symbol=SYMBOL,
            )
        ]
        if forming
        else []
    )
    return build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=as_of, candles=[*candles, *extra])


def test_the_carried_windows_depend_on_the_minutes_and_on_nothing_else() -> None:
    """The purity the carry rests on, asserted against ``windows`` itself.

    ``bars_15m`` and the minute index are memoised functions of
    ``final_candles``; carrying them into the next tick's context is only sound
    while that stays true. If a derivation upstream starts reading ``as_of`` or
    the forming candle, this test fails -- instead of a stale window reaching a
    vector.
    """
    from hunter_indicators.features import windows

    base = ORIGIN + timedelta(minutes=200)
    # Two instants inside the minute, and two more that cross a 15-minute
    # boundary with the *same* minutes behind them -- the boundary is where a
    # dependency on ``as_of`` would show up if there were one (Astra).
    cuts = (
        base + timedelta(seconds=5),
        base + timedelta(seconds=45),
        base + timedelta(minutes=4, seconds=59),
        base + timedelta(minutes=5, seconds=1),
        base + timedelta(minutes=14, seconds=59),
    )
    first = _context(cuts[0], forming=False)
    reference = windows.bars_15m(first)
    for cut in cuts[1:]:
        other = _context(cut, forming=True)
        assert windows.bars_15m(other).bars == reference.bars, cut.isoformat()
        assert windows.bars_15m(other).reason == reference.reason, cut.isoformat()
        assert other.memo["minute_index"].tail == first.memo["minute_index"].tail
        assert list(other.memo["minute_index"].minutes) == list(first.memo["minute_index"].minutes)


def test_the_windows_travel_while_the_minutes_hold_and_stop_when_they_move() -> None:
    from hunter_indicators.features import windows

    base = ORIGIN + timedelta(minutes=200)
    cache = HotCache()
    first = _context(base, forming=False)
    cache.adopt(first)
    folded = windows.bars_15m(first)

    second = _context(base + timedelta(seconds=30), forming=True)
    cache.adopt(second)
    assert second.memo["bars_15m"] is folded, "the same minutes, the same bars"
    assert cache.carried == 2

    third = _context(base + timedelta(minutes=15), forming=False, minutes=215)
    cache.adopt(third)
    assert "bars_15m" not in third.memo, "new minutes derive their own windows"
    assert cache.carried == 2, "and nothing was carried into them"
    assert len(windows.bars_15m(third).bars) > len(folded.bars)


def test_a_future_row_the_loader_would_skip_does_not_raise_early() -> None:
    """The loader reads ``side`` **after** the cut, and so must the cache.

    ``decode_trades`` drops a row stamped after ``as_of`` before it ever looks
    at ``side``; decoding that row eagerly, without a cut, would raise on the
    unusable side and take the whole evaluation cycle down with it (Astra,
    T2.5c diff review). The verdict on such a row belongs to the cut, so it is
    asked again at every cut -- skipped while it is in the future, raising the
    moment the cut reaches it, exactly like the loader.
    """
    cut = ORIGIN + timedelta(minutes=5)
    future_ts = cut + timedelta(seconds=30)
    broken = bad_side_trade_row(future_ts)
    rows = [broken, *trade_rows(10, until=cut)]
    cache = TapeCache()

    assert cache.decode(rows, cut, 2000) == decode_trades(rows, cut, 2000)

    later = future_ts + timedelta(seconds=1)
    with pytest.raises(ValueError):
        decode_trades(rows, later, 2000)
    with pytest.raises(ValueError):
        cache.decode(rows, later, 2000)
