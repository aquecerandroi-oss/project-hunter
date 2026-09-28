"""Synchronous chain reads the executor needs before and after a trade — one
client, one place, every number stamped with the slot it was read at.

Wraps ``hunter_exchanges.pumpfun.tx_rpc.SolanaTxRpcClient`` (T4.8): ``Global``
(cached for a minute — the fee recipients change on the order of months), the
bonding curve of a mint (never cached: the curve moves in seconds), the wallet's
lamports, the buyer's token account (exists? balance?), every token account the wallet
owns (``token_holdings``, §3.2's unrecognized-holdings input) and the blockhash.
Runs in the submitter's thread (``asyncio.to_thread``), never on the loop.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from hunter_exchanges.pumpfun.decode import BondingCurveAccount, decode_bonding_curve_account
from hunter_exchanges.pumpfun.global_state import (
    GLOBAL_ACCOUNT_ADDRESS,
    GlobalAccount,
    decode_global_account,
)
from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    associated_token_address,
)
from hunter_exchanges.pumpfun.tx import bonding_curve_address
from hunter_exchanges.pumpfun.tx_rpc import SolanaTxRpcClient
from hunter_exchanges.pumpswap.decode import (
    GLOBAL_CONFIG_ADDRESS,
    GlobalConfig,
    Pool,
    decode_global_config,
    decode_pool_account,
)
from hunter_exchanges.pumpswap.pdas import pool_address

__all__ = [
    "ChainReader",
    "CurveRead",
    "EntryReads",
    "HoldingsRead",
    "PoolRead",
    "TokenAccountRead",
    "TokenHolding",
    "WalletRead",
    "parse_token_accounts",
    "read_entry",
]

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
    commitment: str = "confirmed"
    """T4.67b: the commitment the account was read at — ``processed`` only on the
    launch lane's quote; ``admission.curve_from`` hands it to the engine as is."""


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


@dataclass(frozen=True, slots=True)
class TokenHolding:
    """One token account the wallet owns, as ``getTokenAccountsByOwner`` said it."""

    mint: str
    program: str
    amount: int
    """Atomic units (``tokenAmount.amount``) — never ``uiAmount``, which a
    Token-2022 scaled-UI mint can present multiplied."""
    decimals: int
    opaque: bool = False
    """A Token-2022 account with a confidential-transfer extension: its public
    ``amount`` does not prove there is nothing in it."""
    state: str = ""
    """``info.state`` verbatim (``initialized``/``frozen``), ``""`` when absent —
    read only by the audited exception (``wallet_exceptions.py``), never coerced."""


@dataclass(frozen=True, slots=True)
class HoldingsRead:
    holdings: tuple[TokenHolding, ...]
    slots: tuple[int, ...]
    """Each program's context slot, in :func:`ChainReader.token_holdings`' order —
    kept apart: a minimum would hide one program's regression (Astra)."""
    observed_at: datetime


def _holding(entry: Any, *, owner: str, program: str) -> TokenHolding:
    account = cast(dict[str, Any], entry["account"])
    info = cast(dict[str, Any], account["data"]["parsed"]["info"])
    token_amount = cast(dict[str, Any], info["tokenAmount"])
    raw, decimals, mint = str(token_amount["amount"]), token_amount["decimals"], info["mint"]
    valid = (
        account["owner"] == program
        and info["owner"] == owner
        and isinstance(mint, str)
        and bool(mint)
        and raw.isdigit()
        and type(decimals) is int
        and 0 <= decimals <= 255
    )
    if not valid:
        raise ValueError("token_accounts_malformed")
    extensions = cast(list[dict[str, Any]], info.get("extensions") or [])
    opaque = any(str(e.get("extension", "")).startswith("confidentialTransfer") for e in extensions)
    state = info.get("state")
    return TokenHolding(
        cast(str, mint),
        program,
        int(raw),
        cast(int, decimals),
        opaque,
        state if isinstance(state, str) else "",
    )


def parse_token_accounts(
    result: Any, *, owner: str, program: str
) -> tuple[tuple[TokenHolding, ...], int]:
    """``getTokenAccountsByOwner`` (``jsonParsed``) → holdings + the context slot.

    Anything that is not the documented shape raises ``ValueError`` for the
    **whole** read: a partial answer must never read as "the wallet is clean"."""
    try:
        slot, entries = result["context"]["slot"], result["value"]
        if type(slot) is not int or slot < 0 or not isinstance(entries, list):
            raise ValueError("token_accounts_malformed")  # never coerced: {} is not "empty"
        found = tuple(_holding(e, owner=owner, program=program) for e in cast(list[Any], entries))
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError("token_accounts_malformed") from exc
    return found, slot


@dataclass(frozen=True, slots=True)
class PoolRead:
    """A migrated mint's canonical PumpSwap pool, read fresh (T4.29a) — never
    cached: reserves move every trade, same discipline as :class:`CurveRead`."""

    address: str
    pool: Pool
    base_token_amount: int
    quote_token_amount: int
    slot: int
    observed_at: datetime


class ChainReader:
    def __init__(self, rpc: SolanaTxRpcClient, *, commitment: str = "confirmed") -> None:
        self._rpc = rpc
        self._commitment = commitment
        self._global: tuple[float, GlobalAccount] | None = None
        self._pumpswap_config: tuple[float, GlobalConfig] | None = None

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

    def curve(self, mint: str, *, commitment: str | None = None) -> CurveRead | None:
        """The bonding curve now, or ``None`` when the account does not exist.
        ``commitment`` (T4.67b, launch: ``processed``) overrides the reader's; the
        read carries it so the admission judges the commitment it was given."""
        level = commitment or self._commitment
        snapshot = self._rpc.get_account(bonding_curve_address(mint), commitment=level)
        if snapshot is None:
            return None
        mint_account = self._rpc.get_account(mint, commitment=level)
        if mint_account is None:
            return None
        account = decode_bonding_curve_account(snapshot.data_base64, owner=snapshot.owner)
        return CurveRead(
            mint=mint,
            account=account,
            token_program=mint_account.owner,
            slot=snapshot.slot,
            observed_at=datetime.now(UTC),
            commitment=level,
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

    def token_holdings(self, owner: str) -> HoldingsRead:
        """Every token account ``owner`` holds under SPL Token **and** Token-2022
        (pump.fun mints are Token-2022). Two calls, **concurrent** (guardian F2: the
        read costs the slower call, not the sum), and this thread returns only when
        both did; either failing fails the read. Stamped **before** the calls, so
        the verdict's age runs from the oldest moment its data can be from."""
        observed_at = datetime.now(UTC)
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="meme-holdings") as pool:
            reads = [
                pool.submit(self._token_accounts, owner, program)
                for program in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID)
            ]
            answers = [read.result() for read in reads]
        found = tuple(holding for held, _slot in answers for holding in held)
        return HoldingsRead(found, tuple(slot for _held, slot in answers), observed_at)

    def _token_accounts(self, owner: str, program: str) -> tuple[tuple[TokenHolding, ...], int]:
        result = self._rpc.call(
            "getTokenAccountsByOwner",
            [
                owner,
                {"programId": program},
                {"encoding": "jsonParsed", "commitment": self._commitment},
            ],
        )
        return parse_token_accounts(result, owner=owner, program=program)

    def blockhash(self) -> tuple[str, int]:
        return self._rpc.get_latest_blockhash(commitment=self._commitment)

    def pumpswap_global_config(self) -> GlobalConfig:
        """Cached the same way ``global_account`` is (fees change on the
        order of months, never hardcoded — T4.29a)."""
        cached = self._pumpswap_config
        if cached is not None and time.monotonic() - cached[0] < _GLOBAL_TTL_S:
            return cached[1]
        snapshot = self._rpc.get_account(GLOBAL_CONFIG_ADDRESS, commitment=self._commitment)
        if snapshot is None:
            raise RuntimeError("PumpSwap GlobalConfig account not found on this cluster")
        decoded = decode_global_config(snapshot.data_base64, owner=snapshot.owner)
        self._pumpswap_config = (time.monotonic(), decoded)
        return decoded

    def pool(self, mint: str) -> PoolRead | None:
        """The migrated mint's canonical PumpSwap pool now, or ``None`` when
        it does not exist yet (``pumpswap_pool_not_found``, T4.29a)."""
        address = pool_address(mint)
        snapshot = self._rpc.get_account(address, commitment=self._commitment)
        if snapshot is None:
            return None
        pool = decode_pool_account(snapshot.data_base64, owner=snapshot.owner)
        base_result = cast(
            dict[str, Any],
            self._rpc.call(
                "getTokenAccountBalance",
                [pool.pool_base_token_account, {"commitment": self._commitment}],
            ),
        )
        quote_result = cast(
            dict[str, Any],
            self._rpc.call(
                "getTokenAccountBalance",
                [pool.pool_quote_token_account, {"commitment": self._commitment}],
            ),
        )
        base_amount = int(str(cast(dict[str, Any], base_result["value"])["amount"]))
        quote_amount = int(str(cast(dict[str, Any], quote_result["value"])["amount"]))
        return PoolRead(
            address=address,
            pool=pool,
            base_token_amount=base_amount,
            quote_token_amount=quote_amount,
            slot=snapshot.slot,
            observed_at=datetime.now(UTC),
        )


@dataclass(frozen=True, slots=True)
class EntryReads:
    """The three reads one admission needs, taken together in the submitter's thread."""

    curve: CurveRead
    wallet: WalletRead
    token_account: TokenAccountRead
    creates_ata: bool


def read_entry(reader: ChainReader, mint: str, pubkey: str) -> EntryReads | None:
    """``None`` when the curve does not exist (``curve_not_found``); the wallet and
    the buyer's ATA are read only for a curve that does."""
    curve = reader.curve(mint)
    if curve is None:
        return None
    wallet = reader.wallet(pubkey)
    account = reader.token_account(pubkey, mint, curve.token_program)
    return EntryReads(curve, wallet, account, not account.exists)
