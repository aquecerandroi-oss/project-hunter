"""The shared admission service — the only path that admits a trade proposal.

``docs/plans/M3.md`` T3.12: explicit origin, deduplication, a durable FIFO place,
and decision + reservation + audit + outbox **atomically**, in one transaction,
under the lock order system -> organization -> portfolio. The manual paper order
of the API and the agent bridge of T3.14 both call :func:`admit`; neither has a
path of its own, because a second writer is a second set of rules.

Reservations are closed here too — a fill *consumes* one, a cancellation
*releases* one, and the 30 s tenure *expires* one — because the cycle is single
by invariant rather than by DDL (DATABASE.md §18.3).
"""

from hunter_core.admission.dedupe import AdmittedProposal, IdempotencyConflict, find_admitted
from hunter_core.admission.inputs import MarketMismatch
from hunter_core.admission.participation import participation_used
from hunter_core.admission.reservation import (
    RESERVATION_TTL,
    ReservationCycleClosed,
    close_reservation,
    expire_reservations,
)
from hunter_core.admission.service import AdmissionResult, admit
from hunter_core.admission.sources import OriginRefused, ProposalRequest, admission_key

__all__ = [
    "RESERVATION_TTL",
    "AdmissionResult",
    "AdmittedProposal",
    "IdempotencyConflict",
    "MarketMismatch",
    "OriginRefused",
    "ProposalRequest",
    "ReservationCycleClosed",
    "admission_key",
    "admit",
    "close_reservation",
    "expire_reservations",
    "find_admitted",
    "participation_used",
]
