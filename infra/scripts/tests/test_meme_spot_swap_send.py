"""``meme_spot_swap_send.run_apply_leg`` (T4.73b) end to end with fakes:
quote (real recorded fixture) -> swap tx (synthetic v0 wire bytes for the
wallet, built like ``test_spot_verify.py``) -> the real verifier -> simulate
(fake RPC answering ``accounts``) -> sign (fake signer, 64 zero bytes) ->
send (fake) -> confirm (fake statuses). No network, no database, no key.

Covers the review of commit ``8fc9dcbe`` (``.claude/state/review-T4.73.md``):
finding 1 (the invariant must read ``simulation.accounts``), finding 2 (a
confirmation that times out stays ``submitted`` and never returns
``confirmed``), finding 3 (every row write is committed on its own, so an
exception after ``sendTransaction`` cannot roll the ``submitted`` row back)
and finding 5 (the impact cap runs inside the leg, so the sell-back gets it).
"""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in ("services/meme-executor", "packages/exchange-adapters", "packages/risk-core"):
    candidate = str(REPO_ROOT / extra)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)
FIXTURE = REPO_ROOT / "packages/exchange-adapters/tests/fixtures/jupiter/quote_sol_to_wif_real.json"

import meme_spot_swap_send as send  # noqa: E402

from hunter_exchanges.jupiter.models import JupiterQuote, JupiterSwapTransaction  # noqa: E402
from hunter_exchanges.pumpfun.solana_codec import (  # noqa: E402
    ASSOCIATED_TOKEN_PROGRAM_ID,
    COMPUTE_BUDGET_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    CompiledInstruction,
    Message,
    associated_token_address,
    b58encode,
    serialize_message,
    serialize_transaction,
)
from hunter_exchanges.pumpfun.tx_rpc import SimulationResult  # noqa: E402
from hunter_meme_executor.treasury_rules import JUP_PROGRAM_ID  # noqa: E402
from hunter_meme_executor.treasury_verify import ROUTE_DISCRIMINATOR  # noqa: E402

WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
WSOL = "So11111111111111111111111111111111111111112"
WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
SIGNATURE = b58encode(bytes(64))  # what FakeSigner's 64 zero bytes encode to
IN_LAMPORTS = 20_000_000
THRESHOLD = 10_402_273  # the fixture's otherAmountThreshold
SELL_IN = 10_402_273
SELL_OUT = 19_950_000
SELL_THRESHOLD = 19_850_000
WALLET_LAMPORTS = 760_000_000
_TAIL = struct.Struct("<QQHB")


# --------------------------------------------------------------------- fakes


def _quote() -> JupiterQuote:
    return JupiterQuote.from_json(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _sell_quote() -> JupiterQuote:
    """The fixture with the pair reversed: WIF -> SOL, the round trip's sell-back."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload.update(
        {
            "inputMint": WIF,
            "outputMint": WSOL,
            "inAmount": str(SELL_IN),
            "outAmount": str(SELL_OUT),
            "otherAmountThreshold": str(SELL_THRESHOLD),
        }
    )
    return JupiterQuote.from_json(payload)


def _v0_tx_b64(keys: tuple[str, ...], instructions: tuple[CompiledInstruction, ...]) -> str:
    legacy = Message(
        num_required_signatures=1,
        num_readonly_signed=0,
        num_readonly_unsigned=6,
        account_keys=keys,
        recent_blockhash=b58encode(bytes([7]) * 32),
        instructions=instructions,
    )
    message_bytes = b"\x80" + serialize_message(legacy) + b"\x00"  # v0 prefix, no lookups
    return base64.b64encode(serialize_transaction((bytes(64),), message_bytes)).decode("ascii")


def unwrap_tx_b64(*, in_amount: int = SELL_IN, out_amount: int = SELL_OUT) -> str:
    """WIF -> SOL for ``WALLET``: create own WSOL ATA, one JUP6 ``route``
    (source = WIF ATA, destination = WSOL ATA), CloseAccount (unwrap)."""
    wsol_ata = associated_token_address(WALLET, WSOL, token_program=TOKEN_PROGRAM_ID)
    wif_ata = associated_token_address(WALLET, WIF, token_program=TOKEN_PROGRAM_ID)
    keys = (
        WALLET,
        JUP_PROGRAM_ID,
        TOKEN_PROGRAM_ID,
        wsol_ata,
        wif_ata,
        ASSOCIATED_TOKEN_PROGRAM_ID,
        SYSTEM_PROGRAM_ID,
        COMPUTE_BUDGET_PROGRAM_ID,
        WSOL,
        WIF,
    )
    route = (
        ROUTE_DISCRIMINATOR
        + struct.pack("<I", 1)
        + bytes((0, 100, 0, 1))
        + _TAIL.pack(in_amount, out_amount, 50, 0)
    )
    instructions = (
        CompiledInstruction(5, (0, 3, 0, 8, 6, 2), b"\x01"),
        CompiledInstruction(1, (0, 0, 4, 3, 1, 0, 1), route),
        CompiledInstruction(2, (3, 0, 0), bytes([9])),  # CloseAccount -> wallet
    )
    return _v0_tx_b64(keys, instructions)


def wrap_tx_b64(*, in_amount: int = IN_LAMPORTS, out_amount: int = 10_454_545) -> str:
    """A v0 transaction (one zeroed signature) for ``WALLET`` buying WIF with
    SOL: ComputeBudget x2, create own WSOL ATA, System.Transfer (wrap),
    SyncNative, one JUP6 ``route`` — the shape ``test_spot_verify`` proves."""
    wsol_ata = associated_token_address(WALLET, WSOL, token_program=TOKEN_PROGRAM_ID)
    wif_ata = associated_token_address(WALLET, WIF, token_program=TOKEN_PROGRAM_ID)
    keys = (
        WALLET,
        JUP_PROGRAM_ID,
        TOKEN_PROGRAM_ID,
        wsol_ata,
        wif_ata,
        ASSOCIATED_TOKEN_PROGRAM_ID,
        SYSTEM_PROGRAM_ID,
        COMPUTE_BUDGET_PROGRAM_ID,
        WSOL,
        WIF,
    )
    route = (
        ROUTE_DISCRIMINATOR
        + struct.pack("<I", 1)
        + bytes((0, 100, 0, 1))
        + _TAIL.pack(in_amount, out_amount, 50, 0)
    )
    instructions = (
        CompiledInstruction(7, (), bytes([2]) + struct.pack("<I", 100_000)),
        CompiledInstruction(7, (), bytes([3]) + struct.pack("<Q", 1)),
        CompiledInstruction(5, (0, 3, 0, 8, 6, 2), b"\x01"),
        CompiledInstruction(6, (0, 3), struct.pack("<I", 2) + struct.pack("<Q", in_amount)),
        CompiledInstruction(2, (3,), bytes([17])),
        CompiledInstruction(1, (0, 0, 3, 4, 1, 0, 1), route),
    )
    return _v0_tx_b64(keys, instructions)


class FakeJupiter:
    def __init__(self, *, tx_b64: str | None = None, quote: JupiterQuote | None = None) -> None:
        self.tx_b64 = tx_b64 or wrap_tx_b64()
        self._quote = quote or _quote()
        self.swap_calls = 0

    def quote(self, **_kwargs: Any) -> JupiterQuote:
        return self._quote

    def swap(self, *, quote: JupiterQuote, user_public_key: str) -> JupiterSwapTransaction:
        self.swap_calls += 1
        assert user_public_key == WALLET
        return JupiterSwapTransaction(
            swap_transaction_b64=self.tx_b64,
            last_valid_block_height=None,
            prioritization_fee_lamports=None,
        )


@dataclass
class FakeRpc:
    sim_accounts: tuple[dict[str, Any] | None, ...] | None
    statuses: list[dict[str, Any] | None]
    sim_ok: bool = True
    sent: list[bytes] = field(default_factory=lambda: [])
    status_calls: int = 0
    raise_on_status: Exception | None = None
    raise_on_send: Exception | None = None

    def simulate_transaction(
        self, raw: bytes, *, sig_verify: bool, accounts: tuple[str, ...]
    ) -> SimulationResult:
        assert sig_verify is False
        assert accounts == (
            WALLET,
            associated_token_address(WALLET, WIF, token_program=TOKEN_PROGRAM_ID),
        )
        return SimulationResult(
            ok=self.sim_ok,
            err=None if self.sim_ok else {"InstructionError": [5, "Custom"]},
            logs=(),
            units_consumed=1,
            slot=1,
            return_data=None,
            accounts=() if self.sim_accounts is None else self.sim_accounts,
        )

    def send_transaction(self, signed: bytes) -> str:
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


@dataclass
class _Wallet:
    lamports: int


@dataclass
class _Token:
    exists: bool
    amount: int


class FakeChain:
    """Balances: the first token read and the first two wallet reads are
    "before"; any read after the send is "after" (the fill has landed)."""

    def __init__(
        self,
        rpc: FakeRpc,
        *,
        token_before: int = 0,
        token_after_confirm: int = THRESHOLD,
        lamports_after_confirm: int = WALLET_LAMPORTS,
    ) -> None:
        self.rpc = rpc
        self.token_reads = 0
        self.token_before = token_before
        self.token_after_confirm = token_after_confirm
        self.lamports_after_confirm = lamports_after_confirm

    def wallet(self, pubkey: str) -> _Wallet:
        assert pubkey == WALLET
        landed = bool(self.rpc.sent)
        return _Wallet(lamports=self.lamports_after_confirm if landed else WALLET_LAMPORTS)

    def token_account(self, owner: str, mint: str, program: str) -> _Token:
        assert mint == WIF
        self.token_reads += 1
        if self.token_reads == 1:
            return _Token(exists=self.token_before > 0, amount=self.token_before)
        return _Token(exists=True, amount=self.token_after_confirm)


class FakeSigner:
    pubkey = WALLET

    def __init__(self) -> None:
        self.sign_calls = 0

    def sign(self, message_bytes: bytes) -> bytes:
        self.sign_calls += 1
        return bytes(64)


class FakeConn:
    """Records every statement and every commit, in order."""

    def __init__(self) -> None:
        self.log: list[tuple[str, dict[str, Any] | None]] = []

    async def execute(self, statement: Any, parameters: Any = None, /) -> Any:
        self.log.append((str(statement), parameters))
        return object()

    async def commit(self) -> None:
        self.log.append(("COMMIT", None))

    def statuses(self) -> list[str]:
        out: list[str] = []
        for sql, params in self.log:
            if sql == "COMMIT":
                out.append("COMMIT")
            elif "INSERT INTO meme_treasury_swaps" in sql:
                out.append(f"insert:{params['status']}" if params else "insert")
            elif "status = 'refused'" in sql:
                out.append(f"refused:{params['refusal']}" if params else "refused")
            elif "status = 'submitted'" in sql:
                out.append("submitted")
            elif "status = 'confirmed'" in sql:
                out.append("confirmed")
            elif "SET status = :status" in sql and params:
                out.append(str(params["status"]))
            elif "system_events" in sql:
                out.append("event")
        return out


def _accounts(*, lamports: int, token_amount: int | None) -> tuple[dict[str, Any] | None, ...]:
    token: dict[str, Any] | None = (
        None
        if token_amount is None
        else {"data": {"parsed": {"info": {"tokenAmount": {"amount": str(token_amount)}}}}}
    )
    return ({"lamports": lamports}, token)


def _run(
    conn: FakeConn,
    chain: FakeChain,
    client: FakeJupiter,
    signer: FakeSigner,
    **overrides: Any,
) -> send.LegResult:
    kwargs: dict[str, Any] = {
        "reason": "t",
        "input_mint": WSOL,
        "output_mint": WIF,
        "amount_atoms": IN_LAMPORTS,
        "slippage_bps": 50,
        "max_impact_pct": Decimal("1"),
    }
    kwargs.update(overrides)
    return asyncio.run(send.run_apply_leg(conn, chain, client, signer, **kwargs))  # type: ignore[arg-type]


# --------------------------------------------------------------------- tests


def test_buy_leg_end_to_end_confirms_and_commits_every_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 1: the fixture's buy (0,02 SOL, threshold 10 402 273) passes
    once the invariant reads the simulated post-state instead of two live
    reads. Finding 3: each row write is followed by its own commit."""
    monkeypatch.setattr(send, "CONFIRM_INTERVAL_S", 0.0)
    rpc = FakeRpc(
        sim_accounts=_accounts(
            lamports=WALLET_LAMPORTS - IN_LAMPORTS - 2_100_000, token_amount=THRESHOLD
        ),
        statuses=[None, {"confirmationStatus": "confirmed", "err": None}],
    )
    conn, chain, client, signer = FakeConn(), FakeChain(rpc), FakeJupiter(), FakeSigner()
    result = _run(conn, chain, client, signer)
    assert result.status == "confirmed"
    assert result.filled == THRESHOLD
    assert result.signature == SIGNATURE
    assert signer.sign_calls == 1 and len(rpc.sent) == 1
    assert conn.statuses() == [
        "insert:quoted",
        "COMMIT",
        "simulated",
        "COMMIT",
        "submitted",
        "COMMIT",
        "confirmed",
        "COMMIT",
        "event",
        "COMMIT",
    ]


@pytest.mark.parametrize(
    ("lamports", "token_amount", "expected"),
    [
        (WALLET_LAMPORTS - IN_LAMPORTS - 2_100_000, THRESHOLD - 1, "simulation_token_short"),
        (WALLET_LAMPORTS - IN_LAMPORTS - 20_000_000, THRESHOLD, "simulation_sol_overspent"),
    ],
)
def test_buy_leg_refuses_when_the_simulated_post_state_is_short(
    lamports: int, token_amount: int, expected: str
) -> None:
    rpc = FakeRpc(sim_accounts=_accounts(lamports=lamports, token_amount=token_amount), statuses=[])
    conn, chain, client, signer = FakeConn(), FakeChain(rpc), FakeJupiter(), FakeSigner()
    result = _run(conn, chain, client, signer)
    assert result.status == "refused"
    assert signer.sign_calls == 0 and rpc.sent == []
    assert conn.statuses() == ["insert:quoted", "COMMIT", f"refused:{expected}", "COMMIT"]


def test_buy_leg_refuses_when_simulation_accounts_are_unreadable() -> None:
    rpc = FakeRpc(sim_accounts=None, statuses=[])
    conn, chain, client, signer = FakeConn(), FakeChain(rpc), FakeJupiter(), FakeSigner()
    result = _run(conn, chain, client, signer)
    assert result.status == "refused"
    assert signer.sign_calls == 0
    assert conn.statuses()[-2] == "refused:simulation_accounts_unreadable"

    rpc = FakeRpc(sim_accounts=_accounts(lamports=WALLET_LAMPORTS, token_amount=None), statuses=[])
    conn, chain, client, signer = FakeConn(), FakeChain(rpc), FakeJupiter(), FakeSigner()
    result = _run(conn, chain, client, signer)
    assert result.status == "refused"
    assert conn.statuses()[-2] == "refused:simulation_accounts_unreadable"


def test_buy_leg_refuses_a_failed_simulation_before_signing() -> None:
    rpc = FakeRpc(sim_accounts=_accounts(lamports=1, token_amount=1), statuses=[], sim_ok=False)
    conn, chain, client, signer = FakeConn(), FakeChain(rpc), FakeJupiter(), FakeSigner()
    result = _run(conn, chain, client, signer)
    assert result.status == "refused"
    assert signer.sign_calls == 0
    assert conn.statuses()[-2].startswith("refused:simulation_failed:")


def test_confirmation_timeout_leaves_the_row_submitted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding 2: 20 x pending -> ``submitted`` with the signature, never
    ``confirmed`` with ``filled=0``."""
    monkeypatch.setattr(send, "CONFIRM_INTERVAL_S", 0.0)
    rpc = FakeRpc(
        sim_accounts=_accounts(
            lamports=WALLET_LAMPORTS - IN_LAMPORTS - 2_100_000, token_amount=THRESHOLD
        ),
        statuses=[None],
    )
    conn, chain, client, signer = FakeConn(), FakeChain(rpc), FakeJupiter(), FakeSigner()
    result = _run(conn, chain, client, signer)
    assert result.status == "submitted"
    assert result.filled == 0
    assert result.signature == SIGNATURE
    assert rpc.status_calls == send.CONFIRM_ATTEMPTS
    assert "confirmed" not in conn.statuses()
    assert conn.statuses()[-2:] == ["submitted", "COMMIT"]


def test_failure_after_mark_submitted_keeps_the_committed_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 3: an RPC error while polling the signature must not undo the
    on-chain send's row — it is already committed, and the leg reports
    ``submitted`` so the caller can reconcile by signature."""
    monkeypatch.setattr(send, "CONFIRM_INTERVAL_S", 0.0)
    rpc = FakeRpc(
        sim_accounts=_accounts(
            lamports=WALLET_LAMPORTS - IN_LAMPORTS - 2_100_000, token_amount=THRESHOLD
        ),
        statuses=[],
        raise_on_status=ConnectionError("rpc down"),
    )
    conn, chain, client, signer = FakeConn(), FakeChain(rpc), FakeJupiter(), FakeSigner()
    result = _run(conn, chain, client, signer)
    assert result.status == "submitted"
    assert result.signature == SIGNATURE
    assert conn.statuses()[-2:] == ["submitted", "COMMIT"]


def test_on_chain_failure_marks_the_row_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(send, "CONFIRM_INTERVAL_S", 0.0)
    rpc = FakeRpc(
        sim_accounts=_accounts(
            lamports=WALLET_LAMPORTS - IN_LAMPORTS - 2_100_000, token_amount=THRESHOLD
        ),
        statuses=[{"err": {"InstructionError": [5, "Custom"]}, "confirmationStatus": "confirmed"}],
    )
    conn, chain, client, signer = FakeConn(), FakeChain(rpc), FakeJupiter(), FakeSigner()
    result = _run(conn, chain, client, signer)
    assert result.status == "failed"
    assert conn.statuses()[-2:] == ["failed", "COMMIT"]


def test_verifier_refusal_never_simulates_or_signs() -> None:
    """A route whose ``in_amount`` differs from the request is refused by the
    real verifier before any RPC call."""
    rpc = FakeRpc(sim_accounts=None, statuses=[])
    client = FakeJupiter(tx_b64=wrap_tx_b64(in_amount=999))
    conn, chain, signer = FakeConn(), FakeChain(rpc), FakeSigner()
    result = _run(conn, chain, client, signer)
    assert result.status == "refused"
    assert signer.sign_calls == 0
    assert conn.statuses()[-2].startswith("refused:route_in_amount_mismatch") or conn.statuses()[
        -2
    ].startswith("refused:system_transfer")


def test_impact_cap_runs_inside_the_leg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding 5: the sell-back calls ``run_apply_leg`` directly, so the cap
    has to live here — a quote with 2% impact against a 1% cap is refused
    before ``POST /swap``."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["priceImpactPct"] = "0.02"
    client = FakeJupiter(quote=JupiterQuote.from_json(payload))
    rpc = FakeRpc(sim_accounts=None, statuses=[])
    conn, chain, signer = FakeConn(), FakeChain(rpc), FakeSigner()
    result = _run(conn, chain, client, signer)
    assert result.status == "refused"
    assert client.swap_calls == 0
    assert conn.statuses()[-2].startswith("refused:price_impact_above_cap:")


# --- T4.73b, Astra's second opinion on the send path


def test_sell_leg_end_to_end_measures_the_fill_in_lamports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The round trip's sell-back (WIF -> SOL): the invariant reads the
    simulated post-state of both accounts, and ``filled`` is the SOL that
    landed, not the token delta (which is negative on a sell)."""
    monkeypatch.setattr(send, "CONFIRM_INTERVAL_S", 0.0)
    rpc = FakeRpc(
        sim_accounts=_accounts(lamports=WALLET_LAMPORTS + SELL_THRESHOLD - 5_000, token_amount=0),
        statuses=[{"confirmationStatus": "confirmed", "err": None}],
    )
    chain = FakeChain(
        rpc,
        token_before=SELL_IN,
        token_after_confirm=0,
        lamports_after_confirm=WALLET_LAMPORTS + SELL_OUT - 5_000,
    )
    client = FakeJupiter(tx_b64=unwrap_tx_b64(), quote=_sell_quote())
    conn, signer = FakeConn(), FakeSigner()
    result = _run(
        conn, chain, client, signer, input_mint=WIF, output_mint=WSOL, amount_atoms=SELL_IN
    )
    assert result.status == "confirmed"
    assert result.filled == SELL_OUT - 5_000
    assert conn.statuses()[-4:] == ["confirmed", "COMMIT", "event", "COMMIT"]


def test_sell_leg_refuses_when_the_simulated_sol_is_short() -> None:
    rpc = FakeRpc(
        sim_accounts=_accounts(lamports=WALLET_LAMPORTS + 1_000_000, token_amount=0), statuses=[]
    )
    chain = FakeChain(rpc, token_before=SELL_IN, token_after_confirm=0)
    client = FakeJupiter(tx_b64=unwrap_tx_b64(), quote=_sell_quote())
    conn, signer = FakeConn(), FakeSigner()
    result = _run(
        conn, chain, client, signer, input_mint=WIF, output_mint=WSOL, amount_atoms=SELL_IN
    )
    assert result.status == "refused"
    assert signer.sign_calls == 0
    assert conn.statuses()[-2] == "refused:simulation_sol_short"


def test_the_signature_is_persisted_before_the_broadcast_and_a_send_error_keeps_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``sendTransaction`` that raises may still have broadcast (HTTP timeout
    after relay): the row must already be ``submitted`` with the locally
    derived signature, never ``failed`` without one."""
    monkeypatch.setattr(send, "CONFIRM_INTERVAL_S", 0.0)
    rpc = FakeRpc(
        sim_accounts=_accounts(
            lamports=WALLET_LAMPORTS - IN_LAMPORTS - 2_100_000, token_amount=THRESHOLD
        ),
        statuses=[],
        raise_on_send=TimeoutError("relay timeout"),
    )
    conn, chain, client, signer = FakeConn(), FakeChain(rpc), FakeJupiter(), FakeSigner()
    result = _run(conn, chain, client, signer)
    assert result.status == "submitted"
    assert result.signature == SIGNATURE
    assert conn.statuses()[-2:] == ["submitted", "COMMIT"]
    assert "failed" not in conn.statuses()
    submitted = [p for sql, p in conn.log if "status = 'submitted'" in sql]
    assert submitted and submitted[0] is not None and submitted[0]["signature"] == SIGNATURE
