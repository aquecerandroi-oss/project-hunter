"""State and plumbing shared by the read and write halves of :class:`Mt5Adapter`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from hunter_core.domain.types import utcnow

from .errors import Mt5ReadError
from .ipc import IpcExecutor, LateResult
from .raw import Mt5Raw
from .spec import SpecWatcher


@dataclass(frozen=True)
class Mt5Config:
    """Everything configurable about the session. Deliberately has no credentials: the terminal
    is logged in by the Everton, and a ``login``/``password`` field here would be a defect."""

    terminal_path: str | None = None
    connect_timeout_ms: int = 60_000
    ipc_call_timeout_s: float = 10.0  # contract §9


class AdapterBase:
    def __init__(
        self,
        raw: Mt5Raw,
        *,
        config: Mt5Config | None = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.config = config or Mt5Config()
        self._raw = raw
        self._clock = clock
        self._watcher: SpecWatcher | None = None
        self._ipc = IpcExecutor(
            timeout_s=self.config.ipc_call_timeout_s, error_probe=raw.last_error
        )

    @property
    def ipc_hung(self) -> bool:
        return self._ipc.hung

    def drain_late_results(self) -> list[LateResult]:
        """Results of calls that returned after their deadline (a late ``order_send`` is real)."""
        return self._ipc.drain_late_results()

    async def _read(self, what: str, fn: Callable[[], Any]) -> Any:
        """Run a vendor read; ``None`` is an error, never an empty answer."""
        result, error = await self._ipc.call(what, fn)
        if result is None:
            raise Mt5ReadError(what, reason="none_result", last_error=error)
        return result
