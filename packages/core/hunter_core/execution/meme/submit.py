"""Verify → simulate → sign → send → confirm, with the doctrine's states and names.

``docs/RISK_ENGINE_MEME.md`` §9.2–§9.6, as a state machine that never guesses:

- **Verify first** (§9.1): the caller injects the verifier (``hunter_exchanges
  .pumpfun.verify`` in production — ``hunter_core`` cannot import the adapter);
  an :class:`UnverifiedTransaction`-like refusal ends the attempt as ``failed``.
- **Simulate always** (§9.2): ``simulateTransaction`` on the unsigned bytes; a
  failed simulation is ``failed:simulation_failed`` and nothing is signed.
- **Send only when allowed**: ``ENABLE_MEME_LIVE_TRADING`` (§3.4) and the §12 gates
  become ``SubmitPolicy.allow_send``; with it off the submitter raises
  :class:`MemeLiveTradingDisabled` before the key is touched — the doctrine's
  "raises on every call".
- **Signature recorded before the send** (§9.4): a crash between the two leaves a
  row that :meth:`MemeSubmitter.reconcile` can settle; a retry never signs a
  second time for the same proposal — same message ⇒ same signature ⇒ the
  network deduplicates, and a *new* blockhash is a new proposal, not a retry.
- **Confirmation by the event** (§9.6): ``confirmed`` means a decoded
  ``TradeEvent`` (the injected ``decode_fill``); a landed transaction without one
  is ``submitted_unconfirmed:trade_event_missing`` — reconciliation, not a fill.
- **Timeouts are not failures** (§9.5/VM5): after the send, every RPC problem is
  ``submitted_unconfirmed`` with a named reason and **never** a blind retry.
- **Old approvals never execute** (§9.5/VM8): ``expires_at`` is checked first.
- **Jito** (§9.3) is a parameter, off by default; the bundle carries one
  transaction and confirmation still goes through the signature.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from hunter_core.execution.meme.base58 import b58encode
from hunter_core.execution.meme.journal import (
    OrderJournal,
    OrderRecord,
    SigningLocked,
    SubmitState,
)
from hunter_core.execution.meme.signer import MemeSigner

__all__ = [
    "ApprovedSubmission",
    "BundleSender",
    "MemeLiveTradingDisabled",
    "MemeSubmitter",
    "SubmitPolicy",
    "SubmitResult",
    "TxRpc",
]

_LANDED = ("confirmed", "finalized")


class MemeLiveTradingDisabled(RuntimeError):
    """``allow_send`` is false: nothing in this process may send a transaction."""


class _Simulation(Protocol):
    @property
    def ok(self) -> bool: ...

    @property
    def err(self) -> Any: ...


class TxRpc(Protocol):
    def simulate_transaction(
        self, transaction: bytes, *, sig_verify: bool = ..., replace_blockhash: bool = ...
    ) -> _Simulation: ...

    def send_transaction(self, transaction: bytes, *, max_retries: int = ...) -> str: ...

    def get_signature_statuses(self, signatures: list[str]) -> list[dict[str, Any] | None]: ...

    def get_transaction(
        self, signature: str, *, commitment: str = ...
    ) -> dict[str, Any] | None: ...

    def get_block_height(self, *, commitment: str = ...) -> int: ...


class BundleSender(Protocol):
    def send_bundle(self, transactions: Sequence[bytes]) -> str: ...


@dataclass(frozen=True, slots=True)
class SubmitPolicy:
    allow_send: bool
    cluster: Literal["mainnet", "devnet"]
    jito_bundle: bool = False
    confirm_timeout_s: float = 30.0
    poll_interval_s: float = 1.0
    commitment: str = "confirmed"


@dataclass(frozen=True, slots=True)
class ApprovedSubmission:
    """What an approved proposal hands the submitter: identity, reservation deadline,
    the verified-intent callback and the message bytes to sign."""

    proposal_id: str
    expires_at: datetime
    message: bytes
    last_valid_block_height: int | None = None


@dataclass(frozen=True, slots=True)
class SubmitResult:
    proposal_id: str
    state: SubmitState
    reason: str
    signature: str | None
    fill: Any
    replayed: bool = False


def _serialize(signature: bytes, message: bytes) -> bytes:
    return b"\x01" + signature + message


class MemeSubmitter:
    def __init__(
        self,
        *,
        rpc: TxRpc,
        signer: MemeSigner | None,
        journal: OrderJournal,
        verify: Callable[[bytes], object],
        decode_fill: Callable[[dict[str, Any]], Sequence[Any]],
        policy: SubmitPolicy,
        now: Callable[[], datetime],
        bundle_sender: BundleSender | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if policy.jito_bundle and bundle_sender is None:
            raise ValueError("jito_bundle=True needs a bundle_sender")
        self._rpc = rpc
        self._signer = signer
        self._journal = journal
        self._verify = verify
        self._decode_fill = decode_fill
        self._policy = policy
        self._now = now
        self._bundles = bundle_sender
        self._sleep = sleep
        self._monotonic = monotonic

    # ---------------------------------------------------------------- submit
    def submit(self, approval: ApprovedSubmission) -> SubmitResult:
        pid = approval.proposal_id
        existing = self._journal.get(pid)
        if existing is not None and existing.signatures:
            return self._replay(existing)
        if approval.expires_at <= self._now():
            return self._fail(pid, "reservation_expired")
        try:
            self._journal.begin_signing(pid)
        except SigningLocked:
            return SubmitResult(pid, SubmitState.FAILED, "signing_locked", None, None)
        try:
            return self._attempt(approval)
        finally:
            self._journal.release_signing(pid)

    def _attempt(self, approval: ApprovedSubmission) -> SubmitResult:
        pid = approval.proposal_id
        try:
            self._verify(approval.message)
        except Exception as exc:  # the verifier's own exception type is the adapter's
            return self._fail(pid, f"unverified_transaction:{getattr(exc, 'reason', exc)}")
        try:
            simulation = self._rpc.simulate_transaction(
                _serialize(b"\0" * 64, approval.message), sig_verify=False, replace_blockhash=True
            )
        except Exception as exc:
            return self._fail(pid, f"simulation_unavailable:{type(exc).__name__}")
        if not simulation.ok:
            return self._fail(pid, f"simulation_failed:{simulation.err}")
        if not self._policy.allow_send:
            self._journal.record_state(pid, SubmitState.FAILED, "meme_live_disabled", None)
            raise MemeLiveTradingDisabled("allow_send is false: simulated only, nothing signed")
        if self._signer is None:
            return self._fail(pid, "secret_key_missing")
        signature_bytes = self._signer.sign(approval.message)
        signature = b58encode(signature_bytes)
        transaction = _serialize(signature_bytes, approval.message)
        self._journal.record_signature(
            pid, signature, last_valid_block_height=approval.last_valid_block_height
        )
        try:
            if self._policy.jito_bundle and self._bundles is not None:
                self._bundles.send_bundle([transaction])
                sent = signature
            else:
                sent = self._rpc.send_transaction(transaction, max_retries=0)
        except Exception as exc:
            if _refused_before_landing(exc):
                return self._fail(pid, f"preflight_failed:{type(exc).__name__}", signature)
            return self._unconfirmed(
                pid, f"rpc_unreachable_after_send:{type(exc).__name__}", signature
            )
        if sent != signature:
            return self._unconfirmed(pid, "signature_mismatch", signature)
        return self._confirm(pid, signature)

    # --------------------------------------------------------------- confirm
    def _confirm(self, pid: str, signature: str) -> SubmitResult:
        deadline = self._monotonic() + self._policy.confirm_timeout_s
        while True:
            try:
                status = self._rpc.get_signature_statuses([signature])[0]
            except Exception as exc:
                return self._unconfirmed(
                    pid, f"rpc_unreachable_during_confirmation:{type(exc).__name__}", signature
                )
            if status is not None:
                if status.get("err") is not None:
                    return self._fail(pid, f"onchain_error:{status.get('err')}", signature)
                if status.get("confirmationStatus") in _LANDED:
                    return self._settle_landed(pid, signature)
            if self._monotonic() >= deadline:
                return self._unconfirmed(pid, "confirmation_timeout", signature)
            self._sleep(self._policy.poll_interval_s)

    def _settle_landed(self, pid: str, signature: str) -> SubmitResult:
        try:
            transaction = self._rpc.get_transaction(signature, commitment=self._policy.commitment)
        except Exception as exc:
            return self._unconfirmed(
                pid, f"rpc_unreachable_fetching_fill:{type(exc).__name__}", signature
            )
        if transaction is None:
            return self._unconfirmed(pid, "transaction_not_found_after_confirmation", signature)
        try:
            fills = list(self._decode_fill(transaction))
        except Exception as exc:
            # The transaction landed; what we could not do is *read* it (a program upgrade
            # that changed the event layout, T4.14). Never a crash after a send: the row
            # stays unconfirmed with the reason, and reconciliation retries the read.
            return self._unconfirmed(pid, f"fill_decode_failed:{type(exc).__name__}", signature)
        if not fills:
            return self._unconfirmed(pid, "trade_event_missing", signature)
        fill = fills[0]
        self._journal.record_state(pid, SubmitState.CONFIRMED, "trade_event", fill)
        return SubmitResult(pid, SubmitState.CONFIRMED, "trade_event", signature, fill)

    # ------------------------------------------------------------- reconcile
    def reconcile(self, proposal_id: str) -> SubmitResult | None:
        """Settle an unconfirmed row after a restart or a timeout — never re-sign."""
        row = self._journal.get(proposal_id)
        if row is None or row.latest_signature is None:
            return None
        if row.state is SubmitState.CONFIRMED:
            return self._replay(row)
        signature = row.latest_signature
        try:
            status = self._rpc.get_signature_statuses([signature])[0]
        except Exception as exc:
            return self._unconfirmed(
                proposal_id,
                f"rpc_unreachable_during_reconciliation:{type(exc).__name__}",
                signature,
            )
        if status is None:
            if row.last_valid_block_height is not None:
                try:
                    height = self._rpc.get_block_height(commitment=self._policy.commitment)
                except Exception as exc:
                    return self._unconfirmed(
                        proposal_id,
                        f"rpc_unreachable_during_reconciliation:{type(exc).__name__}",
                        signature,
                    )
                if height > row.last_valid_block_height:
                    return self._fail(proposal_id, "blockhash_expired_never_landed", signature)
            return self._unconfirmed(proposal_id, "not_found_yet", signature)
        if status.get("err") is not None:
            return self._fail(proposal_id, f"onchain_error:{status.get('err')}", signature)
        if status.get("confirmationStatus") in _LANDED:
            return self._settle_landed(proposal_id, signature)
        return self._unconfirmed(proposal_id, "processed_not_confirmed", signature)

    def on_stream_event(self, signature: str, transaction: dict[str, Any]) -> SubmitResult | None:
        """A confirmation delivered by a stream (WS, webhook, tape) — idempotent (§9.4 rule 5):
        a signature already settled returns the recorded result and creates nothing."""
        row = self._journal.find_by_signature(signature)
        if row is None:
            return None
        if row.state is SubmitState.CONFIRMED:
            return self._replay(row)
        try:
            fills = list(self._decode_fill(transaction))
        except Exception as exc:
            return self._unconfirmed(
                row.proposal_id, f"fill_decode_failed:{type(exc).__name__}", signature
            )
        if not fills:
            return self._unconfirmed(row.proposal_id, "trade_event_missing", signature)
        self._journal.record_state(row.proposal_id, SubmitState.CONFIRMED, "trade_event", fills[0])
        return SubmitResult(
            row.proposal_id, SubmitState.CONFIRMED, "trade_event", signature, fills[0]
        )

    # --------------------------------------------------------------- helpers
    def _replay(self, row: OrderRecord) -> SubmitResult:
        state = row.state or SubmitState.SUBMITTED_UNCONFIRMED
        return SubmitResult(
            row.proposal_id,
            state,
            row.reason or "already_signed",
            row.latest_signature,
            row.fill,
            True,
        )

    def _fail(self, pid: str, reason: str, signature: str | None = None) -> SubmitResult:
        if self._journal.get(pid) is None:
            self._journal.begin_signing(pid)
            self._journal.release_signing(pid)
        self._journal.record_state(pid, SubmitState.FAILED, reason, None)
        return SubmitResult(pid, SubmitState.FAILED, reason, signature, None)

    def _unconfirmed(self, pid: str, reason: str, signature: str) -> SubmitResult:
        self._journal.record_state(pid, SubmitState.SUBMITTED_UNCONFIRMED, reason, None)
        return SubmitResult(pid, SubmitState.SUBMITTED_UNCONFIRMED, reason, signature, None)


def _refused_before_landing(exc: Exception) -> bool:
    """An RPC *error reply* to ``sendTransaction`` (preflight failure, malformed) means the
    transaction was refused and did not enter the network; a transport failure means we
    do not know — and "do not know" is ``submitted_unconfirmed``."""
    return getattr(exc, "retryable", True) is False
