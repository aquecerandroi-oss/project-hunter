"""T4.90 — ``MemeSubmitter.reconcile`` read the signature status **before** the
block height: a transaction that landed in the **last valid block** sits in the
gap between the two reads, and the row was written
``failed:blockhash_expired_never_landed`` on the stale ``None``. With T4.88's
pending-exit retry a wrongly failed sell is sent again, finds no tokens and
leaves the position open with a divergence. The rule is the one the
confirmation loop already follows (``confirm.expired_or_landed``, T4.55b) and
the spot reconcile (T4.74-5): expired only after a second look still finds
nothing; a short answer is never "absent".

Fake RPC (test fixture): each ``getSignatureStatuses`` answer is scripted in
order; every call is logged so the read order itself is asserted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from hunter_core.execution.meme.journal import InMemoryOrderJournal, SubmitState
from hunter_core.execution.meme.submit import MemeSubmitter, SubmitPolicy

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
PID = "prop-1:exit:1"
SIGNATURE = "5igNaTuRe1111111111111111111111111111111111111111111111111111111"
LAST_VALID = 150
CONFIRMED: dict[str, Any] = {"confirmationStatus": "confirmed", "err": None}
TX_META: dict[str, Any] = {"meta": {"fee": 5000}, "fill": {"sol_received": 123_456_789}}


class RpcDown(Exception):
    retryable = True


@dataclass
class ScriptedRpc:
    """Fixture: ``statuses`` are the successive answers of ``getSignatureStatuses``
    (a list answer as the node returns it — ``[]`` is a short answer; an
    ``Exception`` is raised). The last answer repeats."""

    statuses: list[list[dict[str, Any] | None] | Exception]
    height: int = LAST_VALID + 1
    transaction: dict[str, Any] | None = field(default_factory=lambda: dict(TX_META))
    calls: list[str] = field(default_factory=lambda: list[str]())

    def simulate_transaction(
        self, transaction: bytes, *, sig_verify: bool = False, replace_blockhash: bool = False
    ) -> Any:
        raise AssertionError("reconcile never simulates")

    def send_transaction(self, transaction: bytes, *, max_retries: int = 0) -> str:
        raise AssertionError("reconcile never sends")

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]:
        assert signatures == [SIGNATURE]
        index = min(sum(c == "status" for c in self.calls), len(self.statuses) - 1)
        self.calls.append("status")
        answer = self.statuses[index]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def get_transaction(
        self, signature: str, *, commitment: str = "confirmed"
    ) -> dict[str, Any] | None:
        assert signature == SIGNATURE
        self.calls.append("transaction")
        return self.transaction

    def get_block_height(self, *, commitment: str = "confirmed") -> int:
        self.calls.append("height")
        return self.height


def decode_fill(tx: dict[str, Any]) -> Sequence[Any]:
    """Fixture decoder: the fill is whatever the transaction's meta carries."""
    fill = tx.get("fill")
    return [fill] if fill else []


def _journal(state: SubmitState, reason: str) -> InMemoryOrderJournal:
    """A sell that was signed, sent and left in ``state`` — as the DB journal holds it."""
    journal = InMemoryOrderJournal()
    journal.begin_signing(PID)
    journal.record_signature(PID, SIGNATURE, last_valid_block_height=LAST_VALID)
    journal.record_state(PID, state, reason, None)
    journal.release_signing(PID)
    return journal


def _submitter(rpc: ScriptedRpc, journal: InMemoryOrderJournal) -> MemeSubmitter:
    return MemeSubmitter(
        rpc=rpc,
        signer=None,
        journal=journal,
        verify=lambda _raw: None,
        decode_fill=decode_fill,
        policy=SubmitPolicy(allow_send=False, cluster="devnet"),
        now=lambda: NOW,
    )


def _unconfirmed() -> InMemoryOrderJournal:
    return _journal(SubmitState.SUBMITTED_UNCONFIRMED, "confirmation_timeout")


def test_a_sell_that_landed_in_the_last_valid_block_is_confirmed_with_its_fill() -> None:
    """The reproduction: status ``None`` (not visible yet), height past
    ``last_valid``, and the second look finds it ``confirmed``."""
    rpc = ScriptedRpc(statuses=[[None], [CONFIRMED]])
    journal = _unconfirmed()
    result = _submitter(rpc, journal).reconcile(PID)
    assert result is not None
    assert result.state is SubmitState.CONFIRMED, result.reason
    assert result.reason == "trade_event" and result.signature == SIGNATURE
    assert result.fill == TX_META["fill"], "the fill is the transaction's own, never invented"
    assert rpc.calls == ["status", "height", "status", "transaction"]
    row = journal.get(PID)
    assert row is not None and row.state is SubmitState.CONFIRMED
    assert row.fill == TX_META["fill"] and row.signatures == [SIGNATURE]


def test_a_transaction_still_absent_on_the_second_look_is_expired_never_landed() -> None:
    rpc = ScriptedRpc(statuses=[[None], [None]])
    journal = _unconfirmed()
    result = _submitter(rpc, journal).reconcile(PID)
    assert result is not None and result.state is SubmitState.FAILED
    assert result.reason == "blockhash_expired_never_landed"
    assert rpc.calls == ["status", "height", "status"]
    row = journal.get(PID)
    assert row is not None and row.state is SubmitState.FAILED


def test_before_the_blockhash_expires_absent_is_only_not_found_yet() -> None:
    rpc = ScriptedRpc(statuses=[[None]], height=LAST_VALID)
    result = _submitter(rpc, _unconfirmed()).reconcile(PID)
    assert result is not None and result.state is SubmitState.SUBMITTED_UNCONFIRMED
    assert result.reason == "not_found_yet"
    assert rpc.calls == ["status", "height"], "no second look before the height has passed"


@pytest.mark.parametrize("first", [[], RpcDown()], ids=["short_answer", "rpc_down"])
def test_an_unreadable_first_look_is_never_absent(
    first: list[dict[str, Any] | None] | Exception,
) -> None:
    """T4.74-5: a short answer is not "not found" — and nothing is decided on it."""
    rpc = ScriptedRpc(statuses=[first])
    result = _submitter(rpc, _unconfirmed()).reconcile(PID)
    assert result is not None and result.state is SubmitState.SUBMITTED_UNCONFIRMED
    assert result.reason.startswith("rpc_unreachable_during_")
    assert rpc.calls == ["status"]


@pytest.mark.parametrize("second", [[], RpcDown()], ids=["short_answer", "rpc_down"])
def test_an_unreadable_second_look_is_unconfirmed_never_failed(
    second: list[dict[str, Any] | None] | Exception,
) -> None:
    rpc = ScriptedRpc(statuses=[[None], second])
    journal = _unconfirmed()
    result = _submitter(rpc, journal).reconcile(PID)
    assert result is not None and result.state is SubmitState.SUBMITTED_UNCONFIRMED
    assert result.reason.startswith("rpc_unreachable_during_")
    row = journal.get(PID)
    assert row is not None and row.state is SubmitState.SUBMITTED_UNCONFIRMED


def test_a_second_look_that_finds_an_onchain_error_is_that_error() -> None:
    errored: dict[str, Any] = {"confirmationStatus": "confirmed", "err": {"Custom": 6003}}
    rpc = ScriptedRpc(statuses=[[None], [errored]])
    result = _submitter(rpc, _unconfirmed()).reconcile(PID)
    assert result is not None and result.state is SubmitState.FAILED
    assert result.reason.startswith("onchain_error:")


def test_a_second_look_below_the_commitment_stays_unconfirmed() -> None:
    processed: dict[str, Any] = {"confirmationStatus": "processed", "err": None}
    rpc = ScriptedRpc(statuses=[[None], [processed]])
    result = _submitter(rpc, _unconfirmed()).reconcile(PID)
    assert result is not None and result.state is SubmitState.SUBMITTED_UNCONFIRMED
    assert result.reason == "landed_below_commitment_at_expiry"


def test_a_row_already_written_failed_by_the_old_rule_is_confirmed_when_the_chain_has_it() -> None:
    """Rows the pre-T4.90 reconcile wrote ``failed`` on the stale read: the
    signature is still asked of the chain (``searchTransactionHistory``), and a
    landed sell becomes ``confirmed`` with its fill — the executor's
    ``no_tokens_on_chain`` path relies on this."""
    rpc = ScriptedRpc(statuses=[[CONFIRMED]])
    journal = _journal(SubmitState.FAILED, "blockhash_expired_never_landed")
    result = _submitter(rpc, journal).reconcile(PID)
    assert result is not None and result.state is SubmitState.CONFIRMED
    assert result.fill == TX_META["fill"]
    row = journal.get(PID)
    assert row is not None and row.state is SubmitState.CONFIRMED
