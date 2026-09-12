"""``swap-api /v2/coins/{mint}/trades`` over the live captures: the 30 ``pump``
rows of ``swap_api_trades_5ejA_raw.json`` (T4.8), the two ``raydium_cpmm``
pages of 2026-09-12 (cursor) and the ``pump_amm`` page of a graduated coin."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from hunter_exchanges.base import ExchangeError, MalformedMessage, RateLimited
from hunter_exchanges.pumpfun.rate_shared import HttpRateLimited
from hunter_exchanges.pumpfun.swap_api import (
    HEADER_LIMIT,
    MEASURED_BLOCK_S,
    MEASURED_LIMIT,
    REQUEST_CAPACITY,
    SwapApiClient,
    parse_trade,
    parse_trades_page,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
CURVE_MINT = "5ejAPUMPMINT"


def _raw(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"), parse_float=Decimal)


def test_the_curve_rows_become_exact_lamports_with_the_verified_slot() -> None:
    page = parse_trades_page(CURVE_MINT, _raw("swap_api_trades_5ejA_raw.json"), received_at=NOW)
    assert len(page.trades) == 30 and page.malformed == 0
    assert page.has_more and page.next_cursor == "0004460703800010800000-1789102287000"
    first = page.trades[0]
    assert first.signature.startswith("5sLxc4wPo2Hfx5Xu6eKB")
    assert first.slot == 446373814, "the slot is the first twelve digits (getTransaction evidence)"
    assert first.observed_at == datetime(2026, 9, 12, 7, 34, 28, tzinfo=UTC)
    assert first.side == "sell" and first.is_bonding_curve and first.quote_is_native_sol
    assert first.sol_amount == Decimal("0.724716993") and first.sol_lamports == 724716993
    assert first.token_amount == Decimal("16800146.527261")
    assert first.price == Decimal("0.00000004313754001038190481118595560712876308514")
    assert first.marginal_price is not None and first.marginal_price != first.price
    assert first.received_at == NOW and first.source == "swap_api"
    assert all(t.is_bonding_curve and t.quote_is_native_sol for t in page.trades)
    assert page.trades[0].slot_index_id > page.trades[-1].slot_index_id, "newest first"
    evidence = json.loads((FIXTURES / "rpc_get_transaction_slot_evidence_raw.json").read_text())
    assert evidence["summary"]["rpc_slot"] == first.slot
    assert evidence["summary"]["rpc_blockTime"] == int(first.observed_at.timestamp())


def test_another_amm_is_named_not_mistaken_for_the_curve_and_its_quote_is_not_sol() -> None:
    page = parse_trades_page("RAYMINT", _raw("swap_api_trades_page1_raw.json"), received_at=NOW)
    assert len(page.trades) == 100 and page.malformed == 0
    assert all(t.program == "raydium_cpmm" and not t.is_bonding_curve for t in page.trades)
    assert all(not t.quote_is_native_sol and t.sol_lamports is None for t in page.trades)
    graduated = parse_trades_page(
        "GRADMINT", _raw("swap_api_trades_graduated_pump_raw.json"), received_at=NOW
    )
    assert all(t.program == "pump_amm" and not t.is_bonding_curve for t in graduated.trades)


def test_the_cursor_walks_to_the_older_page_without_overlap() -> None:
    page1 = parse_trades_page("RAYMINT", _raw("swap_api_trades_page1_raw.json"), received_at=NOW)
    page2 = parse_trades_page("RAYMINT", _raw("swap_api_trades_page2_raw.json"), received_at=NOW)
    assert page1.next_cursor is not None and page1.next_cursor.startswith(
        page1.trades[-1].slot_index_id
    )
    assert page2.trades[0].observed_at <= page1.trades[-1].observed_at
    assert not {t.slot_index_id for t in page1.trades} & {t.slot_index_id for t in page2.trades}
    assert not {t.signature for t in page1.trades} & {t.signature for t in page2.trades}


def test_a_float_amount_or_a_bad_row_is_counted_and_the_page_survives() -> None:
    body = _raw("swap_api_trades_5ejA_raw.json")
    body["trades"][0]["amountSol"] = 0.5
    body["trades"][1]["type"] = "swap"
    body["trades"].append("garbage")
    body["trades"][2]["slotIndexId"] = "abc"
    page = parse_trades_page(CURVE_MINT, body, received_at=NOW)
    assert page.malformed == 4 and len(page.trades) == 27
    with pytest.raises(MalformedMessage):
        parse_trades_page(CURVE_MINT, {"pagination": {}}, received_at=NOW)
    with pytest.raises(MalformedMessage):
        parse_trade(CURVE_MINT, {"slotIndexId": "1" * 12}, received_at=NOW)


def test_a_non_lamport_exact_sol_amount_is_not_native_sol() -> None:
    row = dict(_raw("swap_api_trades_5ejA_raw.json")["trades"][0])
    row["amountSol"] = row["quoteAmount"] = "0.7247169931"  # ten decimals: not lamports
    trade = parse_trade(CURVE_MINT, row, received_at=NOW)
    assert not trade.quote_is_native_sol and trade.sol_lamports is None


async def test_the_client_sends_limit_and_cursor_and_spends_the_declared_budget() -> None:
    body = (FIXTURES / "swap_api_trades_page1_raw.json").read_bytes()
    seen: list[httpx.URL] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(respond)
    ) as http:
        client = SwapApiClient(http_client=http)
        page = await client.get_trades("RAYMINT", limit=100)
        older = await client.get_trades("RAYMINT", cursor=page.next_cursor)
    assert seen[0].path == "/v2/coins/RAYMINT/trades" and seen[0].params["limit"] == "100"
    assert seen[1].params["cursor"] == page.next_cursor and older.has_more
    assert REQUEST_CAPACITY == 16 and MEASURED_LIMIT == 20 and HEADER_LIMIT == 1000
    with pytest.raises(ValueError):
        SwapApiClient(http_client=http, capacity=MEASURED_LIMIT + 1)
    with pytest.raises(ValueError):
        await client.get_trades("RAYMINT", limit=101)


@pytest.mark.parametrize("status", [404, 429, 503])
async def test_errors_are_named_and_a_429_is_never_retried_silently(status: int) -> None:
    calls = 0

    def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, headers={"Retry-After": "7"})

    async with httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(respond)
    ) as http:
        client = SwapApiClient(http_client=http, max_retries=2, sleep=_no_sleep)
        with pytest.raises(RateLimited if status == 429 else ExchangeError) as error:
            await client.get_trades("MINT")
    if status == 429:
        assert calls == 1 and error.value.retry_after_s == 7  # type: ignore[attr-defined]
        assert isinstance(error.value, HttpRateLimited)
        assert error.value.status_code == 429 and error.value.headers == {"retry-after": "7"}
        assert not error.value.edge, "no server header: not the edge's rule"
    elif status == 404:
        assert calls == 1
    else:
        assert calls == 2, "a 5xx retries a bounded number of times"


async def _no_sleep(_: float) -> None:
    return None


def test_the_measured_limit_is_cloudflares_rule_not_the_backends_window() -> None:
    """T4.2f, four live probes (12/09 13:36–13:48 UTC): every first 429 is
    Cloudflare error 1015 with ``retry-after: 60`` and no ``x-ratelimit-*``; the
    backend's header said 1000 and ~900 remaining on the request before. The
    rule counts ~20 requests per 60 s per IP — 19–27 successes fit before the
    cut, at 0,85 req/s as at 16 req/s and with 40 distinct mints alike."""
    probes = _raw("t42f_swap_api_ratelimit_probes.json")
    phases = {p["name"]: p for p in probes["phases"]}
    assert set(phases) >= {
        "A_burst",
        "B_paced_4ps",
        "C_paced_8ps",
        "D_paced_0.7ps",
        "F_distinct_mints",
    }
    for name, phase in phases.items():
        first = phase["first_429"]
        assert first is not None and first["status"] == 429, name
        refused = HttpRateLimited(
            "swap-api 429",
            exchange="pumpfun_swap_api",
            retry_after_s=60,
            status_code=429,
            headers=first["headers"],
        )
        assert refused.edge and refused.headers["retry-after"] == str(int(MEASURED_BLOCK_S)), name
        assert "x-ratelimit-limit" not in refused.headers, name
        assert "Error 1015" in first["body"], name
        ok_before = sum(1 for e in phase["log"] if e.get("status") == 200)
        assert 19 <= ok_before <= 27, (name, ok_before)
        last_ok = [e for e in phase["log"] if e.get("status") == 200][-1]["headers"]
        assert last_ok["x-ratelimit-limit"] == str(HEADER_LIMIT)
        assert int(last_ok["x-ratelimit-remaining"]) > 800, "the backend's window never binds"
        assert phase["recovery"]["status"] == 200, "60 s later the IP answers again"
    paced = phases["D_paced_0.7ps"]
    assert paced["ok_in_10s_before_429"] <= 8 < MEASURED_LIMIT, "the window is not 10 s"
    assert REQUEST_CAPACITY <= MEASURED_LIMIT - 4, "four requests of margin under the edge's count"
