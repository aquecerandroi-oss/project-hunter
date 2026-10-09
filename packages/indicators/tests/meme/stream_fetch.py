"""Test-only keyed sources for the parallel replay (CPU plan step 3). Fixtures, not production.

:func:`~hunter_indicators.meme.wallets.stream_parallel.stream_snapshot_parallel` workers load each
mint they are handed through a picklable ``fetch(name) -> MintWindow``; in production it reads the
storage. These hold the windows in a plain ``dict`` (a ``MappingProxyType`` does not pickle) and
live in an importable module so a spawned worker can unpickle them.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, replace
from pathlib import Path

from hunter_indicators.meme.wallets.carry import ContractViolation
from hunter_indicators.meme.wallets.stream import MintWindow


@dataclass(frozen=True)
class ByName:
    windows: dict[str, MintWindow]

    def __call__(self, name: str) -> MintWindow:
        return self.windows[name]


@dataclass(frozen=True)
class Sleepy:
    """A random delay per (seed, mint) before the load: shuffles the real completion order."""

    windows: dict[str, MintWindow]
    seed: int
    max_seconds: float = 0.03

    def __call__(self, name: str) -> MintWindow:
        time.sleep(random.Random(f"{self.seed}:{name}").uniform(0, self.max_seconds))
        return self.windows[name]


@dataclass(frozen=True)
class Failing:
    """Raises inside the worker for one mint (``violation``: a named contract refusal)."""

    windows: dict[str, MintWindow]
    bad: str
    violation: bool = False

    def __call__(self, name: str) -> MintWindow:
        if name == self.bad:
            if self.violation:
                raise ContractViolation("slot_time_inconsistent", f"{name} (test)")
            raise RuntimeError(f"storage unavailable for {name} (test)")
        return self.windows[name]


@dataclass(frozen=True)
class Tampered:
    """Loads one mint without its last event: the window differs from the one surveyed."""

    windows: dict[str, MintWindow]
    bad: str

    def __call__(self, name: str) -> MintWindow:
        window = self.windows[name]
        return replace(window, fills=window.fills[:-1]) if name == self.bad else window


def _wait_for(folder: Path, pattern: str, count: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while len(list(folder.glob(pattern))) < count:
        if time.monotonic() > deadline:
            raise TimeoutError(f"{pattern}: fewer than {count} in {folder} after {timeout} s")
        time.sleep(0.02)


@dataclass(frozen=True)
class Rendezvous:
    """Forces real concurrency and an inverted completion (code review, step 3): every load
    registers its worker's pid and waits until ``workers`` distinct pids are registered; the
    load of ``held`` also waits until the coordinator emitted the carry of some other mint
    (the test's ``emit`` writes ``emitted-<mint>``)."""

    windows: dict[str, MintWindow]
    folder: str
    held: str
    workers: int = 2
    timeout: float = 120.0

    def __call__(self, name: str) -> MintWindow:
        folder = Path(self.folder)
        (folder / f"pid-{os.getpid()}").touch()
        _wait_for(folder, "pid-*", self.workers, self.timeout)
        if name == self.held:
            _wait_for(folder, "emitted-*", 1, self.timeout)
        return self.windows[name]


def by_name(windows: list[MintWindow]) -> dict[str, MintWindow]:
    return {w.carry.mint: w for w in windows}
