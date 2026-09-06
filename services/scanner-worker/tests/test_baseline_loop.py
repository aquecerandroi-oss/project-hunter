"""The loop that actually runs in production, stitched (T2.5d).

Until now the pieces had tests and the loop did not, and the seam hid a real
defect (code review of T2.5b, MEDIUM 1): the "no persisted candles" shortcut
lived in ``replay_io.run_bootstrap``, which **nothing in production called**.
``main.py`` starts ``baseline_loop``, which built the job with ``prepare_job``
and went straight into ``run_slice`` -- so a market with no candle row (a new
listing, or the scanner up before the collector) held the single bootstrap slot
for ~13 s of wall clock computing 10 080 empty cuts and finished as
``history_incomplete`` instead of ``no_persisted_candles``.

These tests drive ``baseline_loop`` itself. The database and the replay are the
only things stubbed; the ledger is the real one, against a fake Redis hash, so
"what the next process will read" is asserted and not assumed.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from hunter_scanner_worker import baseline_jobs, baseline_runner
from hunter_scanner_worker.baseline_runner import BootstrapProgress, baseline_loop
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.bootstrap import (
    REASON_NO_CANDLES,
    BootstrapOutcome,
    window_for,
)
from hunter_scanner_worker.config import ScannerConfig
from hunter_scanner_worker.registry import MarketRef, MarketRegistry
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState

from .builders import EXCHANGE
from .policies import build_policy

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 20, 0, 30, tzinfo=UTC)

EMPTY = MarketRef(
    market_id=UUID("22222222-2222-7222-8222-222222222222"), exchange=EXCHANGE, symbol="EMPTYUSDT"
)
GOOD = MarketRef(
    market_id=UUID("33333333-3333-7333-8333-333333333333"), exchange=EXCHANGE, symbol="GOODUSDT"
)


class FakeRedis:
    """The hash the ledger keeps, and nothing else."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, Any]] = {}

    async def hgetall(self, key: str) -> dict[str, Any]:
        return dict(self.hashes.get(key, {}))

    async def hset(self, key: str, field: str, value: Any) -> int:
        self.hashes.setdefault(key, {})[field] = value
        return 1

    async def expire(self, _key: str, _ttl: int) -> bool:
        return True


class FakeJob:
    """A prepared bootstrap, without the ten thousand cuts."""

    def __init__(self, ref: MarketRef, *, candles: int, raises: bool = False) -> None:
        self.ref = ref
        self.window = window_for(NOW, days=1)
        self.candles = [object()] * candles
        self.gaps: tuple[tuple[datetime, datetime], ...] = ()
        self.cuts_done = 0
        self.slices = 0
        self._raises = raises

    async def run_slice(self, _budget_s: float | None = None, *, pressure: Any = None) -> bool:
        del pressure
        self.slices += 1
        if self._raises:
            raise RuntimeError("this market always blows up")
        self.cuts_done = 1440
        return True


class _Runtime:
    def __init__(self) -> None:
        self.errors = 0
        self.successes = 0

    def mark_error(self) -> None:
        self.errors += 1

    def mark_success(self) -> None:
        self.successes += 1


class Harness:
    """One scripted pass of the loop over a fixed list of pending markets."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, jobs: dict[str, FakeJob]) -> None:
        self.jobs = jobs
        self.redis = FakeRedis()
        self.runtime = _Runtime()
        self.progress = BootstrapProgress()
        self.refreshed_hours: list[datetime] = []
        self.events: list[str] = []
        self.done: set[str] = set()
        self.scanner = Scanner(
            config=ScannerConfig(exchange=EXCHANGE, baseline_check_s=0.01),
            policy=build_policy(),
            registry=MarketRegistry(exchange=EXCHANGE),
            state=ScannerState(),
        )
        self.scanner.cache = BaselineCache(gate=self.scanner.policy.gate)
        refs = [EMPTY, GOOD]
        self.scanner.registry.apply(refs)
        for ref in refs:
            self.scanner.state.ensure(ref, now=NOW)
        self._install(monkeypatch)

    def _install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def refresh_hour(*_args: Any, **kwargs: Any) -> int:
            self.refreshed_hours.append(kwargs["closed_hour"])
            self.events.append("refresh")
            return 0

        async def pending_markets(*_args: Any, **_kwargs: Any) -> list[MarketRef]:
            # Like the real one: a market with an attempt on record is not
            # pending again until its backoff expires, so an attempt that is
            # never written would make this loop pick the same market forever.
            recorded = set(self.redis.hashes.get(f"scan:bootstrap:{EXCHANGE}", {}))
            pending = [ref for ref in (EMPTY, GOOD) if str(ref.market_id) not in recorded]
            if not pending:
                raise asyncio.CancelledError
            return pending

        async def prepare_job(_session: Any, ref: MarketRef, **_kwargs: Any) -> Any:
            self.events.append(f"prepare:{ref.symbol}")
            return self.jobs[ref.symbol]

        async def request_gaps(*_args: Any, **_kwargs: Any) -> int:
            return 0

        async def finish_job(_factory: Any, job: Any, **_kwargs: Any) -> BootstrapOutcome:
            self.events.append(f"finish:{job.ref.symbol}")
            self.done.add(job.ref.symbol)
            return BootstrapOutcome(
                ref=job.ref, window=job.window, cuts=job.cuts_done, complete=True
            )

        monkeypatch.setattr(baseline_runner, "refresh_hour", refresh_hour)
        monkeypatch.setattr(baseline_runner, "pending_markets", pending_markets)
        monkeypatch.setattr(baseline_jobs, "prepare_job", prepare_job)
        monkeypatch.setattr(baseline_jobs, "request_gaps", request_gaps)
        monkeypatch.setattr(baseline_jobs, "finish_job", finish_job)
        monkeypatch.setattr(baseline_jobs, "role_session", _fake_session)

    async def run(self) -> None:
        with pytest.raises(asyncio.CancelledError):
            await baseline_loop(
                self.scanner,
                None,  # type: ignore[arg-type]
                None,  # type: ignore[arg-type]
                self.redis,  # type: ignore[arg-type]
                self.runtime,  # type: ignore[arg-type]
                self.progress,
                None,  # type: ignore[arg-type]
            )

    async def ledger_entry(self, ref: MarketRef) -> Any:
        from hunter_scanner_worker.ledger import BootstrapLedger

        entries = await BootstrapLedger(EXCHANGE).read(self.redis)  # type: ignore[arg-type]
        return entries.get(ref.market_id)


class _fake_session:
    """``role_session(factory, db_role=...)`` without a database."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


async def test_a_market_with_no_persisted_candles_never_enters_the_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defect this file exists for: 10 080 empty cuts and the wrong reason.

    The shortcut has to be on the path ``main.py`` starts, not only in a helper
    the tests called.
    """
    empty, good = FakeJob(EMPTY, candles=0), FakeJob(GOOD, candles=100)
    harness = Harness(monkeypatch, {"EMPTYUSDT": empty, "GOODUSDT": good})

    await harness.run()

    assert empty.slices == 0, "a market with no candles must not hold the slot"
    assert good.slices == 1, "and the next market must get it"


async def test_the_empty_market_is_recorded_with_its_own_reason_and_a_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``no_persisted_candles`` is a different sentence from
    ``history_incomplete``: nothing was read, so nothing was replayed. The
    attempt is still written, or the same market is chosen again forever."""
    harness = Harness(
        monkeypatch, {"EMPTYUSDT": FakeJob(EMPTY, candles=0), "GOODUSDT": FakeJob(GOOD, candles=9)}
    )

    await harness.run()

    entry = await harness.ledger_entry(EMPTY)
    assert entry is not None
    assert entry.reason == REASON_NO_CANDLES
    assert entry.complete is False
    assert entry.attempts == 1
    assert entry.retry_at is not None
    assert harness.scanner.state.markets["EMPTYUSDT"].baseline_note == REASON_NO_CANDLES
    assert harness.progress.running is None


async def test_the_hourly_refresh_runs_before_any_bootstrap_and_only_once_per_hour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refresh is bounded and is the only thing keeping the archive current;
    the bootstrap is hours of work that can wait one more slice."""
    harness = Harness(
        monkeypatch, {"EMPTYUSDT": FakeJob(EMPTY, candles=0), "GOODUSDT": FakeJob(GOOD, candles=9)}
    )

    await harness.run()

    assert harness.events[0] == "refresh"
    assert harness.refreshed_hours == [_closed_hour()]
    assert harness.events.count("refresh") == 1


async def test_a_market_that_raises_is_parked_and_the_next_one_still_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One market's failure is one market's backoff -- not the universe's."""
    broken = FakeJob(EMPTY, candles=50, raises=True)
    good = FakeJob(GOOD, candles=50)
    harness = Harness(monkeypatch, {"EMPTYUSDT": broken, "GOODUSDT": good})

    await harness.run()

    entry = await harness.ledger_entry(EMPTY)
    assert entry is not None and entry.reason == baseline_jobs.REASON_FAILED
    assert entry.attempts == 1 and entry.retry_at is not None
    assert good.slices == 1
    assert harness.runtime.errors == 1


def _closed_hour() -> datetime:
    from hunter_scanner_worker.refresh import closed_hour_before

    return closed_hour_before(datetime.now(UTC)) or datetime.now(UTC).replace(
        minute=0, second=0, microsecond=0
    ) - timedelta(hours=1)
