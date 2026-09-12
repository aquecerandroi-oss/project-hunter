"""``POST /v1/coins/market-activity/batch`` over the live captures of
12/09/2026 20:24 UTC (T4.2g): the two-coin shape with every metric, the
fifty-coin batch, the validator's ceiling of 50 addresses, a ``null`` window
as a stated zero only where the response filled that window for someone, the
``Date`` header as the windows' end, and a 429 that is never retried."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from hunter_exchanges.base import ExchangeError, MalformedMessage
from hunter_exchanges.pumpfun.market_activity import (
    ACTIVITY_SOURCE,
    MAX_ADDRESSES,
    METRICS,
    WINDOW_SECONDS,
    parse_activity_batch,
    parse_activity_block,
    response_stamp,
)
from hunter_exchanges.pumpfun.rate_shared import HttpRateLimited
from hunter_exchanges.pumpfun.swap_api import SwapApiClient

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
RECEIVED = datetime(2026, 9, 12, 20, 24, 2, 500_000, tzinfo=UTC)
STAMP = datetime(2026, 9, 12, 20, 24, 2, tzinfo=UTC)
WINDOWS = ("1m", "5m", "1h", "6h", "24h")


def _raw(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"), parse_float=Decimal)


def _mints(name: str) -> list[str]:
    return list(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_the_two_coin_capture_carries_every_metric_as_decimal_and_the_empty_windows() -> None:
    raw = _raw("t42g_market_activity_batch_raw.json")
    batch = parse_activity_batch(
        raw,
        mints=_mints("t42g_market_activity_batch_raw.json"),
        windows=WINDOWS,
        observed_at=STAMP,
        received_at=RECEIVED,
    )
    assert batch.asked == 2 and batch.missing == () and batch.malformed == 0
    assert batch.windows_live == {"24h"}, "the coins were seven hours old: only the day traded"
    assert len(batch.readings) == 2
    first = batch.readings[0]
    assert first.mint.startswith("EV4JbtMh") and first.window == "24h"
    assert first.window_s == 86_400 and first.source == ACTIVITY_SOURCE
    assert (first.num_txs, first.buys, first.sells) == (2, 1, 1)
    assert (first.unique_users, first.unique_buyers, first.unique_sellers) == (1, 1, 1)
    assert first.volume_usd == Decimal("99.20229804272005")
    assert first.buy_volume_usd == Decimal("49.60028645179046")
    assert first.sell_volume_usd == Decimal("49.602011590929585")
    assert first.price_change_pct == Decimal("-2.699026967752155")
    assert first.observed_at == STAMP and first.received_at == RECEIVED
    second = batch.readings[1]
    assert (second.buys, second.sells, second.unique_buyers, second.unique_sellers) == (
        20,
        18,
        4,
        3,
    )
    for window in ("1m", "5m", "1h", "6h"):
        assert len(batch.empty[window]) == 2, window
    assert batch.empty["24h"] == ()


def test_the_fifty_coin_capture_shows_null_means_no_trade_in_a_window_someone_filled() -> None:
    """24h filled for 50 of 50, 6h for 7 of 50, the short windows for none: a
    ``null`` under ``6h`` is a coin that did not trade in six hours (its 24h
    block still counts trades), and ``1m``/``5m``/``1h`` are *not* proven
    live by this capture — the parser says which is which."""
    name = "t42g_market_activity_batch_50_raw.json"
    batch = parse_activity_batch(
        _raw(name), mints=_mints(name), windows=WINDOWS, observed_at=STAMP, received_at=RECEIVED
    )
    assert batch.asked == 50 and batch.missing == () and batch.malformed == 0
    assert batch.windows_live == {"24h", "6h"}
    by_window: dict[str, int] = {}
    for reading in batch.readings:
        by_window[reading.window] = by_window.get(reading.window, 0) + 1
    assert by_window == {"24h": 50, "6h": 7}
    assert len(batch.empty["6h"]) == 43 and len(batch.empty["1m"]) == 50
    six = {r.mint: r for r in batch.readings if r.window == "6h"}
    day = {r.mint: r for r in batch.readings if r.window == "24h"}
    for mint, reading in six.items():
        assert reading.num_txs <= day[mint].num_txs, "a shorter window never counts more"
        assert reading.buys + reading.sells == reading.num_txs
    zero_sells = six["4avriyNVMyDNzdatqU5p84q4DsV66cGsCxDUwQLipump"]
    assert zero_sells.sells == 0 and zero_sells.sell_volume_usd == 0
    assert zero_sells.price_change_pct == 0, "an integer zero is a decimal zero"


def test_the_probes_froze_the_validators_ceiling_and_the_windows_it_accepts() -> None:
    probes = _raw("t42g_market_activity_batch_probes.json")
    assert probes["calls"] == 5 and probes["pace_s"] >= 4
    by_name = {entry["name"]: entry for entry in probes["log"]}
    assert by_name["A_shape"]["status"] == 201 and by_name["B_50"]["status"] == 201
    assert set(by_name["A_shape"]["request"]["metrics"]) == set(METRICS)
    assert set(by_name["A_shape"]["request"]["intervals"]) == set(WINDOW_SECONDS)
    for name in ("B_140", "B_100"):
        assert by_name[name]["status"] == 400
        assert "no more than 50 elements" in by_name[name]["body"]["message"]
        assert by_name[name]["request"]["addresses"] > MAX_ADDRESSES
    assert by_name["B_50"]["request"]["addresses"] == MAX_ADDRESSES
    assert "at least 1 elements" in by_name["E_active_boards"]["body"]["message"], (
        "the fifth probe was spent on an empty list: the 1m window stays unproven live"
    )
    for entry in probes["log"]:
        assert entry["headers"]["server"] == "cloudflare"
        assert entry["headers"]["x-ratelimit-limit"] == "1000"
        assert "date" in entry["headers"]
    stamp = response_stamp(by_name["B_50"]["headers"], received_at=RECEIVED)
    assert stamp == datetime(2026, 9, 12, 20, 24, 15, tzinfo=UTC)
    assert response_stamp({}, received_at=RECEIVED) == RECEIVED
    assert response_stamp({"date": "not a date"}, received_at=RECEIVED) == RECEIVED


def test_a_bad_block_is_counted_and_the_batch_survives_and_a_bad_body_does_not() -> None:
    raw = _raw("t42g_market_activity_batch_raw.json")
    mints = list(raw)
    raw[mints[0]]["24h"]["numBuys"] = -1
    raw[mints[1]]["5m"] = "garbage"
    raw[mints[1]]["1h"] = {"numTxs": 1}  # every metric or none
    batch = parse_activity_batch(
        raw, mints=[*mints, "NOTASKED"], windows=WINDOWS, observed_at=STAMP, received_at=RECEIVED
    )
    assert batch.malformed == 3 and len(batch.readings) == 1
    assert batch.missing == ("NOTASKED",) and batch.windows_live == {"24h"}
    with pytest.raises(MalformedMessage):
        parse_activity_batch(
            [], mints=mints, windows=WINDOWS, observed_at=STAMP, received_at=RECEIVED
        )
    block = dict(_raw("t42g_market_activity_batch_raw.json")[mints[0]]["24h"])
    block["buyVolumeUSD"] = 1.5  # a float: a body decoded without parse_float=Decimal
    with pytest.raises(MalformedMessage):
        parse_activity_block(mints[0], "24h", block, observed_at=STAMP, received_at=RECEIVED)
    with pytest.raises(MalformedMessage):
        parse_activity_block(mints[0], "2m", block, observed_at=STAMP, received_at=RECEIVED)


async def test_the_client_posts_the_measured_body_and_refuses_more_than_fifty_first() -> None:
    body = (FIXTURES / "t42g_market_activity_batch_50_raw.json").read_bytes()
    mints = _mints("t42g_market_activity_batch_50_raw.json")
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, content=body, headers={"date": "Sat, 12 Sep 2026 20:24:15 GMT"})

    async with httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(respond)
    ) as http:
        client = SwapApiClient(http_client=http)
        batch = await client.market_activity_batch(mints, windows=("1m", "5m"))
        with pytest.raises(ValueError):
            await client.market_activity_batch([*mints, "ONE_MORE"])
        with pytest.raises(ValueError):
            await client.market_activity_batch(mints[:1], windows=("2m",))
        with pytest.raises(ValueError):
            await client.market_activity_batch([])
    assert len(seen) == 1 and seen[0].method == "POST"
    assert seen[0].url.path == "/v1/coins/market-activity/batch"
    sent = json.loads(seen[0].content)
    assert sent == {"addresses": mints, "intervals": ["1m", "5m"], "metrics": list(METRICS)}
    assert batch.asked == 50 and batch.windows_live == frozenset(), (
        "asked only for 1m and 5m: the capture fills neither, and no zero is claimed"
    )
    assert len(batch.empty["1m"]) == 50 and batch.readings == ()
    assert batch.observed_at == datetime(2026, 9, 12, 20, 24, 15, tzinfo=UTC)
    assert batch.received_at > batch.observed_at


@pytest.mark.parametrize("status", [400, 429, 503])
async def test_a_refusal_is_named_and_a_429_is_never_retried_silently(status: int) -> None:
    calls = 0

    def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if status == 400:
            return httpx.Response(
                400,
                json={
                    "statusCode": 400,
                    "message": '{"message":["addresses must contain no more than 50 elements"]}',
                },
            )
        return httpx.Response(status, headers={"Retry-After": "60", "server": "cloudflare"})

    async with httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(respond)
    ) as http:
        client = SwapApiClient(http_client=http, max_retries=2, sleep=_no_sleep)
        with pytest.raises(ExchangeError) as error:
            await client.market_activity_batch(["MINT"])
    if status == 429:
        assert calls == 1 and isinstance(error.value, HttpRateLimited)
        assert error.value.edge and error.value.retry_after_s == 60
    elif status == 400:
        assert calls == 1 and not error.value.retryable
        assert "no more than 50" in str(error.value), "the validator's words travel"
    else:
        assert calls == 2


async def _no_sleep(_: float) -> None:
    return None
