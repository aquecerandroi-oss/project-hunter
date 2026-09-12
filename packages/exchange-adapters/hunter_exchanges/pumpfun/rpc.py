"""Read-only finalized Solana account snapshots; endpoint injection never loads dotenv.

The caller supplies the mint's bonding-curve address; PDA derivation/verification
and durable reconciliation belong to the future collector. No transaction method
is exposed. HTTP/RPC errors never include the injected URL (it may carry a key).
"""

from __future__ import annotations

import os
from typing import Any, cast

import httpx

from hunter_exchanges.base import ExchangeError, ExchangeUnavailable, MalformedMessage, RateLimited
from hunter_exchanges.pumpfun.decode import decode_bonding_curve_account
from hunter_exchanges.pumpfun.models import NormalizedCurveState
from hunter_exchanges.pumpfun.normalize import curve_state_from_rpc_account
from hunter_exchanges.rate_limit import TokenBucketRateLimiter

PUBLIC_RPC_URL = "https://api.mainnet-beta.solana.com"


class SolanaRpcClient:
    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        method_limiter: TokenBucketRateLimiter | None = None,
    ) -> None:
        self._url = rpc_url or os.environ.get("SOLANA_RPC_URL") or PUBLIC_RPC_URL
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=10)
        self._limiter = rate_limiter or TokenBucketRateLimiter(
            "solana_rpc", capacity=10, refill_period_s=1
        )
        # Public RPC also limits each method to 40/10s. Pace conservatively
        # (no 40-request burst followed by a second burst inside that window).
        self._method_limiter = method_limiter
        if self._method_limiter is None and self._url.rstrip("/") == PUBLIC_RPC_URL:
            self._method_limiter = TokenBucketRateLimiter(
                "solana_rpc_method", capacity=1, refill_period_s=0.26
            )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_curve_state(self, mint: str, bonding_curve: str) -> NormalizedCurveState:
        await self._limiter.acquire("requests", 1)
        if self._method_limiter is not None:
            await self._method_limiter.acquire("getAccountInfo", 1)
        try:
            response = await self._client.post(
                self._url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getAccountInfo",
                    "params": [bonding_curve, {"encoding": "base64", "commitment": "finalized"}],
                },
            )
        except httpx.TransportError:
            raise ExchangeUnavailable("Solana RPC transport failure", exchange="pumpfun") from None
        if response.status_code == 429:
            try:
                delay = max(1.0, float(response.headers.get("Retry-After", "10")))
            except ValueError:
                delay = 10.0
            await self._limiter.cooldown("requests", retry_after_s=delay)
            raise RateLimited("Solana RPC rate limited", exchange="pumpfun", retry_after_s=delay)
        if response.is_error:
            raise ExchangeUnavailable(f"Solana RPC HTTP {response.status_code}", exchange="pumpfun")
        try:
            payload: Any = response.json()
            if not isinstance(payload, dict) or "error" in payload:
                raise ExchangeError("Solana RPC returned an error", exchange="pumpfun")
            result: Any = cast(dict[str, Any], payload)["result"]
            account = result["value"]
            if account is None:
                raise ExchangeError(
                    "bonding curve account not found", exchange="pumpfun", retryable=False
                )
            data = account["data"]
            if account.get("executable") is not False or data[1] != "base64":
                raise ValueError("invalid account encoding/type")
            decoded = decode_bonding_curve_account(data[0], owner=account["owner"])
            slot = result["context"]["slot"]
            if type(slot) is not int or slot < 0:
                raise ValueError("invalid slot")
        except (KeyError, IndexError, TypeError, ValueError):
            raise MalformedMessage("invalid Solana account response", exchange="pumpfun") from None
        state = curve_state_from_rpc_account(mint, decoded)
        return state.model_copy(update={"slot": slot, "commitment": "finalized"})
