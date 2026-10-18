"""The B3 robot's enums — ``docs/RISK_ENGINE_B3.md`` §1.2, verbatim.

One ``StrEnum`` per Postgres type that ``0071_b3_robot`` creates; the labels
and their order are the contract's (``pg_enum.enumsortorder`` is compared by
the schema tests). Registered in :data:`hunter_core.domain.enums.ALL_ENUMS`.

``b3_kill_state`` is **not** a type of its own: the contract writes it as
"mesmo enum do SPOT", and DATABASE.md §1 allows one enum per concept, so the
column type is ``kill_switch_state`` and :data:`B3KillState` is an alias of
:class:`~hunter_core.domain.enums.KillSwitchState` (DATABASE.md §74).
"""

from __future__ import annotations

from enum import StrEnum


class B3AuthorityPhase(StrEnum):
    """``b3_authority_phase`` — §2.1. ``read_only`` never has a row."""

    READ_ONLY = "read_only"
    MANAGEMENT = "management"
    ENTRIES = "entries"


class B3AuthorityStatus(StrEnum):
    """``b3_authority_status`` — §2.2."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class B3EntryIntentStatus(StrEnum):
    """``b3_entry_intent_status`` — §3.1."""

    PROPOSED = "proposed"
    REJECTED = "rejected"
    APPROVED = "approved"
    EXPIRED = "expired"
    SUBMITTING = "submitting"
    ABORTED_BEFORE_SEND = "aborted_before_send"
    WORKING = "working"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELED = "canceled"
    BROKER_REJECTED = "broker_rejected"
    UNKNOWN = "unknown"
    RESOLVED_MANUAL = "resolved_manual"


class B3UnknownCause(StrEnum):
    """``b3_unknown_cause`` — §1.2, §6.1."""

    CLAIM_ACK_LOST = "claim_ack_lost"
    SEND_NO_RESULT = "send_no_result"
    SEND_TIMEOUT = "send_timeout"
    IPC_HANG = "ipc_hang"
    PROCESS_DIED = "process_died"
    CANCEL_NO_RESULT = "cancel_no_result"
    RESULT_NOT_PERSISTED = "result_not_persisted"
    JOURNAL_LOST = "journal_lost"
    HEARTBEAT_IN_FLIGHT = "heartbeat_in_flight"


class B3PositionState(StrEnum):
    """``b3_position_state`` — §4.1."""

    UNPROTECTED = "unprotected"
    PROTECTED = "protected"
    DEGRADED = "degraded"
    EXITING = "exiting"
    EXIT_OVERDUE = "exit_overdue"
    CLOSED = "closed"
    UNATTRIBUTED = "unattributed"


class B3DegradedReason(StrEnum):
    """``b3_degraded_reason`` — §4.1."""

    NAKED_AFTER_GRACE = "naked_after_grace"
    REPAIR_REJECTED = "repair_rejected"
    FLOOR_UNPLACEABLE = "floor_unplaceable"
    PROTECTION_UNKNOWN = "protection_unknown"


class B3SltpSlot(StrEnum):
    """``b3_sltp_slot`` — §4.3."""

    IDLE = "idle"
    IN_FLIGHT = "in_flight"
    UNKNOWN = "unknown"


class B3SltpRequestStatus(StrEnum):
    """``b3_sltp_request_status`` — §4.3. ``intended`` never downgrades a terminal."""

    INTENDED = "intended"
    NOT_SENT = "not_sent"
    DONE = "done"
    REJECTED = "rejected"
    UNKNOWN = "unknown"
    MOOT = "moot"
    RESOLVED_MANUAL = "resolved_manual"


class B3ExitReason(StrEnum):
    """``b3_exit_reason`` — §5.2."""

    TIME_EXIT = "time_exit"
    SESSION_FLATTEN = "session_flatten"
    EMERGENCY = "emergency"
    REVERSAL = "reversal"
    OVERNIGHT_CARRY = "overnight_carry"


class B3CloseCause(StrEnum):
    """``b3_close_cause`` — §4.2, §5.3."""

    SERVER_SL = "server_sl"
    SERVER_TP = "server_tp"
    BRACKET_SL = "bracket_sl"
    BRACKET_TP = "bracket_tp"
    MANUAL = "manual"
    BROKER_COMPULSORY = "broker_compulsory"
    UNEXPLAINED = "unexplained"


class B3Attribution(StrEnum):
    """``b3_attribution`` — §4.5."""

    ATTRIBUTED = "attributed"
    FOREIGN = "foreign"
    AMBIGUOUS = "ambiguous"
    UNREADABLE = "unreadable"


class B3CheckState(StrEnum):
    """``b3_check_state`` — §8.2. Lives inside ``checks[]``; the type exists for
    the 1:1 mirror, like ``backtest_warning_code`` (DATABASE.md §15.1)."""

    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class B3KillCause(StrEnum):
    """``b3_kill_cause`` — §1.2, §7.1."""

    DAILY_LOSS_LIMIT = "daily_loss_limit"
    BROKER_REJECT_BREAKER = "broker_reject_breaker"
    REVERSAL_DETECTED = "reversal_detected"
    MANUAL_ROUTE = "manual_route"
    AGENT_COMMAND = "agent_command"
    OWNER_COMMAND = "owner_command"
    OWNER_BUTTON = "owner_button"


B3_ENUMS: dict[str, type[StrEnum]] = {
    "b3_authority_phase": B3AuthorityPhase,
    "b3_authority_status": B3AuthorityStatus,
    "b3_entry_intent_status": B3EntryIntentStatus,
    "b3_unknown_cause": B3UnknownCause,
    "b3_position_state": B3PositionState,
    "b3_degraded_reason": B3DegradedReason,
    "b3_sltp_slot": B3SltpSlot,
    "b3_sltp_request_status": B3SltpRequestStatus,
    "b3_exit_reason": B3ExitReason,
    "b3_close_cause": B3CloseCause,
    "b3_attribution": B3Attribution,
    "b3_check_state": B3CheckState,
    "b3_kill_cause": B3KillCause,
}
"""Type name -> class, merged into ``ALL_ENUMS``."""
