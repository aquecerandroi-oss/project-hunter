"""T4.8f (Astra, round 3): a block that appears **during the simulation** must still stop an
entry — the gate the executor passes is consulted immediately before ``signer.sign``, after
the verifier and the simulation, the last point where nothing has been signed yet.

No key exists here: the signer is a sentinel that records the attempt and returns 64 filler
bytes; the point is whether it is *asked*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from hunter_core.execution.meme.journal import InMemoryOrderJournal, SubmitState
from hunter_core.execution.meme.submit import MemeSubmitter, SubmitPolicy
from packages.core.tests.unit.execution.meme.test_meme_submit import NOW, FakeRpc, approval


@dataclass
class SentinelSigner:
    calls: int = 0
    pubkey: str = "SentinelWallet"
    seen: list[bytes] = field(default_factory=lambda: list[bytes]())

    def sign(self, message: bytes) -> bytes:
        self.calls += 1
        self.seen.append(message)
        return b"\x11" * 64


@dataclass
class BlockDuringSimulation(FakeRpc):
    """The runtime tick finds the program block while ``simulateTransaction`` is in flight."""

    flag: list[str | None] = field(default_factory=lambda: [None])

    def simulate_transaction(self, transaction: bytes, **kwargs: Any) -> Any:
        result = super().simulate_transaction(transaction, **kwargs)
        self.flag[0] = "program_upgraded_before_signing"
        return result


def _submitter(
    rpc: FakeRpc, signer: SentinelSigner, journal: InMemoryOrderJournal, gate: Any
) -> MemeSubmitter:
    return MemeSubmitter(
        rpc=rpc,
        signer=signer,  # type: ignore[arg-type]
        journal=journal,
        verify=lambda _m: None,
        decode_fill=lambda tx: [{"token_amount": 1}] if tx.get("fill") else [],
        policy=SubmitPolicy(allow_send=True, cluster="devnet", poll_interval_s=0.0),
        now=lambda: NOW,
        sleep=lambda _s: None,
        pre_sign_gate=gate,
    )


def test_a_block_that_appears_during_the_simulation_stops_the_entry_before_it_is_signed() -> None:
    rpc = BlockDuringSimulation()
    signer, journal = SentinelSigner(), InMemoryOrderJournal()
    result = _submitter(rpc, signer, journal, lambda: rpc.flag[0]).submit(approval())
    assert result.state is SubmitState.FAILED
    assert result.reason == "program_upgraded_before_signing"
    assert rpc.simulated == 1, "the simulation ran, and succeeded: it is not what stopped it"
    assert signer.calls == 0 and rpc.sent == [] and result.signature is None
    row = journal.get("p1")
    assert row is not None and row.state is SubmitState.FAILED and not row.signatures


def test_a_gate_that_stays_clear_lets_the_entry_through() -> None:
    rpc, signer = FakeRpc(), SentinelSigner()
    result = _submitter(rpc, signer, InMemoryOrderJournal(), lambda: None).submit(approval())
    assert result.state is SubmitState.CONFIRMED
    assert signer.calls == 1 and len(rpc.sent) == 1


def test_without_a_gate_nothing_changes() -> None:
    """Exits are built without one: they are never gated by the program identity."""
    rpc, signer = FakeRpc(), SentinelSigner()
    result = _submitter(rpc, signer, InMemoryOrderJournal(), None).submit(approval())
    assert result.state is SubmitState.CONFIRMED and signer.calls == 1


@pytest.mark.parametrize(
    "reason", ["kill_switch_blocked_before_signing", "program_upgraded_before_signing"]
)
def test_the_gate_reason_is_the_refusal_reason_verbatim(reason: str) -> None:
    rpc, signer = FakeRpc(), SentinelSigner()
    result = _submitter(rpc, signer, InMemoryOrderJournal(), lambda: reason).submit(approval())
    assert result.reason == reason and signer.calls == 0
