"""One market's hot state, decoded once and reused between ticks.

**The measured problem.** ``Scanner.advance`` rebuilt its whole ``MarketContext``
from bytes on every tick: ``hotstate.decode_candles`` turned 1500 msgpack rows
into pydantic candles and ``decode_trades`` turned 2000 rows into tape trades,
every second, for every market. Measured in the container, per market per tick:
**29 ms** of candles and **14 ms** of trades against **0.5 ms** and **0.2 ms**
warm (notes-T2.5 sections 22 and 25). Yet between two ticks the two lists barely
move -- the candle head is rewritten as the minute forms, one candle row is
pushed per minute, a handful of trades arrive -- and every other row is
byte-for-byte the one already decoded.

**Why the key is the row.** The identity claimed here is "the same answer the
loader would give for these rows", and the only thing that proves a row did not
change is the row. Keying by ``open_time`` (or by ``trade_id``) would mean
re-deciding the writer's precedence rules to know whether the payload behind a
key changed, and would need the row unpacked to find the key at all -- part of
the very cost being removed.

**Why the whole list is still read every tick.** Reading only the newest rows
and merging them into a remembered window was refused in the design review with
three counterexamples (Astra, T2.5c): a websocket candle older than
``CANDLE_FAST_WINDOW`` rewrites the middle of the list and is not announced on
``market.candles.closed``; a REST backfill whose row was already inserted
announces nothing on the second insert; and a key Redis lost and that came back
holding one row would leave a merged window claiming 1499 candles Redis does not
have. Rebuilding the sequence **from the rows received** makes all three correct
by construction, with no invalidation rule to get wrong: what the list dropped,
this cache drops with it, in the same pass.

The decoders themselves are never forked: an unknown row goes through the very
function the loader uses, one row at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from hunter_indicators.features.context import INPUT_TRADES, SourceEntry, TapeTrade, missing
from hunter_indicators.features.hotstate import (
    CANDLES_MAXLEN,
    EMPTY,
    TRADES_MAXLEN,
    decode_candles,
    decode_trades,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hunter_core.domain.market import NormalizedCandle
    from hunter_indicators.features.context import MarketContext

__all__ = ["CandleCache", "HotCache", "TapeCache"]

_NEVER = datetime.max.replace(tzinfo=UTC)
"""A cut no observation can be after: used to decode a row *without* applying
the cut, which the assembly applies afterwards. ``as_of`` moves every tick, so
the cut cannot be baked into what is cached."""

DEFERRED = object()
"""A trade row whose verdict depends on the cut, so it cannot be cached.

``decode_trades`` reads ``side`` **only after** the row survived the cut, so a
row stamped in the future with an unusable ``side`` is silently skipped by the
loader and would raise here if decoded eagerly at :data:`_NEVER` (Astra, T2.5c
diff review, must-fix 1). Such a row is handed to the loader at the **real**
cut on every tick instead: it is skipped while it is in the future and raises
the day it is not, which is exactly what the loader does with it."""


class CandleCache:
    """Decoded candles of one market, keyed by the exact row that produced them."""

    __slots__ = ("_resident", "decoded")

    def __init__(self) -> None:
        self._resident: dict[bytes, NormalizedCandle] = {}
        self.decoded = 0
        """How many rows this cache had to decode since it was created."""

    def __len__(self) -> int:
        return len(self._resident)

    @property
    def row_bytes(self) -> int:
        """Bytes held as keys — the price of the reuse, for the memory report."""
        return sum(len(row) for row in self._resident)

    def decode(
        self, rows: Sequence[bytes], limit: int = CANDLES_MAXLEN
    ) -> SourceEntry[tuple[NormalizedCandle, ...]]:
        """``decode_candles(rows, limit)``, decoding only the rows never seen.

        The returned sequence is built from ``rows`` alone, and the residency
        afterwards is exactly ``rows``: a row that left the list leaves the
        cache in the same pass, so nothing here can outlive what Redis holds.
        """
        previous = self._resident
        resident: dict[bytes, NormalizedCandle] = {}
        candles: list[NormalizedCandle] = []
        for row in reversed(list(rows)):
            # ``in`` and not ``or``: a truthiness test would depend on whether a
            # decoded candle is ever falsy, which is not this module's to know.
            if row in previous:
                known = previous[row]
            elif row in resident:
                known = resident[row]
            else:
                known = _decode_candle(row)
                self.decoded += 1
            resident[row] = known
            candles.append(known)
        self._resident = resident
        truncated = len(rows) >= limit
        if not candles:
            return SourceEntry(reason=EMPTY, truncated=truncated)
        return SourceEntry(
            value=tuple(candles),
            ts=candles[-1].close_time,
            covers_from=candles[0].open_time,
            truncated=truncated,
        )


class TapeCache:
    """Decoded trades of one market, keyed by the row, cut at assembly time.

    A row that the loader refuses (an unparsable timestamp, price or quantity)
    is remembered as a refusal, so a corrupt row is not re-parsed once a second
    forever either.
    """

    __slots__ = ("_resident", "decoded")

    def __init__(self) -> None:
        self._resident: dict[bytes, TapeTrade | None | object] = {}
        self.decoded = 0

    def __len__(self) -> int:
        return len(self._resident)

    @property
    def row_bytes(self) -> int:
        return sum(len(row) for row in self._resident)

    def decode(
        self, rows: Sequence[bytes], as_of: datetime, limit: int = TRADES_MAXLEN
    ) -> SourceEntry[tuple[TapeTrade, ...]]:
        """``decode_trades(rows, as_of, limit)``, decoding only the new rows.

        The cut is applied **here**, never in what is stored: ``as_of`` moves
        every tick, so a tape decoded against one cut has to answer for the
        next one without being decoded again.
        """
        if not rows:
            self._resident = {}
            return missing(INPUT_TRADES)
        previous = self._resident
        resident: dict[bytes, TapeTrade | None | object] = {}
        tape: list[TapeTrade] = []
        for row in reversed(list(rows)):
            if row in previous:
                known = previous[row]
            elif row in resident:
                known = resident[row]
            else:
                known = _decode_trade(row)
                self.decoded += 1
            resident[row] = known
            if known is DEFERRED:
                # The loader decides, at this cut, with its own validation
                # order — including whether it raises.
                late = decode_trades((row,), as_of, TRADES_MAXLEN).value
                if late:
                    tape.append(late[0])
                continue
            if isinstance(known, TapeTrade) and known.ts <= as_of:
                tape.append(known)
        self._resident = resident
        truncated = len(rows) >= limit
        if not tape:
            return SourceEntry(reason=EMPTY, truncated=truncated)
        return SourceEntry(
            value=tuple(tape),
            ts=tape[-1].ts,
            covers_from=tape[0].ts,
            truncated=truncated,
        )


CARRIED_WINDOWS = ("minute_index", "bars_15m")
"""The ``MarketContext.memo`` entries that survive a tick, and why only these two.

T2.2b memoised two derivations on the context because a vector asked for them
seventeen and three times: the epoch-minute index of ``final_candles`` and the
complete 15-minute bars. Both are functions of ``final_candles`` **alone** --
``windows._build_index(ctx.final_candles)`` and ``_bars_15m``, which reads
``last_final`` and ``final_candles`` and nothing else -- and the minute history
changes once a minute while the context is rebuilt once a second. Folding a
hundred 15-minute bars 60 times per minute instead of once was 6 ms of the
17 ms a market cost.

A **whitelist**, never the whole memo: a derivation added upstream that depends
on ``as_of``, on the forming candle or on the book must not travel, and one that
is simply not listed here is recomputed, which is only slower. The equality
above is the other half of the argument -- the entries travel only to a context
whose minutes are the same objects in the same order -- and
``tests/test_hotcache.py`` asserts the purity of both entries directly against
``windows``, so the day one of them starts reading ``as_of`` this fails here
instead of silently producing a stale window."""


@dataclass(slots=True)
class HotCache:
    """The two lists of one market that are worth keeping decoded, and the
    windows derived from them."""

    candles: CandleCache = field(default_factory=CandleCache)
    trades: TapeCache = field(default_factory=TapeCache)
    carried: int = 0
    """How many memo entries were carried into a new context, for the report."""

    _minutes: tuple[NormalizedCandle, ...] | None = None
    _memo: dict[str, Any] = field(default_factory=dict[str, "Any"])

    @property
    def rows(self) -> int:
        return len(self.candles) + len(self.trades)

    @property
    def decoded(self) -> int:
        return self.candles.decoded + self.trades.decoded

    def adopt(self, context: MarketContext) -> None:
        """Give ``context`` the windows of the previous one, if they still hold.

        The comparison is by value and costs a pointer check per candle: the
        candles come from :class:`CandleCache`, so an unchanged minute history
        is the *same objects*, and ``tuple.__eq__`` settles each of them by
        identity before it would ever call ``__eq__``.

        The dictionary kept here is the previous context's own ``memo``, not a
        copy: it is filled while that context is evaluated, so what is carried
        is what the last evaluation actually derived.
        """
        if self._minutes is not None and self._minutes == context.final_candles:
            for key in CARRIED_WINDOWS:
                if key in self._memo:
                    context.memo[key] = self._memo[key]
                    self.carried += 1
        self._minutes = context.final_candles
        self._memo = context.memo


def _decode_candle(row: bytes) -> NormalizedCandle:
    """One row through the production loader — never a second decoder.

    ``decode_candles`` owns the payload contract (the ``ts`` key folded back
    into ``event_ts``, the refusals that raise); calling it with a single row
    costs a function call and keeps this module unable to disagree with it.
    """
    decoded = decode_candles((row,), CANDLES_MAXLEN).value
    if decoded is None:
        # ``decode_candles`` only refuses an *empty* list, and this one has a
        # row: anything else it cannot read raises inside it, as it should.
        raise ValueError("a candle row decoded to no candle")
    return decoded[0]


def _decode_trade(row: bytes) -> TapeTrade | None | object:
    """One trade row through ``decode_trades``, with the cut kept out of it.

    ``None`` is the loader's own verdict on a row it cannot parse -- it skips
    it -- and skipping it again at assembly reproduces that exactly.
    :data:`DEFERRED` is the third answer: decoding it *without* a cut raised,
    which the loader would only have done for a row the cut lets through, so
    the verdict belongs to the cut and not to the cache.
    """
    try:
        decoded = decode_trades((row,), _NEVER, TRADES_MAXLEN).value
    except Exception:
        return DEFERRED
    return None if not decoded else decoded[0]
