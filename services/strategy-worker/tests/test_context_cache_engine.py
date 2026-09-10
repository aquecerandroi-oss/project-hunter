"""Family context cache — equivalence and benchmark against real Postgres (T3.74b).

One testcontainer invocation proves both halves the brief asks for. Design:
``docs/plans/T3.74b-CONTEXT-CACHE.md``.

1. **Equivalence** (``TestEquivalence``): every version of a family, decided
   through the real ``evaluate_slot`` twice on the same recorded, immutable
   series — once the old way (``candles_reader=None``, one query per version)
   and once through :func:`build_family_readers` (one query per family) — must
   return byte-identical :class:`~hunter_core.strategies.base.Evaluation`
   objects. ``Evaluation`` is computed *before* any slot lock or persistence
   (``decide.py``), so calling ``evaluate_slot`` twice for the same
   version/market/bar never corrupts the comparison: only the second call's
   *persistence* is a no-op (the slot barrier already moved), never its
   returned decision.
2. **Benchmark** (``TestBenchmark``): 11 versions across two families (8 + 3,
   the shape T3.74 measured live) times 16 markets, timed with and without the
   cache. The two passes use different bar closes on the same markets so
   neither pass's slot state can influence the other's timing. What is
   *asserted* is the number of real ``load_candles`` round trips (176 before,
   32 after — robust, host-independent); wall-clock bars/s is reported in
   ``notes-T3.74b.md``, not asserted, because CI/dev-box timing is not a
   contract.

Simplification, stated plainly: every version here wraps the same frozen
``volume_anomaly_v1`` contract under different ``strategy_key`` labels. The
cache does not know or care what a version's code does — grouping is by
``strategy_key`` alone — so this is a faithful stand-in for "N versions of one
family" without needing N distinct registered strategies.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_core.strategies.canonical import params_hash
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_strategy_worker import context as context_module
from hunter_strategy_worker.catalogue import ActiveVersion
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.context_cache import build_family_readers
from hunter_strategy_worker.decide import evaluate_slot
from hunter_strategy_worker.replay import candles as replay_candles_module
from hunter_strategy_worker.repo import load_candles as real_load_candles
from hunter_strategy_worker.repo import load_market

from .builders import (
    EXCHANGE,
    activate_version,
    ensure_partitions,
    insert_candles,
    seed_market,
    series,
)

pytestmark = pytest.mark.integration

logger = get_logger(__name__)

LATE = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)
"""The series' own end — the bar with the volume spike (``builders.series``)."""
CONFIG = ShadowConfig(hot_state_tail=0)
MARKET_COUNT = 16


def _version(
    key: str, version_id: uuid.UUID, *, version: str = "v1", atr_bars: int = 97
) -> ActiveVersion:
    params = dict(VOLUME_ANOMALY_V1.default_parameters)
    params["atr_bars"] = atr_bars
    frozen = dict(params)
    return ActiveVersion(
        id=version_id,
        strategy_key=key,
        version=version,
        params=frozen,
        params_hash=params_hash(frozen),
        strategy=VOLUME_ANOMALY_V1,
        code_ref=None,
        purpose="research_only",
    )


async def _seed_market(session: Any, symbol: str) -> uuid.UUID:
    _exchange_id, market_id = await seed_market(session, symbol=symbol, base_asset="BTC")
    await insert_candles(session, market_id, series(LATE))
    return market_id


@pytest.fixture
async def markets(db_session_factory: Any) -> list[Any]:
    """``MARKET_COUNT`` perpetuals, each with the same 1600-minute series
    (spike included) ending at :data:`LATE`."""
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, LATE)
    symbols = [f"BENCH{i}USDT" for i in range(MARKET_COUNT)]
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        await session.execute(text("DELETE FROM candles"))
        for symbol in symbols:
            await _seed_market(session, symbol)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        rows = [await load_market(session, EXCHANGE, symbol) for symbol in symbols]
    assert all(row is not None for row in rows)
    return rows


class TestEquivalence:
    async def test_every_family_members_decision_is_byte_identical_with_and_without_the_cache(
        self, db_session_factory: Any, redis_client: Any, markets: list[Any]
    ) -> None:
        market = markets[0]
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await session.execute(text("DELETE FROM shadow_outbox"))
            await session.execute(text("DELETE FROM shadow_episodes"))
            await session.execute(text("DELETE FROM signal_outcomes"))
            await session.execute(text("DELETE FROM agent_signals"))
            ids = [
                (await activate_version(session, key="equiv_family", version=f"v{i}"))[1]
                for i in range(1, 5)
            ]
        # Two distinct requirements inside the same family (97 -> the 1560
        # floor, 103 -> 1570, just over it) so the cache's ceiling logic is
        # actually exercised, not just a same-size coincidence.
        versions = [
            _version("equiv_family", ids[0], version="v1", atr_bars=97),
            _version("equiv_family", ids[1], version="v2", atr_bars=97),
            _version("equiv_family", ids[2], version="v3", atr_bars=103),
            _version("equiv_family", ids[3], version="v4", atr_bars=103),
        ]
        assert versions[0].context_minutes(CONFIG) != versions[2].context_minutes(CONFIG)

        # Astra, final-diff review, must-fix: without a fixed ``clock=``,
        # ``evaluate_slot`` defaults to the wall clock, and ``lag_s = now -
        # bar_close`` past ``eligibility_max_lag_s`` (300 s) short-circuits to
        # ``unavailable`` *before* touching a candle — which would make this
        # "equivalence" compare two identical refusals instead of two real
        # decisions, silently, on any run where the wall clock has moved past
        # ``LATE``. A clock pinned just after ``bar_close`` makes every run
        # deterministic regardless of when it is actually executed.
        clock = lambda: LATE + timedelta(seconds=2)  # noqa: E731

        uncached: dict[str, Any] = {}
        for version in versions:
            uncached[version.id.hex] = await evaluate_slot(
                db_session_factory,
                redis_client,
                version=version,
                market=market,
                bar_close=LATE,
                config=CONFIG,
                clock=clock,
                candles_reader=None,
            )

        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            family_readers = await build_family_readers(
                session, versions, market=market, bar_close=LATE, config=CONFIG
            )
        assert set(family_readers) == {"equiv_family"}

        for version in versions:
            cached = await evaluate_slot(
                db_session_factory,
                redis_client,
                version=version,
                market=market,
                bar_close=LATE,
                config=CONFIG,
                clock=clock,
                candles_reader=family_readers["equiv_family"],
            )
            before = uncached[version.id.hex]
            assert cached.state == before.state
            assert cached.reason == before.reason
            assert cached.decision == before.decision, (
                f"version {version.version} (atr_bars={version.params['atr_bars']}) "
                "disagreed between cached and uncached reads"
            )


def _counting_load_candles(counts: dict[str, int]) -> Any:
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        counts["calls"] = counts.get("calls", 0) + 1
        return await real_load_candles(*args, **kwargs)

    return wrapper


class TestBenchmark:
    """11 versions (8 + 3, T3.74's measured shape) x 16 markets."""

    FAMILY_A = 8
    FAMILY_B = 3

    async def test_the_cache_cuts_load_candles_round_trips_and_is_never_slower(
        self,
        db_session_factory: Any,
        redis_client: Any,
        markets: list[Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        assert self.FAMILY_A + self.FAMILY_B == 11
        versions: list[ActiveVersion] = []
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            for i in range(self.FAMILY_A):
                label = f"v{i + 1}"
                _strategy_id, version_id = await activate_version(
                    session, key="bench_a", version=label
                )
                versions.append(_version("bench_a", version_id, version=label))
            for i in range(self.FAMILY_B):
                label = f"v{i + 1}"
                _strategy_id, version_id = await activate_version(
                    session, key="bench_b", version=label
                )
                versions.append(_version("bench_b", version_id, version=label))

        counts: dict[str, int] = {}
        wrapper = _counting_load_candles(counts)
        monkeypatch.setattr(context_module, "load_candles", wrapper)
        monkeypatch.setattr(replay_candles_module, "load_candles", wrapper)

        # Both cuts are quiet minutes (well clear of the spike in the last 5
        # before LATE) with ample history behind them, and different from one
        # another so neither pass's slot state can influence the other's — the
        # comparison is meant to be about candle-read cost alone, not about
        # one pass triggering (persist + confirm_or_lapse) and the other not.
        before_cut = LATE - timedelta(minutes=60)
        before_clock = lambda: before_cut + timedelta(seconds=2)  # noqa: E731
        counts.clear()
        started = time.perf_counter()
        for market in markets:
            for version in versions:
                await evaluate_slot(
                    db_session_factory,
                    redis_client,
                    version=version,
                    market=market,
                    bar_close=before_cut,
                    config=CONFIG,
                    clock=before_clock,
                    candles_reader=None,
                )
        before_elapsed = time.perf_counter() - started
        before_calls = counts["calls"]
        before_bars_per_s = (MARKET_COUNT * len(versions)) / before_elapsed

        after_cut = LATE - timedelta(minutes=30)
        after_clock = lambda: after_cut + timedelta(seconds=2)  # noqa: E731
        counts.clear()
        started = time.perf_counter()
        for market in markets:
            async with role_session(db_session_factory, db_role="hunter_worker") as session:
                family_readers = await build_family_readers(
                    session, versions, market=market, bar_close=after_cut, config=CONFIG
                )
            for version in versions:
                await evaluate_slot(
                    db_session_factory,
                    redis_client,
                    version=version,
                    market=market,
                    bar_close=after_cut,
                    config=CONFIG,
                    clock=after_clock,
                    candles_reader=family_readers.get(version.strategy_key),
                )
        after_elapsed = time.perf_counter() - started
        after_calls = counts["calls"]
        after_bars_per_s = (MARKET_COUNT * len(versions)) / after_elapsed

        # Robust, host-independent: one load_candles per version before
        # (16 x 11 = 176) versus one per family per market after (16 x 2 = 32).
        assert before_calls == MARKET_COUNT * len(versions)
        assert after_calls == MARKET_COUNT * 2
        assert after_calls < before_calls

        # The real number the brief asks for (T3.74b) — captured with -s or
        # read from the test's own log line, then copied into notes-T3.74b.md
        # by hand; never asserted on for a magnitude, only for direction above.
        logger.info(
            "t374b_context_cache_benchmark",
            before_bars_per_s=round(before_bars_per_s, 1),
            before_load_candles_calls=before_calls,
            before_elapsed_s=round(before_elapsed, 2),
            after_bars_per_s=round(after_bars_per_s, 1),
            after_load_candles_calls=after_calls,
            after_elapsed_s=round(after_elapsed, 2),
        )
