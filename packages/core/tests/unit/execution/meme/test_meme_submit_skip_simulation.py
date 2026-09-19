"""T4.67b — ``SubmitPolicy.skip_simulation`` (the launch lane's
``MEME_LAUNCH_SKIP_SIMULATION``): off by default the submitter simulates before
signing exactly as before; on, it signs and sends without the executor's own
``simulateTransaction`` — the node's preflight still stands (``send_transaction``
refusing is ``preflight_failed``, nothing landed, no fee paid) and a refused
send never becomes a second signature.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from hunter_core.execution.meme.journal import InMemoryOrderJournal, SubmitState
from hunter_core.execution.meme.signer import MemeSigner
from hunter_core.execution.meme.submit import MemeSubmitter, SubmitPolicy

from .test_meme_submit_resend import (
    FakeClock,
    FakeRpc,
    RpcRefused,
    Sim,
    approval,
    decode_fill,
    make,
)


class CountingRpc(FakeRpc):
    simulations: int = 0

    def simulate_transaction(
        self, transaction: bytes, *, sig_verify: bool = False, replace_blockhash: bool = False
    ) -> Sim:
        self.simulations += 1
        return super().simulate_transaction(
            transaction, sig_verify=sig_verify, replace_blockhash=replace_blockhash
        )


def _submitter(
    rpc: CountingRpc, clock: FakeClock, signer: MemeSigner, *, skip: bool
) -> MemeSubmitter:
    base = make(rpc, clock, signer)
    policy = replace(base._policy, skip_simulation=skip)  # pyright: ignore[reportPrivateUsage]
    return MemeSubmitter(
        rpc=rpc,
        signer=signer,
        journal=InMemoryOrderJournal(),
        verify=lambda _m: None,
        decode_fill=decode_fill,
        policy=policy,
        now=base._now,  # pyright: ignore[reportPrivateUsage]
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )


def test_the_policy_simulates_by_default() -> None:
    assert SubmitPolicy(allow_send=True, cluster="devnet").skip_simulation is False


def test_off_simulates_once_before_signing_and_on_signs_without_simulating(
    signer: MemeSigner,
) -> None:
    clock = FakeClock()
    rpc = CountingRpc(clock)
    result = _submitter(rpc, clock, signer, skip=False).submit(approval("p1"))
    assert result.state is SubmitState.CONFIRMED and rpc.simulations == 1
    rpc2 = CountingRpc(FakeClock())
    result2 = _submitter(rpc2, clock, signer, skip=True).submit(approval("p2"))
    assert result2.state is SubmitState.CONFIRMED and rpc2.simulations == 0
    assert len(rpc2.sent) == 1 and result2.signature


def test_with_simulation_skipped_a_preflight_refusal_is_a_named_failure_not_a_second_signature(
    signer: MemeSigner,
) -> None:
    clock = FakeClock()
    rpc = CountingRpc(clock, resend_errors={1: RpcRefused("preflight")})
    journal = InMemoryOrderJournal()
    submitter = MemeSubmitter(
        rpc=rpc,
        signer=signer,
        journal=journal,
        verify=lambda _m: None,
        decode_fill=decode_fill,
        policy=SubmitPolicy(allow_send=True, cluster="devnet", skip_simulation=True),
        now=make(rpc, clock, signer)._now,  # pyright: ignore[reportPrivateUsage]
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )
    result = submitter.submit(approval("p3"))
    assert result.state is SubmitState.FAILED and result.reason.startswith("preflight_failed")
    assert rpc.simulations == 0 and rpc.sent == []
    row = journal.get("p3")
    assert row is not None and len(row.signatures) == 1, "signed once, journaled once"
    replay = submitter.submit(approval("p3"))
    assert replay.replayed and len(journal.get("p3").signatures) == 1  # type: ignore[union-attr]


@pytest.fixture
def signer(test_key: object) -> MemeSigner:
    from hunter_core.execution.meme.signer import ENV_SECRET_KEY

    return MemeSigner.from_environment({ENV_SECRET_KEY: test_key.base58})  # type: ignore[attr-defined]
