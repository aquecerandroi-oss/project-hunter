"""Jupiter v6 aggregator client (T4.54) — public quote + swap-transaction build.

No API key (Jupiter's ``quote-api.jup.ag`` is public). One request per call,
5 s timeout, **no retries on a 4xx** (a bad request is a bad request, never a
loop): a 4xx is :class:`JupiterQuoteError` with the body's ``error`` field
when present. A 5xx or a transport failure is
:class:`hunter_exchanges.base.ExchangeUnavailable` — the caller's own cadence
(the treasury's kill-switch tick) is the retry, exactly like every other
adapter in this package.

This client only ever returns an **unsigned** transaction
(:class:`JupiterSwapTransaction`); it holds no key and calls ``sendTransaction``
nowhere. Verification, simulation, signing and sending are
``hunter_meme_executor.treasury``'s job, on the executor side of the wall this
package exists to keep (``docs/EXCHANGE_INTEGRATION.md``).
"""

from __future__ import annotations

from typing import Any, cast

import httpx

from hunter_exchanges.base import ExchangeError, ExchangeUnavailable, MalformedMessage
from hunter_exchanges.jupiter.models import JupiterQuote, JupiterSwapTransaction

__all__ = ["JupiterClient", "JupiterQuoteError"]

DEFAULT_BASE_URL = "https://quote-api.jup.ag/v6"
EXCHANGE = "jupiter"


class JupiterQuoteError(ExchangeError):
    """A 4xx from Jupiter — malformed request, no route, unknown mint. Not retried."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message, exchange=EXCHANGE, retryable=False)
        self.status_code = status_code


class JupiterClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        http_client: httpx.Client | None = None,
        timeout_s: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> JupiterClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ quote
    def quote(
        self,
        *,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int,
    ) -> JupiterQuote:
        """``GET /quote`` — ``amount`` is atoms of ``input_mint``, an ``int`` (no
        fractional atom exists on-chain, so this is deliberately not ``Decimal``)."""
        if amount <= 0:
            raise ValueError("amount must be a positive integer of atoms")
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": str(slippage_bps),
        }
        payload = self._get("/quote", params)
        try:
            return JupiterQuote.from_json(payload)
        except (KeyError, ValueError, TypeError) as exc:
            raise MalformedMessage(
                f"Jupiter quote reply missing/invalid field: {exc}", exchange=EXCHANGE
            ) from exc

    # ------------------------------------------------------------------- swap
    def swap(self, *, quote: JupiterQuote, user_public_key: str) -> JupiterSwapTransaction:
        """``POST /swap`` — the unsigned versioned transaction for ``quote``."""
        body = {
            "quoteResponse": quote.raw,
            "userPublicKey": user_public_key,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": "auto",
        }
        payload = self._post("/swap", body)
        try:
            return JupiterSwapTransaction.from_json(payload)
        except (KeyError, ValueError, TypeError) as exc:
            raise MalformedMessage(
                f"Jupiter swap reply missing/invalid field: {exc}", exchange=EXCHANGE
            ) from exc

    # ------------------------------------------------------------------ core
    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._client.get(self._base_url + path, params=params)
        except httpx.TransportError as exc:
            raise ExchangeUnavailable(
                f"Jupiter transport failure during GET {path}", exchange=EXCHANGE
            ) from exc
        return self._parse(response, f"GET {path}")

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(self._base_url + path, json=body)
        except httpx.TransportError as exc:
            raise ExchangeUnavailable(
                f"Jupiter transport failure during POST {path}", exchange=EXCHANGE
            ) from exc
        return self._parse(response, f"POST {path}")

    def _parse(self, response: httpx.Response, label: str) -> dict[str, Any]:
        if response.status_code == 429:
            raise ExchangeUnavailable(f"Jupiter rate limited during {label}", exchange=EXCHANGE)
        if 400 <= response.status_code < 500:
            detail = _error_detail(response)
            raise JupiterQuoteError(
                f"Jupiter {label} refused: HTTP {response.status_code} {detail}".strip(),
                status_code=response.status_code,
            )
        if response.is_error:
            raise ExchangeUnavailable(
                f"Jupiter HTTP {response.status_code} during {label}", exchange=EXCHANGE
            )
        try:
            raw: object = response.json()
        except ValueError as exc:
            raise MalformedMessage(f"Jupiter non-JSON reply to {label}", exchange=EXCHANGE) from exc
        if not isinstance(raw, dict):
            raise MalformedMessage(f"Jupiter {label} reply is not a JSON object", exchange=EXCHANGE)
        return cast("dict[str, Any]", raw)


def _error_detail(response: httpx.Response) -> str:
    try:
        raw: object = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(raw, dict):
        body = cast("dict[str, Any]", raw)
        return str(body.get("error", body))[:200]
    return str(raw)[:200]
