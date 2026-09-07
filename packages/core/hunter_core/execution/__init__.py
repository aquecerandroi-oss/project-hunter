"""``hunter_core.execution`` — the paper wallet's execution layer (M3, T3.4).

Four modes and three pure calculations:

- :class:`~hunter_core.execution.paper.PaperExecutionAdapter` walks the real
  spot book after a declared latency and returns an
  :class:`~hunter_core.execution.adapter.ExecutionReport`; the ledger applies it;
- :class:`~hunter_core.execution.shadow.ShadowExecutionAdapter` records the
  attempt and, structurally, fills nothing;
- :class:`~hunter_core.execution.live.LiveExecutionAdapter` raises
  :class:`~hunter_core.execution.adapter.LiveTradingDisabled`, always;
- :mod:`~hunter_core.execution.triggers` decides stop and target from the last
  valid SPOT trade, :mod:`~hunter_core.execution.book_walk` decides what a book
  fills, and :mod:`~hunter_core.execution.intents` keeps the difference between
  an attempt and a durable intention.
"""

from hunter_core.execution.adapter import (
    EntryWithoutApproval,
    ExecutionAdapter,
    ExecutionJournal,
    ExecutionReport,
    FeeCharge,
    FeeSchedule,
    InMemoryExecutionJournal,
    LevelFill,
    LiveTradingDisabled,
    Residual,
    SpotFilters,
)
from hunter_core.execution.book_walk import (
    BOOK_POLICY_VERSION,
    BookVerdict,
    BookWalk,
    eligible_book,
    walk_book,
)
from hunter_core.execution.entries import (
    MarketEntryOrder,
    client_order_id_for_entry,
    execution_key_for_entry,
)
from hunter_core.execution.intents import (
    ExitAttempt,
    ExitIntent,
    allocate_sellable,
    apply_attempt,
    client_order_id_for_exit,
    execution_key_for_exit,
    supersede,
    void_intent,
)
from hunter_core.execution.live import LiveExecutionAdapter
from hunter_core.execution.paper import PaperExecutionAdapter
from hunter_core.execution.pricing import EXECUTION_POLICY_VERSION, ExecutionPolicy
from hunter_core.execution.shadow import ShadowExecutionAdapter
from hunter_core.execution.triggers import (
    MARKING_POLICY_VERSION,
    MarkingPolicy,
    ProtectedPosition,
    TriggerEvaluation,
    check_triggers,
)

__all__ = [
    "BOOK_POLICY_VERSION",
    "EXECUTION_POLICY_VERSION",
    "MARKING_POLICY_VERSION",
    "BookVerdict",
    "BookWalk",
    "EntryWithoutApproval",
    "ExecutionAdapter",
    "ExecutionJournal",
    "ExecutionPolicy",
    "ExecutionReport",
    "ExitAttempt",
    "ExitIntent",
    "FeeCharge",
    "FeeSchedule",
    "InMemoryExecutionJournal",
    "LevelFill",
    "LiveExecutionAdapter",
    "LiveTradingDisabled",
    "MarketEntryOrder",
    "MarkingPolicy",
    "PaperExecutionAdapter",
    "ProtectedPosition",
    "Residual",
    "ShadowExecutionAdapter",
    "SpotFilters",
    "TriggerEvaluation",
    "allocate_sellable",
    "apply_attempt",
    "check_triggers",
    "client_order_id_for_entry",
    "client_order_id_for_exit",
    "eligible_book",
    "execution_key_for_entry",
    "execution_key_for_exit",
    "supersede",
    "void_intent",
    "walk_book",
]
