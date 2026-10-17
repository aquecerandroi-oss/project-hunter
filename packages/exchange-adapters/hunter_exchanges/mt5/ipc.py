"""One serialized lane to the terminal, with a deadline per call and a latch when one hangs.

The vendor API is blocking IPC to a local terminal and is not meant to be called concurrently.
Every call therefore goes through a **single** worker thread, and is awaited with a deadline
(``ipc_call_timeout_s``, contract §9 / F4).

Lifecycle of a call (``docs/RISK_ENGINE_B3.md`` F4, G5, I-A-4):

* **admission** — refused at once when the lane is latched ``hung``;
* **start** — the worker marks the call ``started`` under a lock, or skips it when it was
  abandoned or the lane latched while it waited in the queue: *work that never started never
  starts later*, so a mutation queued behind a stuck call cannot fire when that call returns;
* **deadline** — a call that has *started* and overruns cannot be cancelled (the thread is stuck
  inside the vendor library): the lane **latches** ``hung`` until the process restarts. A call
  that overruns without having started is abandoned and does not latch (``started=False``);
* **cancellation** of the awaiting coroutine is not cancellation of the call: a started call
  keeps running. Its outcome is kept like a late one, and if it was a *mutation* the lane
  reports :attr:`IpcExecutor.unresolved` — no new mutation until the caller has collected it.

A late result is exposed only through ``on_late`` (the adapter turns an ``order_send`` result
into a normalized ``SendOutcome``). The raw vendor object — which for ``account_info`` carries
``login`` and ``server`` — is never stored (I-S-1).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from hunter_core.domain.types import utcnow

from .errors import Mt5IpcTimeout, Mt5ReadError

log = structlog.get_logger(__name__)

ErrorProbe = Callable[[], tuple[int, str]]
OnLate = Callable[[Any, tuple[int, str] | None], object]
_SKIPPED = object()


@dataclass(frozen=True)
class LateResult:
    """A call whose awaiter had given up (deadline or cancellation) when it returned."""

    name: str
    value: object | None  # whatever `on_late` made of the result; never the raw vendor object
    raised: str | None  # exception type name only
    last_error: tuple[int, str] | None
    at: datetime
    call_id: int = field(default=0, repr=False)


@dataclass
class _Call:
    call_id: int
    name: str
    mutation: bool
    started: bool = False
    abandoned: bool = False


class IpcExecutor:
    def __init__(self, *, timeout_s: float, error_probe: ErrorProbe) -> None:
        self._timeout_s = timeout_s
        self._probe = error_probe
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mt5-ipc")
        self._lock = threading.Lock()
        self._seq = 0
        self._hung_call: str | None = None
        self._late: list[LateResult] = []
        self._unresolved: set[int] = set()

    @property
    def hung(self) -> bool:
        return self._hung_call is not None

    @property
    def hung_call(self) -> str | None:
        return self._hung_call

    @property
    def unresolved(self) -> bool:
        """A mutation was (maybe) sent and its awaiter gave up; its result is not collected yet."""
        return bool(self._unresolved)

    def drain_late_results(self) -> list[LateResult]:
        with self._lock:
            late, self._late = self._late, []
            for item in late:
                self._unresolved.discard(item.call_id)
        return late

    def close(self) -> None:
        # A stuck thread cannot be killed; do not wait for it.
        self._pool.shutdown(wait=not self.hung, cancel_futures=True)

    async def call(
        self,
        name: str,
        fn: Callable[[], Any],
        *,
        timeout_s: float | None = None,
        mutation: bool = False,
        on_late: OnLate | None = None,
    ) -> tuple[Any, tuple[int, str] | None]:
        """Run ``fn`` on the lane. Returns ``(result, last_error)``; ``last_error`` only when the
        result is ``None`` (it is read on the same thread, right after the call)."""
        if self._hung_call is not None:
            raise Mt5ReadError(name, reason=f"ipc_hung:{self._hung_call}")
        self._seq += 1
        call = _Call(self._seq, name, mutation)

        def run() -> Any:
            with self._lock:
                if call.abandoned or self._hung_call is not None:
                    return _SKIPPED
                call.started = True
            result = fn()
            return result, (self._probe() if result is None else None)

        future = asyncio.get_running_loop().run_in_executor(self._pool, run)
        deadline = self._timeout_s if timeout_s is None else timeout_s
        try:
            outcome = await asyncio.wait_for(asyncio.shield(future), timeout=deadline)
        except TimeoutError:
            started = self._give_up(call, future, on_late, latch=True)
            raise Mt5IpcTimeout(name, started=started) from None
        except asyncio.CancelledError:
            self._give_up(call, future, on_late, latch=False)
            raise
        if outcome is _SKIPPED:
            raise Mt5IpcTimeout(f"{name} (lane latched while queued)", started=False)
        return outcome

    def _give_up(
        self,
        call: _Call,
        future: asyncio.Future[Any],
        on_late: OnLate | None,
        *,
        latch: bool,
    ) -> bool:
        """The awaiter leaves. Returns whether the call had started (so it may have taken effect)."""
        with self._lock:
            started = call.started
            if not started:
                call.abandoned = True  # still in the queue: it will be skipped, never run
                return False
            if latch and self._hung_call is None:
                self._hung_call = call.name
                log.error("mt5_ipc_hung", call=call.name)
            if call.mutation:
                self._unresolved.add(call.call_id)
        future.add_done_callback(lambda f: self._keep_late(call, f, on_late))
        return True

    def _keep_late(self, call: _Call, future: asyncio.Future[Any], on_late: OnLate | None) -> None:
        if future.cancelled():
            return
        exc = future.exception()
        value: object | None = None
        error: tuple[int, str] | None = None
        if exc is None:
            outcome = future.result()
            if outcome is not _SKIPPED:
                result, error = outcome
                value = on_late(result, error) if on_late is not None else None
        late = LateResult(
            call.name,
            value,
            None if exc is None else type(exc).__name__,
            error,
            utcnow(),
            call.call_id,
        )
        with self._lock:
            self._late.append(late)
        log.warning("mt5_ipc_late_result", call=call.name, raised=late.raised)
