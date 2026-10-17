"""The frozen vocabulary of docs/RISK_ENGINE_B3.md §1.2 that the pure engine uses.

``b3_kill_state`` is "the same enum as SPOT" (§1.2), so it is
``hunter_core.domain.enums.KillSwitchState`` — re-exported, never redefined. The values
here are the names in the database, the event and the TypeScript types; renaming one is
changing the contract first.
"""

from __future__ import annotations

from enum import StrEnum

from hunter_core.domain.enums import KillSwitchState

__all__ = [
    "AuthorityPhase",
    "CheckState",
    "DecisionKind",
    "ExitReason",
    "KillCause",
    "KillSwitchState",
    "Side",
    "SpecStatus",
    "TradeMode",
]


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class TradeMode(StrEnum):
    """``AccountSnapshot.trade_mode``: only ``demo`` and ``real`` (with K1) may trade."""

    DEMO = "demo"
    REAL = "real"
    CONTEST = "contest"


class AuthorityPhase(StrEnum):
    """``b3_authority_phase`` (§2.1)."""

    READ_ONLY = "read_only"
    MANAGEMENT = "management"
    ENTRIES = "entries"


class CheckState(StrEnum):
    """``b3_check_state``: ``unavailable`` rejects, like ``failed``."""

    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class SpecStatus(StrEnum):
    """``SpecNow.status`` (§8.1)."""

    OK = "ok"
    CHANGED = "changed"
    UNREADABLE = "unreadable"


class ExitReason(StrEnum):
    """``b3_exit_reason``."""

    TIME_EXIT = "time_exit"
    SESSION_FLATTEN = "session_flatten"
    EMERGENCY = "emergency"
    REVERSAL = "reversal"
    OVERNIGHT_CARRY = "overnight_carry"


class KillCause(StrEnum):
    """``b3_kill_cause``. The engine only ever emits the first two (§8.4 ``triggers``)."""

    DAILY_LOSS_LIMIT = "daily_loss_limit"
    BROKER_REJECT_BREAKER = "broker_reject_breaker"
    REVERSAL_DETECTED = "reversal_detected"
    MANUAL_ROUTE = "manual_route"
    AGENT_COMMAND = "agent_command"
    OWNER_COMMAND = "owner_command"
    OWNER_BUTTON = "owner_button"


class DecisionKind(StrEnum):
    """An entry decision carries the 25 checks; an exit decision always approves (§8.6)."""

    ENTRY = "entry"
    EXIT = "exit"
