"""The confirmation loop with the re-send of §9.4 rule 3 (T4.55).

Polls ``getSignatureStatuses`` every ``poll_interval_s`` and, while the signature
is not found anywhere, sends the **same signed bytes** again every
``resend_interval_s`` — same signature, the network deduplicates, so a re-send
can never produce a second position. Three ways out, each named:

- ``landed``: ``confirmed``/``finalized`` — the caller fetches the fill;
- ``failed``: the chain recorded an error, **or** the signature is still unknown
  and the chain is past the blockhash's ``last_valid_block_height``
  (``blockhash_expired_never_landed`` — what ``reconcile`` would say 50–60 s
  later, said now, and no more sends for a blockhash that cannot land);
- ``unconfirmed``: the window closed or the RPC failed mid-loop — reconciliation.

A re-send the node refuses (``AlreadyProcessed``, a transport blip) is counted
and ignored: the first send already reached the network and the status poll is
the only source of truth. ``processed`` (a node has it) is not re-sent either.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from hunter_core.execution.meme.submit_types import LANDED, ResendStats, SubmitPolicy, TxRpc

__all__ = ["Settled", "poll_until_settled"]


@dataclass(frozen=True, slots=True)
class Settled:
    outcome: Literal["landed", "failed", "unconfirmed"]
    reason: str
    stats: ResendStats


def poll_until_settled(
    rpc: TxRpc,
    policy: SubmitPolicy,
    signature: str,
    *,
    resend: bytes | None,
    last_valid_block_height: int | None,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> Settled:
    started = monotonic()
    deadline = started + policy.confirm_timeout_s
    interval = policy.resend_interval_s
    next_resend = started + interval
    stats = ResendStats()
    while True:
        try:
            status = rpc.get_signature_statuses([signature])[0]
        except Exception as exc:
            reason = f"rpc_unreachable_during_confirmation:{type(exc).__name__}"
            return Settled("unconfirmed", reason, stats)
        if status is not None:
            if status.get("err") is not None:
                return Settled("failed", f"onchain_error:{status.get('err')}", stats)
            if status.get("confirmationStatus") in LANDED:
                return Settled("landed", "trade_event", stats)
        now = monotonic()
        if now >= deadline:
            return Settled("unconfirmed", "confirmation_timeout", stats)
        if resend is not None and interval > 0 and now >= next_resend and status is None:
            if _blockhash_expired(rpc, policy, last_valid_block_height):
                # Review T4.55: the status above was read BEFORE the height; a
                # transaction that landed on the very last valid block sits in
                # that gap. Ask once more before calling it never landed — a
                # wrong ``failed`` is never reconciled and leaves tokens in the
                # wallet with no position and no stop.
                return _expired_or_landed(rpc, signature, stats)
            _resend(rpc, resend, stats)
            next_resend = now + interval
        sleep(policy.poll_interval_s)


def _expired_or_landed(rpc: TxRpc, signature: str, stats: ResendStats) -> Settled:
    """The height passed ``last_valid``: re-read the status once. Landed wins;
    an error is an error; unreadable stays ``unconfirmed`` so the reconcile
    (which searches history) decides — never ``failed`` on a guess."""
    try:
        status = rpc.get_signature_statuses([signature])[0]
    except Exception as exc:
        reason = f"rpc_unreachable_during_confirmation:{type(exc).__name__}"
        return Settled("unconfirmed", reason, stats)
    if status is not None:
        if status.get("err") is not None:
            return Settled("failed", f"onchain_error:{status.get('err')}", stats)
        if status.get("confirmationStatus") in LANDED:
            return Settled("landed", "trade_event", stats)
        return Settled("unconfirmed", "landed_below_commitment_at_expiry", stats)
    return Settled("failed", "blockhash_expired_never_landed", stats)


def _blockhash_expired(rpc: TxRpc, policy: SubmitPolicy, last_valid: int | None) -> bool:
    if last_valid is None:
        return False
    try:
        height = rpc.get_block_height(commitment=policy.commitment)
    except Exception:
        return False  # unknown is not expired; the next poll asks again
    return height > last_valid


def _resend(rpc: TxRpc, transaction: bytes, stats: ResendStats) -> None:
    """Same bytes, same signature — idempotent on chain. An error here is
    counted, never acted on: the first send already reached the network."""
    try:
        rpc.send_transaction(transaction, max_retries=0)
    except Exception:
        stats.errors += 1
        return
    stats.resends += 1
