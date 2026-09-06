"""One backfill request, turned into the minutes this worker will actually ask for.

Pure arithmetic over minutes — no session, no Redis, no adapter — because every
hard decision of the feature lives here and each one is cheap to pin with a
test: where the request's interval ends, how far back we are willing to go, what
is already covered, and how much of it one pass may write.

**Two interval conventions meet in this module.** The scanner publishes a
**half-open** window ``[gap_start, gap_end)`` (``hunter_scanner_worker.backfill``:
"the five missing minutes 10:00..10:04 spanned four and were rejected"), and
``ingestion_gaps`` is **inclusive at both ends** — ``recovery.expected_times``
counts ``gap_end`` in and the REST fetch asks for ``gap_end + 1min``. The
translation happens once, here, and :func:`normalize_window` is the only place
allowed to know it.

The request is a *fact about a window*, never a command: nothing in this module
fetches anything. It produces rows for the gap table, and the recovery loop that
already owns REST, the rate limit and the retry policy drains them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import ensure_utc

MINUTE = timedelta(minutes=1)

MAX_REQUEST_MINUTES = 7 * 24 * 60
"""Ceiling of one request: seven days, the baseline bootstrap window of the
joint M2 decision ("420 observações esperadas por bucket em 7 dias").

A larger window is **truncated to its most recent** seven days rather than
refused: the recent end is what a baseline needs first, and refusing outright
would leave a market with no history at all. The truncation is final — the
ceiling is policy, not budget — and it is said in the log, so a consumer that
needs thirty days (the regime's reference) sees that it got seven and can ask
again for the rest as its own window."""

CHUNK_MINUTES = 240
"""Minutes per ``ingestion_gaps`` row. Four hours, and the number is bounded
from **both** sides.

Above: ``BinanceRestClient.fetch_candles`` pages at ``_KLINES_PAGE_LIMIT``
(1500) with weight 10 per page, so anything up to 1500 minutes is one page —
one HTTP call inside ``recovery.FETCH_TIMEOUT_S``.

Below: the retry unit, not the outbox anymore. A chunk is one
``recover_registered`` attempt, so a chunk that fails (timeout, a transient
Postgres error) retries 240 minutes instead of a whole multi-day request.
Before T2.9c this floor was doing double duty: every backfilled minute was
announced as its own ``market.candles.closed`` through the outbox
(``durable.enqueue_candles``, the same path as a live candle), so one
recovered chunk enqueued ``CHUNK_MINUTES`` rows in one transaction and 240 was
also sized to keep that from being most of the readiness ceiling
(``MAX_PENDING``, 500) by itself. T2.9c replaced that with one aggregate
``market.candles.backfilled`` per chunk
(``backfill_announce.enqueue_candles_backfilled``), so the outbox no longer
bounds this number from below.

**What 240 bounds, precisely (T2.9c):** the retry unit and the per-cycle
history *throughput*, not the outbox. ``MAX_HISTORY_GAPS_PER_CYCLE x
CHUNK_MINUTES`` = 1 440 minutes of history recovered per cycle is still the
real per-cycle ceiling (Astra, T2.5-backfill diff review) — it now bounds how
much history a bootstrap catches up per minute of wall clock, not how many
outbox rows a cycle produces. That number is ``MAX_HISTORY_GAPS_PER_CYCLE``
(one aggregate event per chunk), independent of ``CHUNK_MINUTES``."""

MERGE_MINUTES = 60
"""Two holes closer than this become one row.

Refetching minutes that are already persisted is free — the upsert is by
natural key and the outbox only enqueues rows it actually inserted — so one
REST call over a short island of present candles beats two calls around it.
The merge **never** crosses minutes owned by an existing ``open``/``failed``
gap: that coverage is a barrier, not an island (Astra, T2.5-backfill design
review, must-fix 2)."""

MAX_ROWS_PER_REQUEST = 48
"""Rows one pass may write for one request. Seven days at ``CHUNK_MINUTES`` is
42, so a contiguous seven-day hole lands whole; the ceiling only bites on a
window shredded into more separate holes than that. What is left over is
**deferred, not dropped**: the plan reports it, the consumer therefore does not
mark the request finished, and the next republication of the same ``event_id``
plans the older holes — the newer ones are covered by the rows this pass wrote
(Astra, T2.5-backfill design review, must-fix 4)."""

MISSING, PERSISTED, BLOCKED = 0, 1, 2

__all__ = [
    "CHUNK_MINUTES",
    "MAX_REQUEST_MINUTES",
    "MAX_ROWS_PER_REQUEST",
    "MERGE_MINUTES",
    "MINUTE",
    "Plan",
    "Refused",
    "Window",
    "normalize_window",
    "outcome_name",
    "plan_chunks",
]


class Refused(Exception):
    """This request will not be served, and the reason is not transient.

    Refusals are answered with a physical ``XACK`` and **no** processed mark:
    the same ``event_id`` republished later is evaluated again from scratch
    (Astra, must-fix 1).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Window:
    """The inclusive minute range this worker accepted from one request."""

    first_minute: datetime
    last_minute: datetime
    requested_minutes: int
    truncated: bool
    clamped_minutes: int = 0
    """Minutes cut off the **recent** end because they are not settled yet.

    Kept apart from ``truncated`` because the two are opposites in time and in
    finality: the seven-day ceiling drops the oldest minutes **for good** (it is
    policy), while this drops the newest ones **for now** — they will be settled
    in a few minutes. A request whose end reached into the future must therefore
    never be marked processed, or the republication after those minutes close
    would be dropped by the guard and nobody would ever plan them (Astra,
    T2.5-backfill diff review, must-fix 1)."""

    @property
    def minutes(self) -> int:
        return int((self.last_minute - self.first_minute) / MINUTE) + 1

    def every_minute(self) -> list[datetime]:
        return [self.first_minute + MINUTE * n for n in range(self.minutes)]


@dataclass(frozen=True)
class Plan:
    """What one pass will write, and what it knowingly left behind."""

    chunks: list[tuple[datetime, datetime]]
    planned_minutes: int
    deferred_minutes: int
    blocked_minutes: int

    @property
    def complete(self) -> bool:
        """Did this pass account for the whole window **by itself**?

        Deliberately conservative: minutes left to a pre-existing gap row count
        as *not* accounted for here, even though that row is someone's promise
        to fetch them. The consequence is that such a request is re-evaluated
        on the next republication instead of being marked processed — two
        queries an hour — and that it self-heals: once the other gap recovers,
        those minutes are persisted and the request completes for real.
        """
        return self.deferred_minutes == 0 and self.blocked_minutes == 0


def normalize_window(gap_start: datetime, gap_end: datetime, *, detection_last: datetime) -> Window:
    """Half-open ``[gap_start, gap_end)`` -> the inclusive minutes we accept.

    ``detection_last`` is ``align_open_time(server_now) - DETECTION_GRACE``:
    the newest minute the collector itself treats as settled. Asking beyond it
    would open a gap for a candle that is not closed yet, or that is still
    sitting in the persistence queue (``recovery.DETECTION_GRACE``).
    """
    try:
        start, end = ensure_utc(gap_start), ensure_utc(gap_end)
    except ValueError as exc:
        raise Refused("naive_timestamp") from exc

    first = align_open_time(start, Timeframe.M1)
    # Astra's formula, and one minute wider than clamping to detection_last
    # directly: the last minute we may ask for is detection_last itself.
    asked_end = align_open_time(end, Timeframe.M1)
    end_exclusive = min(asked_end, detection_last + MINUTE)
    last = end_exclusive - MINUTE
    if last < first:
        raise Refused("future_window" if first > detection_last else "empty_window")

    clamped = max(0, int((asked_end - end_exclusive) / MINUTE))
    requested = int((last - first) / MINUTE) + 1 + clamped
    truncated = requested - clamped > MAX_REQUEST_MINUTES
    if truncated:
        first = last - MINUTE * (MAX_REQUEST_MINUTES - 1)
    return Window(
        first_minute=first,
        last_minute=last,
        requested_minutes=requested,
        truncated=truncated,
        clamped_minutes=clamped,
    )


def _classify(
    window: Window, persisted: set[datetime], blocked: set[datetime]
) -> list[tuple[datetime, int]]:
    states: list[tuple[datetime, int]] = []
    for minute in window.every_minute():
        if minute in persisted:
            states.append((minute, PERSISTED))
        elif minute in blocked:
            states.append((minute, BLOCKED))
        else:
            states.append((minute, MISSING))
    return states


def _runs(states: list[tuple[datetime, int]]) -> list[tuple[datetime, datetime]]:
    """Contiguous stretches of missing minutes, merged over short present ones."""
    runs: list[tuple[datetime, datetime]] = []
    run: tuple[datetime, datetime] | None = None
    present_since_run = 0
    for minute, state in states:
        if state == MISSING:
            if run is None or present_since_run >= MERGE_MINUTES:
                if run is not None:
                    runs.append(run)
                run = (minute, minute)
            else:
                run = (run[0], minute)
            present_since_run = 0
        elif state == PERSISTED:
            if run is not None:
                present_since_run += 1
        else:  # BLOCKED: a hard barrier, never merged across.
            if run is not None:
                runs.append(run)
            run, present_since_run = None, 0
    if run is not None:
        runs.append(run)
    return runs


def _chunked(runs: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    chunks: list[tuple[datetime, datetime]] = []
    for start, end in runs:
        cursor = start
        while cursor <= end:
            stop = min(end, cursor + MINUTE * (CHUNK_MINUTES - 1))
            chunks.append((cursor, stop))
            cursor = stop + MINUTE
    return chunks


def plan_chunks(
    window: Window,
    *,
    persisted: set[datetime],
    blocked: set[datetime],
    max_rows: int = MAX_ROWS_PER_REQUEST,
) -> Plan:
    """The ``ingestion_gaps`` rows this pass will write for ``window``.

    ``persisted`` are the final candles already in Postgres; ``blocked`` are the
    minutes an ``open``/``failed`` gap of the same market already owns. Both are
    read inside the same transaction that writes the rows, under the gap-planning
    advisory lock, so the periodic detection cannot insert a row for the same
    minutes between the read and the write.
    """
    states = _classify(window, persisted, blocked)
    chunks = _chunked(_runs(states))
    kept = chunks[-max_rows:] if max_rows > 0 else []

    covered: set[datetime] = set()
    for start, end in kept:
        covered |= {start + MINUTE * n for n in range(int((end - start) / MINUTE) + 1)}
    missing = [minute for minute, state in states if state == MISSING]
    return Plan(
        chunks=kept,
        planned_minutes=len(covered),
        deferred_minutes=sum(1 for minute in missing if minute not in covered),
        blocked_minutes=sum(1 for _, state in states if state == BLOCKED),
    )


def outcome_name(plan: Plan, window: Window, left_out: int) -> str:
    """One word for the metric; the log carries the numbers behind it.

    ``accepted`` means **planned in full**, never "recovered" — the fetch is the
    recovery loop's, and it happens minutes later (Astra's nice-to-have). A pass
    that wrote rows but left missing minutes behind, whether to the row budget or
    to a month with no partition, says ``partial`` instead: the first operational
    run showed a real seven-day request landing 5 247 minutes and dropping 3 300
    for want of the previous month's partition, and calling that ``accepted``
    would have hidden it.

    ``left_out`` is every minute this pass did not account for — deferred by the
    row budget, owned by another gap, unstorable for want of a partition, or not
    settled yet. It is exactly the condition under which the consumer withholds
    the processed mark, so the metric and the acknowledgement can never tell two
    different stories (Astra, T2.5-backfill diff review, nice-to-have 2).
    """
    if left_out:
        return "partial"
    if not plan.chunks:
        return "empty"
    return "truncated" if window.truncated else "accepted"
