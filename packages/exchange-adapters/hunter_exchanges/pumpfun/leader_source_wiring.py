"""Production wiring of the leader source (H-037): the RPC reads it needs, over ``SolanaRpcClient.call``.

Read-only: ``getTransaction`` (confirmed, ``maxSupportedTransactionVersion: 1``),
``getSignaturesForAddress`` (confirmed, for the post-reconnect recovery) and the one-off seed of a
wallet's balances (``getBalance`` + ``getTokenAccountsByOwner`` for both token programs). Nothing here
signs or sends. All three go through the client's buckets (the public endpoint paces one call per
second per method — a paid ``SOLANA_RPC_URL`` is what makes the pilot's confirmations fast).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from hunter_exchanges.pumpfun.leader_source import CombinedLeaderSource
from hunter_exchanges.pumpfun.leader_source_chain import ChainLeaderSource, LogsFeed
from hunter_exchanges.pumpfun.leader_source_nats import (
    ConnectFn,
    FetchConfig,
    NatsLeaderSource,
    WalletSnapshot,
    default_connect,
    default_fetch_config,
)
from hunter_exchanges.pumpfun.leader_source_rpc_guard import RpcGuard
from hunter_exchanges.pumpfun.leader_source_stats import LeaderSourceStats
from hunter_exchanges.pumpfun.rpc_wallet import SignatureInfo

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"  # noqa: S105 - a program id
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"  # noqa: S105 - a program id

__all__ = ["build_leader_source", "rpc_fetch_tx", "rpc_list_signatures", "rpc_wallet_seeder"]


class RpcCall(Protocol):
    async def call(self, method: str, params: list[Any]) -> Any: ...


def rpc_fetch_tx(rpc: RpcCall) -> Callable[[str], Awaitable[dict[str, Any] | None]]:
    async def fetch(signature: str) -> dict[str, Any] | None:
        result = await rpc.call(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "json",
                    "commitment": "confirmed",
                    "maxSupportedTransactionVersion": 1,
                },
            ],
        )
        return cast("dict[str, Any]", result) if isinstance(result, dict) else None

    return fetch


def rpc_list_signatures(
    rpc: RpcCall,
) -> Callable[[str, str | None, int, str | None], Awaitable[Sequence[SignatureInfo]]]:
    async def lister(
        wallet: str, until: str | None, limit: int, before: str | None
    ) -> Sequence[SignatureInfo]:
        config: dict[str, Any] = {"limit": max(1, min(limit, 1000)), "commitment": "confirmed"}
        if until:
            config["until"] = until
        if before:
            config["before"] = before
        result = await rpc.call("getSignaturesForAddress", [wallet, config])
        out: list[SignatureInfo] = []
        for entry_any in cast("list[Any]", result) if isinstance(result, list) else []:
            entry = cast("dict[str, Any]", entry_any) if isinstance(entry_any, dict) else {}
            sig, slot, when = entry.get("signature"), entry.get("slot"), entry.get("blockTime")
            if not isinstance(sig, str) or not isinstance(slot, int):
                continue
            block_time = (
                datetime.fromtimestamp(when, tz=UTC) if isinstance(when, int) and when > 0 else None
            )
            out.append(SignatureInfo(sig, slot, block_time, entry.get("err") is not None))
        return out

    return lister


def _context_slot(result: Any) -> int:
    body = cast("dict[str, Any]", result) if isinstance(result, dict) else {}
    context = (
        cast("dict[str, Any]", body.get("context")) if isinstance(body.get("context"), dict) else {}
    )
    slot = context.get("slot")
    if not isinstance(slot, int) or isinstance(slot, bool):
        raise ValueError("seed answer carries no slot")
    return slot


def _token_atoms(result: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    body = cast("dict[str, Any]", result) if isinstance(result, dict) else {}
    rows = body.get("value")
    for row_any in cast("list[Any]", rows) if isinstance(rows, list) else []:
        try:
            info = row_any["account"]["data"]["parsed"]["info"]
            mint, atoms = str(info["mint"]), int(str(info["tokenAmount"]["amount"]))
        except (KeyError, TypeError, ValueError):
            raise ValueError("seed token account unreadable") from None
        if atoms:
            out[mint] = out.get(mint, 0) + atoms
    return out


def rpc_wallet_seeder(rpc: RpcCall) -> Callable[[str], Awaitable[WalletSnapshot]]:
    """The complete balance snapshot of a wallet — what ``BalanceBook.seed`` needs. A malformed answer
    raises ``ValueError``: a zero guessed here would turn the next buy into a phantom position."""

    async def seed(wallet: str) -> WalletSnapshot:
        config = {"encoding": "jsonParsed", "commitment": "confirmed"}
        balance, legacy, t22 = await asyncio.gather(
            rpc.call("getBalance", [wallet, {"commitment": "confirmed"}]),
            rpc.call("getTokenAccountsByOwner", [wallet, {"programId": TOKEN_PROGRAM}, config]),
            rpc.call(
                "getTokenAccountsByOwner", [wallet, {"programId": TOKEN_2022_PROGRAM}, config]
            ),
        )
        try:
            lamports = balance["value"]
            sol_slot = _context_slot(balance)
            legacy_slot, t22_slot = _context_slot(legacy), _context_slot(t22)
            tokens: dict[str, tuple[int, int]] = {
                m: (a, legacy_slot) for m, a in _token_atoms(legacy).items()
            }
            for mint, atoms in _token_atoms(t22).items():  # each mint keeps the slot of ITS read
                held, held_slot = tokens.get(mint, (0, 0))
                tokens[mint] = (held + atoms, max(held_slot, t22_slot))
        except (KeyError, TypeError, ValueError):
            raise ValueError("seed answer unreadable") from None
        if not isinstance(lamports, int) or isinstance(lamports, bool):
            raise ValueError("seed answer unreadable")
        return WalletSnapshot(
            sol_lamports=lamports,
            sol_slot=sol_slot,
            tokens=tokens,
            tokens_slot=max(legacy_slot, t22_slot),
        )

    return seed


def build_leader_source(
    rpc: RpcCall,
    feed: LogsFeed,
    *,
    stats: LeaderSourceStats | None = None,
    fetch_config: FetchConfig = default_fetch_config,
    connect: ConnectFn = default_connect,
) -> CombinedLeaderSource:
    """NATS first, the chain confirms — the :class:`LeaderSource` the copy lane consumes. ``rpc`` is a
    ``SolanaRpcClient`` (its ``call``), ``feed`` a ``SolanaWsClient``; one ``stats`` object is shared by
    the three parts so a single ``stats.snapshot()`` carries both latency distributions."""
    shared = stats or LeaderSourceStats()
    guarded = RpcGuard(rpc)  # one pause for the fetch, the listing and the seed
    nats = NatsLeaderSource(
        fetch_config=fetch_config, connect=connect, seeder=rpc_wallet_seeder(guarded), stats=shared
    )
    chain = ChainLeaderSource(
        feed=feed,
        fetch_tx=rpc_fetch_tx(guarded),
        list_signatures=rpc_list_signatures(guarded),
        stats=shared,
    )
    return CombinedLeaderSource(nats=nats, chain=chain, stats=shared)
