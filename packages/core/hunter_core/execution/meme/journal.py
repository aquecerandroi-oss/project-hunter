"""One durable row per proposal, with every signature it ever produced (§9.4).

``docs/RISK_ENGINE_MEME.md`` §9.4 rules 1–2 and 5: a proposal has **one** order
row (``client_order_id = meme:{proposal_id}``), the row lists the signatures
already emitted for it, and signing requires holding the row's ``signing`` lock —
two sessions never sign the same proposal (VM9). In production the row is
``meme_orders`` (T4.6/T4.7's migration, not this task's); this module defines the
protocol the submitter drives and an in-memory implementation with the same
semantics for tests, the VM scripts and the devnet run.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

__all__ = [
    "InMemoryOrderJournal",
    "OrderJournal",
    "OrderRecord",
    "SigningLocked",
    "SubmitState",
    "client_order_id_for_proposal",
]


class SubmitState(StrEnum):
    SUBMITTED_UNCONFIRMED = "submitted_unconfirmed"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class SigningLocked(RuntimeError):
    """Another session holds the proposal's signing lock (VM9: one signature per proposal)."""


def client_order_id_for_proposal(proposal_id: str) -> str:
    return f"meme:{proposal_id}"


@dataclass(slots=True)
class OrderRecord:
    proposal_id: str
    client_order_id: str
    signatures: list[str] = field(default_factory=lambda: list[str]())
    state: SubmitState | None = None
    reason: str = ""
    fill: Any = None
    signing: bool = False
    last_valid_block_height: int | None = None

    @property
    def latest_signature(self) -> str | None:
        return self.signatures[-1] if self.signatures else None


class OrderJournal(Protocol):
    def get(self, proposal_id: str) -> OrderRecord | None: ...

    def find_by_signature(self, signature: str) -> OrderRecord | None: ...

    def begin_signing(self, proposal_id: str) -> OrderRecord:
        """Create-or-load the row and take its signing lock, or raise :class:`SigningLocked`."""
        ...

    def record_signature(
        self, proposal_id: str, signature: str, *, last_valid_block_height: int | None
    ) -> None: ...

    def record_state(
        self, proposal_id: str, state: SubmitState, reason: str, fill: Any
    ) -> None: ...

    def release_signing(self, proposal_id: str) -> None: ...


class InMemoryOrderJournal:
    """Reference implementation: a dict under a lock, first writer wins."""

    def __init__(self) -> None:
        self._rows: dict[str, OrderRecord] = {}
        self._lock = threading.Lock()

    def get(self, proposal_id: str) -> OrderRecord | None:
        with self._lock:
            return self._rows.get(proposal_id)

    def find_by_signature(self, signature: str) -> OrderRecord | None:
        with self._lock:
            for row in self._rows.values():
                if signature in row.signatures:
                    return row
            return None

    def begin_signing(self, proposal_id: str) -> OrderRecord:
        with self._lock:
            row = self._rows.get(proposal_id)
            if row is None:
                row = OrderRecord(proposal_id, client_order_id_for_proposal(proposal_id))
                self._rows[proposal_id] = row
            if row.signing:
                raise SigningLocked(proposal_id)
            row.signing = True
            return row

    def record_signature(
        self, proposal_id: str, signature: str, *, last_valid_block_height: int | None
    ) -> None:
        with self._lock:
            row = self._rows[proposal_id]
            if signature not in row.signatures:
                row.signatures.append(signature)
            row.last_valid_block_height = last_valid_block_height

    def record_state(self, proposal_id: str, state: SubmitState, reason: str, fill: Any) -> None:
        with self._lock:
            row = self._rows[proposal_id]
            if row.state is SubmitState.CONFIRMED and state is not SubmitState.CONFIRMED:
                return  # a confirmed fill is never downgraded by a later observation
            row.state, row.reason, row.fill = state, reason, fill

    def release_signing(self, proposal_id: str) -> None:
        with self._lock:
            row = self._rows.get(proposal_id)
            if row is not None:
                row.signing = False

    def rows(self) -> list[OrderRecord]:
        with self._lock:
            return list(self._rows.values())
