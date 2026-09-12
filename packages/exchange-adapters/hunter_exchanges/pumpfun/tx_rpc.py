"""Solana JSON-RPC for the execution path: simulate, send, confirm, read — synchronous.

Deliberately separate from ``rpc.py`` (the radar's read-only, finalized reader):
this client is the one a submitter drives, and it carries the two guards the
doctrine asks for before any transaction leaves the box:

- :meth:`SolanaTxRpcClient.send_transaction` is **refused** unless the client was
  constructed with ``allow_send=True`` — the meme-executor sets it from
  ``ENABLE_MEME_LIVE_TRADING`` + the §12 gates (``hunter_core.execution.meme``),
  and a devnet run sets it explicitly. The default is inert.
- preflight stays on (``skipPreflight=false``): the cluster's simulation is the
  last free "this would fail" (``docs/RISK_ENGINE_MEME.md`` §9.2).

Error messages never include the RPC URL (it may carry a provider key), matching
``rpc.py``. No method here reads or writes any secret.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, cast

import httpx

from hunter_exchanges.base import ExchangeError, ExchangeUnavailable, MalformedMessage

__all__ = [
    "AccountSnapshot",
    "SendDisabled",
    "SimulationResult",
    "SolanaTxRpcClient",
]

MAINNET_PUBLIC_RPC_URL = "https://api.mainnet-beta.solana.com"
DEVNET_PUBLIC_RPC_URL = "https://api.devnet.solana.com"


class SendDisabled(ExchangeError):
    """``send_transaction`` on a client built without ``allow_send=True``."""

    def __init__(self) -> None:
        super().__init__(
            "sendTransaction refused: this RPC client was not built with allow_send=True",
            exchange="pumpfun",
            retryable=False,
        )


@dataclass(frozen=True, slots=True)
class SimulationResult:
    ok: bool
    err: Any
    logs: tuple[str, ...]
    units_consumed: int | None
    slot: int | None
    return_data: str | None


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    address: str
    owner: str
    data_base64: str
    lamports: int
    slot: int
    executable: bool


class SolanaTxRpcClient:
    def __init__(
        self,
        rpc_url: str,
        *,
        allow_send: bool = False,
        http_client: httpx.Client | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        if not rpc_url or not rpc_url.startswith(("http://", "https://")):
            raise ValueError("rpc_url must be an http(s) URL")
        self._url = rpc_url
        self._allow_send = allow_send
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout_s)

    @property
    def allow_send(self) -> bool:
        return self._allow_send

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ------------------------------------------------------------------ core
    def _call(self, method: str, params: list[Any]) -> Any:
        try:
            response = self._client.post(
                self._url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            )
        except httpx.TransportError as exc:
            raise ExchangeUnavailable(
                f"Solana RPC transport failure during {method}", exchange="pumpfun"
            ) from exc
        if response.status_code == 429:
            raise ExchangeUnavailable(
                f"Solana RPC rate limited during {method}", exchange="pumpfun"
            )
        if response.is_error:
            raise ExchangeUnavailable(
                f"Solana RPC HTTP {response.status_code} during {method}", exchange="pumpfun"
            )
        try:
            payload = cast(dict[str, Any], response.json())
        except ValueError as exc:
            raise MalformedMessage(
                f"Solana RPC non-JSON reply to {method}", exchange="pumpfun"
            ) from exc
        if "error" in payload:
            error = cast(dict[str, Any], payload["error"])
            raise ExchangeError(
                f"Solana RPC error during {method}: code={error.get('code')} "
                f"message={str(error.get('message', ''))[:200]}",
                exchange="pumpfun",
                retryable=False,
            )
        return payload.get("result")

    def call(self, method: str, params: list[Any]) -> Any:
        """A read-only JSON-RPC call by name (T4.14: ``getBalance``,
        ``getTokenAccountBalance``). ``sendTransaction`` is refused here too — the
        one method that mutates the chain has exactly one door, below."""
        if method == "sendTransaction":
            raise SendDisabled()
        return self._call(method, params)

    # ------------------------------------------------------------------ reads
    def get_latest_blockhash(self, *, commitment: str = "confirmed") -> tuple[str, int]:
        result = cast(
            dict[str, Any], self._call("getLatestBlockhash", [{"commitment": commitment}])
        )
        value = cast(dict[str, Any], result["value"])
        return str(value["blockhash"]), int(value["lastValidBlockHeight"])

    def get_block_height(self, *, commitment: str = "confirmed") -> int:
        return int(cast(int, self._call("getBlockHeight", [{"commitment": commitment}])))

    def get_account(self, address: str, *, commitment: str = "confirmed") -> AccountSnapshot | None:
        result = cast(
            dict[str, Any],
            self._call(
                "getAccountInfo", [address, {"encoding": "base64", "commitment": commitment}]
            ),
        )
        value = result.get("value")
        if value is None:
            return None
        account = cast(dict[str, Any], value)
        data = cast(list[Any], account["data"])
        if data[1] != "base64":
            raise MalformedMessage("account encoding is not base64", exchange="pumpfun")
        return AccountSnapshot(
            address=address,
            owner=str(account["owner"]),
            data_base64=str(data[0]),
            lamports=int(account["lamports"]),
            slot=int(cast(dict[str, Any], result["context"])["slot"]),
            executable=bool(account.get("executable", False)),
        )

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        result = cast(
            dict[str, Any],
            self._call("getSignatureStatuses", [signatures, {"searchTransactionHistory": True}]),
        )
        return cast(list[dict[str, Any] | None], result["value"])

    def get_transaction(
        self, signature: str, *, commitment: str = "confirmed"
    ) -> dict[str, Any] | None:
        result = self._call(
            "getTransaction",
            [
                signature,
                {"encoding": "json", "commitment": commitment, "maxSupportedTransactionVersion": 0},
            ],
        )
        return None if result is None else cast(dict[str, Any], result)

    # --------------------------------------------------------------- simulate
    def simulate_transaction(
        self, transaction: bytes, *, sig_verify: bool = False, replace_blockhash: bool = False
    ) -> SimulationResult:
        """``simulateTransaction`` — never mutates the chain. ``sig_verify=False`` lets an
        *unsigned* transaction (zeroed signature) be simulated, which is how the
        mainnet proof runs without any key."""
        config: dict[str, Any] = {
            "encoding": "base64",
            "sigVerify": sig_verify,
            "replaceRecentBlockhash": replace_blockhash,
            "commitment": "confirmed",
        }
        result = cast(
            dict[str, Any],
            self._call(
                "simulateTransaction", [base64.b64encode(transaction).decode("ascii"), config]
            ),
        )
        value = cast(dict[str, Any], result["value"])
        return_data = cast(dict[str, Any] | None, value.get("returnData"))
        return SimulationResult(
            ok=value.get("err") is None,
            err=value.get("err"),
            logs=tuple(str(line) for line in cast(list[Any], value.get("logs") or [])),
            units_consumed=cast(int | None, value.get("unitsConsumed")),
            slot=int(cast(dict[str, Any], result["context"])["slot"]),
            return_data=None if return_data is None else str(return_data.get("data")),
        )

    # ------------------------------------------------------------------- send
    def send_transaction(self, transaction: bytes, *, max_retries: int = 0) -> str:
        """``sendTransaction`` with preflight **on**. Refused unless ``allow_send``."""
        if not self._allow_send:
            raise SendDisabled()
        config = {
            "encoding": "base64",
            "skipPreflight": False,
            "preflightCommitment": "confirmed",
            "maxRetries": max_retries,
        }
        signature = self._call(
            "sendTransaction", [base64.b64encode(transaction).decode("ascii"), config]
        )
        return str(signature)
