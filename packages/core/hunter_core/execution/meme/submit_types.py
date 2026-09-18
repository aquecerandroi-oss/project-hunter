"""The types ``submit.py`` and ``confirm.py`` share: the RPC and bundle
protocols, the policy, what an approval hands in and what a submission returns.
Split out of ``submit.py`` in T4.55 (file-size budget); ``submit`` re-exports
every public name, so callers keep importing from there.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from hunter_core.execution.meme.journal import SubmitState

__all__ = [
    "LANDED",
    "ApprovedSubmission",
    "BundleSender",
    "MemeLiveTradingDisabled",
    "ResendStats",
    "SubmitPolicy",
    "SubmitResult",
    "TxRpc",
    "result_of",
]

LANDED = ("confirmed", "finalized")


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
    resend_interval_s: float = 2.0
    """T4.55: how often the same signed bytes are sent again while unconfirmed;
    ``0`` keeps the single send. Never applies to a Jito bundle."""


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
    resends: int = 0
    """T4.55: re-sends of the same signed bytes the confirmation loop made."""
    resend_errors: int = 0
    """Of those, the ones the RPC refused or could not carry — informational."""


@dataclass(slots=True)
class ResendStats:
    resends: int = 0
    errors: int = 0


def result_of(
    pid: str,
    state: SubmitState,
    reason: str,
    signature: str | None,
    stats: ResendStats | None,
    fill: Any = None,
) -> SubmitResult:
    stats = stats or ResendStats()
    return SubmitResult(
        pid, state, reason, signature, fill, resends=stats.resends, resend_errors=stats.errors
    )
