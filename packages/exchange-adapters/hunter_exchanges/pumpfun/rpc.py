"""Read-only finalized Solana account snapshots; endpoint injection never loads dotenv.

The caller supplies the mint's bonding-curve address for a curve read; the Mayhem
flow read derives its four accounts from the mint by the IDL's seeds
(``mayhem_state.py``) and batches 25 mints per ``getMultipleAccounts`` (T4.2e).
No transaction method is exposed. HTTP/RPC errors never include the injected
URL (it may carry a key).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import httpx

from hunter_core.domain.types import utcnow
from hunter_exchanges.base import ExchangeError, ExchangeUnavailable, MalformedMessage, RateLimited
from hunter_exchanges.pumpfun.decode import decode_bonding_curve_account
from hunter_exchanges.pumpfun.mayhem_state import (
    MINTS_PER_BATCH,
    MayhemRefused,
    NormalizedMayhemFlow,
    decode_mayhem_state,
    decode_mint_supply,
    decode_token_account_amount,
    mayhem_accounts_for,
    mayhem_flow_from_accounts,
)
from hunter_exchanges.pumpfun.models import NormalizedCurveState
from hunter_exchanges.pumpfun.normalize import curve_state_from_rpc_account
from hunter_exchanges.rate_limit import TokenBucketRateLimiter

PUBLIC_RPC_URL = "https://api.mainnet-beta.solana.com"
_FINALIZED = {"encoding": "base64", "commitment": "finalized"}


@dataclass(frozen=True, slots=True)
class MayhemFlowBatch:
    """One ``get_mayhem_flows`` call: the flows, and every mint refused by name.

    Refusals: ``curve_not_found`` | ``not_mayhem`` (no ``MayhemState`` account —
    a standard coin) | ``vault_not_found`` | ``mint_not_found`` |
    ``mint_mismatch`` | ``not_mayhem_curve`` | ``identity_failed`` | ``malformed``.
    """

    flows: dict[str, NormalizedMayhemFlow] = field(default_factory=dict[str, NormalizedMayhemFlow])
    refused: dict[str, str] = field(default_factory=dict[str, str])
    slot: int | None = None
    calls: int = 0


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

    async def _call(self, method: str, params: list[Any]) -> Any:
        """One JSON-RPC call under both buckets; returns ``result`` or raises."""
        await self._limiter.acquire("requests", 1)
        if self._method_limiter is not None:
            await self._method_limiter.acquire(method, 1)
        try:
            response = await self._client.post(
                self._url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
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
        except ValueError:
            raise MalformedMessage("invalid Solana RPC JSON", exchange="pumpfun") from None
        if not isinstance(payload, dict) or "error" in payload:
            raise ExchangeError("Solana RPC returned an error", exchange="pumpfun")
        try:
            return cast(dict[str, Any], payload)["result"]
        except KeyError:
            raise MalformedMessage(
                "Solana RPC response has no result", exchange="pumpfun"
            ) from None

    async def get_curve_state(self, mint: str, bonding_curve: str) -> NormalizedCurveState:
        result = await self._call("getAccountInfo", [bonding_curve, _FINALIZED])
        try:
            account = result["value"]
            if account is None:
                raise ExchangeError(
                    "bonding curve account not found", exchange="pumpfun", retryable=False
                )
            data, owner = _account_data(account)
            decoded = decode_bonding_curve_account(data, owner=owner)
            slot = _slot(result)
        except (KeyError, IndexError, TypeError, ValueError):
            raise MalformedMessage("invalid Solana account response", exchange="pumpfun") from None
        state = curve_state_from_rpc_account(mint, decoded)
        return state.model_copy(update={"slot": slot, "commitment": "finalized"})

    async def get_mayhem_flows(self, mints: Sequence[str]) -> MayhemFlowBatch:
        """The agent's net flow for each Mayhem mint, four accounts per mint in
        one ``getMultipleAccounts`` per 25 mints (T4.2e). A mint whose accounts
        do not reconcile is **refused by name**, never a number."""
        batch = MayhemFlowBatch()
        for start in range(0, len(mints), MINTS_PER_BATCH):
            chunk = list(mints[start : start + MINTS_PER_BATCH])
            addresses = [address for mint in chunk for address in mayhem_accounts_for(mint)]
            result = await self._call("getMultipleAccounts", [addresses, _FINALIZED])
            try:
                slot = _slot(result)
                raw_values: Any = result["value"]
                if not isinstance(raw_values, list) or len(cast(list[Any], raw_values)) != len(
                    addresses
                ):
                    raise ValueError("account count")
                values = cast(list[Any], raw_values)
            except (KeyError, TypeError, ValueError):
                raise MalformedMessage(
                    "invalid getMultipleAccounts response", exchange="pumpfun"
                ) from None
            now = utcnow()
            batch = MayhemFlowBatch(batch.flows, batch.refused, slot, batch.calls + 1)
            for index, mint in enumerate(chunk):
                accounts = values[index * 4 : index * 4 + 4]
                try:
                    batch.flows[mint] = _flow(mint, accounts, slot=slot, now=now)
                except MayhemRefused as exc:
                    batch.refused[mint] = exc.reason
                except _Absent as exc:
                    batch.refused[mint] = exc.reason
                except (MalformedMessage, KeyError, IndexError, TypeError, ValueError):
                    batch.refused[mint] = "malformed"
        return batch


class _Absent(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _account_data(account: Any) -> tuple[str, str]:
    """``(data_base64, owner)`` of one account object, refusing a program or a
    non-base64 encoding."""
    data = account["data"]
    if account.get("executable") is not False or data[1] != "base64":
        raise ValueError("invalid account encoding/type")
    return str(data[0]), str(account["owner"])


def _slot(result: Any) -> int:
    slot = result["context"]["slot"]
    if type(slot) is not int or slot < 0:
        raise ValueError("invalid slot")
    return slot


def _flow(mint: str, accounts: list[Any], *, slot: int, now: Any) -> NormalizedMayhemFlow:
    curve_account, state_account, vault_account, mint_account = accounts
    if curve_account is None:
        raise _Absent("curve_not_found")
    if state_account is None:
        raise _Absent("not_mayhem")
    if vault_account is None:
        raise _Absent("vault_not_found")
    if mint_account is None:
        raise _Absent("mint_not_found")
    curve_data, curve_owner = _account_data(curve_account)
    state_data, state_owner = _account_data(state_account)
    vault_data, vault_owner = _account_data(vault_account)
    mint_data, mint_owner = _account_data(mint_account)
    return mayhem_flow_from_accounts(
        mint,
        curve=decode_bonding_curve_account(curve_data, owner=curve_owner),
        state=decode_mayhem_state(state_data, owner=state_owner),
        vault_tokens=decode_token_account_amount(vault_data, owner=vault_owner),
        mint_supply=decode_mint_supply(mint_data, owner=mint_owner),
        slot=slot,
        commitment="finalized",
        now=now,
    )


__all__ = ["PUBLIC_RPC_URL", "MayhemFlowBatch", "SolanaRpcClient"]
