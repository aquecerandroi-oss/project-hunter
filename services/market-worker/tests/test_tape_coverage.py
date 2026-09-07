"""The collector's own proof that it was still listening (T2.5, Astra must-fix).

``hunter_indicators.features.windows.trades_between`` refuses every trade window
whose ``covered_until`` the collector did not prove, so ``trade_velocity_1m``,
``buy_pressure_5m`` and ``sell_pressure_5m`` — and with them every EARLY stage —
are ``insufficient_coverage`` until this module writes that proof.

Inferring it from ``hb:market:<exchange>`` was rejected in the T2.5 design
review: that hash reports ``ws_state`` next to a *cumulative* ``dropped_events``,
so a connected socket that dropped a trade would still read "covered".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from hunter_core.redis import keys
from hunter_market_worker.coverage import (
    COVERAGE_SAFETY_S,
    COVERAGE_TTL_S,
    CoverageTracker,
)

pytestmark = pytest.mark.integration


def _at(second: float) -> datetime:
    return datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC) + timedelta(seconds=second)


async def _hash(redis: Any, exchange: str = "binance") -> dict[str, str]:
    """The published coverage hash, decoded. Real Redis since T2.5g: the stamp
    is one Lua script (``coverage_publish``), so a hand-written double would be
    testing a different writer than production runs."""
    raw = await redis.hgetall(keys.tape_coverage(exchange))
    return {k.decode(): v.decode() for k, v in raw.items()}


async def test_a_stamp_publishes_the_session_and_a_conservative_covered_until(
    redis_client: Any,
) -> None:
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT", "ETHUSDT"], at=_at(0))

    stamped = await tracker.stamp(redis, dropped_events=0, now=_at(1))

    assert stamped is True
    hash_ = await _hash(redis)
    assert hash_["session_since"] == _at(0).isoformat()
    # Never `now`: an event the adapter already received may not have reached
    # the tape yet, so the claim stops one safety margin short of the clock.
    assert hash_["covered_until"] == (_at(1) - timedelta(seconds=COVERAGE_SAFETY_S)).isoformat()
    assert hash_["sym:BTCUSDT"] == _at(0).isoformat()
    ttl = await redis.ttl(keys.tape_coverage("binance"))
    assert 0 < ttl <= COVERAGE_TTL_S


async def test_a_dropped_event_restarts_the_interval_instead_of_extending_it(
    redis_client: Any,
) -> None:
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    await tracker.stamp(redis, dropped_events=0, now=_at(1))

    await tracker.stamp(redis, dropped_events=3, now=_at(2))

    hash_ = await _hash(redis)
    # A drop can have been a trade on any symbol: the interval cannot span it.
    assert hash_["session_since"] == _at(2).isoformat()
    # And it cannot reach *back* across it either. The safety margin would put
    # ``covered_until`` half a second before the break, i.e. inside the interval
    # the drop just invalidated, so the published interval is empty
    # (``covered_until == session_since``) until the next stamp earns one.
    assert hash_["covered_until"] == _at(2).isoformat()

    await tracker.stamp(redis, dropped_events=3, now=_at(4))
    assert (await _hash(redis))["covered_until"] == (
        _at(4) - timedelta(seconds=COVERAGE_SAFETY_S)
    ).isoformat()


async def test_a_write_in_flight_holds_the_stamp_back(redis_client: Any) -> None:
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    tracker.writing()

    assert await tracker.stamp(redis, dropped_events=0, now=_at(1)) is False
    assert await redis.exists(keys.tape_coverage("binance")) == 0

    tracker.written()
    assert await tracker.stamp(redis, dropped_events=0, now=_at(2)) is True


async def test_a_symbol_subscribed_mid_session_is_covered_only_from_its_subscription(
    redis_client: Any,
) -> None:
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    tracker.subscribed(["SOLUSDT"], at=_at(30))
    await tracker.stamp(redis, dropped_events=0, now=_at(31))

    hash_ = await _hash(redis)
    assert hash_["sym:BTCUSDT"] == _at(0).isoformat()
    assert hash_["sym:SOLUSDT"] == _at(30).isoformat()


async def test_an_unsubscribed_symbol_stops_claiming_coverage(redis_client: Any) -> None:
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT", "ETHUSDT"], at=_at(0))
    await tracker.stamp(redis, dropped_events=0, now=_at(1))

    tracker.unsubscribed(["ETHUSDT"])
    await tracker.stamp(redis, dropped_events=0, now=_at(2))

    hash_ = await _hash(redis)
    assert "sym:ETHUSDT" not in hash_
    assert "sym:BTCUSDT" in hash_


async def test_a_broken_session_publishes_nothing_until_it_is_restarted(redis_client: Any) -> None:
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    await tracker.stamp(redis, dropped_events=0, now=_at(1))

    tracker.session_broken()

    assert await tracker.stamp(redis, dropped_events=0, now=_at(2)) is False
    # The reader must see an interval that ended, never one that keeps growing
    # while the socket is down.
    assert (await _hash(redis))["session_since"] == ""

    tracker.session_started(["BTCUSDT"], at=_at(5))
    assert await tracker.stamp(redis, dropped_events=0, now=_at(6)) is True
    assert (await _hash(redis))["session_since"] == _at(5).isoformat()


# --- T2.5-adapter: ws_state / queue_progress (Astra diff review finding 1) ----


async def test_a_disconnected_ws_state_holds_covered_until_back_then_starts_fresh(
    redis_client: Any,
) -> None:
    """An internal reconnect the adapter handles without ever ending
    ``stream()``'s generator never raises out of ``consume_once`` and never
    increases ``dropped_events`` on its own — the only signal left is the
    adapter's own ``connection_state()``, read fresh every stamp. A real
    rupture, once resumed, must not stretch the *old* session across the gap
    (Astra review, second round, finding 2): a fresh, conservative session
    starts at the instant resumption is confirmed."""
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    await tracker.stamp(redis, dropped_events=0, now=_at(1), ws_state="connected")
    healthy = (await _hash(redis))["covered_until"]

    await tracker.stamp(redis, dropped_events=0, now=_at(1.5), ws_state="reconnecting")
    await tracker.stamp(redis, dropped_events=0, now=_at(2), ws_state="reconnecting")

    frozen = (await _hash(redis))["covered_until"]
    assert frozen == healthy  # never advanced while disconnected

    await tracker.stamp(redis, dropped_events=0, now=_at(3), ws_state="connected")
    hash_ = await _hash(redis)
    # A fresh session, not the old one stretched across the gap: publishing
    # `_at(3) - 0.5s` here would claim continuity straight through the outage.
    assert hash_["session_since"] == _at(3).isoformat()
    assert hash_["covered_until"] == _at(3).isoformat()
    assert hash_["covered_until"] > frozen


async def test_a_reconnect_cycle_between_two_stamps_is_still_caught_by_generation(
    redis_client: Any,
) -> None:
    """A rotation or F8 restart can complete entirely between two
    housekeeping ticks: ``ws_state`` reads ``"connected"`` both before and
    after, having never been observed as anything else. The generation
    counter does not reset back, so it still catches the cycle (Astra
    review, second round, finding 3)."""
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    await tracker.stamp(redis, dropped_events=0, now=_at(1), connection_generation=0)
    healthy = (await _hash(redis))["covered_until"]

    # The whole reconnect cycle happened between this stamp and the last one
    # -- ws_state reads "connected" right now, but the generation moved, so
    # this stamp still freezes instead of advancing.
    await tracker.stamp(redis, dropped_events=0, now=_at(1.1), connection_generation=1)
    frozen = (await _hash(redis))["covered_until"]
    assert frozen == healthy

    # Generation stable again: confirmed resumed, fresh session starts now.
    await tracker.stamp(redis, dropped_events=0, now=_at(2), connection_generation=1)
    hash_ = await _hash(redis)
    assert hash_["session_since"] == _at(2).isoformat()
    assert hash_["covered_until"] == _at(2).isoformat()

    await tracker.stamp(redis, dropped_events=0, now=_at(3), connection_generation=1)
    resumed = (await _hash(redis))["covered_until"]
    assert resumed == (_at(3) - timedelta(seconds=COVERAGE_SAFETY_S)).isoformat()


async def test_reconnect_followed_by_backlog_before_resumption_still_starts_fresh(
    redis_client: Any,
) -> None:
    """Astra review, third round: a queue backlog observed *after* a
    rupture but *before* resumption is confirmed must not downgrade the
    remembered break reason to ``"queue_backlog"`` — that would let the
    eventual catch-up just un-freeze the old session across the rupture
    instead of starting the fresh one a real reconnect still requires."""
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    await tracker.stamp(
        redis, dropped_events=0, now=_at(1), ws_state="connected", queue_progress=(1, 1, 0)
    )
    healthy = (await _hash(redis))["covered_until"]

    await tracker.stamp(redis, dropped_events=0, now=_at(1.5), ws_state="reconnecting")
    # ws_state is healthy again, but the queue is still draining -- must not
    # read as "just a backlog": the session is still broken by the reconnect.
    await tracker.stamp(
        redis, dropped_events=0, now=_at(2), ws_state="connected", queue_progress=(7, 5, 0)
    )
    frozen = (await _hash(redis))["covered_until"]
    assert frozen == healthy

    # Fully caught up: this is the confirmed resumption.
    await tracker.stamp(
        redis, dropped_events=0, now=_at(3), ws_state="connected", queue_progress=(7, 7, 0)
    )
    hash_ = await _hash(redis)
    assert hash_["session_since"] == _at(3).isoformat()  # fresh session, not stretched
    assert hash_["covered_until"] == _at(3).isoformat()


async def test_generation_detected_reconnect_followed_by_backlog_still_starts_fresh(
    redis_client: Any,
) -> None:
    """Same guard as above, but the rupture is caught only by
    ``connection_generation`` (``ws_state`` never leaves ``"connected"`` in
    this trace) — Astra review, third round, nice-to-have."""
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    await tracker.stamp(
        redis, dropped_events=0, now=_at(1), connection_generation=0, queue_progress=(1, 1, 0)
    )
    healthy = (await _hash(redis))["covered_until"]

    await tracker.stamp(redis, dropped_events=0, now=_at(1.5), connection_generation=1)
    await tracker.stamp(
        redis,
        dropped_events=0,
        now=_at(2),
        connection_generation=1,
        queue_progress=(7, 5, 0),
    )
    frozen = (await _hash(redis))["covered_until"]
    assert frozen == healthy

    await tracker.stamp(
        redis,
        dropped_events=0,
        now=_at(3),
        connection_generation=1,
        queue_progress=(7, 7, 0),
    )
    hash_ = await _hash(redis)
    assert hash_["session_since"] == _at(3).isoformat()
    assert hash_["covered_until"] == _at(3).isoformat()


async def test_never_connected_this_session_publishes_only_session_since(redis_client: Any) -> None:
    """A market still doing its very first connect — never yet ``connected``
    — must not claim any coverage at all, not even the zero-events "quiet
    market" allowance, which only applies once continuity has been proven."""
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))

    await tracker.stamp(redis, dropped_events=0, now=_at(2), ws_state="connecting")

    hash_ = await _hash(redis)
    assert hash_["covered_until"] == hash_["session_since"] == _at(0).isoformat()


async def test_a_backlogged_adapter_queue_holds_covered_until_back(redis_client: Any) -> None:
    """``enqueued != delivered + evicted``: an item this process's
    ``_in_flight`` counter cannot see (already popped by the adapter's
    reader task, not yet yielded) is still in transit."""
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    await tracker.stamp(redis, dropped_events=0, now=_at(1), queue_progress=(5, 5, 0))
    healthy = (await _hash(redis))["covered_until"]

    await tracker.stamp(redis, dropped_events=0, now=_at(1.5), queue_progress=(7, 5, 0))
    frozen = (await _hash(redis))["covered_until"]
    assert frozen == healthy

    await tracker.stamp(redis, dropped_events=0, now=_at(2), queue_progress=(7, 7, 0))
    resumed = (await _hash(redis))["covered_until"]
    assert resumed == (_at(2) - timedelta(seconds=COVERAGE_SAFETY_S)).isoformat()
    assert resumed > frozen


async def test_an_eviction_does_not_look_like_permanent_backlog(redis_client: Any) -> None:
    """``evicted`` items are gone for good and must count on the "caught up"
    side of the ledger — the one real break an eviction causes is
    ``dropped_events``' job, not an ever-growing ``enqueued - delivered``
    gap that never closes again."""
    redis: Any = redis_client
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))

    # 2 enqueued, 1 evicted, 1 delivered: caught up (2 == 1 + 1).
    assert (
        await tracker.stamp(redis, dropped_events=0, now=_at(1), queue_progress=(2, 1, 1)) is True
    )
    hash_ = await _hash(redis)
    assert hash_["covered_until"] == (_at(1) - timedelta(seconds=COVERAGE_SAFETY_S)).isoformat()
