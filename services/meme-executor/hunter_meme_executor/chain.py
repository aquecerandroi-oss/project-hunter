"""Synchronous chain reads the executor needs before and after a trade — one
client, one place, every number stamped with the slot it was read at.

Wraps ``hunter_exchanges.pumpfun.tx_rpc.SolanaTxRpcClient`` (T4.8): ``Global``
(cached for a minute — the fee recipients change on the order of months), the
bonding curve of a mint (never cached: the curve moves in seconds), the wallet's
lamports, the buyer's token account (exists? balance?) and the blockhash. Runs
in the submitter's thread (``asyncio.to_thread``), never on the loop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from hunter_exchanges.pumpfun.decode import BondingCurveAccount, decode_bonding_curve_account
from hunter_exchanges.pumpfun.global_state import (
    GLOBAL_ACCOUNT_ADDRESS,
    GlobalAccount,
    decode_global_account,
)
from hunter_exchanges.pumpfun.solana_codec import associated_token_address
from hunter_exchanges.pumpfun.tx import bonding_curve_address
from hunter_exchanges.pumpfun.tx_rpc import SolanaTxRpcClient

__all__ = ["ChainReader", "CurveRead", "TokenAccountRead", "WalletRead"]

_GLOBAL_TTL_S = 60.0


@dataclass(frozen=True, slots=True)
class CurveRead:
    mint: str
    account: BondingCurveAccount
    token_program: str
    slot: int
    observed_at: datetime
    """Wall-clock instant of the read (the RPC does not stamp ``getAccountInfo``
    with a block time); the slot is the chain's own clock."""


@dataclass(frozen=True, slots=True)
class WalletRead:
    pubkey: str
    lamports: int
    slot: int
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class TokenAccountRead:
    exists: bool
    amount: int


class ChainReader:
    def __init__(self, rpc: SolanaTxRpcClient, *, commitment: str = "confirmed") -> None:
        self._rpc = rpc
        self._commitment = commitment
        self._global: tuple[float, GlobalAccount] | None = None

    @property
    def rpc(self) -> SolanaTxRpcClient:
        return self._rpc

    def global_account(self) -> GlobalAccount:
        cached = self._global
        if cached is not None and time.monotonic() - cached[0] < _GLOBAL_TTL_S:
            return cached[1]
        snapshot = self._rpc.get_account(GLOBAL_ACCOUNT_ADDRESS, commitment=self._commitment)
        if snapshot is None:
            raise RuntimeError("Global account not found on this cluster")
        decoded = decode_global_account(snapshot.data_base64, owner=snapshot.owner)
        self._global = (time.monotonic(), decoded)
        return decoded

    def curve(self, mint: str) -> CurveRead | None:
        """The bonding curve now, or ``None`` when the account does not exist."""
        snapshot = self._rpc.get_account(bonding_curve_address(mint), commitment=self._commitment)
        if snapshot is None:
            return None
        mint_account = self._rpc.get_account(mint, commitment=self._commitment)
        if mint_account is None:
            return None
        account = decode_bonding_curve_account(snapshot.data_base64, owner=snapshot.owner)
        return CurveRead(
            mint=mint,
            account=account,
            token_program=mint_account.owner,
            slot=snapshot.slot,
            observed_at=datetime.now(UTC),
        )

    def wallet(self, pubkey: str) -> WalletRead:
        result = cast(
            dict[str, Any],
            self._rpc.call("getBalance", [pubkey, {"commitment": self._commitment}]),
        )
        return WalletRead(
            pubkey=pubkey,
            lamports=int(cast(int, result["value"])),
            slot=int(cast(dict[str, Any], result["context"])["slot"]),
            observed_at=datetime.now(UTC),
        )

    def token_account(self, owner: str, mint: str, token_program: str) -> TokenAccountRead:
        address = associated_token_address(owner, mint, token_program=token_program)
        snapshot = self._rpc.get_account(address, commitment=self._commitment)
        if snapshot is None:
            return TokenAccountRead(exists=False, amount=0)
        result = cast(
            dict[str, Any],
            self._rpc.call("getTokenAccountBalance", [address, {"commitment": self._commitment}]),
        )
        value = cast(dict[str, Any], result["value"])
        return TokenAccountRead(exists=True, amount=int(str(value["amount"])))

    def blockhash(self) -> tuple[str, int]:
        return self._rpc.get_latest_blockhash(commitment=self._commitment)
