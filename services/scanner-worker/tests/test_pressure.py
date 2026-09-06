"""The bootstrap stands aside when the live loop is behind.

T2.5b gave the bootstrap a cooperative slice (50 ms of work, then a pause that
leaves it 40% of the wall clock). That is the right shape while the scanner is
keeping up and the wrong one while it is not: a duty cycle spends its share
whatever the backlog, and the budget being defended is the **age of a tick**,
not the fairness between two jobs.

So the split is no longer fixed. The replay asks, at every cooperative
boundary it already had, whether the evaluation loop is late; while it is, the
replay sleeps instead of taking its share. Hysteresis keeps it from
oscillating: it stands aside at one throttle of backlog and only comes back at
half of one, which is a loop that genuinely caught up.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from hunter_core.domain.types import utcnow
from hunter_scanner_worker.bootstrap import BootstrapSettings, window_for
from hunter_scanner_worker.pressure import LivePressure
from hunter_scanner_worker.registry import MarketRef
from hunter_scanner_worker.replay import BootstrapJob
from hunter_scanner_worker.state import ScannerState

from .builders import EXCHANGE, ORIGIN, series

pytestmark = pytest.mark.unit

REF = MarketRef(market_id=UUID(int=3), exchange=EXCHANGE, symbol="SYM000USDT")


def _state_dirty_for(seconds: float) -> ScannerState:
    state = ScannerState()
    market = state.ensure(REF)
    market.touch("tick")
    market.dirty_since = utcnow() - timedelta(seconds=seconds)
    return state


def test_a_loop_that_is_up_to_date_leaves_the_bootstrap_alone() -> None:
    pressure = LivePressure(ScannerState())
    assert pressure() is False
    assert pressure.oldest_dirty_s() == 0.0


def test_a_market_waiting_longer_than_its_throttle_suspends_the_bootstrap() -> None:
    pressure = LivePressure(_state_dirty_for(1.4))
    assert pressure() is True, "1 s of backlog is a missed cadence, not noise"


def test_the_bootstrap_comes_back_only_when_the_backlog_is_really_gone() -> None:
    state = _state_dirty_for(1.4)
    pressure = LivePressure(state)
    assert pressure() is True

    market = state.markets[REF.symbol]
    market.dirty_since = utcnow() - timedelta(seconds=0.7)
    assert pressure() is True, "still suspended: 0.7 s is above the resume line"

    market.clear_dirty()
    assert pressure() is False
    # And it suspends again the moment the backlog returns -- the hysteresis is
    # about oscillation, not about giving up on the decision.
    market.touch("tick")
    market.dirty_since = utcnow() - timedelta(seconds=2.0)
    assert pressure() is True


def test_the_oldest_dirt_is_what_counts_not_the_average() -> None:
    """One market starving while 199 are fresh is exactly the p99 violation."""
    state = ScannerState()
    for index in range(5):
        ref = MarketRef(market_id=UUID(int=index + 10), exchange=EXCHANGE, symbol=f"S{index}USDT")
        market = state.ensure(ref)
        market.touch("tick")
        market.dirty_since = utcnow() - timedelta(seconds=0.05)
    starving = state.markets["S3USDT"]
    starving.dirty_since = utcnow() - timedelta(seconds=4.0)

    pressure = LivePressure(state)
    assert pressure.oldest_dirty_s() >= 4.0
    assert pressure() is True


def _job() -> BootstrapJob:
    """One market's replay over a day of synthetic candles, no database."""
    settings = BootstrapSettings(window_days=1, buffer_minutes=60, duty=1.0, slice_s=0.001)
    start = ORIGIN + timedelta(days=1)
    window = window_for(start, days=1)
    candles = series(1440, start=window.start, symbol=REF.symbol)
    return BootstrapJob(REF, window=window, settings=settings, candles=candles)


async def test_a_late_evaluation_loop_suspends_the_replay_without_losing_it() -> None:
    """Suspended, not cancelled: the generator and the collector stay alive.

    Recreating them would re-anchor Wilder's recursion and pay for the cuts
    again (T2.5b section 12), so backpressure has to be a pause, never a reset.
    """
    job = _job()
    late = LivePressure(_state_dirty_for(3.0))

    finished = await job.run_slice(0.05, pressure=late)
    assert finished is False
    assert job.cuts_done == 0, "not one cut is replayed while a tick is waiting"

    calm = LivePressure(ScannerState())
    while not await job.run_slice(0.5, pressure=calm):
        pass
    assert job.cuts_done == 24 * 60, "and the whole window is replayed afterwards"


async def test_backpressure_is_checked_between_slices_not_only_at_the_start() -> None:
    """A visit has a 120 s budget; noticing the backlog only on entry would let
    a bootstrap hold the loop for two minutes after the scanner fell behind."""
    state = ScannerState()
    pressure = LivePressure(state)
    job = _job()

    started = await job.run_slice(0.05, pressure=pressure)
    assert started is False
    replayed = job.cuts_done
    assert replayed > 0, "an idle loop lets the replay run"

    market = state.ensure(REF)
    market.touch("tick")
    market.dirty_since = utcnow() - timedelta(seconds=5)
    assert await job.run_slice(0.05, pressure=pressure) is False
    assert job.cuts_done == replayed, "the backlog stops it mid-window"


async def test_the_backlog_is_noticed_inside_a_single_visit() -> None:
    """The check lives at the cooperative boundary, not at the door.

    Written against the weakness of the test above (Astra, T2.5c diff review):
    that one changes the pressure *between* two calls, so removing the check
    inside ``run_slice`` would leave it green. This one turns the pressure on
    while the same call is running, and only an inner check can see it.
    """
    job = _job()
    seen = {"checks": 0}

    def rising() -> bool:
        seen["checks"] += 1
        return seen["checks"] > 2

    assert await job.run_slice(5.0, pressure=rising) is False
    assert seen["checks"] > 2, "the replay has to have asked more than once"
    assert 0 < job.cuts_done < 24 * 60, "it started, and it stopped before the end"
