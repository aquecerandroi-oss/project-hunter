"""Unit tests: the ``data_quality`` aggregate rule (every branch from
``docs/plans/M1.md`` / ``dialogue-M1.md`` rodada 4), Decimal-as-string
serialization, and the msgpack book/trades parsers — no IO, no Redis, no
Postgres.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import msgpack
import pytest
import redis.exceptions

from hunter_api.schemas.markets import ComponentQuality, MarketOut
from hunter_api.services.markets import (
    HotState,
    _pipeline_hot_state,  # pyright: ignore[reportPrivateUsage]
    aggregate_data_quality,
    build_market_out,
    parse_book,
    parse_trades,
    spread_pct,
)
from hunter_core.domain.enums import MarketStatus, MarketType, Timeframe
from hunter_core.domain.market import DataQuality

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
STALE_AFTER_S = 10.0
FRESH = NOW - timedelta(seconds=1)
STALE = NOW - timedelta(seconds=STALE_AFTER_S + 5)


class _RaisingPipeline:
    """A fake ``redis.asyncio.Redis.pipeline()`` whose ``execute()`` raises —
    for the F2 "Redis unavailable" / "WRONGTYPE" scenarios, without a real
    Redis connection.
    """

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def hgetall(self, *_args: object, **_kwargs: object) -> _RaisingPipeline:
        return self

    def get(self, *_args: object, **_kwargs: object) -> _RaisingPipeline:
        return self

    def lrange(self, *_args: object, **_kwargs: object) -> _RaisingPipeline:
        return self

    async def execute(self, raise_on_error: bool = True) -> list[object]:
        del raise_on_error
        raise self._exc


class _RaisingRedis:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def pipeline(self, transaction: bool = False) -> _RaisingPipeline:
        del transaction
        return _RaisingPipeline(self._exc)


class _PartialFailurePipeline:
    """A fake pipeline whose ``execute(raise_on_error=False)`` returns a
    fixed list of results with exception objects standing in place of
    specific failed commands -- mirrors real redis-py's per-command
    isolation (verified against a real server: a WRONGTYPE on one command
    comes back as a ``ResponseError`` *in the results list*, the other
    commands' results are unaffected) -- for the (G3) "one bad key must not
    poison every market" scenario, without a real Redis connection.
    """

    def __init__(self, results: list[object]) -> None:
        self._results = results

    def hgetall(self, *_args: object, **_kwargs: object) -> _PartialFailurePipeline:
        return self

    def get(self, *_args: object, **_kwargs: object) -> _PartialFailurePipeline:
        return self

    def lrange(self, *_args: object, **_kwargs: object) -> _PartialFailurePipeline:
        return self

    async def execute(self, raise_on_error: bool = True) -> list[object]:
        assert raise_on_error is False, "must isolate per-command, not raise the whole pipeline"
        return self._results


class _PartialFailureRedis:
    def __init__(self, results: list[object]) -> None:
        self._results = results

    def pipeline(self, transaction: bool = False) -> _PartialFailurePipeline:
        del transaction
        return _PartialFailurePipeline(self._results)


def _row(*, symbol: str = "BTCUSDT"):
    from hunter_api.repositories.markets import MarketRow

    return MarketRow(
        id=uuid.uuid4(),
        exchange="binance",
        symbol=symbol,
        base_asset="BTC",
        quote_asset="USDT",
        market_type=MarketType.PERPETUAL,
        status=MarketStatus.ACTIVE,
        is_monitored=True,
        monitor_rank=1,
    )


def _out(
    *,
    ticker_ts: datetime | None,
    book_ts: datetime | None,
    mark_ts: datetime | None,
    oi_ts: datetime | None = None,
    has_gap: bool = False,
) -> MarketOut:
    ticker = {"last": "1", "ts": ticker_ts.isoformat()} if ticker_ts else {}
    deriv: dict[str, str] = {}
    if mark_ts:
        deriv["mark_price"] = "1"
        deriv["mark_ts"] = mark_ts.isoformat()
    if oi_ts:
        deriv["open_interest"] = "1"
        deriv["oi_ts"] = oi_ts.isoformat()
    hot = HotState(ticker=ticker, deriv=deriv, book_ts=book_ts)
    return build_market_out(_row(), hot, has_gap=has_gap, now=NOW, stale_after_s=STALE_AFTER_S)


class TestAggregateDataQuality:
    """Pure precedence rule, decoupled from Redis parsing."""

    def test_all_absent_is_unavailable(self) -> None:
        assert (
            aggregate_data_quality(
                ticker=ComponentQuality.ABSENT,
                book=ComponentQuality.ABSENT,
                mark=ComponentQuality.ABSENT,
                has_gap=False,
            )
            is DataQuality.UNAVAILABLE
        )

    def test_one_required_absent_is_degraded_even_if_others_are_ok(self) -> None:
        assert (
            aggregate_data_quality(
                ticker=ComponentQuality.OK,
                book=ComponentQuality.ABSENT,
                mark=ComponentQuality.OK,
                has_gap=False,
            )
            is DataQuality.DEGRADED
        )

    def test_open_gap_is_degraded_even_with_every_component_ok(self) -> None:
        assert (
            aggregate_data_quality(
                ticker=ComponentQuality.OK,
                book=ComponentQuality.OK,
                mark=ComponentQuality.OK,
                has_gap=True,
            )
            is DataQuality.DEGRADED
        )

    def test_stale_component_without_gap_or_absence_is_stale(self) -> None:
        assert (
            aggregate_data_quality(
                ticker=ComponentQuality.OK,
                book=ComponentQuality.OK,
                mark=ComponentQuality.STALE,
                has_gap=False,
            )
            is DataQuality.STALE
        )

    def test_every_required_component_ok_is_ok(self) -> None:
        assert (
            aggregate_data_quality(
                ticker=ComponentQuality.OK,
                book=ComponentQuality.OK,
                mark=ComponentQuality.OK,
                has_gap=False,
            )
            is DataQuality.OK
        )

    def test_gap_beats_stale_and_absence_beats_gap_precedence_holds(self) -> None:
        """Precedence is absence-first (-> degraded/unavailable), then gap,
        then staleness — an absent required component with a gap is still
        just ``degraded``, not some fourth state.
        """
        assert (
            aggregate_data_quality(
                ticker=ComponentQuality.ABSENT,
                book=ComponentQuality.STALE,
                mark=ComponentQuality.STALE,
                has_gap=True,
            )
            is DataQuality.DEGRADED
        )


class TestBuildMarketOutQualityScenarios:
    """End-to-end scenarios off real ticker/deriv/book inputs — the
    dialogue-M1.md rodada 4 acceptance list, verbatim.
    """

    def test_no_data_at_all_is_unavailable(self) -> None:
        out = _out(ticker_ts=None, book_ts=None, mark_ts=None)
        assert out.data_quality is DataQuality.UNAVAILABLE
        assert out.last_price is None
        assert out.components.ticker.quality is ComponentQuality.ABSENT

    def test_book_stopped_alone_is_degraded_with_other_channels_fresh(self) -> None:
        out = _out(ticker_ts=FRESH, book_ts=None, mark_ts=FRESH)
        assert out.data_quality is DataQuality.DEGRADED
        assert out.components.ticker.quality is ComponentQuality.OK
        assert out.components.book.quality is ComponentQuality.ABSENT

    def test_mark_stopped_alone_is_degraded(self) -> None:
        out = _out(ticker_ts=FRESH, book_ts=FRESH, mark_ts=None)
        assert out.data_quality is DataQuality.DEGRADED
        assert out.components.mark.quality is ComponentQuality.ABSENT

    def test_open_interest_updated_while_mark_is_frozen_still_reads_stale(self) -> None:
        """OI freshness must never rejuvenate mark — a still-frozen mark with
        a fresh OI stays ``stale`` at the aggregate level, and the OI
        component's own age is reported independently.
        """
        out = _out(ticker_ts=FRESH, book_ts=FRESH, mark_ts=STALE, oi_ts=FRESH)
        assert out.data_quality is DataQuality.STALE
        assert out.components.mark.quality is ComponentQuality.STALE
        assert out.components.open_interest.age_ms == 1000

    def test_expired_key_reads_as_absent_same_as_never_written(self) -> None:
        out = _out(ticker_ts=FRESH, book_ts=FRESH, mark_ts=None)
        assert out.components.mark.ts is None
        assert out.components.mark.quality is ComponentQuality.ABSENT
        assert out.data_quality is DataQuality.DEGRADED

    def test_failed_gap_degrades_even_with_fresh_ticks_on_every_component(self) -> None:
        out = _out(ticker_ts=FRESH, book_ts=FRESH, mark_ts=FRESH, has_gap=True)
        assert out.data_quality is DataQuality.DEGRADED
        assert out.components.ticker.quality is ComponentQuality.OK
        assert out.has_open_gap is True

    def test_has_open_gap_distinguishes_the_gap_reason_from_an_absent_component(self) -> None:
        """Both scenarios read ``degraded``; ``has_open_gap`` is what tells a
        client which reason applies — the gap flag is never inferred from
        ``components`` alone (dialogue-M1.md rodada 4: "preservar ... motivos").
        """
        gap_only = _out(ticker_ts=FRESH, book_ts=FRESH, mark_ts=FRESH, has_gap=True)
        absent_only = _out(ticker_ts=FRESH, book_ts=None, mark_ts=FRESH, has_gap=False)
        assert gap_only.data_quality is absent_only.data_quality is DataQuality.DEGRADED
        assert gap_only.has_open_gap is True
        assert absent_only.has_open_gap is False

    def test_future_mark_ts_beyond_clock_skew_tolerance_is_stale_not_ok(self) -> None:
        """(F3) A worker with clock skew writing ``mark_ts`` an hour in the
        future must not read ``ok`` with a negative ``age_ms`` -- the
        component reads ``stale``, ``age_ms`` is clamped at 0 (never
        negative), and the aggregate is not ``ok``.
        """
        far_future_mark = NOW + timedelta(hours=1)
        out = _out(ticker_ts=FRESH, book_ts=FRESH, mark_ts=far_future_mark)
        assert out.components.mark.quality is ComponentQuality.STALE
        assert out.components.mark.age_ms == 0
        assert out.data_quality is not DataQuality.OK

    def test_mildly_future_ts_within_clock_skew_tolerance_still_reads_ok(self) -> None:
        """Ordinary clock jitter (well under ``CLOCK_SKEW_TOLERANCE_S``) must
        not flip a component stale -- only skew past the tolerance does.
        """
        slightly_future_mark = NOW + timedelta(seconds=1)
        out = _out(ticker_ts=FRESH, book_ts=FRESH, mark_ts=slightly_future_mark)
        assert out.components.mark.quality is ComponentQuality.OK
        assert out.components.mark.age_ms == 0
        assert out.data_quality is DataQuality.OK

    def test_book_present_but_aged_reads_stale_not_absent(self) -> None:
        """ "book parado, resto ativo" as a *present but aged* timestamp, not
        merely an absent key -- exercising the STALE branch through ``book``,
        which otherwise only ``mark`` reaches in this suite.
        """
        stale_book = NOW - timedelta(seconds=STALE_AFTER_S + 20)
        out = _out(ticker_ts=FRESH, book_ts=stale_book, mark_ts=FRESH)
        assert out.components.book.quality is ComponentQuality.STALE
        assert out.components.book.ts == stale_book
        assert out.data_quality is DataQuality.STALE

    def test_time_advancing_without_new_publications_flips_ok_to_stale(self) -> None:
        ticker = {"last": "1", "ts": (NOW - timedelta(seconds=1)).isoformat()}
        deriv = {"mark_price": "1", "mark_ts": (NOW - timedelta(seconds=1)).isoformat()}
        hot = HotState(ticker=ticker, deriv=deriv, book_ts=NOW - timedelta(seconds=1))
        fresh = build_market_out(_row(), hot, has_gap=False, now=NOW, stale_after_s=STALE_AFTER_S)
        later = build_market_out(
            _row(),
            hot,
            has_gap=False,
            now=NOW + timedelta(seconds=STALE_AFTER_S + 1),
            stale_after_s=STALE_AFTER_S,
        )
        assert fresh.data_quality is DataQuality.OK
        assert later.data_quality is DataQuality.STALE

    def test_funding_kind_and_age_are_reported_without_a_quality_field(self) -> None:
        hot = HotState(
            ticker={"last": "1", "ts": FRESH.isoformat()},
            deriv={
                "mark_price": "1",
                "mark_ts": FRESH.isoformat(),
                "funding_rate": "0.0001",
                "funding_kind": "estimated",
                "funding_ts": FRESH.isoformat(),
            },
            book_ts=FRESH,
        )
        out = build_market_out(_row(), hot, has_gap=False, now=NOW, stale_after_s=STALE_AFTER_S)
        assert out.funding_kind == "estimated"
        assert out.components.funding.kind == "estimated"
        assert out.components.funding.age_ms == 1000

    def test_realized_funding_kind_passes_through(self) -> None:
        """(G10) The other documented value (dialogue-M1.md rodada 3/4) must
        pass through just as cleanly as ``estimated``.
        """
        hot = HotState(
            ticker={"last": "1", "ts": FRESH.isoformat()},
            deriv={
                "funding_rate": "0.0001",
                "funding_kind": "realized",
                "funding_ts": FRESH.isoformat(),
            },
            book_ts=FRESH,
        )
        out = build_market_out(_row(), hot, has_gap=False, now=NOW, stale_after_s=STALE_AFTER_S)
        assert out.funding_kind == "realized"
        assert out.components.funding.kind == "realized"

    def test_unrecognized_funding_kind_drops_to_none(self) -> None:
        """(G10) A value this API does not document (a worker bug, or some
        future third kind) must not flow through typed as one of the two
        values it isn't -- dropping to ``None`` (unknown) is the honest
        choice, mirroring what an absent ``funding_kind`` already reads as.
        """
        hot = HotState(
            ticker={"last": "1", "ts": FRESH.isoformat()},
            deriv={
                "funding_rate": "0.0001",
                "funding_kind": "bogus",
                "funding_ts": FRESH.isoformat(),
            },
            book_ts=FRESH,
        )
        out = build_market_out(_row(), hot, has_gap=False, now=NOW, stale_after_s=STALE_AFTER_S)
        assert out.funding_kind is None
        assert out.components.funding.kind is None


def test_spread_pct_is_a_fraction_of_the_mid_price() -> None:
    # bid 99, ask 101 -> mid 100, spread 2 -> 0.02 (2%)
    assert spread_pct(Decimal("99"), Decimal("101")) == Decimal("0.02")


def test_spread_pct_is_none_when_either_side_is_missing() -> None:
    assert spread_pct(None, Decimal("101")) is None
    assert spread_pct(Decimal("99"), None) is None


def test_market_out_serializes_decimal_and_enum_fields_as_json_strings() -> None:
    """CLAUDE.md: money/quantities are ``Decimal``, never floats — this is the
    boundary where that would otherwise be silently undone by JSON encoding.
    """
    out = _out(ticker_ts=FRESH, book_ts=FRESH, mark_ts=FRESH)
    payload = out.model_dump(mode="json")
    assert payload["last_price"] == "1"
    assert isinstance(payload["last_price"], str)
    assert payload["data_quality"] == "ok"
    assert payload["components"]["ticker"]["quality"] == "ok"


def test_candle_out_close_time_matches_the_timeframe_duration() -> None:
    """(G8) Asserts a *literal* expected ``close_time`` -- the previous
    version of this test built its own expectation with
    ``timeframe_seconds(Timeframe.M5)``, the exact arithmetic
    ``CandleOut.from_candle`` itself uses, so a bug in that arithmetic could
    never fail it. A hardcoded wall-clock value can.
    """
    from hunter_api.schemas.markets import CandleOut
    from hunter_core.db.models.market_data import Candle

    open_time = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
    candle = Candle(
        market_id=uuid.uuid4(),
        timeframe=Timeframe.M5,
        open_time=open_time,
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("1"),
        close=Decimal("1.5"),
        volume=Decimal("10"),
        is_final=True,
    )
    out = CandleOut.from_candle(candle, Timeframe.M5)
    assert out.close_time == datetime(2026, 9, 5, 12, 5, 0, tzinfo=UTC)


def test_candle_out_from_candle_derives_close_time_from_an_orm_row() -> None:
    from hunter_api.schemas.markets import CandleOut
    from hunter_core.db.models.market_data import Candle

    open_time = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
    row = Candle(
        market_id=uuid.uuid4(),
        timeframe=Timeframe.M1,
        open_time=open_time,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("10"),
        is_final=True,
    )
    out = CandleOut.from_candle(row, Timeframe.M1)
    assert out.close_time == open_time + timedelta(minutes=1)
    assert out.open == Decimal("100")


def test_candle_out_from_candles_maps_every_row() -> None:
    from hunter_api.schemas.markets import CandleOut
    from hunter_core.db.models.market_data import Candle

    def _row(minute: int) -> Candle:
        return Candle(
            market_id=uuid.uuid4(),
            timeframe=Timeframe.M1,
            open_time=datetime(2026, 9, 5, 12, minute, 0, tzinfo=UTC),
            open=Decimal("1"),
            high=Decimal("1"),
            low=Decimal("1"),
            close=Decimal("1"),
            volume=Decimal("1"),
            is_final=True,
        )

    out = CandleOut.from_candles([_row(0), _row(1)], Timeframe.M1)
    assert len(out) == 2
    assert out[1].open_time > out[0].open_time


def test_parse_book_returns_none_when_the_key_is_absent() -> None:
    assert parse_book(None) is None


def test_parse_book_returns_none_for_a_corrupted_non_map_payload() -> None:
    """(F1) A ``mkt:*:book`` value that decodes to something other than a
    msgpack map (here: a bare string) must not raise -- the component reads
    absent, same as the key never having been written.
    """
    garbage = cast(bytes, msgpack.packb("not-a-book"))  # type: ignore[reportUnknownMemberType]
    assert parse_book(garbage) is None


def test_parse_book_returns_none_for_truncated_msgpack_bytes() -> None:
    """(F1) ``\\x81`` is a msgpack map header promising one key/value pair
    with no bytes behind it -- ``unpackb`` raises ``OutOfData`` for this, and
    that exception must not escape ``parse_book``.
    """
    assert parse_book(b"\x81") is None


def test_parse_book_skips_a_malformed_level_but_keeps_the_valid_ones() -> None:
    """(F1) One bad level (wrong shape) must not drop the whole side."""
    payload = {
        "ts": "2026-09-05T12:00:00+00:00",
        "bids": [["50000", "1.5"], ["oops"], "not-even-a-list"],
        "asks": [["50001", "0.5"]],
    }
    raw = cast(bytes, msgpack.packb(payload))  # type: ignore[reportUnknownMemberType]
    book = parse_book(raw)
    assert book is not None
    assert len(book.bids) == 1
    assert book.bids[0].price == Decimal("50000")


def test_parse_book_skips_every_malformed_level_shape_without_fabricating_numbers() -> None:
    """(G1) Indexing a level without checking its shape first turns a bare
    string like ``"12"`` into a *fabricated* ``price=1``/``qty=2`` --
    digits that were never in the data (``"12"[0] == "1"``, ``"12"[1] ==
    "2"``, and both parse as valid Decimals, so the old code never even
    raised). Every malformed shape below must be skipped individually,
    never turned into a ``BookLevelOut`` -- only the one well-formed level
    survives.
    """
    payload = {
        "ts": "2026-09-05T12:00:00+00:00",
        "bids": [
            "12",  # a bare string -- [0]/[1] would fabricate "1"/"2"
            ["50000"],  # 1-element list
            ["50000", "1", "extra"],  # 3-element list
            {"price": "50000", "qty": "1"},  # dict
            ["50000", "1.5"],  # the one good level
        ],
        "asks": [],
    }
    raw = cast(bytes, msgpack.packb(payload))  # type: ignore[reportUnknownMemberType]
    book = parse_book(raw)
    assert book is not None
    assert len(book.bids) == 1
    assert book.bids[0].price == Decimal("50000")
    assert book.bids[0].qty == Decimal("1.5")


def test_parse_book_ts_is_none_for_a_non_string_value_not_a_raise() -> None:
    """(G7) A msgpack map carrying ``ts`` as an int (no separate "datetime"
    type in msgpack) must not raise ``TypeError`` out of
    ``datetime.fromisoformat`` and 500 the response -- the book's own ``ts``
    is read before any per-level guard, so this path matters most.
    """
    payload = {"ts": 123, "bids": [["50000", "1.5"]], "asks": []}
    raw = cast(bytes, msgpack.packb(payload))  # type: ignore[reportUnknownMemberType]
    book = parse_book(raw)
    assert book is not None
    assert book.ts is None
    assert book.bids[0].price == Decimal("50000")


def test_decode_hash_never_raises_on_invalid_utf8_bytes() -> None:
    """(G7) A hash value that is not valid UTF-8 must decode to *something*
    rather than raise ``UnicodeDecodeError`` past this boundary -- it then
    simply fails whatever parser reads it next.
    """
    from hunter_api.services.markets_codec import decode_hash

    decoded = decode_hash({b"last": b"\xff\xfe not valid utf-8"})
    assert isinstance(decoded["last"], str)


def test_parse_book_projects_kind_snapshot_and_depth_20() -> None:
    """M1.md/dialogue rodada 4: the API's book projection is a fixed
    ``kind="snapshot"``/``depth=20``, regardless of what (if anything) the
    wire payload itself carries under those names.
    """
    payload = {
        "ts": "2026-09-05T12:00:00+00:00",
        "bids": [["50000", "1.5"], ["49999", "2"]],
        "asks": [["50001", "0.5"]],
    }
    raw = cast(bytes, msgpack.packb(payload))  # type: ignore[reportUnknownMemberType]
    book = parse_book(raw)
    assert book is not None
    assert book.kind == "snapshot"
    assert book.depth == 20
    assert book.bids[0].price == Decimal("50000")
    assert book.bids[0].qty == Decimal("1.5")
    assert book.asks[0].price == Decimal("50001")


def test_parse_trades_preserves_the_already_newest_first_lpush_order() -> None:
    """The worker ``LPUSH``es each new trade (index 0 = newest), so
    ``LRANGE 0 49`` already comes back newest-first; the API must not
    reverse it a second time.
    """
    newest_payload = {
        "ts": "2026-09-05T12:00:00+00:00",
        "price": "2",
        "qty": "1",
        "side": "sell",
        "trade_id": "b",
    }
    oldest_payload = {
        "ts": "2026-09-05T11:59:00+00:00",
        "price": "1",
        "qty": "1",
        "side": "buy",
        "trade_id": "a",
    }
    newest = cast(bytes, msgpack.packb(newest_payload))  # type: ignore[reportUnknownMemberType]
    oldest = cast(bytes, msgpack.packb(oldest_payload))  # type: ignore[reportUnknownMemberType]
    trades = parse_trades([newest, oldest])
    assert [t.trade_id for t in trades] == ["b", "a"]
    assert trades[0].side.value == "sell"


def test_parse_trades_drops_an_entry_with_an_unparseable_timestamp() -> None:
    """A trade this API cannot date is dropped, never stamped with the read
    time — CLAUDE.md: no invented data.
    """
    bad_payload = {"ts": "not-a-date", "price": "1", "qty": "1", "side": "buy", "trade_id": "x"}
    bad = cast(bytes, msgpack.packb(bad_payload))  # type: ignore[reportUnknownMemberType]
    assert parse_trades([bad]) == []


def test_parse_trades_empty_list_is_empty() -> None:
    assert parse_trades([]) == []


def test_parse_trades_drops_an_entry_missing_a_required_field_but_keeps_the_rest() -> None:
    """(F1) A trade entry with a valid ``ts`` but no ``price`` must not raise
    and must not take the other, valid trades down with it.
    """
    good_payload = {
        "ts": "2026-09-05T12:00:00+00:00",
        "price": "1",
        "qty": "1",
        "side": "buy",
        "trade_id": "good",
    }
    missing_price_payload = {
        "ts": "2026-09-05T11:59:00+00:00",
        "qty": "1",
        "side": "buy",
        "trade_id": "bad",
    }
    good = cast(bytes, msgpack.packb(good_payload))  # type: ignore[reportUnknownMemberType]
    bad = cast(bytes, msgpack.packb(missing_price_payload))  # type: ignore[reportUnknownMemberType]
    trades = parse_trades([good, bad])
    assert [t.trade_id for t in trades] == ["good"]


def test_parse_trades_drops_an_entry_that_is_not_a_decodable_map() -> None:
    """(F1) A corrupted trade entry (not a msgpack map at all) is skipped,
    same as one missing a field -- never a raise for the whole list.
    """
    garbage = cast(bytes, msgpack.packb([1, 2, 3]))  # type: ignore[reportUnknownMemberType]
    assert parse_trades([garbage]) == []


async def test_pipeline_hot_state_degrades_to_absent_when_redis_is_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """(F2) Redis down -> every market in the batch degrades to absent hot
    state rather than a 500; only the error's type is logged, never a key.

    Uses pytest's stdlib-``logging``-backed ``caplog`` rather than
    ``structlog.testing.capture_logs()`` -- once any earlier test in this
    session has caused ``configure_logging`` to run (any integration test
    that builds the app does), structlog's ``cache_logger_on_first_use``
    freezes this module's bound logger onto the real processor chain, and
    ``capture_logs()``'s later reconfiguration no longer reaches it.
    """
    fake_redis = _RaisingRedis(redis.exceptions.ConnectionError("connection refused"))
    with caplog.at_level(logging.WARNING, logger="hunter_api.services.markets"):
        result = await _pipeline_hot_state(fake_redis, [_row()])  # pyright: ignore[reportArgumentType]
    assert result == {}
    assert "ConnectionError" in caplog.text
    assert "mkt:" not in caplog.text


async def test_pipeline_hot_state_wrongtype_error_never_logs_the_offending_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """(F2) redis-py appends the failing command *and its key* to a
    WRONGTYPE ``ResponseError`` message -- that must never reach a log line.
    """
    exc = redis.exceptions.ResponseError(
        "WRONGTYPE Operation against a key holding the wrong kind of value: "
        "mkt:binance:BTCUSDT:ticker"
    )
    fake_redis = _RaisingRedis(exc)
    with caplog.at_level(logging.WARNING, logger="hunter_api.services.markets"):
        result = await _pipeline_hot_state(fake_redis, [_row()])  # pyright: ignore[reportArgumentType]
    assert result == {}
    assert "mkt:binance:BTCUSDT:ticker" not in caplog.text
    assert "ticker" not in caplog.text
    assert "ResponseError" in caplog.text


async def test_pipeline_hot_state_isolates_a_single_market_command_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """(G3) A single market's ticker command failing (verified against a real
    Redis server: a WRONGTYPE comes back as a ``ResponseError`` *in place* in
    ``execute(raise_on_error=False)``'s results, not as a whole-pipeline
    raise) must not erase the hot state of every other market in the same
    request -- only the market whose command actually failed degrades.
    """
    good_ticker_raw = {b"last": b"1", b"ts": FRESH.isoformat().encode()}
    exc = redis.exceptions.ResponseError(
        "WRONGTYPE Operation against a key holding the wrong kind of value"
    )
    # Two markets, one command each (ticker/deriv/book) in request order:
    # market 0's ticker command failed; everything else succeeded.
    results: list[object] = [
        exc,
        {},
        None,  # market 0 (AAA): ticker WRONGTYPE, deriv/book fine
        good_ticker_raw,
        {},
        None,  # market 1 (BBB): every command fine
    ]
    fake_redis = _PartialFailureRedis(results)
    rows = [_row(symbol="AAA"), _row(symbol="BBB")]
    with caplog.at_level(logging.WARNING, logger="hunter_api.services.markets"):
        out = await _pipeline_hot_state(fake_redis, rows)  # pyright: ignore[reportArgumentType]
    assert out["binance:AAA"].ticker == {}
    assert out["binance:BBB"].ticker["last"] == "1"
    assert "ResponseError" in caplog.text
    assert "AAA" not in caplog.text
    assert "BBB" not in caplog.text
