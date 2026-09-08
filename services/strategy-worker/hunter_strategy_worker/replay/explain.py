"""The explain ledger — one line per evaluated bar, with the reason the bar gave.

T3.33f. A replay already writes a receipt per *slice* (``ledger.py``) and a row
per *decision* (``agent_signals``). Between the two there is a hole that cost a
whole experiment: ``breakout v1`` evaluated 5 952 bars over 31 days, decided
nothing, and the only durable trace of *why* was a state histogram
(``rejected: 14``) with no reason attached (notes-T3.33e). "Why zero decisions"
was a guess, and a guess is not a measurement.

This module closes it with the cheapest thing that could work: the strategy's
own :class:`~hunter_core.strategies.base.Evaluation` — ``state``, ``reason``,
``detail``, the vocabulary that already exists (``geometry_invalidation``,
``not_compressed``, ``rvol_low``, ``atr_out_of_range``…) — appended to a JSONL
file as the bar loop visits each bar. No new table, no new evaluation path, no
second opinion about what a bar did: the row is written **from the same
``Evaluation`` the run counts**, so the ledger's histogram is the receipt's
``evaluations_by_state`` by construction, and a test asserts it.

**A shard per market, merged by the parent.** The replay is parallel by market
in *processes*; two processes appending to one file is atomic only where the OS
says so (and Windows does not), so each market writes its own
``<ledger>.<exchange>-<symbol>.part`` and :func:`merge_shards` concatenates them
in the order the markets were dispatched and deletes them. The merge **appends**
to the ledger, like ``ledger.append_jsonl``: two slices of one run are one
population and belong in one file.

**It records, it never decides.** Nothing here is read back by the engine, and a
row exists only for a bar the run already evaluated — the ledger cannot add a
bar, drop one, or change what one answered.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Mapping, Sequence
    from datetime import datetime
    from types import TracebackType

    from hunter_core.strategies.base import Evaluation

logger = get_logger(__name__)

SUFFIX = ".part"
"""What a shard's name ends with — a merged ledger never keeps this suffix."""

__all__ = [
    "ExplainLedger",
    "ExplainRow",
    "ledger_for",
    "merge_markets",
    "merge_shards",
    "shard_path",
]


@dataclass(frozen=True, slots=True)
class ExplainRow:
    """One evaluated bar, as the ledger holds it.

    Five fields and no more (brief T3.33f): the run, the version and the cohort
    are properties of the *file*, written once in the slice's receipt, and
    repeating them on every one of tens of thousands of lines would make the
    ledger heavier without making it more answerable.
    """

    bar_close: datetime
    market: str
    """``<exchange>:<symbol>``, the same key ``ReplayRun.markets`` uses."""
    state: str
    """``EvaluationState`` value: ``triggered``, ``not_triggered``, ``rejected``,
    ``unavailable``, ``ineligible``."""
    reason: str
    """The strategy's diagnostic code, verbatim. Never mapped or renamed here."""
    detail: Mapping[str, str]
    """The strategy's already-stringified context for that reason."""

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "bar_close": ensure_utc(self.bar_close).isoformat(),
            "market": self.market,
            "state": self.state,
            "reason": self.reason,
            "detail": dict(self.detail),
        }


def shard_path(base: Path, *, exchange: str, symbol: str) -> Path:
    """Where the process replaying ``exchange:symbol`` writes its lines."""
    return base.with_name(f"{base.name}.{exchange}-{symbol}{SUFFIX}")


class ExplainLedger:
    """An open JSONL shard for one market. Append-only, flushed line by line.

    Line-buffered on purpose: a run that dies at hour 20 of 31 days should leave
    the twenty hours it did measure, and the ledger is diagnostic output, not a
    hot path (one small ``write`` per 15-minute bar).
    """

    __slots__ = ("_handle", "_market", "_path", "_rows")

    def __init__(self, path: Path, *, market: str) -> None:
        self._path = path
        self._market = market
        self._handle: Any = None
        self._rows = 0

    @property
    def rows(self) -> int:
        """How many lines this shard has written."""
        return self._rows

    @property
    def path(self) -> Path:
        return self._path

    def __enter__(self) -> ExplainLedger:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # ``w``: a shard belongs to one process and one slice, so re-running a
        # slice replaces its shard instead of doubling it. The *ledger* is the
        # thing that accumulates (``merge_shards`` appends).
        self._handle = self._path.open("w", encoding="utf-8", newline="\n")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def record(self, bar_close: datetime, evaluation: Evaluation) -> None:
        """Write the line for one evaluated bar."""
        if self._handle is None:  # pragma: no cover - misuse, not a runtime path
            raise RuntimeError("ExplainLedger.record outside its context manager")
        row = ExplainRow(
            bar_close=bar_close,
            market=self._market,
            state=evaluation.state.value,
            reason=evaluation.reason,
            detail=evaluation.detail,
        )
        self._handle.write(json.dumps(row.to_jsonable(), separators=(",", ":")) + "\n")
        self._handle.flush()
        self._rows += 1


def merge_shards(base: Path, shards: Sequence[Path]) -> int:
    """Append every shard to ``base`` in order, delete them, return the lines.

    Order is the caller's — the order the markets were dispatched — because a
    global sort by ``bar_close`` would mean holding the whole run in memory for
    a file nobody reads sequentially anyway. Inside a market the lines are
    already chronological, which is the order a "why did this market do nothing"
    question is asked in.

    The shards are deleted **after** the ledger is closed, never while it is
    still open: a shard removed before the destination's last flush would be a
    copy lost to a failed ``close`` (full disk), and the shard is the only other
    copy there is (Astra, revisão T3.33f, must-fix 2).
    """
    lines = 0
    copied: list[Path] = []
    base.parent.mkdir(parents=True, exist_ok=True)
    with base.open("a", encoding="utf-8", newline="\n") as ledger:
        for shard in shards:
            if not shard.exists():
                continue
            with shard.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        ledger.write(line if line.endswith("\n") else line + "\n")
                        lines += 1
            copied.append(shard)
    for shard in copied:
        shard.unlink(missing_ok=True)
    return lines


@contextmanager
def ledger_for(base: str | None, *, exchange: str, symbol: str) -> Generator[ExplainLedger | None]:
    """The shard one market process writes, or nothing when the run asked for none.

    A context manager either way, so the caller has **one** call to
    ``replay_market`` instead of two that could drift apart.
    """
    if base is None:
        yield None
        return
    path = shard_path(Path(base), exchange=exchange, symbol=symbol)
    with ExplainLedger(path, market=f"{exchange}:{symbol}") as ledger:
        yield ledger


def merge_markets(base: Path, markets: Iterable[tuple[str, str]], *, bars: int) -> int:
    """Merge one run's shards into ``base`` and say whether the ledger is complete.

    One line per evaluated bar is the whole contract of the file, so a merge that
    produced fewer lines than the run evaluated bars is a **warning** — a shard
    that never arrived — and not something a reader has to discover by counting
    the file afterwards (Astra, revisão T3.33f, must-fix 2).
    """
    lines = merge_shards(
        base, [shard_path(base, exchange=exchange, symbol=symbol) for exchange, symbol in markets]
    )
    event = "replay_explain_ledger" if lines == bars else "replay_explain_ledger_incomplete"
    log = logger.info if lines == bars else logger.warning
    log(event, path=str(base), lines=lines, bars=bars)
    return lines
