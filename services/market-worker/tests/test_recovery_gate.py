"""L3: run_recovery's cadence gate, pinned as pure unit tests.

Split out of ``test_recovery.py`` (which is an integration module and was at
the 350-line budget); an inverted operator here would silently change the
gap-detection frequency with nothing failing.
"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
from typing import Any

import pytest

from hunter_core.domain.types import utcnow
from hunter_exchanges.base import RateLimited
from hunter_exchanges.rate_limit_suspension import REDIS_UNAVAILABLE
from hunter_market_worker import recovery
from hunter_market_worker.supervision import rest_gate_suspended


def test_should_check_gate_no_check_before_interval() -> None:
    gate = recovery._should_check  # pyright: ignore[reportPrivateUsage]
    assert gate(50.0, 0.0, 0, 0, ["BTCUSDT"]) is False


def test_should_check_gate_checks_at_the_interval() -> None:
    gate = recovery._should_check  # pyright: ignore[reportPrivateUsage]
    assert gate(float(recovery.CHECK_INTERVAL_S), 0.0, 0, 0, ["BTCUSDT"]) is True


def test_should_check_gate_checks_immediately_on_reconnect() -> None:
    gate = recovery._should_check  # pyright: ignore[reportPrivateUsage]
    assert gate(1.0, 0.0, reconnects=1, last_reconnects=0, symbols=["BTCUSDT"]) is True


def test_should_check_gate_never_checks_an_empty_universe() -> None:
    gate = recovery._should_check  # pyright: ignore[reportPrivateUsage]
    assert gate(10_000.0, 0.0, reconnects=5, last_reconnects=0, symbols=[]) is False


class _GateAdapter:
    """The one thing ``run_recovery`` asks an adapter about the REST gate."""

    code = "fake"

    def __init__(self, status: str = "ok") -> None:
        self.status = status

    def rest_gate_status(self) -> str:
        return self.status


class _Universe:
    symbols = ["BTCUSDT"]


class _Runtime:
    def __init__(self) -> None:
        self.successes = 0
        self.errors = 0

    def mark_success(self) -> None:
        self.successes += 1

    def mark_error(self) -> None:
        self.errors += 1


class _State:
    reconnects = 0
    open_gaps = 0


def test_an_adapter_without_a_rest_gate_is_treated_as_admitting() -> None:
    """Every ``FakeAdapter`` in this suite predates ``rest_gate_status``."""
    assert rest_gate_suspended(object()) is False


def test_a_suspended_adapter_is_reported_as_such() -> None:
    assert rest_gate_suspended(_GateAdapter("suspended")) is True
    assert rest_gate_suspended(_GateAdapter("ok")) is False


async def test_run_recovery_waits_for_the_rest_gate_instead_of_burning_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2.9: with Redis down, REST admissions are suspended. A backfill
    attempted anyway would fail, increment ``ingestion_gaps.attempts`` and,
    after ``MAX_ATTEMPTS``, park the gap as ``failed`` for an hour — losing
    the data because of an infrastructure outage. So the cycle waits, and
    resumes on its own once the gate re-opens."""
    calls: list[tuple[str, ...]] = []

    async def spy(_factory: object, adapter: object, symbols: list[str], _state: object) -> None:
        calls.append(tuple(symbols))

    monkeypatch.setattr(recovery, "check_gaps", spy)
    monkeypatch.setattr(recovery, "POLL_S", 0.01)
    adapter = _GateAdapter("suspended")
    runtime = _Runtime()
    task = asyncio.create_task(recovery.run_recovery(None, adapter, _Universe(), _State(), runtime))
    try:
        await asyncio.sleep(0.15)
        assert calls == [], "nothing may hit REST while admissions are suspended"
        assert runtime.errors == 0, "a suspension is a wait, not a worker error"

        adapter.status = "ok"
        await asyncio.sleep(0.15)

        assert calls, "and the cycle resumes by itself once the gate re-opens"
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _open_gap() -> Any:
    return SimpleNamespace(attempts=0, status="open", market_id=1, gap_start=None, gap_end=None)


def _suspended() -> RateLimited:
    return RateLimited(
        "admissions are suspended",
        exchange="binance",
        retry_after_s=1.0,
        reason=REDIS_UNAVAILABLE,
    )


async def test_a_coordination_outage_does_not_burn_a_gap_attempt() -> None:
    """Astra, T2.9 round 3: the gate is only consulted at the top of the
    cycle, so a Redis outage that *starts* mid-backfill still reaches
    ``recover_registered`` as a failed fetch. Counting that as an attempt
    parks the gap as ``failed`` for an hour after ``MAX_ATTEMPTS`` — market
    data lost to an infrastructure outage, which is the whole thing the
    fail-closed gate is supposed to prevent."""
    gap = _open_gap()

    await recovery.recover_registered(
        None, _GateAdapter(), gap, "BTCUSDT", utcnow(), fetch_error=_suspended()
    )

    assert gap.attempts == 0, "an outage is not an attempt"
    assert gap.status == "open", "and the gap stays open for the next cycle"


async def test_an_ordinary_fetch_failure_still_burns_an_attempt() -> None:
    """The deferral is narrow on purpose: only ``reason=redis_unavailable``.
    A symbol Binance refuses to serve must still exhaust its attempts, or a
    permanently broken gap is retried forever."""
    gap = _open_gap()

    await recovery.recover_registered(
        None, _GateAdapter(), gap, "BTCUSDT", utcnow(), fetch_error=ValueError("bad symbol")
    )

    assert gap.attempts == 1


async def test_an_ordinary_rate_limit_still_burns_an_attempt() -> None:
    """A plain "no budget right now" (``reason is None``) is the exchange
    working as designed, not coordination being unreachable."""
    gap = _open_gap()
    spent = RateLimited("no budget", exchange="binance", retry_after_s=1.0)

    await recovery.recover_registered(
        None, _GateAdapter(), gap, "BTCUSDT", utcnow(), fetch_error=spent
    )

    assert gap.attempts == 1


async def test_a_timeout_while_the_gate_is_suspended_does_not_burn_an_attempt() -> None:
    """Astra, T2.9 round 4: ``FETCH_TIMEOUT_S`` (20s) is shorter than the
    limiter's default ``max_wait_s`` (30s), so during a Redis outage the
    backfill is cancelled by the *timeout* before ``acquire`` ever gets to
    raise ``RateLimited(reason="redis_unavailable")``. Matching on the
    exception type alone therefore missed the common case. Asking the adapter
    what its gate is doing right now covers every way the fetch can die of
    the same outage."""
    gap = _open_gap()

    await recovery.recover_registered(
        None,
        _GateAdapter("suspended"),
        gap,
        "BTCUSDT",
        utcnow(),
        fetch_error=TimeoutError(),
    )

    assert gap.attempts == 0
    assert gap.status == "open"


async def test_a_timeout_with_a_healthy_gate_still_burns_an_attempt() -> None:
    gap = _open_gap()

    await recovery.recover_registered(
        None, _GateAdapter("ok"), gap, "BTCUSDT", utcnow(), fetch_error=TimeoutError()
    )

    assert gap.attempts == 1
