"""T4.55 — the re-send loop of §9.4 rule 3: while a signed transaction waits for
confirmation, the **same bytes** go out again every ``resend_interval_s`` (same
signature — the network deduplicates) until it lands, the blockhash expires, or
the confirmation window closes. Nothing here ever signs twice.

R56 §2.1: 3 of ~23 real sends in 30 h ended ``blockhash_expired_never_landed``
because a 0,000004 SOL priority transaction sent **once** with ``maxRetries: 0``
was dropped by a busy leader and nobody re-sent it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from hunter_core.execution.meme.base58 import b58encode
from hunter_core.execution.meme.journal import InMemoryOrderJournal, SubmitState
from hunter_core.execution.meme.signer import ENV_SECRET_KEY, MemeSigner
from hunter_core.execution.meme.submit import ApprovedSubmission, MemeSubmitter, SubmitPolicy
from packages.core.tests.unit.execution.meme.conftest import TestKey

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
MESSAGE = b"\x01\x00\x01" + b"\x02" + b"\x11" * 64 + b"\x22" * 32 + b"\x00"
LAST_VALID = 150


class RpcDown(Exception):
    retryable = True


class RpcRefused(Exception):
    retryable = False


@dataclass
class Sim:
    ok: bool = True
    err: Any = None


class FakeClock:
    """``monotonic`` only moves when the submitter sleeps — the loop's own cadence."""

    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


@dataclass
class FakeRpc:
    """Confirms once ``confirm_after_sends`` sends were seen (``None`` = never);
    ``expire_at`` is the clock instant after which the block height is past
    ``LAST_VALID``; ``resend_errors`` raises on those re-send indexes (1-based)."""

    clock: FakeClock
    confirm_after_sends: int | None = 1
    expire_at: float | None = None
    resend_errors: dict[int, Exception] = field(default_factory=lambda: dict[int, Exception]())
    processed_only: bool = False
    sent: list[bytes] = field(default_factory=lambda: list[bytes]())
    attempts: int = 0
    status_calls: int = 0
    height_calls: int = 0

    def simulate_transaction(
        self, transaction: bytes, *, sig_verify: bool = False, replace_blockhash: bool = False
    ) -> Sim:
        return Sim()

    def send_transaction(self, transaction: bytes, *, max_retries: int = 0) -> str:
        assert max_retries == 0, "the node never retries for us; the submitter does"
        self.attempts += 1
        error = self.resend_errors.get(self.attempts)
        if error is not None:
            raise error
        self.sent.append(transaction)
        return b58encode(transaction[1:65])

    def _landed(self) -> bool:
        return self.confirm_after_sends is not None and len(self.sent) >= self.confirm_after_sends

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        self.status_calls += 1
        if self.processed_only:
            return [{"confirmationStatus": "processed", "err": None}]
        if self._landed():
            return [{"confirmationStatus": "confirmed", "err": None}]
        return [None]

    def get_transaction(
        self, signature: str, *, commitment: str = "confirmed"
    ) -> dict[str, Any] | None:
        return {"fill": True}

    def get_block_height(self, *, commitment: str = "confirmed") -> int:
        self.height_calls += 1
        if self.expire_at is not None and self.clock.t >= self.expire_at:
            return LAST_VALID + 1
        return LAST_VALID - 10


def decode_fill(tx: dict[str, Any]) -> Sequence[Any]:
    return [{"token_amount": 1}] if tx.get("fill") else []


@pytest.fixture
def signer(test_key: TestKey) -> MemeSigner:
    return MemeSigner.from_environment({ENV_SECRET_KEY: test_key.base58})


def make(
    rpc: FakeRpc,
    clock: FakeClock,
    signer: MemeSigner,
    *,
    resend_interval_s: float = 2.0,
    confirm_timeout_s: float = 30.0,
    journal: InMemoryOrderJournal | None = None,
) -> MemeSubmitter:
    return MemeSubmitter(
        rpc=rpc,
        signer=signer,
        journal=journal or InMemoryOrderJournal(),
        verify=lambda _m: None,
        decode_fill=decode_fill,
        policy=SubmitPolicy(
            allow_send=True,
            cluster="devnet",
            confirm_timeout_s=confirm_timeout_s,
            poll_interval_s=1.0,
            resend_interval_s=resend_interval_s,
        ),
        now=lambda: NOW,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )


def approval(pid: str = "p1") -> ApprovedSubmission:
    return ApprovedSubmission(
        proposal_id=pid,
        expires_at=NOW + timedelta(seconds=5),
        message=MESSAGE,
        last_valid_block_height=LAST_VALID,
    )


def test_the_same_signed_bytes_are_resent_every_2s_until_the_third_send_confirms(
    signer: MemeSigner,
) -> None:
    clock = FakeClock()
    rpc = FakeRpc(clock, confirm_after_sends=3)
    result = make(rpc, clock, signer).submit(approval())
    assert result.state is SubmitState.CONFIRMED and result.reason == "trade_event"
    assert len(rpc.sent) == 3 and result.resends == 2
    assert len({bytes(tx) for tx in rpc.sent}) == 1, "re-sends are byte-identical (same signature)"
    assert result.signature == b58encode(rpc.sent[0][1:65])
    # first send at t=0, re-sends at t=2 and t=4, confirmed on the next poll (t=5)
    assert clock.t == 5.0


def test_a_blockhash_past_its_last_valid_height_stops_the_resends_and_fails_by_name(
    signer: MemeSigner,
) -> None:
    clock = FakeClock()
    rpc = FakeRpc(clock, confirm_after_sends=None, expire_at=5.0)
    journal = InMemoryOrderJournal()
    result = make(rpc, clock, signer, journal=journal).submit(approval())
    assert result.state is SubmitState.FAILED
    assert result.reason == "blockhash_expired_never_landed"
    # sends at t=0, 2, 4; at t=6 the height is past 150 and nothing goes out again
    assert len(rpc.sent) == 3 and result.resends == 2
    assert clock.t == 6.0
    row = journal.get("p1")
    assert row is not None and row.state is SubmitState.FAILED
    assert row.signatures == [result.signature], "expired means never landed; never re-signed"


def test_the_confirmation_window_caps_the_loop_at_30s(signer: MemeSigner) -> None:
    clock = FakeClock()
    rpc = FakeRpc(clock, confirm_after_sends=None)
    result = make(rpc, clock, signer).submit(approval())
    assert result.state is SubmitState.SUBMITTED_UNCONFIRMED
    assert result.reason == "confirmation_timeout"
    assert clock.t == 30.0
    # t = 0 (send), 2, 4, ..., 28 → 14 re-sends; t = 30 is the deadline, not a send
    assert len(rpc.sent) == 15 and result.resends == 14


def test_a_failed_resend_never_changes_the_state_and_the_loop_goes_on(
    signer: MemeSigner,
) -> None:
    """The first send succeeded: the transaction is in the network. A re-send
    the node refuses (``AlreadyProcessed``, a transport blip) is counted and
    ignored — the status poll is the only source of truth."""
    clock = FakeClock()
    rpc = FakeRpc(clock, confirm_after_sends=3, resend_errors={2: RpcRefused(), 3: RpcDown()})
    result = make(rpc, clock, signer).submit(approval())
    assert result.state is SubmitState.CONFIRMED
    assert len(rpc.sent) == 3 and result.resends == 2 and result.resend_errors == 2


def test_a_processed_transaction_is_not_resent(signer: MemeSigner) -> None:
    """``processed`` is a node that already has it: re-sending would be noise,
    and ``processed`` never decides (§8.2) — the loop keeps polling to the cap."""
    clock = FakeClock()
    rpc = FakeRpc(clock, confirm_after_sends=None, processed_only=True)
    result = make(rpc, clock, signer, confirm_timeout_s=6.0).submit(approval())
    assert result.state is SubmitState.SUBMITTED_UNCONFIRMED
    assert len(rpc.sent) == 1 and result.resends == 0


def test_resend_interval_zero_keeps_the_pre_t455_single_send(signer: MemeSigner) -> None:
    clock = FakeClock()
    rpc = FakeRpc(clock, confirm_after_sends=None)
    result = make(rpc, clock, signer, resend_interval_s=0.0, confirm_timeout_s=6.0).submit(
        approval()
    )
    assert result.state is SubmitState.SUBMITTED_UNCONFIRMED
    assert len(rpc.sent) == 1 and result.resends == 0


def test_the_first_send_failing_on_transport_still_never_signs_twice(signer: MemeSigner) -> None:
    """VM5 unchanged by the loop: a transport failure on the **first** send is
    ``submitted_unconfirmed`` and reconciliation, never a blind retry."""
    clock = FakeClock()
    rpc = FakeRpc(clock, confirm_after_sends=None, resend_errors={1: RpcDown()})
    submitter = make(rpc, clock, signer)
    result = submitter.submit(approval())
    assert result.state is SubmitState.SUBMITTED_UNCONFIRMED
    assert result.reason == "rpc_unreachable_after_send:RpcDown" and rpc.sent == []
    replay = submitter.submit(approval())
    assert replay.replayed and rpc.sent == []
