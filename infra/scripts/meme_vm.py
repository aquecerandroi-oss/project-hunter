#!/usr/bin/env python3
"""VM1-VM9 (docs/RISK_ENGINE_MEME.md section 11): run what exists, name what does not.

Usage:
    timeout 290 uv run python infra/scripts/meme_vm.py            # table + exit code
    timeout 290 uv run python infra/scripts/meme_vm.py --json     # machine-readable

Exit codes: 0 all PASS; 2 no FAIL but at least one PENDING; 1 any FAIL.

T4.8: the execution path (signer, verifier, submitter, quote) runs for real over the
recorded mainnet fixtures with in-memory fakes — T4.8b: the post-upgrade ones
(``t48b_*``, program of 2026-09-12 15:24 UTC). T4.14: VM1/VM2/VM3/VM7 run over the
engine (``meme_vm_engine.py``); VM6(c) and the Postgres halves of VM8/VM9 stay PENDING
by name (paper simulator / ``services/meme-executor/tests/test_live_persistence.py``).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hunter_core.execution.meme.base58 import b58encode
from hunter_core.execution.meme.journal import InMemoryOrderJournal, SubmitState
from hunter_core.execution.meme.signer import ENV_SECRET_KEY, MemeSigner
from hunter_core.execution.meme.submit import ApprovedSubmission, MemeSubmitter, SubmitPolicy
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.global_state import GlobalAccount, decode_global_account
from hunter_exchanges.pumpfun.quote import BONDING_CURVE_FEE_TIER_2026_05_20 as FEES
from hunter_exchanges.pumpfun.quote import CurveReserves, quote_buy
from hunter_exchanges.pumpfun.solana_codec import serialize_message
from hunter_exchanges.pumpfun.trade_event import trade_events_from_transaction
from hunter_exchanges.pumpfun.tx import TradeIntent, build_buy_instruction, build_trade_message
from hunter_exchanges.pumpfun.tx_rpc import SimulationResult
from hunter_exchanges.pumpfun.verify import ExecutionCaps, UnverifiedTransaction
from hunter_exchanges.pumpfun.verify import verify_trade_message as verify_message

sys.path.insert(0, str(Path(__file__).resolve().parent))
from meme_vm_engine import vm1_sizing, vm2_caps, vm3_kill_switch, vm7_rug_during_hold

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "packages/exchange-adapters/tests/fixtures/pumpfun"
NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
ENGINE_MISSING = "Postgres half: services/meme-executor/tests/test_live_persistence.py"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"  # noqa: S105 - program id
BLOCKHASH = "BQ8v5pyUzayNkgPghSBd36pVgG14SGLExT5kwWkmYZWJ"
ENGINE_VMS = {
    "VM1": vm1_sizing,
    "VM2": vm2_caps,
    "VM3": vm3_kill_switch,
    "VM7": vm7_rug_during_hold,
}


@dataclass
class Outcome:
    vm: str
    status: str  # PASS | FAIL | PENDING
    detail: str


@dataclass
class FakeRpc:
    """Scripted RPC, no network. ``send_error`` simulates a transport failure mid-send."""

    send_error: Exception | None = None
    statuses: list[dict[str, Any] | None] = field(
        default_factory=lambda: [{"confirmationStatus": "confirmed", "err": None}]
    )
    transaction: dict[str, Any] | None = None
    block_height: int = 100
    sent: list[bytes] = field(default_factory=lambda: list[bytes]())
    status_calls: int = 0
    simulate_hook: Callable[[], None] | None = None

    def simulate_transaction(self, transaction: bytes, **_: Any) -> SimulationResult:
        if self.simulate_hook is not None:
            self.simulate_hook()
        return SimulationResult(True, None, (), None, None, None)

    def send_transaction(self, transaction: bytes, *, max_retries: int = 0) -> str:
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(transaction)
        return b58encode(transaction[1:65])

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        self.status_calls += 1
        return [self.statuses[min(self.status_calls - 1, len(self.statuses) - 1)]]

    def get_transaction(self, signature: str, **_: Any) -> dict[str, Any] | None:
        return self.transaction

    def get_block_height(self, **_: Any) -> int:
        return self.block_height


class RpcDown(Exception):
    retryable = True


@dataclass(frozen=True)
class Scenario:
    signer: MemeSigner
    message: bytes
    intent: TradeIntent
    global_account: GlobalAccount
    caps: ExecutionCaps

    def verify(self, raw: bytes) -> object:
        return verify_message(raw, self.intent, self.global_account, self.caps)

    def approval(self, pid: str = "p1", *, expires: datetime | None = None) -> ApprovedSubmission:
        return ApprovedSubmission(pid, expires or NOW + timedelta(seconds=5), self.message, 150)


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _scenario() -> Scenario:
    seed = random.Random(20260912).randbytes(32)
    key = Ed25519PrivateKey.from_private_bytes(seed)
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    env = {ENV_SECRET_KEY: b58encode(seed + pub)}
    signer = MemeSigner.from_environment(env)
    assert ENV_SECRET_KEY not in env
    g = _fixture("t48b_rpc_global_account_raw.json")["result"]["value"]
    global_account = decode_global_account(g["data"][0], owner=g["owner"])
    (event,) = trade_events_from_transaction(
        _fixture("t48b_rpc_tx_sell_raw.json")["result"], program_id=PUMP_PROGRAM_ID
    )
    intent = TradeIntent(
        "buy",
        event.mint,
        signer.pubkey,
        event.creator,
        TOKEN_2022,
        event.token_amount,
        990000001,
        global_account.fee_recipients_for(is_mayhem_mode=event.mayhem_mode)[0],
        global_account.buyback_fee_recipients[0],
        event.mayhem_mode,
    )
    message = build_trade_message(
        build_buy_instruction(intent, global_account),
        payer=signer.pubkey,
        recent_blockhash=BLOCKHASH,
        compute_unit_limit=400_000,
        compute_unit_price_micro_lamports=10_000,
    )
    caps = ExecutionCaps(400_000, 10_000)
    return Scenario(signer, serialize_message(message), intent, global_account, caps)


def _submitter(rpc: FakeRpc, sc: Scenario, journal: InMemoryOrderJournal) -> MemeSubmitter:
    rpc.transaction = rpc.transaction or _fixture("t48b_rpc_tx_sell_raw.json")["result"]
    policy = SubmitPolicy(True, "devnet", confirm_timeout_s=3.0, poll_interval_s=0.0)
    return MemeSubmitter(
        rpc=rpc,
        signer=sc.signer,
        journal=journal,
        verify=sc.verify,
        decode_fill=lambda tx: trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID),
        policy=policy,
        now=lambda: NOW,
        sleep=lambda _s: None,
    )


def vm4_duplicate_submission() -> Outcome:
    sc = _scenario()
    rpc, journal = FakeRpc(), InMemoryOrderJournal()
    sub = _submitter(rpc, sc, journal)
    first = sub.submit(sc.approval())
    second = sub.submit(sc.approval())  # retry of the same proposal
    tx = rpc.transaction or {}
    stream_a = sub.on_stream_event(str(first.signature), tx)
    stream_b = sub.on_stream_event(str(first.signature), tx)  # redelivered
    rows = journal.rows()
    checks = [
        first.state is SubmitState.CONFIRMED,
        second.replayed and second.signature == first.signature,
        len(rpc.sent) == 1 and len(rows) == 1 and rows[0].signatures == [first.signature],
        stream_a is not None and stream_b is not None and stream_b.replayed,
        stream_a is not None and stream_b is not None and stream_b.fill == stream_a.fill,
    ]
    detail = (
        f"1 signature for 2 submits ({len(rpc.sent)} send); stream event redelivered -> "
        "replayed; new blockhash = new proposal by construction (signature = f(message))"
    )
    return Outcome("VM4", "PASS" if all(checks) else "FAIL", detail)


def vm5_rpc_failure_midsend() -> Outcome:
    sc = _scenario()
    rpc, journal = FakeRpc(send_error=RpcDown()), InMemoryOrderJournal()
    sub = _submitter(rpc, sc, journal)
    result = sub.submit(sc.approval())
    retry = sub.submit(sc.approval())
    rpc.send_error = None
    settled = sub.reconcile("p1")
    row = journal.rows()[0]
    checks = [
        result.state is SubmitState.SUBMITTED_UNCONFIRMED,
        result.reason.startswith("rpc_unreachable_after_send"),
        retry.replayed and len(row.signatures) == 1 and rpc.sent == [],
        settled is not None and settled.state is SubmitState.CONFIRMED,
        settled is not None and settled.signature == result.signature,
    ]
    detail = (
        f"timeout after send -> {result.state}:{result.reason}; retry -> replayed (no blind "
        f"resend, {len(row.signatures)} signature); reconcile -> "
        f"{settled.state if settled is not None else None}"
    )
    return Outcome("VM5", "PASS" if all(checks) else "FAIL", detail)


def vm6_partial_or_no_fill() -> Outcome:
    proof = _fixture("t48b_simulation_proof_mainnet_raw.json")["simulations"]
    short = proof["buy_max_sol_cost_one_lamport_short"]
    a = short["ok"] is False and short["err"]["InstructionError"][1] == {"Custom": 6002}
    (event,) = trade_events_from_transaction(
        _fixture("rpc_tx_buy_raw.json")["result"], program_id=PUMP_PROGRAM_ID
    )
    reserves = CurveReserves(
        event.virtual_sol_reserves - event.sol_amount,
        event.virtual_token_reserves + event.token_amount,
        1,
        event.real_token_reserves + event.token_amount,
    )
    quote = quote_buy(reserves, event.token_amount, FEES, max_slippage_bps=100)
    b = event.token_amount == quote.token_amount and event.buy_total_cost == quote.total_cost
    detail = (
        f"(a) max_sol_cost short -> TooMuchSolRequired 6002, no position: {a}; (b) fill = "
        f"TradeEvent token_amount {event.token_amount}, cost {event.buy_total_cost} lamports "
        f"(event, not quote): {b}; (c) paper 'no later snapshot -> no fill': PENDING "
        "(paper simulator, T4.5/T4.6)"
    )
    return Outcome("VM6", "PENDING" if a and b else "FAIL", detail)


def vm8_restart_open_position() -> Outcome:
    sc = _scenario()
    journal = InMemoryOrderJournal()
    before = _submitter(FakeRpc(statuses=[None]), sc, journal).submit(sc.approval())
    rpc2 = FakeRpc()  # "restart": a new process over the same rows; the chain now shows the tx
    sub2 = _submitter(rpc2, sc, journal)
    after = sub2.reconcile("p1")
    late = sub2.submit(sc.approval("p2", expires=NOW - timedelta(seconds=1)))
    checks = [
        before.state is SubmitState.SUBMITTED_UNCONFIRMED,
        after is not None and after.state is SubmitState.CONFIRMED,
        after is not None and after.signature == before.signature,
        rpc2.sent == [] and late.reason == "reservation_expired",
    ]
    detail = (
        f"rows rebuilt -> reconcile {after.state if after is not None else None} with the same "
        f"signature, nothing re-sent: {all(checks[:3])}; expired approval -> {late.reason}; "
        f"position rebuild + chain reconciliation of meme_live_positions: PENDING ({ENGINE_MISSING})"
    )
    return Outcome("VM8", "PENDING" if all(checks) else "FAIL", detail)


def vm9_concurrent_sessions() -> Outcome:
    sc = _scenario()
    inside, proceed = threading.Event(), threading.Event()

    def hold() -> None:
        inside.set()
        proceed.wait(5)

    rpc, journal = FakeRpc(simulate_hook=hold), InMemoryOrderJournal()
    sub = _submitter(rpc, sc, journal)
    first: list[Any] = []
    session_a = threading.Thread(target=lambda: first.append(sub.submit(sc.approval())))
    session_a.start()
    inside.wait(5)
    second = sub.submit(sc.approval())
    proceed.set()
    session_a.join(10)
    ok = bool(first) and first[0].state is SubmitState.CONFIRMED
    ok = ok and second.reason == "signing_locked" and len(rpc.sent) == 1
    detail = (
        f"two sessions, one signature: {ok} (second -> {second.reason}); kill switch re-read "
        f"inside the effect transaction + lock order system->org->wallet: PENDING "
        f"({ENGINE_MISSING})"
    )
    return Outcome("VM9", "PENDING" if ok else "FAIL", detail)


def adversarial_gate() -> Outcome:
    """Not a VM number: section 12 item 4 - a tampered transaction is refused."""
    sc = _scenario()
    tampered = bytearray(sc.message)
    tampered[-9] ^= 0x01  # flip a bit inside max_sol_cost (last 8 bytes of the trade data)
    try:
        verify_message(bytes(tampered), sc.intent, sc.global_account, sc.caps)
    except UnverifiedTransaction as exc:
        return Outcome("9.1", "PASS", f"tampered max_sol_cost refused: {exc.reason}")
    return Outcome("9.1", "FAIL", "tampered transaction was accepted")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    def engine(vm: str) -> Outcome:
        try:
            ok, detail = ENGINE_VMS[vm]()
        except Exception as exc:
            return Outcome(vm, "FAIL", f"{type(exc).__name__}: {exc}")
        return Outcome(vm, "PASS" if ok else "FAIL", detail)

    outcomes = [
        engine("VM1"),
        engine("VM2"),
        engine("VM3"),
        vm4_duplicate_submission(),
        vm5_rpc_failure_midsend(),
        vm6_partial_or_no_fill(),
        engine("VM7"),
        vm8_restart_open_position(),
        vm9_concurrent_sessions(),
        adversarial_gate(),
    ]
    if args.json:
        print(json.dumps([o.__dict__ for o in outcomes], indent=1))
    else:
        print(f"meme_vm - {datetime.now(UTC).isoformat()} (UTC)")
        for o in outcomes:
            print(f"{o.vm:<5} {o.status:<8} {o.detail}")
    if any(o.status == "FAIL" for o in outcomes):
        return 1
    return 2 if any(o.status == "PENDING" for o in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())
