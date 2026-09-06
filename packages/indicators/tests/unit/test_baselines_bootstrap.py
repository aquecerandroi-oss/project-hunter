"""Bootstrap over persisted candles: equivalence with the live path, and honesty.

The joint decision (``docs/plans/M2.md`` §Baselines) allows a bootstrap only with
the **same calculators** as the live scanner, and admits ``trade_velocity`` only
if bootstrap and live agree byte for byte. This file proves the first and
documents the second as *not* proven, with the reason machine-readable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import BaselineSource
from hunter_core.domain.market import NormalizedCandle
from hunter_indicators.baselines import (
    REASON_HISTORICAL_SOURCE_UNAVAILABLE,
    REASON_PARTIAL_CANDLE,
    REASON_SEMANTICS_UNPROVEN,
    BaselineRevision,
    bootstrap_exclusions,
    bootstrap_feature_keys,
    bootstrap_revisions,
)
from hunter_indicators.baselines.bootstrap import replay_vectors
from hunter_indicators.features import DEFAULT_REGISTRY, build_context, compute_features
from packages.indicators.tests.factories import EXCHANGE, MINUTE, SYMBOL, candle

MARKET = uuid.UUID("0199a1d0-0000-7000-8000-000000000001")
ORIGIN = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)


def ramp(minutes: int, *, start: datetime = ORIGIN) -> list[NormalizedCandle]:
    """A series whose close walks a small saw so no window is degenerate."""
    out: list[NormalizedCandle] = []
    price = Decimal("100")
    for index in range(minutes):
        price = price + (Decimal("0.1") if index % 3 else Decimal("-0.05"))
        out.append(
            candle(
                start + index * MINUTE,
                close=price,
                high=price + Decimal("0.2"),
                low=price - Decimal("0.2"),
                volume=Decimal(10 + (index % 7)),
            )
        )
    return out


class TestWhatABootstrapMayProduce:
    def test_only_candle_features_are_eligible(self) -> None:
        keys = bootstrap_feature_keys()
        assert "return_1h" in keys
        assert "relative_volume_1h" in keys
        assert "atr_14_pct" in keys
        assert "spread_pct" not in keys
        assert "funding_rate" not in keys
        assert "return_1h_live" not in keys

    def test_every_registered_feature_is_either_produced_or_excluded_with_a_reason(self) -> None:
        produced = set(bootstrap_feature_keys())
        excluded = {item.feature: item.reason for item in bootstrap_exclusions()}
        registered = {definition.key for definition in DEFAULT_REGISTRY.definitions()}
        assert produced | set(excluded) == registered
        assert produced.isdisjoint(excluded)

    def test_trade_velocity_is_excluded_because_the_equivalence_is_unproven(self) -> None:
        reasons = {item.feature: item.reason for item in bootstrap_exclusions()}
        assert reasons["trade_velocity_1m"] == REASON_SEMANTICS_UNPROVEN
        assert reasons["spread_pct"] == REASON_HISTORICAL_SOURCE_UNAVAILABLE
        assert reasons["buy_pressure_5m"] == REASON_HISTORICAL_SOURCE_UNAVAILABLE
        assert reasons["return_1h_live"] == REASON_PARTIAL_CANDLE


class TestBootstrapEqualsLive:
    def test_the_replayed_vector_is_byte_identical_to_the_live_one(self) -> None:
        candles = ramp(400)
        cut = ORIGIN + 400 * MINUTE
        replayed = list(
            replay_vectors(exchange=EXCHANGE, symbol=SYMBOL, candles=candles, cuts=[cut])
        )
        live_ctx = build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=cut, candles=candles)
        live = compute_features(live_ctx)
        assert replayed[0][0].canonical_bytes() == live.vector.canonical_bytes()

    def test_the_carried_state_matches_over_a_sequence_of_cuts(self) -> None:
        # The ATR checkpoint is state and does not travel inside the vector: two
        # runs that agree on one cut can still diverge on the next (Astra, T2.3
        # design review, item 10).
        candles = ramp(400)
        cuts = [ORIGIN + minute * MINUTE for minute in range(380, 400)]
        replayed = list(
            replay_vectors(exchange=EXCHANGE, symbol=SYMBOL, candles=candles, cuts=cuts)
        )
        state = None
        for index, cut in enumerate(cuts):
            ctx = build_context(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                as_of=cut,
                candles=[c for c in candles if c.close_time <= cut],  # type: ignore[attr-defined]
            )
            live = compute_features(ctx) if state is None else compute_features(ctx, state)
            state = live.state
            assert replayed[index][0].canonical_bytes() == live.vector.canonical_bytes()
            assert replayed[index][1].as_wire() == live.state.as_wire()

    def test_the_replay_is_bar_only_and_says_so(self) -> None:
        # The proof above covers the *candle* features. A live vector that also
        # had a book and a tape is not equal to a bootstrap vector, and this test
        # exists so nobody reads the equivalence as wider than it is.
        candles = ramp(200)
        cut = ORIGIN + 200 * MINUTE
        replayed = next(
            iter(replay_vectors(exchange=EXCHANGE, symbol=SYMBOL, candles=candles, cuts=[cut]))
        )
        assert replayed[0].quality_of("spread_pct").value == "unavailable"
        assert replayed[0].quality_of("return_1h").value == "ok"


class TestBootstrapRevisions:
    def test_a_bootstrap_produces_revisions_marked_as_bootstrap(self) -> None:
        candles = ramp(400)
        cuts = [ORIGIN + minute * MINUTE for minute in range(300, 360)]
        window_end = cuts[-1] + MINUTE  # half-open: the last cut is inside
        result = bootstrap_revisions(
            market_id=MARKET,
            exchange=EXCHANGE,
            symbol=SYMBOL,
            candles=candles,
            cuts=cuts,
            window_start=window_end - timedelta(days=7),
            window_end=window_end,
            available_at=window_end + timedelta(minutes=5),
            expected_size=420,
        )
        assert result.sampled == 60
        computed = [item for item in result.revisions if isinstance(item, BaselineRevision)]
        assert computed
        assert all(item.source is BaselineSource.BOOTSTRAP for item in computed)
        assert all(item.expected_size == 420 for item in computed)

    def test_a_bootstrap_is_published_now_never_back_dated(self) -> None:
        candles = ramp(400)
        cuts = [ORIGIN + minute * MINUTE for minute in range(300, 320)]
        window_end = cuts[-1] + MINUTE  # half-open: the last cut is inside
        published = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
        result = bootstrap_revisions(
            market_id=MARKET,
            exchange=EXCHANGE,
            symbol=SYMBOL,
            candles=candles,
            cuts=cuts,
            window_start=window_end - timedelta(days=7),
            window_end=window_end,
            available_at=published,
            expected_size=420,
        )
        computed = [item for item in result.revisions if isinstance(item, BaselineRevision)]
        assert computed
        assert all(item.available_at == published for item in computed)

    def test_warm_up_shows_up_as_rejections_not_as_invented_numbers(self) -> None:
        # Cuts that start at minute 20 cannot produce return_1h: the window does
        # not exist yet. The bucket is thin and says why.
        candles = ramp(40)
        cuts = [ORIGIN + minute * MINUTE for minute in range(20, 40)]
        result = bootstrap_revisions(
            market_id=MARKET,
            exchange=EXCHANGE,
            symbol=SYMBOL,
            candles=candles,
            cuts=cuts,
            window_start=ORIGIN,
            window_end=cuts[-1] + MINUTE,  # half-open
            available_at=cuts[-1] + timedelta(minutes=1),
            expected_size=420,
        )
        assert result.rejections["return_1h"]["warmup"] == 20
        assert not [
            item
            for item in result.revisions
            if isinstance(item, BaselineRevision) and item.key.feature == "return_1h"
        ]


class TestAstraDiffReviewRing:
    """Regression for finding 6: the replay must cut the ring the way the loader does."""

    def test_the_window_never_exceeds_the_ring(self) -> None:
        # ``bisect_left(cut - 1500 min)`` with ``bisect_right(cut)`` selects 1501
        # closes on a continuous series, so the bootstrap saw one minute the live
        # hot state never held and the bytes diverged.
        candles = ramp(1600)
        cut = ORIGIN + 1600 * MINUTE
        replayed = next(
            iter(
                replay_vectors(
                    exchange=EXCHANGE,
                    symbol=SYMBOL,
                    candles=candles,
                    cuts=[cut],
                    buffer_minutes=1500,
                )
            )
        )
        # the live side is the hot state: the last 1500 entries, flagged truncated
        # because the loader got as many rows as it asked for
        live_ctx = build_context(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=cut,
            candles=candles[-1500:],
            candles_truncated=True,
        )
        live = compute_features(live_ctx)
        assert replayed[0].canonical_bytes() == live.vector.canonical_bytes()

    def test_a_full_ring_is_reported_as_truncated(self) -> None:
        candles = ramp(1600)
        cut = ORIGIN + 1600 * MINUTE
        replayed = next(
            iter(
                replay_vectors(
                    exchange=EXCHANGE,
                    symbol=SYMBOL,
                    candles=candles,
                    cuts=[cut],
                    buffer_minutes=1500,
                )
            )
        )
        assert replayed[0].provenance["candles:1m"].truncated is True

    def test_a_short_history_is_not_reported_as_truncated(self) -> None:
        candles = ramp(400)
        cut = ORIGIN + 400 * MINUTE
        replayed = next(
            iter(
                replay_vectors(
                    exchange=EXCHANGE,
                    symbol=SYMBOL,
                    candles=candles,
                    cuts=[cut],
                    buffer_minutes=1500,
                )
            )
        )
        assert replayed[0].provenance["candles:1m"].truncated is False
