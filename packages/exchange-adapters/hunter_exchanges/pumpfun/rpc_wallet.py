"""The two reads a watched wallet needs (T4.12), over :class:`SolanaRpcClient`:
``getSignaturesForAddress`` (newest first, ``until`` a cursor) and
``getTransaction`` (``encoding: json``, version 0 accepted). Reads only —
nothing here sends — under the client's own buckets, so the wallet loop's
budget is whatever bucket the client was built with.

:class:`WalletRpc` is the ``hunter_meme_worker.context.WalletChainSource``; a
test fakes it with two coroutines and no socket.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.rpc import SolanaRpcClient

__all__ = ["SignatureInfo", "WalletRpc"]


@dataclass(frozen=True, slots=True)
class SignatureInfo:
    """One entry of ``getSignaturesForAddress``; ``failed`` = the node reports ``err``."""

    signature: str
    slot: int
    block_time: datetime | None
    failed: bool


class WalletRpc:
    def __init__(self, client: SolanaRpcClient) -> None:
        self._client = client

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_signatures_for_address(
        self, address: str, *, until: str | None = None, limit: int = 100
    ) -> list[SignatureInfo]:
        """The address's newest signatures first, stopping at ``until`` (exclusive)
        — the cursor of a wallet loop (T4.12). ``limit`` ≤ 1000, the node's cap."""
        config: dict[str, Any] = {"limit": max(1, min(int(limit), 1000)), "commitment": "finalized"}
        if until:
            config["until"] = until
        result = await self._client.call("getSignaturesForAddress", [address, config])
        if not isinstance(result, list):
            raise MalformedMessage("invalid getSignaturesForAddress result", exchange="pumpfun")
        out: list[SignatureInfo] = []
        for entry_any in cast(list[Any], result):
            entry = cast(dict[str, Any], entry_any) if isinstance(entry_any, dict) else {}
            block_time = entry.get("blockTime")
            try:
                out.append(
                    SignatureInfo(
                        signature=str(entry["signature"]),
                        slot=int(entry["slot"]),
                        block_time=datetime.fromtimestamp(block_time, tz=UTC)
                        if isinstance(block_time, int) and block_time > 0
                        else None,
                        failed=entry.get("err") is not None,
                    )
                )
            except (KeyError, TypeError, ValueError):
                raise MalformedMessage(
                    "invalid getSignaturesForAddress entry", exchange="pumpfun"
                ) from None
        return out

    async def get_transaction(self, signature: str) -> dict[str, Any] | None:
        """One finalized transaction as ``encoding: json`` (version 0 accepted), or
        ``None`` when the node does not have it. Read only."""
        result = await self._client.call(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "json",
                    "commitment": "finalized",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        )
        if result is None:
            return None
        if not isinstance(result, dict):
            raise MalformedMessage("invalid getTransaction result", exchange="pumpfun")
        return cast(dict[str, Any], result)
