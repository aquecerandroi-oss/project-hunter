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

from hunter_core.redis import keys
from hunter_market_worker.coverage import (
    COVERAGE_SAFETY_S,
    COVERAGE_TTL_S,
    CoverageTracker,
)


def _at(second: float) -> datetime:
    return datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC) + timedelta(seconds=second)


class FakeRedis:
    """Just the two commands the tracker issues."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.expirations: dict[str, int] = {}
        self.deleted: list[str] = []

    async def hset(self, key: str, *, mapping: dict[str, str]) -> int:
        self.hashes.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def hdel(self, key: str, *fields: str) -> int:
        entry = self.hashes.get(key, {})
        removed = 0
        for field in fields:
            removed += 1 if entry.pop(field, None) is not None else 0
        return removed

    async def expire(self, key: str, ttl: int) -> bool:
        self.expirations[key] = ttl
        return True


async def test_a_stamp_publishes_the_session_and_a_conservative_covered_until() -> None:
    redis: Any = FakeRedis()
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT", "ETHUSDT"], at=_at(0))

    stamped = await tracker.stamp(redis, dropped_events=0, now=_at(1))

    assert stamped is True
    hash_ = redis.hashes[keys.tape_coverage("binance")]
    assert hash_["session_since"] == _at(0).isoformat()
    # Never `now`: an event the adapter already received may not have reached
    # the tape yet, so the claim stops one safety margin short of the clock.
    assert hash_["covered_until"] == (_at(1) - timedelta(seconds=COVERAGE_SAFETY_S)).isoformat()
    assert hash_["sym:BTCUSDT"] == _at(0).isoformat()
    assert redis.expirations[keys.tape_coverage("binance")] == COVERAGE_TTL_S


async def test_a_dropped_event_restarts_the_interval_instead_of_extending_it() -> None:
    redis: Any = FakeRedis()
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    await tracker.stamp(redis, dropped_events=0, now=_at(1))

    await tracker.stamp(redis, dropped_events=3, now=_at(2))

    hash_ = redis.hashes[keys.tape_coverage("binance")]
    # A drop can have been a trade on any symbol: the interval cannot span it.
    assert hash_["session_since"] == _at(2).isoformat()
    # And it cannot reach *back* across it either. The safety margin would put
    # ``covered_until`` half a second before the break, i.e. inside the interval
    # the drop just invalidated, so the published interval is empty
    # (``covered_until == session_since``) until the next stamp earns one.
    assert hash_["covered_until"] == _at(2).isoformat()

    await tracker.stamp(redis, dropped_events=3, now=_at(4))
    assert (
        redis.hashes[keys.tape_coverage("binance")]["covered_until"]
        == (_at(4) - timedelta(seconds=COVERAGE_SAFETY_S)).isoformat()
    )


async def test_a_write_in_flight_holds_the_stamp_back() -> None:
    redis: Any = FakeRedis()
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    tracker.writing()

    assert await tracker.stamp(redis, dropped_events=0, now=_at(1)) is False
    assert keys.tape_coverage("binance") not in redis.hashes

    tracker.written()
    assert await tracker.stamp(redis, dropped_events=0, now=_at(2)) is True


async def test_a_symbol_subscribed_mid_session_is_covered_only_from_its_subscription() -> None:
    redis: Any = FakeRedis()
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    tracker.subscribed(["SOLUSDT"], at=_at(30))
    await tracker.stamp(redis, dropped_events=0, now=_at(31))

    hash_ = redis.hashes[keys.tape_coverage("binance")]
    assert hash_["sym:BTCUSDT"] == _at(0).isoformat()
    assert hash_["sym:SOLUSDT"] == _at(30).isoformat()


async def test_an_unsubscribed_symbol_stops_claiming_coverage() -> None:
    redis: Any = FakeRedis()
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT", "ETHUSDT"], at=_at(0))
    await tracker.stamp(redis, dropped_events=0, now=_at(1))

    tracker.unsubscribed(["ETHUSDT"])
    await tracker.stamp(redis, dropped_events=0, now=_at(2))

    hash_ = redis.hashes[keys.tape_coverage("binance")]
    assert "sym:ETHUSDT" not in hash_
    assert "sym:BTCUSDT" in hash_


async def test_a_broken_session_publishes_nothing_until_it_is_restarted() -> None:
    redis: Any = FakeRedis()
    tracker = CoverageTracker("binance")
    tracker.session_started(["BTCUSDT"], at=_at(0))
    await tracker.stamp(redis, dropped_events=0, now=_at(1))

    tracker.session_broken()

    assert await tracker.stamp(redis, dropped_events=0, now=_at(2)) is False
    # The reader must see an interval that ended, never one that keeps growing
    # while the socket is down.
    assert redis.hashes[keys.tape_coverage("binance")]["session_since"] == ""

    tracker.session_started(["BTCUSDT"], at=_at(5))
    assert await tracker.stamp(redis, dropped_events=0, now=_at(6)) is True
    assert redis.hashes[keys.tape_coverage("binance")]["session_since"] == _at(5).isoformat()
