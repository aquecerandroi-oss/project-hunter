"""hunter_exchanges.binance.normalize: REST payload -> Normalized* models.

Every test loads a small fixture recorded from the real public API (see
``testing/fixtures/`` and the task report for provenance) so the parsing
logic is checked against Binance's actual wire format, not a hand-guessed
shape.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_core.domain.enums import MarketStatus, MarketType, Timeframe
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.binance import normalize

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).parents[1] / ".." / "hunter_exchanges" / "testing" / "fixtures"
).resolve()


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_exchange_info_keeps_only_usdt_trading_perpetuals() -> None:
    raw = _load("exchange_info.json")

    markets = normalize.parse_exchange_info(raw)

    symbols = {m.symbol for m in markets}
    assert symbols == {"BTCUSDT", "ETHUSDT", "BCHUSDT", "XRPUSDT", "LTCUSDT"}
    assert all(m.market_type is MarketType.PERPETUAL for m in markets)
    assert all(m.quote == "USDT" for m in markets)
    assert all(m.status is MarketStatus.ACTIVE for m in markets)


def test_parse_exchange_info_filters_settling_symbol() -> None:
    """OMGUSDT in the fixture is a real, currently SETTLING perpetual — it
    must never reach a NormalizedMarket (status != TRADING)."""
    raw = _load("exchange_info.json")

    markets = normalize.parse_exchange_info(raw)

    assert "OMGUSDT" not in {m.symbol for m in markets}


def test_parse_exchange_info_filters_non_usdt_quote() -> None:
    """ETHBTC in the fixture is a real BTC-quoted perpetual."""
    raw = _load("exchange_info.json")

    markets = normalize.parse_exchange_info(raw)

    assert "ETHBTC" not in {m.symbol for m in markets}


def test_parse_exchange_info_filters_quarterly_future() -> None:
    """BTCUSDT_260925 in the fixture is a real quarterly delivery contract."""
    raw = _load("exchange_info.json")

    markets = normalize.parse_exchange_info(raw)

    assert "BTCUSDT_260925" not in {m.symbol for m in markets}


def test_parse_market_reads_tick_step_and_min_notional() -> None:
    raw = _load("exchange_info.json")
    btc = next(s for s in raw["symbols"] if s["symbol"] == "BTCUSDT")

    market = normalize.parse_market(btc)

    assert market.tick_size == Decimal("0.10")
    assert market.step_size == Decimal("0.001")
    assert market.min_notional == Decimal("50")
    assert market.base == "BTC"
    assert market.quote == "USDT"


def test_parse_klines_produces_aligned_final_candles() -> None:
    raw = _load("klines.json")
    now = datetime(2030, 1, 1, tzinfo=UTC)  # far in the future: every fixture row is "final"

    candles = normalize.parse_klines(raw, symbol="BTCUSDT", now=now)

    assert len(candles) == len(raw)
    first = candles[0]
    assert first.timeframe is Timeframe.M1
    assert first.is_final is True
    assert first.open == Decimal("79488.60")
    assert first.close == Decimal("79488.50")
    assert first.volume == Decimal("6.043")


def test_parse_kline_marks_the_still_forming_candle_as_not_final() -> None:
    raw = _load("klines.json")
    last_row = raw[-1]
    close_time = datetime.fromtimestamp(last_row[6] / 1000, tz=UTC)
    now = close_time  # "now" is exactly the close time boundary: not yet closed

    candle = normalize.parse_kline(last_row, symbol="BTCUSDT", now=now)

    assert candle.is_final is False


def test_duplicate_candle_parses_identically_both_times() -> None:
    """Parsing the same raw kline row twice must be a pure, side-effect-free
    operation: no error, and the two results are field-for-field identical
    (the market-worker is responsible for de-duplication on write)."""
    raw = _load("klines.json")
    now = datetime(2030, 1, 1, tzinfo=UTC)

    first = normalize.parse_kline(raw[0], symbol="BTCUSDT", now=now)
    second = normalize.parse_kline(raw[0], symbol="BTCUSDT", now=now)

    assert first.model_dump(exclude={"received_at"}) == second.model_dump(exclude={"received_at"})


def test_parse_kline_rejects_a_short_row() -> None:
    with pytest.raises(MalformedMessage):
        normalize.parse_kline([1, "1", "1", "1", "1"], symbol="BTCUSDT", now=datetime.now(UTC))


def test_parse_ticker_24h() -> None:
    raw = _load("ticker_24hr.json")

    ticker = normalize.parse_ticker_24h(raw)

    assert ticker.symbol == "BTCUSDT"
    assert ticker.last == Decimal("79497.30")
    assert ticker.bid is None
    assert ticker.ask is None
    assert ticker.volume_24h == Decimal("169789.646")


def test_parse_order_book_from_rest_depth() -> None:
    raw = _load("depth.json")

    book = normalize.parse_order_book(raw, symbol="BTCUSDT")

    assert book.is_snapshot is True
    assert book.sequence == 11479668428160
    assert book.bids[0].price == Decimal("79497.20")
    assert book.asks[0].price == Decimal("79497.30")
    assert book.best_bid == Decimal("79497.20")
    assert book.best_ask == Decimal("79497.30")


def test_parse_funding_builds_the_estimate_from_premium_index_only() -> None:
    """F1: ``fetch_funding`` is the *estimated* rate — ``lastFundingRate`` off
    ``premiumIndex``, never the (possibly stale, already-settled) history
    row. ``parse_funding`` no longer takes a ``funding_history`` argument."""
    premium = _load("premium_index.json")

    funding = normalize.parse_funding(premium, symbol="BTCUSDT")

    assert funding.funding_rate == Decimal(premium["lastFundingRate"])
    assert funding.mark_price == Decimal(premium["markPrice"])
    assert funding.index_price == Decimal(premium["indexPrice"])
    assert funding.next_funding_time is not None
    assert funding.funding_kind == "estimated"


def test_parse_funding_kind_is_always_explicitly_estimated() -> None:
    premium = _load("premium_index.json")

    funding = normalize.parse_funding(premium, symbol="BTCUSDT")

    # Explicit, not just "happens to equal the model default" (F1).
    assert funding.funding_kind == "estimated"


def test_parse_funding_keeps_extra_premium_index_fields_in_metadata() -> None:
    premium = _load("premium_index.json")

    funding = normalize.parse_funding(premium, symbol="BTCUSDT")

    assert funding.metadata["estimatedSettlePrice"] == premium["estimatedSettlePrice"]
    assert funding.metadata["interestRate"] == premium["interestRate"]


def test_parse_realized_funding_reads_the_settlement_time_and_rate() -> None:
    raw = _load("funding_rate_history.json")

    rows = [normalize.parse_realized_funding(row) for row in raw]

    assert len(rows) == len(raw)
    assert all(r.funding_kind == "realized" for r in rows)
    assert rows[0].ts == datetime.fromtimestamp(raw[0]["fundingTime"] / 1000, tz=UTC)
    assert rows[0].funding_rate == Decimal(raw[0]["fundingRate"])
    assert rows[0].mark_price == Decimal(raw[0]["markPrice"])


def test_parse_realized_funding_two_rows_keep_their_own_settlement_time() -> None:
    """Astra review, T1.2 resume finding 4: repeated fetches must not make
    the same settlement look newly timestamped — each row's own
    ``fundingTime`` survives untouched, never overwritten by a shared
    request-time clock."""
    raw = _load("funding_rate_history.json")

    rows = [normalize.parse_realized_funding(row) for row in raw]

    assert len({r.ts for r in rows}) == len(rows)  # every settlement keeps a distinct ts


def test_parse_realized_funding_rejects_missing_mark_price() -> None:
    raw = _load("funding_rate_history.json")[0].copy()
    del raw["markPrice"]

    with pytest.raises(MalformedMessage):
        normalize.parse_realized_funding(raw)


def test_parse_realized_funding_rejects_missing_funding_time() -> None:
    raw = _load("funding_rate_history.json")[0].copy()
    del raw["fundingTime"]

    with pytest.raises(MalformedMessage):
        normalize.parse_realized_funding(raw)


def test_parse_open_interest() -> None:
    raw = _load("open_interest.json")

    oi = normalize.parse_open_interest(raw, symbol="BTCUSDT")

    assert oi.open_interest == Decimal("107603.291")
    assert oi.open_interest_value is None


def test_parse_server_time() -> None:
    raw = _load("server_time.json")

    server_time = normalize.parse_server_time(raw)

    assert server_time == datetime.fromtimestamp(raw["serverTime"] / 1000, tz=UTC)


def test_parse_server_time_rejects_a_non_object_payload() -> None:
    with pytest.raises(MalformedMessage):
        normalize.parse_server_time([1, 2, 3])


def test_parse_ticker_24h_rejects_missing_field() -> None:
    raw = _load("ticker_24hr.json")
    del raw["lastPrice"]

    with pytest.raises(MalformedMessage):
        normalize.parse_ticker_24h(raw)


def test_to_decimal_rejects_float_and_bool() -> None:
    with pytest.raises(MalformedMessage):
        normalize.to_decimal(1.5, field="x")
    with pytest.raises(MalformedMessage):
        normalize.to_decimal(True, field="x")


# ---- T1.6b-A: to_decimal skips the redundant str() for the (always) str
# case Binance actually sends over the wire (~5.7% self time at 200 markets,
# t16b-profile.md) — these pin the output as byte-for-byte identical to
# ``Decimal(str(value))`` for every accepted input shape. ----------------


@pytest.mark.parametrize("raw", ["79497.20", "0", "-1.5", "1e10", "0.00000649"])
def test_to_decimal_accepts_a_string_value_unchanged(raw: str) -> None:
    assert normalize.to_decimal(raw, field="x") == Decimal(str(raw))


def test_to_decimal_accepts_an_int_value() -> None:
    assert normalize.to_decimal(5, field="x") == Decimal(str(5))


def test_to_decimal_accepts_a_decimal_value() -> None:
    value = Decimal("1.23")
    assert normalize.to_decimal(value, field="x") == Decimal(str(value))


def test_to_decimal_rejects_an_invalid_decimal_string() -> None:
    with pytest.raises(MalformedMessage):
        normalize.to_decimal("not-a-number", field="x")
