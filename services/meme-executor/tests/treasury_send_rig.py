"""T4.84 — the fakes of the treasury money path (no network, no key, no
Postgres), shared by ``test_treasury_send_alt.py`` (T4.83, the address lookup
tables) and ``test_treasury_send_ambiguous.py`` (T4.84, the send that neither
confirms nor refuses). Extracted unchanged from ``test_treasury_send_alt.py``
except for the three knobs the ambiguous cases need: an RPC that can fail or
answer another signature on ``sendTransaction`` and a signer that can raise.

The transaction is the **real** recorded Jupiter swap (USDC -> SOL,
18/09/2026, nothing signed); the signer returns fixed bytes, so the signature
the lane derives locally is known here as ``LOCAL_SIGNATURE``.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.jupiter import JupiterQuote, JupiterSwapTransaction
from hunter_exchanges.pumpfun.solana_codec import b58encode
from hunter_exchanges.pumpfun.tx_rpc import SimulationResult
from hunter_meme_executor import treasury_send
from hunter_meme_executor.chain import TokenAccountRead, WalletRead
from hunter_meme_executor.context import ExecutorContext, ExecutorState
from hunter_meme_executor.spot_alt import ALT_PROGRAM_ID
from hunter_meme_executor.treasury_rules import USDC_MINT
from hunter_meme_executor.treasury_send import attempt_swap

from .spot_tx_fixtures import lookup_table_data

FIXTURES = Path(__file__).parent / "fixtures"
WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
WSOL = "So11111111111111111111111111111111111111112"
TABLE = "HVck7rwUxqFPNxbzdrsFGcCHDpMVEkCAoUh6ZiZXsSow"
"""The single lookup table of the recorded capture."""
MINT_SLOT = 11
USDC_ATOMS = 1_000_000
QUOTED_OUT = 9_487_602
THRESHOLD = QUOTED_OUT * 9950 // 10_000
SIG_BYTES = bytes(range(1, 65))
LOCAL_SIGNATURE = b58encode(SIG_BYTES)
"""What the lane derives from the signed bytes — the transaction's own id."""
SOL_BEFORE = 680_000_000
USDC_BEFORE = 21_330_000
SOL_FILL_LAMPORTS = 9_400_000
"""What the recorded swap adds to the wallet, as ``getTransaction``'s meta
reports it for **this** signature (fee already deducted)."""


def confirmed_tx(sol_delta: int = SOL_FILL_LAMPORTS, *, payer: str = WALLET) -> dict[str, Any]:
    return {
        "meta": {
            "err": None,
            "fee": 5_000,
            "preBalances": [SOL_BEFORE, 1],
            "postBalances": [SOL_BEFORE + sol_delta, 1],
            "preTokenBalances": [],
            "postTokenBalances": [],
        },
        "transaction": {"message": {"accountKeys": [payer, "11111111111111111111111111111111"]}},
        "blockTime": 1_758_000_000,
    }


def swap_tx() -> JupiterSwapTransaction:
    payload = json.loads((FIXTURES / "jupiter_swap_usdc_to_sol_real.json").read_text("utf-8"))
    return JupiterSwapTransaction(str(payload["swapTransaction"]), 250_000_123, 99_999)


def quote() -> JupiterQuote:
    return JupiterQuote(
        input_mint=USDC_MINT,
        output_mint=WSOL,
        in_amount=Decimal(USDC_ATOMS),
        out_amount=Decimal(QUOTED_OUT),
        other_amount_threshold=Decimal(THRESHOLD),
        price_impact_pct=Decimal("0.0006"),
        slippage_bps=50,
        route_labels=("HumidiFi",),
        raw={},
    )


# ---------------------------------------------------------------------- fakes
@dataclass
class FakeRpc:
    log: list[str]
    lookup_tables: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    call_error: Exception | None = None
    send_error: Exception | None = None
    relayed: str | None = None
    commitments: list[str] = field(default_factory=lambda: list[str]())
    sent: list[bytes] = field(default_factory=lambda: list[bytes]())
    tx: dict[str, Any] | None = field(default_factory=confirmed_tx)
    tx_error: Exception | None = None

    def call(self, method: str, params: list[Any]) -> Any:
        assert method == "getMultipleAccounts"
        self.log.append("get_multiple_accounts")
        self.commitments.append(str(cast("dict[str, Any]", params[1])["commitment"]))
        if self.call_error is not None:
            raise self.call_error
        value = [
            None
            if address not in self.lookup_tables
            else {
                "data": [self.lookup_tables[address], "base64"],
                "owner": ALT_PROGRAM_ID,
                "lamports": 1_000_000,
                "executable": False,
            }
            for address in cast("list[str]", params[0])
        ]
        return {"context": {"slot": 1}, "value": value}

    def simulate_transaction(
        self, raw: bytes, *, sig_verify: bool = False, accounts: tuple[str, ...] = ()
    ) -> SimulationResult:
        self.log.append("simulate")
        token = {
            "data": {"parsed": {"info": {"tokenAmount": {"amount": str(USDC_BEFORE - USDC_ATOMS)}}}}
        }
        return SimulationResult(
            ok=True,
            err=None,
            logs=(),
            units_consumed=90_000,
            slot=1,
            return_data=None,
            accounts=({"lamports": SOL_BEFORE + THRESHOLD}, token),
        )

    def send_transaction(self, tx: bytes, *, max_retries: int = 0) -> str:
        self.log.append("send")
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(tx)
        return self.relayed or LOCAL_SIGNATURE

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        self.log.append("statuses")
        return [{"confirmationStatus": "confirmed", "err": None}]

    def get_transaction(self, signature: str) -> dict[str, Any] | None:
        self.log.append("transaction")
        if self.tx_error is not None:
            raise self.tx_error
        return self.tx


@dataclass
class FakeChain:
    log: list[str]
    rpc: FakeRpc

    def wallet(self, pubkey: str) -> WalletRead:
        self.log.append("wallet")
        return WalletRead(pubkey, SOL_BEFORE, 1, datetime.now(UTC))

    def token_account(self, owner: str, mint: str, token_program: str) -> TokenAccountRead:
        self.log.append("token_account")
        return TokenAccountRead(exists=True, amount=USDC_BEFORE)


@dataclass
class FakeSigner:
    log: list[str]
    pubkey: str = WALLET
    error: Exception | None = None
    signed: list[bytes] = field(default_factory=lambda: list[bytes]())

    def sign(self, message_bytes: bytes) -> bytes:
        self.log.append("sign")
        if self.error is not None:
            raise self.error
        self.signed.append(message_bytes)
        return SIG_BYTES


@dataclass
class FakeConfig:
    treasury_max_slippage_bps: int = 50
    confirm_timeout_s: float = 1.0


@dataclass
class FakeJupiter:
    def swap(self, *, quote: JupiterQuote, user_public_key: str) -> JupiterSwapTransaction:
        assert user_public_key == WALLET
        return swap_tx()


@dataclass
class FakeContext:
    config: FakeConfig
    chain: FakeChain
    signer: FakeSigner
    treasury_client: FakeJupiter
    session_factory: Any
    state: ExecutorState = field(default_factory=ExecutorState)


@dataclass
class Rig:
    ctx: FakeContext
    log: list[str]
    statuses: list[str]
    signatures: list[str | None]
    """The ``signature`` handed to ``mark_submitted``, in order."""
    fills: list[tuple[Decimal, Decimal]]
    """``(sol_out_filled, wallet_sol_after)`` handed to ``mark_confirmed``."""


def rig(monkeypatch: pytest.MonkeyPatch, tables: dict[str, str]) -> Rig:
    log: list[str] = []
    rpc = FakeRpc(log=log, lookup_tables=tables)
    ctx = FakeContext(
        config=FakeConfig(),
        chain=FakeChain(log=log, rpc=rpc),
        signer=FakeSigner(log=log),
        treasury_client=FakeJupiter(),
        session_factory=object(),
    )
    statuses: list[str] = []
    signatures: list[str | None] = []
    fills: list[tuple[Decimal, Decimal]] = []
    _patch_db(monkeypatch, statuses, signatures, fills)
    return Rig(ctx=ctx, log=log, statuses=statuses, signatures=signatures, fills=fills)


def _patch_db(
    monkeypatch: pytest.MonkeyPatch,
    statuses: list[str],
    signatures: list[str | None],
    fills: list[tuple[Decimal, Decimal]],
) -> None:
    """``attempt_swap``'s only database writes, recorded in order."""

    class _Session:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_exc: object) -> None:
            return None

    def fake_session(_factory: Any, *, db_role: str) -> _Session:
        return _Session()

    async def insert_quoted(_session: Any, **_kw: Any) -> uuid.UUID:
        statuses.append("quoted")
        return uuid.UUID(int=1)

    async def insert_refused(_session: Any, **_kw: Any) -> None:
        statuses.append("refused")

    def _marker(name: str) -> Any:
        async def mark(_session: Any, _swap_id: uuid.UUID, **kw: Any) -> None:
            statuses.append(name)
            if name == "submitted":
                signatures.append(cast("str | None", kw.get("signature")))
            if name == "confirmed":
                fills.append(
                    (cast(Decimal, kw["sol_out_filled"]), cast(Decimal, kw["wallet_sol_after"]))
                )

        return mark

    monkeypatch.setattr(treasury_send, "role_session", fake_session)
    monkeypatch.setattr(treasury_send.treasury_db, "insert_quoted", insert_quoted)
    monkeypatch.setattr(treasury_send.treasury_db, "insert_refused", insert_refused)
    for name in ("refused", "simulated", "submitted", "confirmed", "failed"):
        monkeypatch.setattr(treasury_send.treasury_db, f"mark_{name}", _marker(name))


async def run_attempt(target: Rig) -> None:
    await attempt_swap(
        cast(ExecutorContext, target.ctx),
        usdc_atoms=USDC_ATOMS,
        quote=quote(),
        wallet_sol=Decimal(SOL_BEFORE) / Decimal(1_000_000_000),
    )


def served(addresses: tuple[str, ...], **kwargs: Any) -> dict[str, str]:
    return {TABLE: lookup_table_data(addresses, **kwargs)}
