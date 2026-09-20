"""``meme_close_atas_send.run_batch`` (T4.77) end to end with fakes, the
same shape as ``test_meme_spot_swap_send.py``: build -> verify -> simulate
(fake RPC answering ``accounts``) -> sign (fake signer, 64 zero bytes) ->
audit row with the signature **before** the broadcast -> send (fake) ->
confirm (fake statuses) -> audit row with what landed. No network, no
database, no key.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for extra in (SCRIPTS_DIR, SCRIPTS_DIR / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))
REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in ("services/meme-executor", "packages/exchange-adapters", "packages/risk-core"):
    candidate = str(REPO_ROOT / extra)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import meme_close_atas_send as send  # noqa: E402
from meme_close_atas_plan import build_plan, parse_token_accounts  # noqa: E402
from test_meme_close_atas_plan import RENT, raw_account  # noqa: E402

from hunter_exchanges.pumpfun.solana_codec import (  # noqa: E402
    TOKEN_PROGRAM_ID,
    b58encode,
    deserialize_message,
)
from hunter_exchanges.pumpfun.tx_rpc import SimulationResult  # noqa: E402

WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
SIGNATURE = b58encode(bytes(64))
BLOCKHASH = b58encode(bytes([7]) * 32)
BEFORE = 500_000_000
FEE = 10_000
N = 3
EXPECTED_RENT = N * RENT
CONFIRMED = {"confirmationStatus": "confirmed", "err": None}


def _batch(n: int = N) -> Any:
    rows = parse_token_accounts([raw_account(i) for i in range(n)], program=TOKEN_PROGRAM_ID)
    return build_plan(rows, wallet=WALLET, limit=None).selected


@dataclass
class FakeRpc:
    statuses: list[dict[str, Any] | None]
    sim_lamports: int | None = BEFORE + EXPECTED_RENT - send.BASE_FEE_LAMPORTS - FEE
    sim_ok: bool = True
    landed: int = BEFORE + EXPECTED_RENT - send.BASE_FEE_LAMPORTS - FEE
    tx_meta: dict[str, Any] | None | str = "default"
    tx_calls: int = 0
    log: list[str] = field(default_factory=lambda: [])
    sent: list[bytes] = field(default_factory=lambda: [])
    simulated: list[bytes] = field(default_factory=lambda: [])
    status_calls: int = 0
    raise_on_send: Exception | None = None
    raise_on_status: Exception | None = None

    def get_latest_blockhash(self, *, commitment: str = "confirmed") -> tuple[str, int]:
        return BLOCKHASH, 100

    def call(self, method: str, params: list[Any]) -> Any:
        assert method == "getBalance" and params[0] == WALLET
        self.log.append("balance")
        return {"context": {"slot": 1}, "value": self.landed if self.sent else BEFORE}

    def simulate_transaction(
        self, raw: bytes, *, sig_verify: bool, accounts: tuple[str, ...]
    ) -> SimulationResult:
        assert sig_verify is False and accounts == (WALLET,)
        self.log.append("simulate")
        self.simulated.append(raw)
        return SimulationResult(
            ok=self.sim_ok,
            err=None if self.sim_ok else {"InstructionError": [2, "Custom"]},
            logs=(),
            units_consumed=1,
            slot=1,
            return_data=None,
            accounts=() if self.sim_lamports is None else ({"lamports": self.sim_lamports},),
        )

    def send_transaction(self, signed: bytes) -> str:
        self.log.append("send")
        if self.raise_on_send is not None:
            raise self.raise_on_send
        self.sent.append(signed)
        return SIGNATURE

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        assert signatures == [SIGNATURE]
        if self.raise_on_status is not None:
            raise self.raise_on_status
        self.status_calls += 1
        index = min(self.status_calls - 1, len(self.statuses) - 1)
        return [self.statuses[index]]

    def get_transaction(self, signature: str, *, commitment: str = "confirmed") -> Any:
        """``getTransaction`` (``encoding: json``): the wallet is account 0; the
        default meta says the wallet grew by exactly the closes minus the fee —
        while ``landed`` (the live balance) may say something else entirely."""
        assert signature == SIGNATURE
        self.tx_calls += 1
        self.log.append("transaction")
        if self.tx_meta == "default":
            return {
                "transaction": {"message": {"accountKeys": [WALLET, "x", "y"]}},
                "meta": {
                    "err": None,
                    "fee": send.BASE_FEE_LAMPORTS + FEE,
                    "preBalances": [BEFORE, RENT, 0],
                    "postBalances": [BEFORE + EXPECTED_RENT - send.BASE_FEE_LAMPORTS - FEE, 0, 0],
                },
            }
        return self.tx_meta


class FakeSigner:
    pubkey = WALLET

    def __init__(self) -> None:
        self.sign_calls = 0

    def sign(self, message_bytes: bytes) -> bytes:
        self.sign_calls += 1
        return bytes(64)


class FakeConn:
    """Records every ``system_events`` insert (event name + data) and every commit."""

    def __init__(self, log: list[str] | None = None) -> None:
        self.log: list[str] = [] if log is None else log
        self.events: list[dict[str, Any]] = []

    async def execute(self, statement: Any, parameters: Any = None, /) -> Any:
        sql = str(statement)
        assert "system_events" in sql, sql
        assert parameters["component"] == send.COMPONENT
        self.events.append(
            {
                "event": parameters["event"],
                "level": parameters["level"],
                "data": json.loads(parameters["data"]),
            }
        )
        self.log.append(f"event:{parameters['event']}")
        return object()

    async def commit(self) -> None:
        self.log.append("COMMIT")


def _run(
    rpc: FakeRpc,
    *,
    conn: FakeConn | None = None,
    signer: FakeSigner | None = None,
    batch: Any = None,
) -> tuple[send.BatchResult, FakeConn, FakeSigner]:
    conn = conn or FakeConn()
    signer = signer or FakeSigner()
    interval = send.CONFIRM_INTERVAL_S
    send.CONFIRM_INTERVAL_S = 0.0
    try:
        result = asyncio.run(
            send.run_batch(
                conn,
                rpc,
                signer,
                batch=_batch() if batch is None else batch,
                reason="T4.77 teste",
                actor="everton",
                priority_fee_lamports=FEE,
            )
        )
    finally:
        send.CONFIRM_INTERVAL_S = interval
    return result, conn, signer


def test_a_batch_end_to_end_confirms_and_audits_every_step() -> None:
    # Astra (T4.77 review, must-fix 1): a 100 SOL deposit lands between the two
    # balance reads; the audit must still say what THIS transaction recovered.
    rpc = FakeRpc(statuses=[None, CONFIRMED], landed=BEFORE + 100_000_000_000)
    result, conn, signer = _run(rpc)
    assert result.status == "confirmed"
    assert result.signature == SIGNATURE
    assert result.n_closed == N
    assert result.expected_rent == EXPECTED_RENT
    assert result.lamports_recovered == EXPECTED_RENT - send.BASE_FEE_LAMPORTS - FEE
    assert signer.sign_calls == 1
    assert [e["event"] for e in conn.events] == ["close_atas_submitted", "close_atas_confirmed"]
    assert conn.log == [
        "event:close_atas_submitted",
        "COMMIT",
        "event:close_atas_confirmed",
        "COMMIT",
    ]
    confirmed = conn.events[1]["data"]
    assert confirmed["signature"] == SIGNATURE
    assert confirmed["n_closed"] == N
    assert confirmed["lamports_recovered"] == result.lamports_recovered
    assert confirmed["actor"] == "everton"
    assert confirmed["measure"] == "tx_meta"
    assert rpc.tx_calls == 1
    # the signed transaction is one zero signature + the very message that was simulated
    (signed,) = rpc.sent
    assert signed[:1] == b"\x01" and signed[1:65] == bytes(64)
    assert rpc.simulated[0][65:] == signed[65:]
    message = deserialize_message(signed[65:])
    assert message.account_keys[0] == WALLET
    assert len(message.instructions) == 2 + N


def test_the_signature_is_persisted_and_committed_before_the_broadcast() -> None:
    shared: list[str] = []
    rpc = FakeRpc(statuses=[CONFIRMED], log=shared)
    _run(rpc, conn=FakeConn(shared))
    assert (
        shared.index("event:close_atas_submitted") < shared.index("COMMIT") < shared.index("send")
    )
    assert shared.index("simulate") < shared.index("event:close_atas_submitted")


def test_the_simulation_runs_before_the_signature_and_a_short_refund_refuses() -> None:
    rpc = FakeRpc(statuses=[CONFIRMED], sim_lamports=BEFORE + EXPECTED_RENT - 50_000 - 1)
    result, conn, signer = _run(rpc)
    assert result.status == "refused"
    assert result.reason is not None and result.reason.startswith("simulation_lamports_short:")
    assert signer.sign_calls == 0
    assert rpc.sent == [] and "send" not in rpc.log
    assert [e["event"] for e in conn.events] == ["close_atas_refused"]


def test_a_failed_simulation_refuses_before_signing() -> None:
    rpc = FakeRpc(statuses=[CONFIRMED], sim_ok=False)
    result, _conn, signer = _run(rpc)
    assert result.status == "refused" and result.reason is not None
    assert result.reason.startswith("simulation_failed:")
    assert signer.sign_calls == 0 and rpc.sent == []


def test_unreadable_simulation_accounts_refuse_instead_of_guessing() -> None:
    rpc = FakeRpc(statuses=[CONFIRMED], sim_lamports=None)
    result, _conn, signer = _run(rpc)
    assert result == send.BatchResult(
        "refused", None, 0, 0, EXPECTED_RENT, "simulation_accounts_unreadable"
    )
    assert signer.sign_calls == 0


def test_the_verifier_runs_on_the_built_message_before_anything_is_signed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hunter_exchanges.pumpfun.solana_codec import AccountMeta, Instruction, compile_message

    other = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"

    def _bad_builder(*, wallet: str, accounts: Any, blockhash: str, **_: Any):
        close = Instruction(
            TOKEN_PROGRAM_ID,
            (
                AccountMeta(accounts[0], False, True),
                AccountMeta(other, False, True),  # refund to a stranger
                AccountMeta(wallet, True, False),
            ),
            bytes([9]),
        )
        return compile_message(wallet, [close], blockhash)

    monkeypatch.setattr(send, "build_batch_message", _bad_builder)
    rpc = FakeRpc(statuses=[CONFIRMED])
    result, _conn, signer = _run(rpc)
    assert result.status == "refused" and result.reason == "close_destination_not_wallet"
    assert signer.sign_calls == 0 and "simulate" not in rpc.log


def test_a_confirmation_that_times_out_stays_submitted_and_never_reports_a_recovery() -> None:
    rpc = FakeRpc(statuses=[None])
    result, conn, _signer = _run(rpc)
    assert result.status == "submitted" and result.signature == SIGNATURE
    assert result.lamports_recovered == 0 and result.n_closed == 0
    assert rpc.status_calls == send.CONFIRM_ATTEMPTS
    assert [e["event"] for e in conn.events] == ["close_atas_submitted"]


def test_a_send_that_raises_keeps_the_submitted_row_and_its_signature() -> None:
    rpc = FakeRpc(statuses=[CONFIRMED], raise_on_send=TimeoutError("relayed?"))
    result, conn, _signer = _run(rpc)
    assert result.status == "submitted" and result.signature == SIGNATURE
    assert conn.events[0]["data"]["signature"] == SIGNATURE
    assert "close_atas_failed" not in [e["event"] for e in conn.events]


def test_an_unreadable_status_stays_submitted() -> None:
    rpc = FakeRpc(statuses=[CONFIRMED], raise_on_status=ConnectionError("rpc down"))
    result, _conn, _signer = _run(rpc)
    assert result.status == "submitted" and result.signature == SIGNATURE


def test_a_transaction_that_fails_on_chain_is_failed_with_an_audit_row() -> None:
    rpc = FakeRpc(
        statuses=[{"confirmationStatus": "confirmed", "err": {"InstructionError": [2, 0]}}]
    )
    result, conn, _signer = _run(rpc)
    assert result.status == "failed" and result.signature == SIGNATURE
    assert result.lamports_recovered == 0
    assert [e["event"] for e in conn.events] == ["close_atas_submitted", "close_atas_failed"]


def test_a_confirmed_batch_whose_meta_shows_less_than_expected_is_reported_not_hidden() -> None:
    rpc = FakeRpc(
        statuses=[CONFIRMED],
        tx_meta={
            "transaction": {"message": {"accountKeys": [WALLET, "x"]}},
            "meta": {
                "err": None,
                "fee": 15_000,
                "preBalances": [BEFORE, RENT],
                "postBalances": [BEFORE - 15_000, RENT],
            },
        },
    )
    result, conn, _signer = _run(rpc)
    assert result.status == "confirmed"
    assert result.lamports_recovered == -15_000
    assert conn.events[1]["level"] == "warning"
    assert conn.events[1]["data"]["recovered_below_expected"] is True


def test_a_confirmed_batch_whose_meta_cannot_be_read_stays_submitted() -> None:
    """Astra must-fix 1: never fall back to the wallet delta — an unmeasured
    recovery is reported as such (exit 66 upstream: reconcile by signature)."""
    rpc = FakeRpc(statuses=[CONFIRMED], tx_meta=None)
    result, conn, _signer = _run(rpc)
    assert result.status == "submitted" and result.signature == SIGNATURE
    assert result.reason == "confirmed_recovery_unmeasured"
    assert result.lamports_recovered == 0
    assert rpc.tx_calls == send.TX_META_ATTEMPTS
    assert [e["event"] for e in conn.events] == ["close_atas_submitted"]


def test_a_meta_whose_first_account_is_not_the_wallet_is_not_trusted() -> None:
    rpc = FakeRpc(
        statuses=[CONFIRMED],
        tx_meta={
            "transaction": {"message": {"accountKeys": ["someone", WALLET]}},
            "meta": {"err": None, "fee": 1, "preBalances": [0, 1], "postBalances": [9, 1]},
        },
    )
    result, _conn, _signer = _run(rpc)
    assert result.status == "submitted" and result.reason == "confirmed_recovery_unmeasured"


def test_an_error_seen_only_at_processed_is_not_a_failure_yet() -> None:
    """Astra must-fix 2: a failure on a fork that is later dropped must not be
    recorded as ``failed`` — only a ``confirmed``/``finalized`` verdict ends it."""
    processed_error = {"confirmationStatus": "processed", "err": {"InstructionError": [2, 0]}}
    rpc = FakeRpc(statuses=[processed_error, processed_error, CONFIRMED])
    result, conn, _signer = _run(rpc)
    assert result.status == "confirmed"
    assert rpc.status_calls == 3
    assert "close_atas_failed" not in [e["event"] for e in conn.events]


def test_an_error_that_never_reaches_confirmed_stays_submitted() -> None:
    processed_error = {"confirmationStatus": "processed", "err": {"InstructionError": [2, 0]}}
    rpc = FakeRpc(statuses=[processed_error])
    result, conn, _signer = _run(rpc)
    assert result.status == "submitted" and result.reason == "confirm_pending"
    assert rpc.status_calls == send.CONFIRM_ATTEMPTS
    assert [e["event"] for e in conn.events] == ["close_atas_submitted"]


def test_result_json_line_names_every_field_everton_needs() -> None:
    result = send.BatchResult("confirmed", SIGNATURE, 3, 6_000_000, 6_117_840, None)
    line = json.loads(send.result_json(result, batch_index=2))
    assert line == {
        "batch": 2,
        "status": "confirmed",
        "signature": SIGNATURE,
        "n_closed": 3,
        "lamports_recovered": 6_000_000,
        "sol_recovered": "0.006000000",
        "expected_rent_lamports": 6_117_840,
        "reason": None,
    }
