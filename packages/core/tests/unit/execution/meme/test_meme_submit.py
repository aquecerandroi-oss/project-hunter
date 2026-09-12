"""The submit state machine (§9.2–§9.6): states, named reasons, two-key idempotency."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from hunter_core.execution.meme.journal import InMemoryOrderJournal, SubmitState
from hunter_core.execution.meme.signer import ENV_SECRET_KEY, MemeSigner
from hunter_core.execution.meme.submit import (
    ApprovedSubmission,
    MemeLiveTradingDisabled,
    MemeSubmitter,
    SubmitPolicy,
)
from packages.core.tests.unit.execution.meme.conftest import TestKey

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
MESSAGE = b"\x01\x00\x01" + b"\x02" + b"\x11" * 64 + b"\x22" * 32 + b"\x00"


class Unverified(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class RpcRefused(Exception):
    retryable = False


class RpcDown(Exception):
    retryable = True


@dataclass
class Sim:
    ok: bool
    err: Any = None


@dataclass
class FakeRpc:
    simulate_ok: bool = True
    send_error: Exception | None = None
    statuses: list[dict[str, Any] | None] = field(
        default_factory=lambda: [{"confirmationStatus": "confirmed", "err": None}]
    )
    transaction: dict[str, Any] | None = field(default_factory=lambda: {"fill": True})
    block_height: int = 100
    statuses_error: Exception | None = None
    sent: list[bytes] = field(default_factory=lambda: list[bytes]())
    simulated: int = 0
    status_calls: int = 0

    def simulate_transaction(
        self, transaction: bytes, *, sig_verify: bool = False, replace_blockhash: bool = False
    ) -> Sim:
        assert transaction[1:65] == b"\0" * 64, "simulation must use the unsigned transaction"
        self.simulated += 1
        return Sim(
            self.simulate_ok,
            None if self.simulate_ok else {"InstructionError": [2, {"Custom": 6002}]},
        )

    def send_transaction(self, transaction: bytes, *, max_retries: int = 0) -> str:
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(transaction)
        from hunter_core.execution.meme.base58 import b58encode

        return b58encode(transaction[1:65])

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        if self.statuses_error is not None:
            raise self.statuses_error
        self.status_calls += 1
        index = min(self.status_calls - 1, len(self.statuses) - 1)
        return [self.statuses[index]]

    def get_transaction(
        self, signature: str, *, commitment: str = "confirmed"
    ) -> dict[str, Any] | None:
        return self.transaction

    def get_block_height(self, *, commitment: str = "confirmed") -> int:
        return self.block_height


class CountingSigner:
    def __init__(self, inner: MemeSigner) -> None:
        self.inner = inner
        self.calls = 0

    @property
    def pubkey(self) -> str:
        return self.inner.pubkey

    def sign(self, message: bytes) -> bytes:
        self.calls += 1
        return self.inner.sign(message)


def decode_fill(tx: dict[str, Any]) -> Sequence[Any]:
    return [{"token_amount": 1}] if tx.get("fill") else []


@pytest.fixture
def signer(test_key: TestKey) -> CountingSigner:
    return CountingSigner(MemeSigner.from_environment({ENV_SECRET_KEY: test_key.base58}))


def make(
    rpc: FakeRpc,
    signer: CountingSigner | None,
    *,
    allow_send: bool = True,
    verify_reason: str | None = None,
    jito: Any = None,
    now: datetime = NOW,
    clock: list[float] | None = None,
) -> MemeSubmitter:
    def verify(message: bytes) -> None:
        if verify_reason:
            raise Unverified(verify_reason)

    ticks = clock or [0.0]

    def monotonic() -> float:
        ticks[0] += 1.0
        return ticks[0]

    return MemeSubmitter(
        rpc=rpc,
        signer=signer,  # type: ignore[arg-type]
        journal=InMemoryOrderJournal(),
        verify=verify,
        decode_fill=decode_fill,
        policy=SubmitPolicy(
            allow_send=allow_send,
            cluster="devnet",
            jito_bundle=jito is not None,
            confirm_timeout_s=5.0,
            poll_interval_s=0.0,
        ),
        now=lambda: now,
        bundle_sender=jito,
        sleep=lambda _s: None,
        monotonic=monotonic,
    )


def approval(
    pid: str = "p1", *, expires: datetime = NOW + timedelta(seconds=5)
) -> ApprovedSubmission:
    return ApprovedSubmission(
        proposal_id=pid, expires_at=expires, message=MESSAGE, last_valid_block_height=150
    )


def test_happy_path_confirmed_by_trade_event(signer: CountingSigner) -> None:
    rpc = FakeRpc()
    submitter = make(rpc, signer)
    result = submitter.submit(approval())
    assert result.state is SubmitState.CONFIRMED and result.reason == "trade_event"
    assert result.fill == {"token_amount": 1} and result.signature
    assert rpc.simulated == 1 and len(rpc.sent) == 1 and signer.calls == 1


def test_replay_of_same_proposal_never_signs_or_sends_twice(signer: CountingSigner) -> None:
    rpc = FakeRpc()
    submitter = make(rpc, signer)
    first = submitter.submit(approval())
    second = submitter.submit(approval())
    assert second.replayed and second.signature == first.signature
    assert second.state is SubmitState.CONFIRMED
    assert len(rpc.sent) == 1 and signer.calls == 1


def test_live_disabled_raises_before_signing(signer: CountingSigner) -> None:
    rpc = FakeRpc()
    submitter = make(rpc, signer, allow_send=False)
    with pytest.raises(MemeLiveTradingDisabled):
        submitter.submit(approval())
    assert rpc.simulated == 1 and rpc.sent == [] and signer.calls == 0


def test_unverified_transaction_is_failed_and_never_simulated(signer: CountingSigner) -> None:
    rpc = FakeRpc()
    result = make(rpc, signer, verify_reason="trade_instruction_differs_from_intent").submit(
        approval()
    )
    assert result.state is SubmitState.FAILED
    assert result.reason == "unverified_transaction:trade_instruction_differs_from_intent"
    assert rpc.simulated == 0 and signer.calls == 0


def test_failed_simulation_is_failed_and_never_signed(signer: CountingSigner) -> None:
    rpc = FakeRpc(simulate_ok=False)
    result = make(rpc, signer).submit(approval())
    assert result.state is SubmitState.FAILED and result.reason.startswith("simulation_failed:")
    assert signer.calls == 0 and rpc.sent == []


def test_expired_reservation_never_executes_late(signer: CountingSigner) -> None:
    rpc = FakeRpc()
    result = make(rpc, signer).submit(approval(expires=NOW - timedelta(seconds=1)))
    assert result.state is SubmitState.FAILED and result.reason == "reservation_expired"
    assert rpc.simulated == 0 and signer.calls == 0


def test_transport_failure_after_send_is_unconfirmed_then_reconciled(
    signer: CountingSigner,
) -> None:
    rpc = FakeRpc(send_error=RpcDown())
    submitter = make(rpc, signer)
    result = submitter.submit(approval())
    assert result.state is SubmitState.SUBMITTED_UNCONFIRMED
    assert result.reason == "rpc_unreachable_after_send:RpcDown" and result.signature
    rpc.send_error = None
    replay = submitter.submit(approval())  # a retry is NOT a second signature
    assert replay.replayed and signer.calls == 1 and rpc.sent == []
    settled = submitter.reconcile("p1")
    assert settled is not None and settled.state is SubmitState.CONFIRMED
    assert settled.signature == result.signature


def test_rpc_refusal_on_send_is_failed_preflight(signer: CountingSigner) -> None:
    result = make(FakeRpc(send_error=RpcRefused()), signer).submit(approval())
    assert result.state is SubmitState.FAILED and result.reason == "preflight_failed:RpcRefused"


def test_confirmation_timeout_then_blockhash_expiry(signer: CountingSigner) -> None:
    rpc = FakeRpc(statuses=[None])
    submitter = make(rpc, signer)
    result = submitter.submit(approval())
    assert (
        result.state is SubmitState.SUBMITTED_UNCONFIRMED
        and result.reason == "confirmation_timeout"
    )
    rpc.block_height = 151  # past last_valid_block_height=150 and still not found
    settled = submitter.reconcile("p1")
    assert settled is not None and settled.state is SubmitState.FAILED
    assert settled.reason == "blockhash_expired_never_landed" and signer.calls == 1


def test_onchain_error_is_failed_with_the_error(signer: CountingSigner) -> None:
    rpc = FakeRpc(
        statuses=[
            {"confirmationStatus": "confirmed", "err": {"InstructionError": [2, {"Custom": 6002}]}}
        ]
    )
    result = make(rpc, signer).submit(approval())
    assert result.state is SubmitState.FAILED and result.reason.startswith("onchain_error:")


def test_landed_without_trade_event_is_not_a_fill(signer: CountingSigner) -> None:
    rpc = FakeRpc(transaction={"fill": False})
    result = make(rpc, signer).submit(approval())
    assert (
        result.state is SubmitState.SUBMITTED_UNCONFIRMED and result.reason == "trade_event_missing"
    )


def test_stream_event_replay_is_idempotent_by_signature(signer: CountingSigner) -> None:
    rpc = FakeRpc(statuses=[None])
    submitter = make(rpc, signer)
    unconfirmed = submitter.submit(approval())
    assert unconfirmed.signature is not None
    first = submitter.on_stream_event(unconfirmed.signature, {"fill": True})
    second = submitter.on_stream_event(unconfirmed.signature, {"fill": True})
    assert first is not None and first.state is SubmitState.CONFIRMED and not first.replayed
    assert second is not None and second.replayed and second.fill == first.fill
    assert submitter.on_stream_event("unknown-signature", {"fill": True}) is None
    rows = submitter._journal.rows()  # type: ignore[attr-defined]  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]
    assert len(rows) == 1 and rows[0].signatures == [unconfirmed.signature]


def test_signing_lock_held_by_another_session(signer: CountingSigner) -> None:
    rpc = FakeRpc()
    submitter = make(rpc, signer)
    submitter._journal.begin_signing("p1")  # type: ignore[attr-defined]  # pyright: ignore[reportPrivateUsage]
    result = submitter.submit(approval())
    assert result.state is SubmitState.FAILED and result.reason == "signing_locked"
    assert signer.calls == 0 and rpc.sent == []


def test_jito_bundle_is_a_parameter_off_by_default(signer: CountingSigner) -> None:
    class Bundles:
        def __init__(self) -> None:
            self.bundles: list[Sequence[bytes]] = []

        def send_bundle(self, transactions: Sequence[bytes]) -> str:
            self.bundles.append(transactions)
            return "bundle-1"

    rpc = FakeRpc()
    bundles = Bundles()
    result = make(rpc, signer, jito=bundles).submit(approval())
    assert result.state is SubmitState.CONFIRMED
    assert len(bundles.bundles) == 1 and len(bundles.bundles[0]) == 1 and rpc.sent == []
    with pytest.raises(ValueError):
        MemeSubmitter(
            rpc=rpc,
            signer=None,
            journal=InMemoryOrderJournal(),
            verify=lambda _m: None,
            decode_fill=decode_fill,
            policy=SubmitPolicy(allow_send=True, cluster="devnet", jito_bundle=True),
            now=lambda: NOW,
        )


def test_two_sessions_one_signature(signer: CountingSigner) -> None:
    """VM9: concurrent submits of the same proposal produce exactly one signature."""
    rpc = FakeRpc()
    in_simulation = threading.Event()
    proceed = threading.Event()
    original = rpc.simulate_transaction

    def slow_simulate(
        transaction: bytes, *, sig_verify: bool = False, replace_blockhash: bool = False
    ) -> Sim:
        in_simulation.set()
        assert proceed.wait(timeout=5), "test harness never released the first session"
        return original(transaction, sig_verify=sig_verify, replace_blockhash=replace_blockhash)

    rpc.simulate_transaction = slow_simulate  # type: ignore[method-assign]
    submitter = make(rpc, signer)
    first: list[Any] = []
    session_a = threading.Thread(target=lambda: first.append(submitter.submit(approval())))
    session_a.start()
    assert in_simulation.wait(timeout=5)
    # session B arrives while A holds the signing lock: refused by name, nothing signed
    second = submitter.submit(approval())
    assert second.state is SubmitState.FAILED and second.reason == "signing_locked"
    proceed.set()
    session_a.join(timeout=10)
    assert first and first[0].state is SubmitState.CONFIRMED
    assert signer.calls == 1 and len(rpc.sent) == 1
    # and after A settled, B's retry is a replay of A's signature, never a second one
    third = submitter.submit(approval())
    assert third.replayed and third.signature == first[0].signature and signer.calls == 1


def test_a_fill_that_cannot_be_decoded_after_the_send_is_unconfirmed_never_a_crash(
    signer: CountingSigner,
) -> None:
    """T4.14: the transaction landed but the event layout changed under us (a program
    upgrade). The send happened, so the only honest state is ``submitted_unconfirmed``
    with the reason; a later reconciliation with a decoder that understands the
    layout settles it as ``confirmed`` with the same signature — nothing re-signed."""
    rpc = FakeRpc()
    journal = InMemoryOrderJournal()
    calls = {"n": 0}

    def broken(tx: dict[str, Any]) -> Sequence[Any]:
        calls["n"] += 1
        raise ValueError("TradeEvent has 16 trailing bytes")

    def build(decoder: Any) -> MemeSubmitter:
        return MemeSubmitter(
            rpc=rpc,
            signer=signer,  # type: ignore[arg-type]
            journal=journal,
            verify=lambda _m: None,
            decode_fill=decoder,
            policy=SubmitPolicy(allow_send=True, cluster="devnet", poll_interval_s=0.0),
            now=lambda: NOW,
            sleep=lambda _s: None,
        )

    result = build(broken).submit(approval())
    assert result.state is SubmitState.SUBMITTED_UNCONFIRMED
    assert result.reason == "fill_decode_failed:ValueError"
    assert result.signature and len(rpc.sent) == 1 and signer.calls == 1
    row = journal.get("p1")
    assert row is not None and row.state is SubmitState.SUBMITTED_UNCONFIRMED
    assert row.signatures == [result.signature]

    settled = build(decode_fill).reconcile("p1")
    assert settled is not None and settled.state is SubmitState.CONFIRMED
    assert settled.signature == result.signature and len(rpc.sent) == 1 and signer.calls == 1

    replay = build(broken).on_stream_event(str(result.signature), {"fill": True})
    assert replay is not None and replay.replayed and replay.state is SubmitState.CONFIRMED
    assert calls["n"] == 1, "a confirmed row is never decoded again"
