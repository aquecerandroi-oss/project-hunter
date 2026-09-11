"""The shadow-universe history gate (T3.82): boundary, TTL join, disabled.

No database here -- :func:`hunter_core.universe.has_min_history` is the pure
boundary check (moved there by T3.88, where the ``breadth_5m`` producer reads the
same rule; the numbers and the inclusive ``<=`` are unchanged, which is what these
tests still assert), and :class:`~hunter_strategy_worker.universe.UniverseCache`
accepts an injected ``loader`` that never opens a session (``universe.py``'s own
``_load_via_session`` is the only piece that does, and it is exercised by the
testcontainer proof, ``test_universe_gate.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from hunter_core.universe import has_min_history
from hunter_strategy_worker.pre_dispatch import refuse_before_dispatch
from hunter_strategy_worker.universe import UniverseCache, UniverseSnapshot

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
NINETY_DAYS = timedelta(days=90)


class TestEligibilityBoundary:
    def test_none_history_is_never_eligible(self) -> None:
        assert has_min_history(None, as_of=AS_OF, min_history_days=90) is False

    def test_exactly_ninety_days_old_is_eligible(self) -> None:
        """Inclusive boundary (``<=``), matching every other gate's own
        convention in this package (``ShadowConfig`` docstrings)."""
        assert has_min_history(AS_OF - NINETY_DAYS, as_of=AS_OF, min_history_days=90) is True

    def test_one_second_short_of_ninety_days_is_not_eligible(self) -> None:
        boundary = AS_OF - NINETY_DAYS + timedelta(seconds=1)
        assert has_min_history(boundary, as_of=AS_OF, min_history_days=90) is False

    def test_far_older_than_ninety_days_is_eligible(self) -> None:
        assert (
            has_min_history(AS_OF - timedelta(days=400), as_of=AS_OF, min_history_days=90) is True
        )

    def test_zero_days_admits_anything_with_any_history_at_all(self) -> None:
        """``min_history_days=0`` is disabled at the ``ShadowConfig``/
        ``run_consumer`` level (no ``UniverseCache`` is even built), but the
        pure function stays honest about what ``0`` means arithmetically:
        any candle at or before ``as_of`` qualifies."""
        assert has_min_history(AS_OF, as_of=AS_OF, min_history_days=0) is True


def _snapshot(eligible: set[tuple[str, str]], candidates: set[tuple[str, str]]) -> UniverseSnapshot:
    return UniverseSnapshot(
        eligible=frozenset(eligible),
        candidates=frozenset(candidates),
        min_history_days=90,
        loaded_at=AS_OF,
    )


class _FakeClock:
    """A manually-advanced monotonic clock, for TTL tests without real time."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestCacheTTL:
    async def test_a_market_that_gains_history_joins_after_the_ttl_elapses(self) -> None:
        """The brief's own example: a market crossing the 90-day line joins
        within the hour, never instantly -- the cache must not reload before
        its TTL just because a caller asked."""
        young = ("binance", "YOUNGUSDT")
        before = _snapshot(eligible=set(), candidates={young})
        after = _snapshot(eligible={young}, candidates={young})
        calls = 0

        async def loader(_factory: Any, *, min_history_days: int, clock: Any) -> UniverseSnapshot:
            nonlocal calls
            calls += 1
            return before if calls == 1 else after

        clock = _FakeClock()
        cache = UniverseCache(90, ttl_s=3600.0, clock=clock, loader=loader)

        first = await cache.get(None)  # type: ignore[arg-type]
        assert young not in first.eligible
        assert calls == 1

        clock.advance(3599.0)
        still_stale_ttl = await cache.get(None)  # type: ignore[arg-type]
        assert young not in still_stale_ttl.eligible, "reloaded before its own TTL elapsed"
        assert calls == 1, "the loader ran again before the TTL window closed"

        clock.advance(2.0)
        refreshed = await cache.get(None)  # type: ignore[arg-type]
        assert young in refreshed.eligible
        assert calls == 2

    async def test_a_failed_reload_serves_the_last_snapshot_and_retries_next_ttl(self) -> None:
        old = ("binance", "OLDUSDT")
        good = _snapshot(eligible={old}, candidates={old})
        calls = 0

        async def flaky_loader(
            _factory: Any, *, min_history_days: int, clock: Any
        ) -> UniverseSnapshot:
            nonlocal calls
            calls += 1
            if calls == 1:
                return good
            raise ConnectionError("db unreachable")

        clock = _FakeClock()
        cache = UniverseCache(90, ttl_s=100.0, clock=clock, loader=flaky_loader)
        first = await cache.get(None)  # type: ignore[arg-type]
        assert old in first.eligible

        clock.advance(101.0)
        second = await cache.get(None)  # type: ignore[arg-type]
        assert old in second.eligible, (
            "a failed reload must keep serving the last-known-good snapshot"
        )
        assert calls == 2

        # The TTL clock still advanced on the failed attempt -- a broken
        # database is retried once per TTL window, not once per bar.
        clock.advance(1.0)
        third = await cache.get(None)  # type: ignore[arg-type]
        assert calls == 2, "a failed reload must not be retried before its own TTL elapses"
        assert old in third.eligible


class TestUniverseCheck:
    async def test_admitted_market_reports_shard_counts(self) -> None:
        in_universe_market = ("binance", "INUSDT")
        out_of_universe_market = ("binance", "OUTUSDT")
        snapshot = _snapshot(
            eligible={in_universe_market}, candidates={in_universe_market, out_of_universe_market}
        )

        async def loader(_factory: Any, *, min_history_days: int, clock: Any) -> UniverseSnapshot:
            return snapshot

        cache = UniverseCache(90, loader=loader)
        admitted, size, total = await cache.check(
            None,  # type: ignore[arg-type]
            exchange="binance",
            symbol="INUSDT",
            shard_index=0,
            shard_total=1,
        )
        assert admitted is True
        assert (size, total) == (1, 2)

        refused, size2, total2 = await cache.check(
            None,  # type: ignore[arg-type]
            exchange="binance",
            symbol="OUTUSDT",
            shard_index=0,
            shard_total=1,
        )
        assert refused is False
        assert (size2, total2) == (1, 2), "the shard counts do not change with the queried market"


def _envelope(*, symbol: str = "AAAUSDT", market_type: str = "perpetual") -> Any:
    class _Envelope:
        payload = {"exchange": "binance", "symbol": symbol, "market_type": market_type}

    return _Envelope()


class _RecordingAck:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(
        self, _redis: Any, _stream: Any, _group: Any, message_id: str, _e: Any
    ) -> None:
        self.calls.append(message_id)


class TestRefuseBeforeDispatchDisabled:
    async def test_universe_none_never_refuses_a_perpetual_bar(self) -> None:
        """``universe=None`` is what ``run_consumer`` builds when
        ``ShadowConfig.universe_min_history_days`` is ``0`` -- today's
        behaviour, byte for byte: no cache, no query, every perpetual bar
        reaches the dispatcher, and the heartbeat counters stay unmeasured
        (``None``), not a fabricated zero."""
        from hunter_strategy_worker.consumer_health import ConsumerHealth

        ack = _RecordingAck()
        health = ConsumerHealth()
        refused = await refuse_before_dispatch(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            message_id="1-1",
            envelope=_envelope(market_type="perpetual"),
            group="g",
            health=health,
            universe=None,
            shard_index=0,
            shard_total=1,
            ack_fn=ack,
        )
        assert refused is False
        assert ack.calls == []
        assert health.universe_size is None
        assert health.universe_total is None

    async def test_a_non_perpetual_bar_never_reaches_universe_check(self) -> None:
        """T3.73's spot exclusion runs later, inside ``handle_candle``; this
        door only ever asks the universe question about a perpetual bar."""

        class _ExplodingUniverse:
            async def check(self, *_a: Any, **_kw: Any) -> Any:
                raise AssertionError("a non-perpetual bar must never reach universe.check")

        from hunter_strategy_worker.consumer_health import ConsumerHealth

        ack = _RecordingAck()
        health = ConsumerHealth()
        refused = await refuse_before_dispatch(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            message_id="1-1",
            envelope=_envelope(market_type="spot"),
            group="g",
            health=health,
            universe=_ExplodingUniverse(),  # type: ignore[arg-type]
            shard_index=0,
            shard_total=1,
            ack_fn=ack,
        )
        assert refused is False
        assert ack.calls == []


class TestRefuseBeforeDispatchUniverseGate:
    async def test_a_market_outside_the_universe_is_acked_and_counted(self) -> None:
        from hunter_core.observability import registry
        from hunter_strategy_worker.consumer_health import ConsumerHealth

        def _skipped(reason: str) -> float:
            value = registry.get_sample_value(
                "hunter_shadow_bars_skipped_total", {"reason": reason}
            )
            return 0.0 if value is None else value

        young = ("binance", "YOUNGUSDT")
        snapshot = _snapshot(eligible=set(), candidates={young})

        async def loader(_factory: Any, *, min_history_days: int, clock: Any) -> UniverseSnapshot:
            return snapshot

        cache = UniverseCache(90, loader=loader)
        ack = _RecordingAck()
        health = ConsumerHealth()
        before = _skipped("universe_history")

        refused = await refuse_before_dispatch(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            message_id="1-1",
            envelope=_envelope(symbol="YOUNGUSDT"),
            group="g",
            health=health,
            universe=cache,
            shard_index=0,
            shard_total=1,
            ack_fn=ack,
        )
        assert refused is True
        assert ack.calls == ["1-1"]
        assert health.universe_size == 0
        assert health.universe_total == 1
        assert _skipped("universe_history") == before + 1

    async def test_a_market_inside_the_universe_reaches_the_dispatcher(self) -> None:
        from hunter_strategy_worker.consumer_health import ConsumerHealth

        old = ("binance", "OLDUSDT")
        snapshot = _snapshot(eligible={old}, candidates={old})

        async def loader(_factory: Any, *, min_history_days: int, clock: Any) -> UniverseSnapshot:
            return snapshot

        cache = UniverseCache(90, loader=loader)
        ack = _RecordingAck()
        health = ConsumerHealth()

        refused = await refuse_before_dispatch(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            message_id="1-1",
            envelope=_envelope(symbol="OLDUSDT"),
            group="g",
            health=health,
            universe=cache,
            shard_index=0,
            shard_total=1,
            ack_fn=ack,
        )
        assert refused is False
        assert ack.calls == []
        assert health.universe_size == 1
        assert health.universe_total == 1
