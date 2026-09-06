"""``FeatureValue``/``FeatureVector`` and the versioned quality policy."""

from __future__ import annotations

import decimal
import json
from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import OrderSide
from hunter_indicators.features.context import (
    INPUT_BOOK,
    INPUT_CANDLES,
    INPUT_FORMING,
    INPUT_FUNDING,
    INPUT_OI,
    INPUT_TRADES,
    BookSnapshot,
    DerivSnapshot,
    SourceEntry,
    TapeTrade,
    build_context,
)
from hunter_indicators.features.quality import (
    QUALITY_POLICY_VERSION,
    FreshnessPolicy,
    provenance_for,
)
from hunter_indicators.features.vector import (
    FeatureValue,
    FeatureVector,
    Quality,
    Reason,
    worst,
)
from packages.indicators.tests.factories import EXCHANGE, MINUTE, ORIGIN, SYMBOL, candle, series

AS_OF = ORIGIN + timedelta(minutes=10, seconds=30)


def _ctx(**kwargs: object):
    base = {
        "exchange": EXCHANGE,
        "symbol": SYMBOL,
        "as_of": AS_OF,
        "candles": series([Decimal(100 + i) for i in range(10)]),
    }
    return build_context(**{**base, **kwargs})  # type: ignore[arg-type]


class TestQualityOrdering:
    def test_worst_wins(self) -> None:
        assert worst(Quality.OK, Quality.DEGRADED) is Quality.DEGRADED
        assert worst(Quality.DEGRADED, Quality.UNAVAILABLE) is Quality.UNAVAILABLE
        assert worst(Quality.OK, Quality.OK) is Quality.OK
        assert worst() is Quality.OK


class TestFeatureValue:
    def test_unavailable_carries_no_number(self) -> None:
        value = FeatureValue.unavailable("return_5m", Reason.WARMUP, inputs=(INPUT_CANDLES,))
        assert value.value is None
        assert value.quality is Quality.UNAVAILABLE
        assert value.reason is Reason.WARMUP

    def test_an_available_value_must_carry_a_number(self) -> None:
        with pytest.raises(ValueError, match="value"):
            FeatureValue(key="return_5m", value=None, quality=Quality.OK)

    def test_an_unavailable_value_must_carry_a_reason(self) -> None:
        with pytest.raises(ValueError, match="reason"):
            FeatureValue(key="return_5m", value=None, quality=Quality.UNAVAILABLE)

    def test_degrading_keeps_the_number_and_records_why(self) -> None:
        value = FeatureValue.ok("spread_pct", Decimal("0.0001"), inputs=(INPUT_BOOK,))
        degraded = value.degraded_to(Quality.DEGRADED, Reason.STALE_INPUT)
        assert degraded.value == Decimal("0.0001")
        assert degraded.quality is Quality.DEGRADED
        assert degraded.reason is Reason.STALE_INPUT

    def test_degrading_to_unavailable_drops_the_number(self) -> None:
        value = FeatureValue.ok("spread_pct", Decimal("0.0001"), inputs=(INPUT_BOOK,))
        gone = value.degraded_to(Quality.UNAVAILABLE, Reason.MISSING_INPUT)
        assert gone.value is None


class TestFeatureVector:
    def test_wire_form_is_canonical_and_decimal_safe(self) -> None:
        vector = FeatureVector(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            ts=AS_OF,
            feature_set_version="abc",
            values={
                "return_5m": FeatureValue.ok(
                    "return_5m", Decimal("0.0100"), inputs=(INPUT_CANDLES,)
                ),
                "funding_rate": FeatureValue.unavailable(
                    "funding_rate", Reason.MISSING_INPUT, inputs=(INPUT_FUNDING,)
                ),
            },
            provenance={},
        )
        wire = vector.as_json()
        assert wire["ts"] == "2026-09-01T00:10:30Z"
        assert wire["quality_policy_version"] == QUALITY_POLICY_VERSION
        assert wire["values"]["return_5m"] == {
            "value": "0.01",
            "quality": "ok",
            "reason": None,
            "inputs": [INPUT_CANDLES],
        }
        assert wire["values"]["funding_rate"]["value"] is None
        assert wire["values"]["funding_rate"]["reason"] == "missing_input"
        # canonical bytes: two equal vectors serialise identically
        assert json.loads(vector.canonical_bytes()) == json.loads(vector.canonical_bytes())

    def test_number_reads_only_return_usable_values(self) -> None:
        vector = FeatureVector(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            ts=AS_OF,
            feature_set_version="abc",
            values={
                "a": FeatureValue.ok("a", Decimal("1"), inputs=(INPUT_CANDLES,)),
                "b": FeatureValue.unavailable("b", Reason.GAP, inputs=(INPUT_CANDLES,)),
            },
            provenance={},
        )
        assert vector.number("a") == Decimal("1")
        assert vector.number("b") is None
        assert vector.number("missing") is None

    def test_keys_must_match_the_values_they_index(self) -> None:
        with pytest.raises(ValueError, match="key"):
            FeatureVector(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                ts=AS_OF,
                feature_set_version="abc",
                values={"a": FeatureValue.ok("b", Decimal("1"), inputs=(INPUT_CANDLES,))},
                provenance={},
            )


class TestProvenance:
    def test_a_fresh_minute_feed_is_ok(self) -> None:
        prov = provenance_for(_ctx())
        assert prov[INPUT_CANDLES].quality is Quality.OK
        assert prov[INPUT_CANDLES].ts == ORIGIN + 10 * MINUTE
        assert prov[INPUT_CANDLES].covers_from == ORIGIN

    def test_a_late_minute_feed_is_degraded_with_its_age(self) -> None:
        ctx = _ctx(candles=series([Decimal(100 + i) for i in range(8)]))
        prov = provenance_for(ctx)
        assert prov[INPUT_CANDLES].quality is Quality.DEGRADED
        assert prov[INPUT_CANDLES].reason is Reason.STALE_INPUT
        assert prov[INPUT_CANDLES].age_s == Decimal("150")

    def test_a_capped_minute_history_says_so(self) -> None:
        """The provenance carries the truncation the loader saw, so a sample can
        be read back knowing its history may not reach as far as it looks."""
        ctx = build_context(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=AS_OF,
            candles=series([Decimal(100)] * 10),
            candles_truncated=True,
        )
        assert provenance_for(ctx)[INPUT_CANDLES].truncated is True
        assert provenance_for(_ctx())[INPUT_CANDLES].truncated is False

    def test_no_candles_at_all_is_unavailable(self) -> None:
        prov = provenance_for(_ctx(candles=[]))
        assert prov[INPUT_CANDLES].quality is Quality.UNAVAILABLE
        assert prov[INPUT_CANDLES].reason is Reason.MISSING_INPUT

    def test_a_stale_book_is_degraded_not_dropped(self) -> None:
        book = BookSnapshot(ts=AS_OF - timedelta(seconds=45), depth=20, bids=(), asks=())
        prov = provenance_for(_ctx(book=SourceEntry(value=book, ts=book.ts)))
        assert prov[INPUT_BOOK].quality is Quality.DEGRADED
        assert prov[INPUT_BOOK].age_s == Decimal("45")

    def test_the_age_of_an_input_is_exact(self) -> None:
        """Same rule as ``SourceEntry.age_s`` (cross review, nice-to-have c):
        the provenance age is integer arithmetic, never a float second count."""
        book = BookSnapshot(
            ts=AS_OF - timedelta(days=100000, microseconds=1), depth=20, bids=(), asks=()
        )
        prov = provenance_for(_ctx(book=SourceEntry(value=book, ts=book.ts)))
        assert prov[INPUT_BOOK].age_s == Decimal("8640000000.000001")

    def test_a_budget_decision_survives_a_hostile_precision(self) -> None:
        """The same age, and therefore the same verdict, whatever precision the
        process runs under (Astra, fix-pass review, must-fix 1)."""
        book = BookSnapshot(
            ts=AS_OF - timedelta(seconds=10, microseconds=1), depth=20, bids=(), asks=()
        )
        ctx = _ctx(book=SourceEntry(value=book, ts=book.ts))
        with decimal.localcontext() as ambient:
            ambient.prec = 6
            entry = provenance_for(ctx)[INPUT_BOOK]
        assert entry.age_s == Decimal("10.000001")
        assert entry.quality is Quality.DEGRADED

    def test_a_refused_book_keeps_its_reason(self) -> None:
        """Astra, fix-pass review, must-fix 2: a crossed snapshot must not reach
        the envelope looking like a book Redis never had."""
        crossed = SourceEntry[BookSnapshot](reason="crossed")
        assert provenance_for(_ctx(book=crossed))[INPUT_BOOK].reason is Reason.CORRUPT_INPUT
        assert provenance_for(_ctx())[INPUT_BOOK].reason is Reason.MISSING_INPUT

    def test_a_fresh_book_is_ok(self) -> None:
        book = BookSnapshot(ts=AS_OF - timedelta(seconds=2), depth=20, bids=(), asks=())
        prov = provenance_for(_ctx(book=SourceEntry(value=book, ts=book.ts)))
        assert prov[INPUT_BOOK].quality is Quality.OK

    def test_derivative_fields_are_judged_one_by_one(self) -> None:
        deriv = DerivSnapshot(
            funding_rate=Decimal("0.0001"),
            funding_ts=AS_OF - timedelta(seconds=5),
            open_interest=Decimal("100"),
            oi_ts=AS_OF - timedelta(minutes=30),
        )
        prov = provenance_for(_ctx(deriv=SourceEntry(value=deriv, ts=deriv.funding_ts)))
        assert prov[INPUT_FUNDING].quality is Quality.OK
        assert prov[INPUT_OI].quality is Quality.DEGRADED
        assert prov[INPUT_OI].age_s == Decimal("1800")

    def test_a_quiet_tape_is_not_degraded_by_silence(self) -> None:
        trades = (
            TapeTrade(AS_OF - timedelta(minutes=9), Decimal("1"), Decimal("1"), OrderSide.BUY, "1"),
        )
        prov = provenance_for(
            _ctx(
                trades=SourceEntry(
                    value=trades, ts=trades[0].ts, covers_from=trades[0].ts, truncated=False
                )
            )
        )
        assert prov[INPUT_TRADES].quality is Quality.OK
        assert prov[INPUT_TRADES].truncated is False

    def test_the_forming_candle_is_its_own_input(self) -> None:
        forming = candle(
            ORIGIN + 10 * MINUTE,
            close=Decimal("999"),
            is_final=False,
            event_ts=AS_OF - timedelta(seconds=1),
        )
        prov = provenance_for(_ctx(candles=[*series([Decimal(100)] * 10), forming]))
        assert prov[INPUT_FORMING].quality is Quality.OK
        assert prov[INPUT_FORMING].ts == AS_OF - timedelta(seconds=1)

    def test_the_policy_is_versioned_and_overridable(self) -> None:
        book = BookSnapshot(ts=AS_OF - timedelta(seconds=45), depth=20, bids=(), asks=())
        ctx = _ctx(book=SourceEntry(value=book, ts=book.ts))
        prov = provenance_for(ctx, FreshnessPolicy(book_max_age_s=60))
        assert prov[INPUT_BOOK].quality is Quality.OK
        assert QUALITY_POLICY_VERSION == "quality_v1"


class TestPolicyIdentity:
    """Astra, T2.2 diff review (nice-to-have): an overridden budget must not be
    published under the identity of the default policy."""

    def test_the_default_policy_publishes_the_plain_version(self) -> None:
        assert FreshnessPolicy().identity == QUALITY_POLICY_VERSION

    def test_an_override_publishes_a_different_identity(self) -> None:
        overridden = FreshnessPolicy(book_max_age_s=60).identity
        assert overridden != QUALITY_POLICY_VERSION
        assert overridden.startswith(QUALITY_POLICY_VERSION)

    def test_the_identity_is_stable_for_the_same_override(self) -> None:
        assert (
            FreshnessPolicy(book_max_age_s=60).identity
            == FreshnessPolicy(book_max_age_s=60).identity
        )
