"""T4.54 — ``JupiterClient`` against recorded/synthetic fixtures, fully offline.

Every case uses ``httpx.MockTransport``; nothing here reaches the network
(the ``live`` marker is for a real hit and is never used in this module).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from hunter_exchanges.base import ExchangeUnavailable, MalformedMessage
from hunter_exchanges.jupiter.client import (
    DEFAULT_JUPITER_BASE_URL,
    JupiterClient,
    JupiterQuoteError,
)
from hunter_exchanges.jupiter.models import WRAPPED_SOL_MINT

FIXTURES = Path(__file__).parent.parent / "fixtures" / "jupiter"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def _load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _client(handler: object) -> JupiterClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return JupiterClient(http_client=httpx.Client(transport=transport, timeout=5.0))


def test_quote_parses_the_recorded_reply() -> None:
    body = _load("quote_usdc_to_sol.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/quote")
        assert request.url.params["inputMint"] == USDC_MINT
        assert request.url.params["outputMint"] == WRAPPED_SOL_MINT
        assert request.url.params["amount"] == "5000000"
        assert request.url.params["slippageBps"] == "50"
        return httpx.Response(200, json=body)

    with _client(handler) as client:
        quote = client.quote(
            input_mint=USDC_MINT, output_mint=WRAPPED_SOL_MINT, amount=5_000_000, slippage_bps=50
        )
    assert quote.in_amount == Decimal("5000000")
    assert quote.out_amount == Decimal("34215678")
    assert quote.price_impact_pct == Decimal("0.0012")
    assert quote.route_labels == ("Whirlpool",)
    assert quote.raw["inAmount"] == "5000000"


def test_quote_rejects_a_non_positive_amount() -> None:
    with _client(lambda _r: httpx.Response(200, json={})) as client:
        with pytest.raises(ValueError, match="positive"):
            client.quote(
                input_mint=USDC_MINT, output_mint=WRAPPED_SOL_MINT, amount=0, slippage_bps=50
            )


def test_a_400_is_a_named_refusal_never_retried() -> None:
    body = _load("quote_no_route_400.json")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json=body)

    with _client(handler) as client:
        with pytest.raises(JupiterQuoteError) as excinfo:
            client.quote(
                input_mint=USDC_MINT, output_mint=WRAPPED_SOL_MINT, amount=1, slippage_bps=50
            )
    assert excinfo.value.status_code == 400
    assert excinfo.value.retryable is False
    assert calls["n"] == 1, "a 4xx is refused once, never retried by this client"


def test_a_429_is_exchange_unavailable() -> None:
    with _client(lambda _r: httpx.Response(429, text="slow down")) as client:
        with pytest.raises(ExchangeUnavailable):
            client.quote(
                input_mint=USDC_MINT, output_mint=WRAPPED_SOL_MINT, amount=1, slippage_bps=50
            )


def test_a_5xx_is_exchange_unavailable() -> None:
    with _client(lambda _r: httpx.Response(503, text="maintenance")) as client:
        with pytest.raises(ExchangeUnavailable):
            client.quote(
                input_mint=USDC_MINT, output_mint=WRAPPED_SOL_MINT, amount=1, slippage_bps=50
            )


def test_non_json_reply_is_malformed_message() -> None:
    with _client(lambda _r: httpx.Response(200, text="<html>not json</html>")) as client:
        with pytest.raises(MalformedMessage):
            client.quote(
                input_mint=USDC_MINT, output_mint=WRAPPED_SOL_MINT, amount=1, slippage_bps=50
            )


def test_quote_missing_a_field_is_malformed_message() -> None:
    with _client(lambda _r: httpx.Response(200, json={"inputMint": USDC_MINT})) as client:
        with pytest.raises(MalformedMessage):
            client.quote(
                input_mint=USDC_MINT, output_mint=WRAPPED_SOL_MINT, amount=1, slippage_bps=50
            )


def test_swap_posts_the_whole_quote_response_back() -> None:
    quote_body = _load("quote_usdc_to_sol.json")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/quote"):
            return httpx.Response(200, json=quote_body)
        assert request.url.path.endswith("/swap")
        payload = json.loads(request.content)
        seen.update(payload)
        return httpx.Response(
            200,
            json={
                "swapTransaction": "AA==",
                "lastValidBlockHeight": 12345,
                "prioritizationFeeLamports": 5000,
            },
        )

    with _client(handler) as client:
        quote = client.quote(
            input_mint=USDC_MINT, output_mint=WRAPPED_SOL_MINT, amount=5_000_000, slippage_bps=50
        )
        assert quote.raw == quote_body
        result = client.swap(
            quote=quote, user_public_key="ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
        )
    assert seen["quoteResponse"] == quote_body
    assert seen["userPublicKey"] == "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
    assert seen["wrapAndUnwrapSol"] is True
    assert seen["dynamicComputeUnitLimit"] is True
    assert seen["prioritizationFeeLamports"] == "auto"
    assert result.swap_transaction_b64 == "AA=="
    assert result.last_valid_block_height == 12345
    assert result.prioritization_fee_lamports == 5000


def test_the_default_base_url_is_the_live_keyless_endpoint() -> None:
    # T4.54b (18/09/2026): quote-api.jup.ag/v6 no longer resolves; the same
    # /quote and /swap live under lite-api.jup.ag/swap/v1 (keyless).
    assert DEFAULT_JUPITER_BASE_URL == "https://lite-api.jup.ag/swap/v1"
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=_load("quote_usdc_to_sol_real.json"))

    with _client(handler) as client:
        client.quote(
            input_mint=USDC_MINT, output_mint=WRAPPED_SOL_MINT, amount=1_000_000, slippage_bps=50
        )
    assert seen[0].startswith("https://lite-api.jup.ag/swap/v1/quote?")


def test_quote_parses_the_real_capture_and_its_price_impact_is_a_fraction() -> None:
    body = _load("quote_usdc_to_sol_real.json")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with _client(handler) as client:
        quote = client.quote(
            input_mint=USDC_MINT, output_mint=WRAPPED_SOL_MINT, amount=1_000_000, slippage_bps=50
        )
    assert quote.in_amount == Decimal(1_000_000)
    assert quote.out_amount == Decimal(9_487_602)
    assert quote.other_amount_threshold == Decimal(9_440_164)
    assert quote.slippage_bps == 50
    assert quote.price_impact_pct == Decimal(0)  # a fraction: "0.0033" would mean 0.33 %
    assert quote.route_labels == ("HumidiFi",)
    assert quote.raw["swapMode"] == "ExactIn"
