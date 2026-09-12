"""Read-only finalized Solana account snapshots; endpoint injection never loads dotenv.

The caller supplies the mint's bonding-curve address for a single curve read; the
Mayhem flow read derives its four accounts from the mint by the IDL's seeds
(``mayhem_state.py``) and batches 25 mints per ``getMultipleAccounts`` (T4.2e);
the curve batch (``rpc_curves.py``, T4.2f) derives the curve PDA of every mint
and reads 100 per call, stamped with the slot's block time. **T4.12** adds the
two reads a watched wallet needs — ``getSignaturesForAddress`` (newest first,
``until`` a cursor) and ``getTransaction`` (``encoding: json``, version 0) —
still reads only: nothing here sends. HTTP/RPC errors never include the
injected URL (it may carry a key).

**Measured limits of the public endpoint** (12/09 13:36 UTC, the RPC's own
response headers, ``tests/fixtures/pumpfun/t42f_capture_http_log.json``):
``x-ratelimit-rps-limit: 250``, ``x-ratelimit-method-limit: 10`` (per method;
``remaining`` fell 9 → 8 across two calls in a window), ``x-ratelimit-conn-limit:
40``. The per-method ceiling is tighter than the 40/10 s ``solana.com`` documents,
so the method spacing below is one call per second — the radar's loops need
about six calls a minute in total.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
from hunter_exchanges.pumpfun.rpc_curves import (
    ACCOUNTS_PER_CALL,
    CurveBatch,
    curve_addresses,
    decode_curve_batch,
)
from hunter_exchanges.rate_limit import TokenBucketRateLimiter

PUBLIC_RPC_URL = "https://api.mainnet-beta.solana.com"
_FINALIZED = {"encoding": "base64", "commitment": "finalized"}
METHOD_SPACING_S = 1.0
"""One call per second per method on the public endpoint: its own header says
``x-ratelimit-method-limit: 10`` (module docstring)."""


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
        # The public RPC also limits each method (its header: 10 per window).
        # Pace one call per second per method — no burst, ever.
        self._method_limiter = method_limiter
        if self._method_limiter is None and self._url.rstrip("/") == PUBLIC_RPC_URL:
            self._method_limiter = TokenBucketRateLimiter(
                "solana_rpc_method", capacity=1, refill_period_s=METHOD_SPACING_S
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

    async def call(self, method: str, params: list[Any]) -> Any:
        """One JSON-RPC call under both buckets — the seam ``rpc_wallet.py`` reads through."""
        return await self._call(method, params)

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

    async def get_block_time(self, slot: int) -> datetime | None:
        """The block time of ``slot`` (UTC), or ``None`` when the node has none."""
        result = await self._call("getBlockTime", [int(slot)])
        if result is None:
            return None
        if type(result) is not int or result <= 0:
            raise MalformedMessage("invalid getBlockTime result", exchange="pumpfun")
        return datetime.fromtimestamp(result, tz=UTC)

    async def get_curve_states(
        self, mints: Sequence[str], *, with_block_time: bool = True
    ) -> CurveBatch:
        """The curve of every mint, 100 per ``getMultipleAccounts`` (T4.2f,
        ``rpc_curves.py``). ``observed_at`` is the slot's block time; a slot
        without one keeps ``received_at`` and is counted. A refusal is by name,
        never a number; a failed call raises and the caller counts it."""
        states: dict[str, NormalizedCurveState] = {}
        refused: dict[str, str] = {}
        slots: list[int] = []
        block_times: dict[int, datetime | None] = {}
        calls = missing = 0
        for start in range(0, len(mints), ACCOUNTS_PER_CALL):
            pairs = curve_addresses(mints[start : start + ACCOUNTS_PER_CALL])
            result = await self._call(
                "getMultipleAccounts", [[address for _, address in pairs], _FINALIZED]
            )
            calls += 1
            received_at = utcnow()
            try:
                slot = _slot(result)
            except (KeyError, TypeError, ValueError):
                raise MalformedMessage(
                    "invalid getMultipleAccounts response", exchange="pumpfun"
                ) from None
            block_time: datetime | None = None
            if with_block_time:
                if slot not in block_times:
                    calls += 1
                    try:
                        block_times[slot] = await self.get_block_time(slot)
                    except RateLimited:
                        raise
                    except ExchangeError:
                        block_times[slot] = None
                block_time = block_times[slot]
            chunk_states, chunk_refused, _ = decode_curve_batch(
                [mint for mint, _ in pairs], result, block_time=block_time, received_at=received_at
            )
            if with_block_time and block_time is None:
                missing += len(chunk_states)
            states.update(chunk_states)
            refused.update(chunk_refused)
            slots.append(slot)
        return CurveBatch(
            states=states,
            refused=refused,
            slots=tuple(slots),
            calls=calls,
            block_time_missing=missing,
        )

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


__all__ = [
    "METHOD_SPACING_S",
    "PUBLIC_RPC_URL",
    "CurveBatch",
    "MayhemFlowBatch",
    "SolanaRpcClient",
]
