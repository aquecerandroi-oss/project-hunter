"""One attempt, one execution — the identity checks that make a replay safe.

Everything in this module answers the same question: *has this exact effect
already happened, and is the thing being replayed really the same thing?*

- :class:`InMemoryExecutionJournal` — the journal a worker keeps for one cycle;
  in production the journal is ``fills.execution_key`` (``docs/DATABASE.md``
  §18.3);
- :func:`guard_replay` — a recorded report is only handed back when the caller
  is replaying **the same** order. Returning the old report for a *different*
  quantity or a *different* decision under the same ``entry:{proposal_id}`` key
  would answer "already executed" to an order that never was (review of
  2026-09-07, item 9), so the mismatch is raised, loudly, with both values;
- :func:`applied_attempts_from_execution_keys` — rebuilds
  :attr:`~hunter_core.execution.intents.ExitIntent.applied_attempts` from the
  rows that were really written — ``fills.execution_key`` **and**
  ``orders.client_order_id``, the same ``exit:{attempt_id}`` string. Both, not
  just the fills: an attempt that found no book is applied to the intention (it
  marks the degradation) and writes no fill at all, so deriving from fills alone
  loses it (Astra, T3.4b review, MUST-FIX 2). This is what keeps
  :func:`~hunter_core.execution.intents.apply_attempt` idempotent across a
  restart while ``portfolio_exit_intents`` still has no column for it (debt
  registered for T3.1b/T3.10 in ``.claude/state/notes-T3.4.md`` §10).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.execution.adapter import ExecutionReport
from hunter_core.strategies.canonical import params_hash

if TYPE_CHECKING:  # pragma: no cover - imported for signatures only
    from collections.abc import Iterable

    from hunter_risk.decision import RiskDecision

__all__ = [
    "InMemoryExecutionJournal",
    "ReplayMismatch",
    "applied_attempts_from_execution_keys",
    "decision_fingerprint",
    "guard_replay",
]

_EXIT_PREFIX = "exit:"


class ReplayMismatch(RuntimeError):
    """The execution key was reused for something that is not the same order.

    Raised instead of returning the recorded report, because the two silent
    alternatives are both worse: answering with the old fill lets a caller
    believe a *bigger* order executed, and walking the book again opens a second
    position for one decision.
    """

    def __init__(
        self,
        execution_key: str,
        *,
        recorded_qty: Decimal | None,
        requested_qty: Decimal,
        recorded_decision: str,
        requested_decision: str,
    ) -> None:
        self.execution_key = execution_key
        self.recorded_qty = recorded_qty
        self.requested_qty = requested_qty
        self.recorded_decision = recorded_decision
        self.requested_decision = requested_decision
        super().__init__(
            f"{execution_key} was already executed for a different order: "
            f"recorded_qty={recorded_qty} requested_qty={requested_qty} "
            f"recorded_decision={recorded_decision or '(none)'} "
            f"requested_decision={requested_decision or '(none)'}"
        )


def decision_fingerprint(decision: RiskDecision) -> str:
    """A stable identity for the decision that authorised an order.

    ``RiskDecision`` has no id of its own — the proposal's id is already in the
    execution key — so the identity is the canonical hash of the decision
    itself. Two evaluations that sized differently fingerprint differently,
    which is exactly what the replay guard has to notice.
    """
    return params_hash(decision.to_jsonable())


def guard_replay(
    recorded: ExecutionReport,
    *,
    submitted_qty: Decimal,
    decision: str = "",
) -> ExecutionReport:
    """Hand back the recorded execution, or refuse to call this a replay.

    **Unknown identity is not equality** (Astra, T3.4b review, MUST-FIX 3). A
    report rebuilt from a row that does not carry ``submitted_qty`` used to
    match anything, so the recorded fill of 3 was handed to an order for 2 —
    the guard defeated by a round trip through Postgres. A recorded report
    without the field fails closed; the decision is compared whenever the
    caller names one (an exit has no decision and names none).
    """
    same_qty = recorded.submitted_qty == submitted_qty
    same_decision = not decision or recorded.decision_fingerprint == decision
    if same_qty and same_decision:
        return recorded
    raise ReplayMismatch(
        recorded.execution_key,
        recorded_qty=recorded.submitted_qty,
        requested_qty=submitted_qty,
        recorded_decision=recorded.decision_fingerprint,
        requested_decision=decision,
    )


def applied_attempts_from_execution_keys(keys: Iterable[str]) -> tuple[uuid.UUID, ...]:
    """The attempt ids behind ``exit:{attempt_id}`` keys, in the order given.

    Feed it ``fills.execution_key`` **and** ``orders.client_order_id`` for the
    intention: a degraded attempt has an order row and no fill row, and only the
    union of the two is the set of attempts already applied. Keys of other kinds
    (an entry's ``entry:{proposal_id}``) are ignored; an ``exit:`` key that does
    not carry a UUID is **refused**, because silently dropping one would
    silently restore the double count it exists to prevent.
    """
    attempts: list[uuid.UUID] = []
    for key in keys:
        if not key.startswith(_EXIT_PREFIX):
            continue
        raw = key[len(_EXIT_PREFIX) :]
        try:
            attempts.append(uuid.UUID(raw))
        except ValueError as exc:
            raise ValueError(f"malformed execution key {key!r}: 'exit:' needs a UUID") from exc
    return tuple(attempts)


class InMemoryExecutionJournal:
    """The journal a worker keeps in memory for one cycle; Postgres keeps the real
    one in ``fills.execution_key`` (``docs/DATABASE.md`` §18.3)."""

    def __init__(self) -> None:
        self.reports: dict[str, ExecutionReport] = {}

    def get(self, execution_key: str) -> ExecutionReport | None:
        return self.reports.get(execution_key)

    def record(self, report: ExecutionReport) -> None:
        """First writer wins: a replay never overwrites the recorded execution."""
        self.reports.setdefault(report.execution_key, report)
