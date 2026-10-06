"""Program logs -> swap records (wave 1a of H-030, "seguir carteiras que ganham de verdade").

A pure reader: one ``logsSubscribe`` notification (or the ``meta.logMessages`` of a
``getTransaction`` used to recover a gap) in, the pump bonding-curve ``TradeEvent``, the PumpSwap
``BuyEvent`` and the PumpSwap ``SellEvent`` out as ONE record shape, :class:`SwapRecord`. No IO, no
clock (``received_at`` is passed in), no database. Not wired into any worker.

**Attribution.** A ``Program data:`` line belongs to the program on top of the invoke stack the log
itself narrates (``Program X invoke [n]`` ... ``Program X success|failed``), never to the
subscription it arrived on: a transaction that touches both programs is delivered on both, so an
event must not be given to the wrong program. A line on top of some other program is only counted
(``foreign_data_lines``). The stack must be coherent: a return line of a program that is not on top, or
an ``invoke [n]`` that does not nest one level down, breaks the context (``stack_inconsistencies``) and
from then on no line is attributed (``unattributed_data_lines``): a gap, never a guess. The same
holds after a ``Log truncated`` marker or a non-text entry (either may hide an event line, so the
ordinal of everything after it is unknowable): only the prefix before the damage is read. A data line
seen with no invoke context is a possible loss too.

**Identity** of an event is ``(signature, program, event_ordinal)``. The ordinal counts that program's
``Program data:`` lines in the transaction **before** anything is validated, so a corrupt neighbour
never shifts the identity of the next event (the full recovery read gives the same one). A line that
is visibly missing (a non-text entry, ``Log truncated``, a data line with no frame around it) stops the
reading instead of shifting it. What cannot be seen from the logs alone is an event line deleted from
the middle of an intact frame; only the inner instructions would show it. Logs that end inside an open
frame (no marker) are a gap too (``open_frames_at_end``). The count agrees with the
``emit_cpi`` self-CPI events of the program on every real fixture (all events, swap or not); that
is observed, not guaranteed by the protocol (``Program data:`` is generic output). Identities
are stable; deduplicating the same transaction seen on two subscriptions or by recovery is the
consumer's job (``tape.dedupe``). For the PumpSwap the event names the **pool**, not the mint
(``mint`` is ``None``; pool -> mint is the collector's lookup, and each event goes to its own pool).

The normalised record and the per-venue arithmetic (what "gross SOL leg" and "fees" mean for each
of the three events, and which reserves are before or after the trade) live in
:mod:`hunter_exchanges.pumpfun.swap_record`.

**Nothing is dropped without a count** (:class:`LogCounters`). An event that does not decode, or
decodes but whose own money does not close, or is quoted in something other than SOL, is not turned
into a record: it is counted and described in :attr:`ProgramLogsRead.problems`, and the rest of the
notification is still read. :attr:`ProgramLogsRead.gap` says when the collector must record an
ingestion gap (``Log truncated``, an undecodable or unconserved event, a line that is not base64, an
unattributable data line or an incoherent invoke stack, logs the node did not return).

**Wave 1b.** The pump ``CompleteEvent`` is read too (it is not a swap): it corroborates each curve
reading of "complete at the event" and turns a contradiction into ``unknown``
(:mod:`hunter_exchanges.pumpfun.curve_completion`; counted, not a gap). Pool legs (mints of the
pool) need the swap instruction, which only a ``getTransaction`` result has: :func:`read_transaction_logs`
attaches them (:mod:`hunter_exchanges.pumpswap.pool_legs`), :func:`read_program_logs` cannot and leaves
them ``None`` without counting that as a failure.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, fields, replace
from datetime import datetime, timedelta
from typing import Any, Final, Literal, cast

from hunter_exchanges.pumpfun.completion_reconcile import reconcile_completion, refused_trade_mint
from hunter_exchanges.pumpfun.curve_completion import (
    COMPLETE_EVENT_DISCRIMINATOR,
    decode_complete_event,
)
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.swap_record import Refused, SwapRecord, swap_record_from_event
from hunter_exchanges.pumpfun.trade_event_codec import TRADE_EVENT_DISCRIMINATOR
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.pool_legs import attach_pool_legs

__all__ = [
    "LogCounters",
    "LogProblem",
    "ProgramLogsRead",
    "SwapRecord",
    "read_program_logs",
    "read_transaction_logs",
]

_DATA: Final = "Program data: "
_TRUNCATED: Final = "Log truncated"
_INVOKE = re.compile(r"^Program (\w+) invoke \[(\d+)\]$")
_RETURN = re.compile(r"^Program (\w+) (?:success|failed)")
_OURS: Final = frozenset({PUMP_PROGRAM_ID, PUMPSWAP_PROGRAM_ID})
_DETAIL_MAX: Final = 200


@dataclass(frozen=True, slots=True)
class LogCounters:
    swaps: int = 0
    non_swap_events: int = 0
    undecodable: int = 0
    unconserved: int = 0
    non_sol_quote: int = 0
    foreign_data_lines: int = 0
    unattributed_data_lines: int = 0
    stack_inconsistencies: int = 0
    """The invoke stack stopped making sense (counted once; attribution stops there)."""
    open_frames_at_end: int = 0
    """The logs ended with a program frame still open and no ``Log truncated`` marker: a successful
    transaction closes every frame, so the suffix (and its events) was lost."""
    orphan_complete_events: int = 0
    """A pump ``CompleteEvent`` with no trade of its mint before it in what was read: the draining
    trade is missing. A gap (the collector recovers the transaction); no swap is invented."""
    curve_completion_unknown: int = 0
    """Curve swaps whose completion at the event is ``unknown`` (a sell reading 0 real tokens, or the
    event and the transaction's ``CompleteEvent`` contradicting each other). Counted, NOT a gap: the
    swap itself is in the records."""
    pool_mints_unresolved: int = 0
    """Pool swaps (transaction path only) with no swap instruction matching the event: their mints
    stay unknown. Counted, not a gap."""
    pool_mints_via_sibling: int = 0
    """Pool swaps whose mints are resolved but share the pool and user with an instruction this reader
    does not understand (e.g. ``SellV2``): right by construction, not proven per invocation. Counted,
    not a gap."""
    pool_mints_conflict: int = 0
    """Pool swaps whose instruction(s) and the transaction's token-balance rows name different mints
    (or two matching instructions disagree): mints stay unknown. Counted, not a gap."""
    bad_base64: int = 0
    """Not valid base64, or shorter than an event discriminator: counted, a gap, never skipped."""
    malformed_lines: int = 0
    truncated_logs: int = 0
    logs_missing: int = 0
    failed_transactions: int = 0

    def __add__(self, other: LogCounters) -> LogCounters:
        return LogCounters(
            **{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)}
        )

    @property
    def gap(self) -> bool:
        """At least one swap may have been on the wire and is not in the records: the collector
        records an ingestion gap. Foreign lines, failed transactions, non-swap events and
        non-SOL quotes are accounted for and are NOT a gap."""
        return bool(
            self.undecodable
            or self.unconserved
            or self.bad_base64
            or self.malformed_lines
            or self.truncated_logs
            or self.logs_missing
            or self.unattributed_data_lines
            or self.stack_inconsistencies
            or self.open_frames_at_end
            or self.orphan_complete_events
        )


@dataclass(frozen=True, slots=True)
class LogProblem:
    program: str
    event_ordinal: int | None
    kind: Literal["undecodable", "unconserved"]
    detail: str


@dataclass(frozen=True, slots=True)
class ProgramLogsRead:
    swaps: tuple[SwapRecord, ...]
    counters: LogCounters
    problems: tuple[LogProblem, ...] = ()
    other_events: tuple[tuple[str, str], ...] = ()
    """``(program, discriminator hex)`` of every event of the two programs that is not a swap this
    reader turns into a record. A collector aggregates it to alert on a NEW event type (a future swap
    variant) instead of finding it missing from the population."""

    @property
    def gap(self) -> bool:
        return self.counters.gap


class _Scan:
    """One pass over one transaction's log lines. Never raises on garbage."""

    def __init__(self, envelope: dict[str, Any]) -> None:
        self.envelope = envelope
        self.c: dict[str, int] = {f.name: 0 for f in fields(LogCounters)}
        self.stack: list[str] = []
        self.blind = False
        """Attribution is no longer trustworthy (an incoherent stack, or a line that may have been an
        event is gone): every later data line is counted as unattributed, none is given an identity."""
        self.ordinals: dict[str, int] = {}
        self.swaps: list[SwapRecord] = []
        self.problems: list[LogProblem] = []
        self.others: list[tuple[str, str]] = []
        self.completes: list[tuple[int, str]] = []
        """``(ordinal, mint)`` of every pump ``CompleteEvent``, to corroborate the curve readings."""
        self.refused_trades: list[tuple[int, str | None]] = []
        """Pump trade events that did not become a record (``mint`` ``None`` when not even decodable):
        they keep their place, so a ``CompleteEvent`` is never attributed to an earlier trade."""

    def line(self, line: Any) -> None:
        if not isinstance(line, str):
            self.c["malformed_lines"] += 1
            self.blind = True  # it may have been an event line: the next ordinal is unknowable
        elif line == _TRUNCATED:
            self.c["truncated_logs"] += 1
            # The runtime may drop one big message, print the marker and keep later small ones, so
            # what follows it cannot be given an ordinal. Only the prefix before it is trusted.
            self.blind = True
        elif line.startswith(_DATA):
            self._data(line)
        elif m := _INVOKE.match(line):
            if not self.blind:
                self._invoke(m.group(1), int(m.group(2)))
        elif (m := _RETURN.match(line)) and not self.blind:
            self._return(m.group(1))

    def _break(self) -> None:
        self.blind = True
        self.c["stack_inconsistencies"] += 1

    def _invoke(self, program: str, depth: int) -> None:
        if depth != len(self.stack) + 1:
            self._break()
        else:
            self.stack.append(program)

    def _return(self, program: str) -> None:
        if not self.stack or self.stack[-1] != program:
            self._break()
        else:
            self.stack.pop()

    def _data(self, line: str) -> None:
        top = None if self.blind or not self.stack else self.stack[-1]
        if top is None:
            self.c["unattributed_data_lines"] += 1
            # An event line with no context: its program (and so its place in the ordinals) is
            # unknown, hence so is the ordinal of every event after it.
            self.blind = True
        elif top not in _OURS:
            self.c["foreign_data_lines"] += 1
        else:
            self._event(line, top)

    def _event(self, line: str, program: str) -> None:
        # The ordinal is taken first: whatever happens to this line, the next one keeps its identity.
        ordinal = self.ordinals.get(program, 0)
        self.ordinals[program] = ordinal + 1
        try:
            payload = base64.b64decode(line[len(_DATA) :], validate=True)
        except ValueError:
            payload = b""
        if len(payload) < 8:
            self.c["bad_base64"] += 1  # not an Anchor event at all: counted, and a gap
            if program == PUMP_PROGRAM_ID:
                self.refused_trades.append((ordinal, None))  # it may have been a trade
            return
        try:
            record = swap_record_from_event(
                program, payload, {**self.envelope, "program": program, "event_ordinal": ordinal}
            )
        except Refused as refusal:
            if program == PUMP_PROGRAM_ID and payload[:8] == TRADE_EVENT_DISCRIMINATOR:
                self.refused_trades.append((ordinal, refused_trade_mint(payload)))
            if refusal.kind == "non_sol_quote":
                self.c["non_sol_quote"] += 1
            else:
                self.c[refusal.kind] += 1
                self.problems.append(
                    LogProblem(program, ordinal, refusal.kind, refusal.detail[:_DETAIL_MAX])
                )
            return
        if record is None:
            self.c["non_swap_events"] += 1
            self.others.append((program, payload[:8].hex()))
            if program == PUMP_PROGRAM_ID and payload[:8] == COMPLETE_EVENT_DISCRIMINATOR:
                self._complete(payload, ordinal)
        else:
            self.c["swaps"] += 1
            self.swaps.append(record)

    def _complete(self, payload: bytes, ordinal: int) -> None:
        try:
            self.completes.append((ordinal, decode_complete_event(payload).mint))
        except ValueError as exc:
            self.c["undecodable"] += 1
            detail = str(exc)[:_DETAIL_MAX]
            self.problems.append(LogProblem(PUMP_PROGRAM_ID, ordinal, "undecodable", detail))


def read_program_logs(
    *,
    signature: str,
    slot: int,
    logs: list[Any] | tuple[Any, ...],
    received_at: datetime,
    err: object = None,
) -> ProgramLogsRead:
    """The swap records of one transaction's logs. ``err`` is the notification's ``value.err``: a
    failed transaction yields nothing (counted). Never raises on malformed ``logs``; raises
    ``ValueError`` only for a ``received_at`` that is not UTC-aware (a caller bug)."""
    if received_at.tzinfo is None or received_at.utcoffset() != timedelta(0):
        raise ValueError("received_at must be UTC-aware")
    if err is not None:
        return ProgramLogsRead((), LogCounters(failed_transactions=1))
    scan = _Scan({"signature": signature, "slot": slot, "received_at": received_at})
    for line in logs:
        scan.line(line)
    if scan.stack and not scan.blind:
        scan.c["open_frames_at_end"] = 1
    swaps, scan.c["orphan_complete_events"] = reconcile_completion(
        scan.swaps, scan.refused_trades, scan.completes
    )
    scan.c["curve_completion_unknown"] = sum(1 for s in swaps if s.curve_completion == "unknown")
    return ProgramLogsRead(
        tuple(swaps), LogCounters(**scan.c), tuple(scan.problems), tuple(scan.others)
    )


def read_transaction_logs(transaction: dict[str, Any], *, received_at: datetime) -> ProgramLogsRead:
    """The same reading over a ``getTransaction`` result (any transaction version: only ``meta``, the
    first signature and the slot are used) — the REST recovery path for a gap. A node that returns no
    ``logMessages`` is a gap (``logs_missing``), not an empty transaction. Raises ``ValueError`` for a
    result without a signature or a slot (a record without them has an identity nobody can look up)."""
    meta_any = transaction.get("meta")
    meta = cast(dict[str, Any], meta_any) if isinstance(meta_any, dict) else {}
    body = transaction.get("transaction")
    signatures = cast(dict[str, Any], body).get("signatures") if isinstance(body, dict) else None
    if not isinstance(signatures, list) or not signatures:
        raise ValueError("transaction without a signature")
    signature = str(cast(list[Any], signatures)[0])
    slot = transaction.get("slot")
    if not isinstance(slot, int) or isinstance(slot, bool) or slot < 0:
        raise ValueError("transaction without a slot")
    err = meta.get("err")
    logs = meta.get("logMessages")
    if err is None and not isinstance(logs, list):
        return ProgramLogsRead((), LogCounters(logs_missing=1))
    read = read_program_logs(
        signature=signature,
        slot=slot,
        logs=cast(list[Any], logs) if isinstance(logs, list) else [],
        received_at=received_at,
        err=err,
    )
    swaps, unresolved, conflicts, sibling = attach_pool_legs(transaction, read.swaps)
    counters = replace(
        read.counters,
        pool_mints_unresolved=unresolved,
        pool_mints_conflict=conflicts,
        pool_mints_via_sibling=sibling,
    )
    return replace(read, swaps=swaps, counters=counters)
