"""Cycle time of a loop, measured (EXP-M26 §6.8, "trava de ciclo").

Until now nothing recorded how long the chain loop or the Lab loop took per
cycle — ``chain_cycle_s`` on the radar heartbeat is only the RPC batch of the
last cycle (not the whole step), and ``meme_lab_ticks`` has no duration. The
§6.8 guard ("ciclo da cadeia e do Lab: +20 % no p95") had no series to compare,
and "não mensurável" never counts as "passou". This module is that series.

**What is measured.** The wall duration of one ``step(ctx)`` call of
:func:`hunter_meme_worker.collect.forever` — for the Lab the whole ``lab_tick``,
``record_tick`` and heartbeat write included — in whole milliseconds (``int``,
integer arithmetic on ``monotonic_ns``; a duration, not money). The sleep that
``forever`` takes *after* the step is **not** part of it, nor is the publication
of the number itself. A cycle is an *overrun* when it is longer than the loop's
nominal period (``chain_cycle_s`` / ``lab_cycle_s``). That is a work threshold,
not a missed deadline: the real cadence is always ``duration + period``, so a
Lab going from 10 s to 13 s got 30 % slower without any overrun. The guard
compares the p95 on its own; the counter is only an alarm.

**Bounded.** A fixed-size ring (``window`` completed cycles — about two hours
only when the work is negligible) feeds the percentiles; the counters are plain
integers. Nothing grows.

**Published** as strings on the worker's own ``hb:meme:radar`` hash, in the
heartbeat style of the repo (an unmeasured number is ``""``, never ``0``)::

    <loop>_cycle_run_id      this process's generation of the series (uuid4 hex)
    <loop>_cycle_since       UTC ISO-8601, when the generation started
    <loop>_cycles_total      cycles recorded in this generation
    <loop>_overruns_total    cycles longer than the nominal period
    <loop>_last_cycle_ms     the last cycle
    <loop>_last_cycle_at     UTC ISO-8601, when the last cycle ended
    <loop>_cycle_ms_p50|p95|p99|max   nearest-rank over the ring
    <loop>_cycle_window_n    samples in the ring right now
    <loop>_cycle_nominal_ms  the loop nominal period
    <loop>_cycle_publish_failed_total   publications that failed or missed their budget

A reader must key on ``run_id``: the general ``ts`` of the heartbeat never says
whether these numbers belong to the running process (:func:`announce` overwrites
the previous process fields with an empty generation at boot).

The numbers are written right after each cycle (one ``HSET``), under a budget of
their own (``PUBLISH_BUDGET_S``) so a degraded Redis costs the loop at most that
much, never the client retries. An overrun is logged (``meme_cycle_overrun``)
at most once per ``log_every_s``; the line says how many it swallowed. Otherwise
the wrapper changes nothing about the loop: same return, same exception
(``forever`` still takes the process down), and a publication that fails is a
warning, never a stopped loop.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_worker.lab_heartbeat import percentile

logger = get_logger(__name__)

__all__ = [
    "CHAIN_WINDOW",
    "LAB_WINDOW",
    "PUBLISH_BUDGET_S",
    "CycleMeter",
    "CyclePublisher",
    "CycleSample",
    "announce",
    "announce_all",
    "timed_step",
]

CHAIN_WINDOW = 120
"""120 completed cycles of a 60 s loop."""

LAB_WINDOW = 480
"""480 completed cycles of a 15 s loop."""

OVERRUN_LOG_EVERY_S = 300.0
PUBLISH_BUDGET_S = 1.0
_NS_PER_S = 1_000_000_000

CyclePublisher = Callable[[dict[str, str]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class CycleSample:
    """One completed cycle, as the durable history records it (``seq`` is the
    meter's ``cycles_total`` inside its ``run_id``)."""

    loop: str
    run_id: str
    seq: int
    ended_at: datetime
    duration_ms: int


class CycleMeter:
    """The rolling record of one loop's cycle durations, for one process."""

    def __init__(
        self,
        loop: str,
        *,
        nominal_s: float,
        window: int,
        started_at: datetime | None = None,
        enabled: bool = True,
    ) -> None:
        if window < 1:
            raise ValueError("window must be at least 1 sample")
        started_at = started_at or utcnow()
        if started_at.utcoffset() != timedelta(0):
            raise ValueError("generation start must be timezone-aware UTC")
        self.loop = loop
        self.enabled = enabled
        self.window = window
        self.nominal_ms = round(nominal_s * 1000)
        self.run_id = uuid.uuid4().hex
        self.started_at = started_at
        self._ring: deque[int] = deque(maxlen=window)
        self.cycles_total = 0
        self.overruns_total = 0
        self.publish_failed_total = 0
        self.last_cycle_ms: int | None = None
        self.last_cycle_at: datetime | None = None

    def record(self, duration_ms: int, at: datetime) -> bool:
        """Record one cycle that ended at ``at`` (UTC); ``True`` when it overran."""
        if duration_ms < 0:
            raise ValueError("duration must not be negative")
        if at.utcoffset() != timedelta(0):
            raise ValueError("cycle end must be timezone-aware UTC")
        self._ring.append(duration_ms)
        self.cycles_total += 1
        self.last_cycle_ms = duration_ms
        self.last_cycle_at = at
        overran = duration_ms > self.nominal_ms
        if overran:
            self.overruns_total += 1
        return overran

    def fields(self) -> dict[str, str]:
        """The heartbeat fields; ``""`` where nothing was measured yet."""
        sample = list(self._ring)

        def number(value: int | None) -> str:
            return "" if value is None else str(value)

        values: dict[str, str] = {
            "cycle_run_id": self.run_id,
            "cycle_since": self.started_at.isoformat(),
            "cycle_enabled": "true" if self.enabled else "false",
            "cycles_total": str(self.cycles_total),
            "overruns_total": str(self.overruns_total),
            "last_cycle_ms": number(self.last_cycle_ms),
            "last_cycle_at": "" if self.last_cycle_at is None else self.last_cycle_at.isoformat(),
            "cycle_ms_p50": number(percentile(sample, 0.50)),
            "cycle_ms_p95": number(percentile(sample, 0.95)),
            "cycle_ms_p99": number(percentile(sample, 0.99)),
            "cycle_ms_max": number(max(sample, default=None)),
            "cycle_window_n": str(len(sample)),
            "cycle_nominal_ms": str(self.nominal_ms),
            "cycle_publish_failed_total": str(self.publish_failed_total),
        }
        return {f"{self.loop}_{name}": value for name, value in values.items()}


async def _publish(
    meter: CycleMeter, publish: CyclePublisher, budget_s: float = PUBLISH_BUDGET_S
) -> None:
    """One bounded, never-raising publication of the meter's fields."""
    try:
        async with asyncio.timeout(budget_s):
            await publish(meter.fields())
    except Exception:  # a heartbeat that cannot be written must not stop the loop
        meter.publish_failed_total += 1
        logger.warning("meme_cycle_metrics_publish_failed", loop=meter.loop)


async def announce(
    meter: CycleMeter, publish: CyclePublisher, *, budget_s: float = PUBLISH_BUDGET_S
) -> None:
    """Publish the empty generation at boot, replacing the previous process's fields."""
    await _publish(meter, publish, budget_s)


async def announce_all(
    meters: Sequence[CycleMeter], publish: CyclePublisher, *, budget_s: float = PUBLISH_BUDGET_S
) -> None:
    """:func:`announce` for every meter, **enabled or not** — a loop that is switched
    off must still replace the previous process's fields (zombie metrics), and one
    failed publication never keeps the others from going out."""
    for meter in meters:
        await announce(meter, publish, budget_s=budget_s)


def timed_step[ContextT, ResultT](
    meter: CycleMeter,
    step: Callable[[ContextT], Awaitable[ResultT]],
    publish: CyclePublisher,
    *,
    clock: Callable[[], int] = time.monotonic_ns,
    now: Callable[[], datetime] = utcnow,
    log_every_s: float = OVERRUN_LOG_EVERY_S,
    publish_budget_s: float = PUBLISH_BUDGET_S,
    on_cycle: Callable[[CycleSample], None] | None = None,
) -> Callable[[ContextT], Coroutine[Any, Any, ResultT]]:
    """``step`` with its duration recorded and published after every cycle.

    A step that raises is not recorded (``forever`` re-raises and the process
    goes down; a half cycle is not a cycle time).
    """
    log_every_ns = round(log_every_s * _NS_PER_S)
    last_logged: int | None = None
    suppressed = 0

    async def wrapped(ctx: ContextT) -> ResultT:
        nonlocal last_logged, suppressed
        started = clock()
        result = await step(ctx)
        ended = clock()
        duration_ms = (ended - started + 500_000) // 1_000_000  # nearest whole ms
        ended_at = now()
        overran = meter.record(duration_ms, ended_at)
        if on_cycle is not None:
            try:
                on_cycle(
                    CycleSample(
                        loop=meter.loop,
                        run_id=meter.run_id,
                        seq=meter.cycles_total,
                        ended_at=ended_at,
                        duration_ms=duration_ms,
                    )
                )
            except Exception:  # the durable copy must never stop the loop
                logger.warning("meme_cycle_history_offer_failed", loop=meter.loop)
        if overran:
            if last_logged is None or ended - last_logged >= log_every_ns:
                logger.warning(
                    "meme_cycle_overrun",
                    loop=meter.loop,
                    duration_ms=duration_ms,
                    nominal_ms=meter.nominal_ms,
                    overruns_total=meter.overruns_total,
                    suppressed=suppressed,
                )
                last_logged, suppressed = ended, 0
            else:
                suppressed += 1
        await _publish(meter, publish, publish_budget_s)
        return result

    return wrapped
