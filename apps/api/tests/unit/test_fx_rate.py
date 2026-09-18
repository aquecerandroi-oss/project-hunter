"""``services/fx_rate.py`` (T4.57) — the USD/BRL cache the "Carteira real"
panel prices totals with: cached for an hour, falls back to the last known
quote on a fetch failure, and never invents a rate before the first success.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from hunter_api.services.fx_rate import UsdBrlRateCache

pytestmark = pytest.mark.unit


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


def _ok_handler(rate: str) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"amount": 1.0, "base": "USD", "rates": {"BRL": rate}})

    return httpx.MockTransport(handle)


def _failing_handler() -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    return httpx.MockTransport(handle)


async def test_a_first_successful_fetch_is_believed() -> None:
    cache = UsdBrlRateCache()
    quote, reason = await cache.get(client=_client(_ok_handler("5.42")))
    assert reason is None
    assert quote is not None
    assert quote.rate == Decimal("5.42")
    assert quote.source == "frankfurter.dev"


async def test_a_second_read_inside_the_ttl_never_refetches() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"rates": {"BRL": "5.00"}})

    cache = UsdBrlRateCache(ttl_s=3600.0)
    client = _client(httpx.MockTransport(handle))
    first, _ = await cache.get(client=client)
    second, _ = await cache.get(client=client)
    assert calls == 1
    assert first == second


async def test_a_fetch_failure_before_any_success_names_the_reason_instead_of_a_rate() -> None:
    cache = UsdBrlRateCache()
    quote, reason = await cache.get(client=_client(_failing_handler()))
    assert quote is None
    assert reason == "no_fx_quote"


async def test_a_fetch_failure_after_a_success_falls_back_to_the_last_known_quote() -> None:
    cache = UsdBrlRateCache(ttl_s=0.0)  # every read past the first refetches
    good = _client(_ok_handler("5.10"))
    first, _ = await cache.get(client=good)
    assert first is not None

    bad = _client(_failing_handler())
    second, reason = await cache.get(client=bad)
    assert reason == "stale"
    assert second == first


async def test_a_document_without_brl_is_treated_as_a_failure() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rates": {"EUR": "0.9"}})

    cache = UsdBrlRateCache()
    quote, reason = await cache.get(client=_client(httpx.MockTransport(handle)))
    assert quote is None
    assert reason == "no_fx_quote"
