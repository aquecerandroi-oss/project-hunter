"""T4.83 — ``treasury_send.attempt_swap`` over the **real** recorded Jupiter
swap (USDC -> SOL, 18/09/2026), whose ``CreateIdempotent`` mint only exists
inside an address lookup table.

Fakes only, in the shape of ``test_treasury_tick.py`` and ``spot_fakes.py``:
no Postgres (``role_session``/``treasury_db`` are patched), no network (the
table is served by the fake RPC's ``getMultipleAccounts``), no key (the signer
returns 64 bytes). The transaction is decoded for real from the fixture.

What these pin down: the tables are read **before** the verification and
before anything is signed, at ``finalized``; a table that cannot be read, that
was deactivated, that is too short or that resolves to another mint refuses
the attempt by name with nothing signed and nothing sent.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.jupiter import JupiterQuote, JupiterSwapTransaction
from hunter_exchanges.pumpfun.tx_rpc import SimulationResult
from hunter_meme_executor import treasury_send
from hunter_meme_executor.chain import TokenAccountRead, WalletRead
from hunter_meme_executor.context import ExecutorContext, ExecutorState
from hunter_meme_executor.spot_alt import ALT_PROGRAM_ID, READ_COMMITMENT
from hunter_meme_executor.treasury_rules import USDC_MINT
from hunter_meme_executor.treasury_send import attempt_swap

from .spot_tx_fixtures import lookup_table_data, table_addresses

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"
WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
WSOL = "So11111111111111111111111111111111111111112"
TABLE = "HVck7rwUxqFPNxbzdrsFGcCHDpMVEkCAoUh6ZiZXsSow"
"""The single lookup table of the recorded capture."""
MINT_SLOT = 11
USDC_ATOMS = 1_000_000
QUOTED_OUT = 9_487_602
THRESHOLD = QUOTED_OUT * 9950 // 10_000
SIGNATURE = "5" * 88
SOL_BEFORE = 680_000_000
USDC_BEFORE = 21_330_000


def _swap_tx() -> JupiterSwapTransaction:
    payload = json.loads((FIXTURES / "jupiter_swap_usdc_to_sol_real.json").read_text("utf-8"))
    return JupiterSwapTransaction(str(payload["swapTransaction"]), 250_000_123, 99_999)


def _quote() -> JupiterQuote:
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
    commitments: list[str] = field(default_factory=lambda: list[str]())
    sent: list[bytes] = field(default_factory=lambda: list[bytes]())

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
        self.sent.append(tx)
        return SIGNATURE

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        self.log.append("statuses")
        return [{"confirmationStatus": "confirmed", "err": None}]


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
    signed: list[bytes] = field(default_factory=lambda: list[bytes]())

    def sign(self, message_bytes: bytes) -> bytes:
        self.log.append("sign")
        self.signed.append(message_bytes)
        return bytes(64)


@dataclass
class FakeConfig:
    treasury_max_slippage_bps: int = 50
    confirm_timeout_s: float = 1.0


@dataclass
class FakeJupiter:
    def swap(self, *, quote: JupiterQuote, user_public_key: str) -> JupiterSwapTransaction:
        assert user_public_key == WALLET
        return _swap_tx()


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


def _rig(monkeypatch: pytest.MonkeyPatch, tables: dict[str, str]) -> Rig:
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
    _patch_db(monkeypatch, statuses)
    return Rig(ctx=ctx, log=log, statuses=statuses)


def _patch_db(monkeypatch: pytest.MonkeyPatch, statuses: list[str]) -> None:
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
        async def mark(_session: Any, _swap_id: uuid.UUID, **_kw: Any) -> None:
            statuses.append(name)

        return mark

    monkeypatch.setattr(treasury_send, "role_session", fake_session)
    monkeypatch.setattr(treasury_send.treasury_db, "insert_quoted", insert_quoted)
    monkeypatch.setattr(treasury_send.treasury_db, "insert_refused", insert_refused)
    for name in ("refused", "simulated", "submitted", "confirmed", "failed"):
        monkeypatch.setattr(treasury_send.treasury_db, f"mark_{name}", _marker(name))


async def _run(rig: Rig) -> None:
    await attempt_swap(
        cast(ExecutorContext, rig.ctx),
        usdc_atoms=USDC_ATOMS,
        quote=_quote(),
        wallet_sol=Decimal(SOL_BEFORE) / Decimal(1_000_000_000),
    )


def _served(addresses: tuple[str, ...], **kwargs: Any) -> dict[str, str]:
    return {TABLE: lookup_table_data(addresses, **kwargs)}


# ----------------------------------------------------------------- the happy path
async def test_a_swap_whose_ata_mint_lives_in_a_table_resolves_and_confirms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch, _served(table_addresses(256, {MINT_SLOT: WSOL})))
    await _run(rig)
    assert rig.statuses == ["quoted", "simulated", "submitted", "confirmed"]
    assert rig.ctx.state.treasury_last_attempt_reason == f"ok:{SIGNATURE}"
    # read the tables first, simulate, and only then sign
    assert rig.log[: rig.log.index("sign")] == [
        "get_multiple_accounts",
        "wallet",
        "token_account",
        "simulate",
    ]
    assert rig.ctx.chain.rpc.commitments == [READ_COMMITMENT] == ["finalized"]
    # the bytes signed are the bytes verified and the bytes sent
    signed = rig.ctx.signer.signed[0]
    assert rig.ctx.chain.rpc.sent[0].endswith(signed)
    raw = base64.b64decode(_swap_tx().swap_transaction_b64)
    assert signed == raw[1 + 64 :]


# -------------------------------------------------------------- named refusals
@pytest.mark.parametrize(
    ("tables", "reason"),
    [
        ({}, f"lookup_table_missing:{TABLE}"),
        (
            _served(table_addresses(256, {MINT_SLOT: WSOL}), deactivation_slot=1),
            f"lookup_table_deactivated:{TABLE}",
        ),
        (
            _served(table_addresses(200, {MINT_SLOT: WSOL})),
            f"lookup_table_index_out_of_range:{TABLE}#244",
        ),
        (
            _served(table_addresses(256, {MINT_SLOT: WSOL}), discriminant=0),
            f"lookup_table_uninitialized:{TABLE}",
        ),
        (_served(table_addresses(256, {MINT_SLOT: USDC_MINT})), "ata_address_mismatch"),
    ],
    ids=["missing", "deactivated", "index-out-of-range", "uninitialized", "wrong-mint"],
)
async def test_a_table_that_does_not_resolve_refuses_unsigned(
    monkeypatch: pytest.MonkeyPatch, tables: dict[str, str], reason: str
) -> None:
    rig = _rig(monkeypatch, tables)
    await _run(rig)
    assert rig.ctx.state.treasury_last_attempt_reason == reason
    assert rig.statuses == ["quoted", "refused"]
    assert "sign" not in rig.log and "send" not in rig.log and "simulate" not in rig.log


async def test_an_rpc_failure_reading_the_tables_refuses_by_name_unsigned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _rig(monkeypatch, _served(table_addresses(256, {MINT_SLOT: WSOL})))
    rig.ctx.chain.rpc.call_error = TimeoutError("rpc down")
    await _run(rig)
    assert rig.ctx.state.treasury_last_attempt_reason == "lookup_table_read_failed:TimeoutError"
    assert rig.statuses == ["quoted", "refused"]
    assert "sign" not in rig.log


async def test_a_table_owned_by_another_program_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fake "table" account whose owner is not the ALT program: whatever it
    holds, it is not a lookup table."""
    rig = _rig(monkeypatch, _served(table_addresses(256, {MINT_SLOT: WSOL})))

    def call(method: str, params: list[Any]) -> Any:
        rig.log.append("get_multiple_accounts")
        return {
            "context": {"slot": 1},
            "value": [
                {
                    "data": [lookup_table_data(table_addresses(256, {MINT_SLOT: WSOL})), "base64"],
                    "owner": USDC_MINT,
                    "lamports": 1,
                    "executable": False,
                }
            ],
        }

    monkeypatch.setattr(rig.ctx.chain.rpc, "call", call)
    await _run(rig)
    assert rig.ctx.state.treasury_last_attempt_reason == f"lookup_table_bad_owner:{TABLE}"
    assert "sign" not in rig.log
