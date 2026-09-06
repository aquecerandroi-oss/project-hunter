"""T2.2b's acceptance test: the memoised engine and the old one agree, byte for byte.

The optimisation of ``features/windows.py`` is only allowed to be faster. So the
test does not check a formula, it checks an **equality between two
implementations**: every cut is computed twice, once through the production
windows and once through ``tests/reference/windows_v0.py`` (the module exactly as
it stood before T2.2b), and both the canonical bytes of the ``FeatureVector`` and
the canonical bytes of ``FeatureState.as_wire()`` must match.

Two details make it a proof rather than a ritual:

- the two runs carry **independent** state cut by cut, so a divergence in the
  anchored ATR checkpoint at cut 3 cannot be papered over by re-seeding both
  runs from the same state at cut 4 (Astra, T2.2b design review);
- the monkeypatch is itself asserted: a spy counts calls into the reference, and
  a run that never entered the old code would fail instead of silently comparing
  the new implementation with itself.

The series are chosen for the places where window selection *decides* something:
the 15-minute boundary, a hole inside the still-open bucket, a hole deep in the
history, a warm-up shorter than one bar, the 1500-minute buffer rolling, and a
forming candle straddling the cut (the ``_live`` features).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.features import compute_features
from hunter_indicators.features.context import MarketContext, build_context
from hunter_indicators.features.state import EMPTY_STATE, FeatureState
from packages.indicators.tests.factories import EXCHANGE, MINUTE, ORIGIN, SYMBOL, candle, series
from packages.indicators.tests.reference import windows_v0

if TYPE_CHECKING:
    from hunter_core.domain.market import NormalizedCandle

pytestmark = pytest.mark.unit

PATCH_SITES = (
    ("hunter_indicators.features.windows", "tail_minutes"),
    ("hunter_indicators.features.windows", "bars_15m"),
    ("hunter_indicators.features.price", "tail_minutes"),
    ("hunter_indicators.features.volume", "tail_minutes"),
    ("hunter_indicators.features.trend", "tail_minutes"),
    ("hunter_indicators.features.trend", "bars_15m"),
    ("hunter_indicators.features.atr", "bars_15m"),
    ("hunter_indicators.features.quality", "bars_15m"),
    ("hunter_indicators.features.micro", "trades_between"),
)
"""Every place the engine imported a window function *by name*.

Patching only ``windows.py`` would leave the module-level bindings pointing at
the new code and the comparison would be vacuous.
"""


class _Spy:
    def __init__(self) -> None:
        self.calls = 0

    def wrap(self, target: object):
        def wrapper(*args: object, **kwargs: object) -> object:
            self.calls += 1
            return target(*args, **kwargs)  # type: ignore[operator]

        return wrapper


def _install_reference(monkeypatch: pytest.MonkeyPatch) -> _Spy:
    import importlib

    spy = _Spy()
    for module_name, attribute in PATCH_SITES:
        module = importlib.import_module(module_name)
        monkeypatch.setattr(module, attribute, spy.wrap(getattr(windows_v0, attribute)))
    return spy


def _closes(count: int, *, start: int = 100) -> list[Decimal]:
    """A series that actually moves, so every feature has something to say."""
    values: list[Decimal] = []
    price = Decimal(start)
    for index in range(count):
        step = Decimal(index % 13) - Decimal(6)
        price = price + step / Decimal(10)
        values.append(price)
    return values


def _shaped(count: int) -> list[NormalizedCandle]:
    closes = _closes(count)
    highs = [value + Decimal(index % 5) / Decimal(20) for index, value in enumerate(closes)]
    lows = [value - Decimal(index % 7) / Decimal(20) for index, value in enumerate(closes)]
    volumes = [Decimal(10 + (index * 7) % 91) for index in range(count)]
    return series(closes, highs=highs, lows=lows, volumes=volumes)


def _with_hole(candles: Sequence[NormalizedCandle], index: int) -> list[NormalizedCandle]:
    return [*candles[:index], *candles[index + 1 :]]


def _cuts(candles: Sequence[NormalizedCandle], count: int) -> Iterator[datetime]:
    """``count`` evaluation instants spread over the series, **oldest first**.

    The order is the point: the ATR checkpoint is an anchored recursion, so a
    walk that runs backwards never folds a *new* bar into a state and would miss
    a defect in exactly the step the scanner takes every fifteen minutes (Astra,
    T2.2b diff review, must-fix 1).
    """
    first, last = candles[0].open_time, candles[-1].close_time
    span = int((last - first) / MINUTE)
    for step in range(count):
        yield first + (span * (step + 1) // count) * MINUTE


def _context(
    candles: Sequence[NormalizedCandle], as_of: datetime, *, forming: bool = False
) -> MarketContext:
    supplied = list(candles)
    if forming:
        opened = as_of.replace(second=0, microsecond=0)
        supplied.append(
            candle(
                opened,
                close=Decimal("123.45"),
                high=Decimal("124"),
                low=Decimal("122"),
                volume=Decimal("3"),
                is_final=False,
                event_ts=as_of,
            )
        )
    return build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=as_of, candles=supplied)


def _walk(candles: Sequence[NormalizedCandle], cuts: Sequence[datetime], *, forming: bool):
    """Run the engine cut by cut, carrying its own state, returning the bytes."""
    state: FeatureState = EMPTY_STATE
    out: list[tuple[bytes, bytes]] = []
    for as_of in cuts:
        result = compute_features(_context(candles, as_of, forming=forming), state)
        state = result.state
        out.append((result.vector.canonical_bytes(), canonical_json(state.as_wire())))
    return out


SERIES = {
    "long_1600": lambda: _shaped(1600),
    "hole_in_open_bucket": lambda: _with_hole(_shaped(400), 396),
    "hole_deep_in_history": lambda: _with_hole(_shaped(400), 40),
    "warmup_below_one_bar": lambda: _shaped(9),
    "exactly_one_bar": lambda: _shaped(15),
    "two_bars_and_a_minute": lambda: _shaped(31),
}


class TestTheMemoisedEngineIsTheOldEngine:
    @pytest.mark.parametrize("name", sorted(SERIES))
    @pytest.mark.parametrize("forming", [False, True])
    def test_same_canonical_bytes_over_twenty_cuts(
        self, monkeypatch: pytest.MonkeyPatch, name: str, forming: bool
    ) -> None:
        candles = SERIES[name]()
        cuts = list(_cuts(candles, 20))
        produced = _walk(candles, cuts, forming=forming)
        with monkeypatch.context() as patched:
            spy = _install_reference(patched)
            reference = _walk(candles, cuts, forming=forming)
        assert spy.calls > 0, "the reference implementation must actually have run"
        for index, (new, old) in enumerate(zip(produced, reference, strict=True)):
            assert new[0] == old[0], f"{name} cut {index}: feature vector bytes differ"
            assert new[1] == old[1], f"{name} cut {index}: feature state bytes differ"

    def test_the_buffer_actually_slides_minute_by_minute(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ring buffer dropping its oldest minute, with the state carried.

        This is the shape the scanner runs in: 1500 minutes in the hot state, one
        more minute closes, the oldest falls out, and the **same** ATR checkpoint
        continues. Four copies of one slice with a reset state would not exercise
        it (Astra, T2.2b diff review, must-fix 2): a memo that answered from the
        previous window would survive that and die here.
        """
        candles = _shaped(1600)
        limit = 1500

        def walk() -> list[tuple[bytes, bytes]]:
            state: FeatureState = EMPTY_STATE
            out: list[tuple[bytes, bytes]] = []
            for end in range(limit, len(candles) + 1):
                window = candles[max(0, end - limit) : end]
                result = compute_features(_context(window, candles[end - 1].close_time), state)
                state = result.state
                out.append((result.vector.canonical_bytes(), canonical_json(state.as_wire())))
            return out

        produced = walk()
        with monkeypatch.context() as patched:
            spy = _install_reference(patched)
            reference = walk()
        assert spy.calls > 0
        assert len(produced) == len(candles) - limit + 1 == 101
        assert produced == reference

    def test_a_close_time_out_of_order_takes_the_general_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The prefix shortcut has a fallback, and the fallback is the old code.

        ``final_candles`` is ordered by ``open_time``; the type does not force
        ``close_time`` to follow, so a candle whose close reaches past the 15m
        anchor while later ones do not makes ``usable`` a non-prefix subsequence.
        The identity check then declines the slice and the minutes are rebuilt --
        which must still produce the pre-T2.2b bytes (Astra, nice-to-have).
        """
        candles = _shaped(400)
        # closes at minute 395: past the 15m anchor (390) but before the cut, so
        # build_context keeps it and bars_15m must leave it out of the middle.
        stretched = candles[300].model_copy(
            update={"close_time": candles[300].open_time + 95 * MINUTE}
        )
        mixed = [*candles[:300], stretched, *candles[301:]]
        as_of = ORIGIN + 400 * MINUTE
        from hunter_indicators.features import windows

        seen: list[int] = []
        original = windows._minutes_of  # pyright: ignore[reportPrivateUsage]

        def counted(values: Sequence[NormalizedCandle]):
            seen.append(len(values))
            return original(values)

        monkeypatch.setattr(windows, "_minutes_of", counted)
        produced = compute_features(_context(mixed, as_of)).vector.canonical_bytes()
        assert len(seen) == 2, "the prefix shortcut must have declined and rebuilt"
        with monkeypatch.context() as patched:
            _install_reference(patched)
            reference = compute_features(_context(mixed, as_of)).vector.canonical_bytes()
        assert produced == reference

    @pytest.mark.parametrize("hole", list(range(300, 400)))
    def test_every_tail_length_where_a_window_changes_its_mind(
        self, monkeypatch: pytest.MonkeyPatch, hole: int
    ) -> None:
        """Sweep the hole across the last hundred minutes of a fixed cut.

        The contiguous tail is the number the whole module turns on, and it only
        *decides* something at the boundaries: 61 minutes (``return_1h`` exists
        or does not), 31, 16, every multiple of 15 for the bar count. Twenty
        scattered cuts can miss all of them -- an off-by-one in ``_tail_length``
        survived that version of this test -- so this one lands on each of them.
        """
        candles = _with_hole(_shaped(400), hole)
        as_of = ORIGIN + 400 * MINUTE
        produced = compute_features(_context(candles, as_of)).vector.canonical_bytes()
        with monkeypatch.context() as patched:
            spy = _install_reference(patched)
            reference = compute_features(_context(candles, as_of)).vector.canonical_bytes()
        assert spy.calls > 0
        assert produced == reference

    def test_a_second_call_on_a_warm_context_returns_the_same_bytes(self) -> None:
        """The memo must not make the *second* vector of one context differ."""
        ctx = _context(_shaped(400), ORIGIN + 400 * MINUTE)
        first = compute_features(ctx)
        second = compute_features(ctx)
        assert first.vector.canonical_bytes() == second.vector.canonical_bytes()
        assert canonical_json(first.state.as_wire()) == canonical_json(second.state.as_wire())


class TestNoLookAheadSurvivesTheMemo:
    def test_a_changing_forming_candle_never_moves_a_bar_feature(self) -> None:
        """The T2.2 anti-look-ahead guarantee, re-run with the memo in place."""
        candles = _shaped(400)
        as_of = ORIGIN + timedelta(minutes=400, seconds=30)
        bar_keys = [key for key in ("return_15m", "atr_14_pct", "relative_volume_15m")]
        readings: list[list[str]] = []
        for close in (Decimal("50"), Decimal("500"), Decimal("5000")):
            supplied = [
                *candles,
                candle(
                    ORIGIN + 400 * MINUTE,
                    close=close,
                    high=close,
                    low=close,
                    volume=Decimal("99"),
                    is_final=False,
                    event_ts=as_of,
                ),
            ]
            ctx = build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=as_of, candles=supplied)
            vector = compute_features(ctx).vector
            readings.append([str(vector.values[key].value) for key in bar_keys])
            assert vector.values["return_15m_live"].value is not None
        assert readings[0] == readings[1] == readings[2]
        assert len({tuple(row) for row in readings}) == 1
