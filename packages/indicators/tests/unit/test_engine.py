"""The engine: one vector per market, with provenance and inherited quality."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from hunter_core.domain.enums import OrderSide
from hunter_indicators.features.context import (
    INPUT_BOOK,
    INPUT_CANDLES,
    BookSnapshot,
    DerivSnapshot,
    SourceEntry,
    TapeTrade,
    build_context,
)
from hunter_indicators.features.engine import (
    DEFAULT_REGISTRY,
    compute_features,
)
from hunter_indicators.features.hotstate import HotStateRaw, load_context
from hunter_indicators.features.quality import QUALITY_POLICY_VERSION
from hunter_indicators.features.state import EMPTY_STATE
from hunter_indicators.features.vector import Quality, Reason
from packages.indicators.tests.factories import (
    EXCHANGE,
    MINUTE,
    ORIGIN,
    SYMBOL,
    book_payload,
    candle_rows,
    series,
)

MINUTES = 400
AS_OF = ORIGIN + timedelta(minutes=MINUTES, seconds=20)


def _candles(count: int = MINUTES):
    closes = [Decimal(100) + Decimal(i % 7) for i in range(count)]
    volumes = [Decimal(10) + Decimal(i % 5) for i in range(count)]
    highs = [c + Decimal("1") for c in closes]
    lows = [c - Decimal("1") for c in closes]
    return series(closes, volumes=volumes, highs=highs, lows=lows)


def _ctx(**kwargs: object):
    return build_context(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        as_of=AS_OF,
        candles=_candles(),
        **kwargs,  # type: ignore[arg-type]
    )


def _book(age_s: int = 1, at: object = None, levels: int = 20):
    """A book of real depth: ``levels`` a side, 3 per bid level and 1 per ask.

    ``orderbook_imbalance_20`` is only defined over 20 levels a side, so a
    one-level fixture would leave the feature unexercised end to end.
    """
    snapshot = BookSnapshot(
        ts=(at or AS_OF) - timedelta(seconds=age_s),  # type: ignore[operator]
        depth=20,
        bids=tuple((Decimal("100") - i * Decimal("0.1"), Decimal("3")) for i in range(levels)),
        asks=tuple((Decimal("100.2") + i * Decimal("0.1"), Decimal("1")) for i in range(levels)),
    )
    return SourceEntry(value=snapshot, ts=snapshot.ts)


def _tape():
    trades = tuple(
        TapeTrade(
            ts=AS_OF - timedelta(seconds=age),
            price=Decimal("100"),
            qty=Decimal("1"),
            side=OrderSide.BUY if age % 2 else OrderSide.SELL,
            trade_id=str(age),
        )
        for age in range(600, 0, -10)
    )
    return SourceEntry(value=trades, ts=trades[-1].ts, covers_from=trades[0].ts)


class TestVector:
    def test_every_registered_feature_appears_exactly_once(self) -> None:
        result = compute_features(_ctx(), EMPTY_STATE)
        assert set(result.vector.values) == set(DEFAULT_REGISTRY.keys())
        assert result.vector.feature_set_version == DEFAULT_REGISTRY.feature_set_version
        assert result.vector.quality_policy_version == QUALITY_POLICY_VERSION

    def test_the_vector_is_stamped_with_the_cut(self) -> None:
        result = compute_features(_ctx(), EMPTY_STATE)
        assert result.vector.ts == AS_OF
        assert result.vector.exchange == EXCHANGE
        assert result.vector.symbol == SYMBOL

    def test_provenance_covers_every_declared_input(self) -> None:
        result = compute_features(_ctx(book=_book(), trades=_tape()), EMPTY_STATE)
        declared = {name for value in result.vector.values.values() for name in value.inputs}
        assert declared <= set(result.vector.provenance)
        assert result.vector.provenance[INPUT_CANDLES].quality is Quality.OK

    def test_missing_sources_leave_their_features_unavailable_not_zero(self) -> None:
        result = compute_features(_ctx(), EMPTY_STATE)
        spread = result.vector.values["spread_pct"]
        assert spread.value is None
        assert spread.quality is Quality.UNAVAILABLE
        assert spread.reason is Reason.MISSING_INPUT
        assert result.vector.number("spread_pct") is None

    def test_the_book_features_are_computed_end_to_end(self) -> None:
        result = compute_features(_ctx(book=_book()), EMPTY_STATE)
        spread = result.vector.values["spread_pct"]
        imbalance = result.vector.values["orderbook_imbalance_20"]
        assert spread.quality is Quality.OK
        assert spread.value == Decimal("0.2") / Decimal("100.1")
        assert imbalance.quality is Quality.OK
        assert imbalance.value == Decimal("0.5")  # (60 - 20) / 80

    def test_a_thin_book_stops_the_imbalance_and_not_the_spread(self) -> None:
        """Cross-review must-fix 2 at the vector level: the two book features are
        judged apart — the top of book is quoted, the depth is not there."""
        result = compute_features(_ctx(book=_book(levels=7)), EMPTY_STATE)
        assert result.vector.values["spread_pct"].quality is Quality.OK
        imbalance = result.vector.values["orderbook_imbalance_20"]
        assert imbalance.value is None
        assert imbalance.reason is Reason.INSUFFICIENT_SAMPLE

    def test_a_crossed_book_stops_both(self) -> None:
        crossed = BookSnapshot(
            ts=AS_OF - timedelta(seconds=1),
            depth=20,
            bids=tuple((Decimal("101") - i * Decimal("0.1"), Decimal("1")) for i in range(20)),
            asks=tuple((Decimal("100") + i * Decimal("0.1"), Decimal("1")) for i in range(20)),
        )
        result = compute_features(_ctx(book=SourceEntry(value=crossed, ts=crossed.ts)), EMPTY_STATE)
        for key in ("spread_pct", "orderbook_imbalance_20"):
            assert result.vector.values[key].value is None
            assert result.vector.values[key].reason is Reason.CORRUPT_INPUT

    def test_a_stale_book_degrades_only_the_book_features(self) -> None:
        result = compute_features(_ctx(book=_book(age_s=45), trades=_tape()), EMPTY_STATE)
        assert result.vector.values["spread_pct"].quality is Quality.DEGRADED
        assert result.vector.values["spread_pct"].value is not None
        assert result.vector.values["return_5m"].quality is Quality.OK

    def test_a_late_candle_feed_degrades_the_bar_features(self) -> None:
        cut = AS_OF + timedelta(minutes=5)  # five minutes with no new candle
        late = build_context(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=cut,
            candles=_candles(),
            book=_book(age_s=1, at=cut),
        )
        result = compute_features(late, EMPTY_STATE)
        assert result.vector.values["return_5m"].quality is Quality.DEGRADED
        assert result.vector.values["return_5m"].reason is Reason.STALE_INPUT
        assert result.vector.provenance[INPUT_BOOK].quality is Quality.OK

    def test_the_wire_form_round_trips_through_canonical_json(self) -> None:
        result = compute_features(_ctx(book=_book(), trades=_tape()), EMPTY_STATE)
        first = result.vector.canonical_bytes()
        second = compute_features(_ctx(book=_book(), trades=_tape()), EMPTY_STATE)
        assert first == second.vector.canonical_bytes()


class TestState:
    def test_the_atr_checkpoint_is_carried_out_and_back_in(self) -> None:
        first = compute_features(_ctx(), EMPTY_STATE)
        assert first.state.atr_15m is not None
        anchor = first.state.atr_15m.origin_bar_open
        later = build_context(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=AS_OF + 15 * MINUTE,
            candles=_candles(MINUTES + 15),
        )
        second = compute_features(later, first.state)
        assert second.state.atr_15m is not None
        assert second.state.atr_15m.origin_bar_open == anchor  # no reseed on the rolling window

    def test_a_cold_start_still_produces_a_reading_and_says_where_it_anchored(self) -> None:
        result = compute_features(_ctx(), EMPTY_STATE)
        assert result.vector.number("atr_14_pct") is not None
        assert result.state.atr_15m is not None
        assert result.state.atr_15m.origin_reason == "bootstrap"

    def test_the_state_survives_serialisation(self) -> None:
        from hunter_indicators.features.state import FeatureState

        result = compute_features(_ctx(), EMPTY_STATE)
        restored = FeatureState.from_wire(result.state.as_wire())
        assert restored == result.state
        again = compute_features(_ctx(), restored)
        assert again.vector.canonical_bytes() == result.vector.canonical_bytes()


class TestDeterminism:
    def test_two_identical_contexts_give_identical_vectors(self) -> None:
        deriv = SourceEntry(
            value=DerivSnapshot(
                funding_rate=Decimal("0.0001"), funding_ts=AS_OF - timedelta(seconds=5)
            ),
            ts=AS_OF - timedelta(seconds=5),
        )
        one = compute_features(_ctx(book=_book(), trades=_tape(), deriv=deriv), EMPTY_STATE)
        two = compute_features(_ctx(book=_book(), trades=_tape(), deriv=deriv), EMPTY_STATE)
        assert one.vector.as_json() == two.vector.as_json()


class TestStatefulDependencies:
    """Astra, T2.2 diff review, must-fix 2: the ATR checkpoint is a dependency of
    four features, so its own staleness has to reach all of them."""

    def test_the_checkpoint_is_an_input_of_every_feature_that_reads_it(self) -> None:
        from hunter_indicators.features.context import INPUT_ATR_STATE

        stateful = {
            key
            for key, calculator in ((c.definition.key, c) for c in DEFAULT_REGISTRY.all())
            if INPUT_ATR_STATE in calculator.definition.inputs
        }
        assert stateful == {
            "atr_14_pct",
            "breakout_strength_20",
            "momentum_15m",
            "momentum_acceleration",
        }

    def test_a_gap_that_blocks_the_bars_degrades_every_stateful_feature(self) -> None:
        from hunter_indicators.features.context import INPUT_ATR_STATE

        warm = compute_features(_ctx(), EMPTY_STATE)
        assert warm.vector.number("atr_14_pct") is not None
        # a hole 9 minutes before the anchor: no complete 15m bar can be built
        candles = _candles(MINUTES + 40)
        holed = [*candles[: MINUTES + 20], *candles[MINUTES + 21 :]]
        ctx = build_context(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=ORIGIN + timedelta(minutes=MINUTES + 40, seconds=20),
            candles=holed,
        )
        result = compute_features(ctx, warm.state)
        assert result.vector.provenance[INPUT_ATR_STATE].quality is not Quality.OK
        for key in ("atr_14_pct", "momentum_15m", "momentum_acceleration"):
            assert result.vector.values[key].quality is not Quality.OK, key


def test_the_numbers_do_not_depend_on_the_ambient_decimal_context() -> None:
    """Astra, must-fix 5: a library that lowered ``decimal.getcontext().prec``
    must not move a frozen feature's number."""
    import decimal

    baseline = compute_features(_ctx(book=_book(), trades=_tape()), EMPTY_STATE)
    with decimal.localcontext() as ambient:
        ambient.prec = 6
        hostile = compute_features(_ctx(book=_book(), trades=_tape()), EMPTY_STATE)
    assert hostile.vector.canonical_bytes() == baseline.vector.canonical_bytes()


class TestTradeCoverageAtVectorLevel:
    """The declared consequence of proving coverage instead of assuming it: until
    the collector fills ``covered_until`` (T2.5), trade features are unavailable
    with a reason — not zero, and not a count over an unknown window."""

    def test_without_the_collectors_proof_the_trade_features_are_unavailable(self) -> None:
        result = compute_features(_ctx(trades=_tape()), EMPTY_STATE)
        for key in ("trade_velocity_1m", "buy_pressure_5m", "sell_pressure_5m"):
            value = result.vector.values[key]
            assert value.value is None, key
            assert value.reason is Reason.INSUFFICIENT_COVERAGE, key

    def test_with_the_proof_they_publish(self) -> None:
        proven = SourceEntry(
            value=_tape().value,
            ts=AS_OF - timedelta(seconds=10),
            covers_from=AS_OF - timedelta(seconds=600),
            covered_until=AS_OF,
        )
        result = compute_features(_ctx(trades=proven), EMPTY_STATE)
        assert result.vector.number("trade_velocity_1m") is not None
        assert result.vector.number("buy_pressure_5m") is not None


def test_a_crossed_snapshot_stays_corrupt_all_the_way_to_the_vector() -> None:
    """Astra, fix-pass review, must-fix 2: end to end over the production path.

    The bytes go through ``load_context`` — which refuses the snapshot — and the
    vector still says ``corrupt_input`` for the book features and for the book's
    provenance. If it said ``missing_input`` the envelope would blame Redis for a
    decode that produced a quote the exchange never published.
    """
    raw = HotStateRaw(
        candles=candle_rows(_candles(20)),
        book=book_payload(AS_OF - timedelta(seconds=1), [("101", "1")], [("100", "1")]),
    )
    ctx = load_context(raw, exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
    result = compute_features(ctx, EMPTY_STATE)
    assert result.vector.provenance[INPUT_BOOK].available is False
    assert result.vector.provenance[INPUT_BOOK].reason is Reason.CORRUPT_INPUT
    for key in ("spread_pct", "orderbook_imbalance_20"):
        assert result.vector.values[key].value is None
        assert result.vector.values[key].reason is Reason.CORRUPT_INPUT


def test_an_absent_book_still_says_missing_input() -> None:
    """The other half of the same rule: no book is not a corrupt book."""
    raw = HotStateRaw(candles=candle_rows(_candles(20)))
    ctx = load_context(raw, exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
    result = compute_features(ctx, EMPTY_STATE)
    assert result.vector.provenance[INPUT_BOOK].reason is Reason.MISSING_INPUT
    assert result.vector.values["spread_pct"].reason is Reason.MISSING_INPUT
