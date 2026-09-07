"""Synthetic, labelled inputs for ``test_m2_pipeline.py`` — nothing recorded.

Everything here is either **imported from the scanner's own test builders**
(``services/scanner-worker/tests/builders.py`` and ``test_bootstrap.py``, loaded
by path because ``scanner-worker`` is not a Python identifier and cannot be
imported by dotted name — the same trick ``conftest.py`` uses for
``jwt_keys.py``) or a deterministic shaping of the series they produce.

Two rules this module exists to keep:

**One series, two readers.** The same seeded random walk is persisted as
``candles`` (what the baseline bootstrap replays) and written into the hot state
as the msgpack rows a market-worker publishes (what the live evaluation reads).
A test that fed the two halves different numbers would prove nothing about the
pipeline that runs in production.

**The shaping is arithmetic, not noise.** The volume spike, the one-hour drift
and the tape are closed-form functions of the base series, so every number the
test asserts can be derived by hand from the constants at the top of it.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import msgpack

from hunter_core.domain.enums import (
    BaselineSampling,
    BaselineSource,
    OrderSide,
    Timeframe,
)
from hunter_core.domain.market import NormalizedCandle
from hunter_core.redis import keys
from hunter_indicators.baselines import ALGO_VERSION, BaselineKey, BaselineRevision

if TYPE_CHECKING:
    from collections.abc import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER_TESTS = REPO_ROOT / "services" / "scanner-worker" / "tests"
_PACKAGE = "hunter_m2_scanner_tests"


def _scanner_tests_package() -> ModuleType:
    """A synthetic package rooted at the scanner's ``tests/`` directory.

    ``test_bootstrap.py`` uses relative imports (``from .builders import ...``),
    so loading it by file path alone raises ``ImportError: attempted relative
    import with no known parent package``. Registering a package whose
    ``__path__`` is that directory makes the relative imports resolve to the
    very files they name, with no copy of their code here.
    """
    existing = sys.modules.get(_PACKAGE)
    if existing is not None:
        return existing
    package = ModuleType(_PACKAGE)
    package.__path__ = [str(SCANNER_TESTS)]  # type: ignore[attr-defined]
    sys.modules[_PACKAGE] = package
    return package


def _scanner_test_module(name: str) -> ModuleType:
    _scanner_tests_package()
    qualified = f"{_PACKAGE}.{name}"
    cached = sys.modules.get(qualified)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(qualified, SCANNER_TESTS / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover - wiring failure
        raise RuntimeError(f"cannot load {name} from {SCANNER_TESTS}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
    return module


scanner_builders = _scanner_test_module("builders")
scanner_bootstrap_tests = _scanner_test_module("test_bootstrap")
scanner_policies = _scanner_test_module("policies")

synthetic_minutes = cast("Any", scanner_bootstrap_tests).synthetic_minutes
"""The seeded random walk of ``test_bootstrap.py`` — labelled fixture, not market data."""

run_bootstrap = cast("Any", scanner_bootstrap_tests).run_bootstrap
"""``prepare_job -> request_gaps -> run_slice -> finish_job``, the unsliced composition."""

seed_market = cast("Any", _scanner_test_module("db_helpers")).seed_market
build_policy = cast("Any", scanner_policies).build_policy

candle_rows = cast("Any", scanner_builders).candle_rows
book_payload = cast("Any", scanner_builders).book_payload
deriv_hash = cast("Any", scanner_builders).deriv_hash

_codec: Any = msgpack


def _packb(value: Any) -> bytes:
    packed: Any = _codec.packb(value, use_bin_type=True, datetime=True)
    assert isinstance(packed, bytes)
    return packed


# --- shaping the base series ------------------------------------------------


def to_candle(row: dict[str, Any], *, exchange: str, symbol: str) -> NormalizedCandle:
    """One persisted-candle dict as the market-worker's normalized candle."""
    open_time: datetime = row["open_time"]
    return NormalizedCandle(
        exchange=exchange,
        symbol=symbol,
        timeframe=Timeframe.M1,
        open_time=open_time,
        close_time=open_time + timedelta(minutes=1),
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume=row["volume"],
        quote_volume=row["quote_volume"],
        trade_count=row["trade_count"],
        taker_buy_volume=row["taker_buy_volume"],
        is_final=True,
    )


def shape_tail(
    rows: list[dict[str, Any]],
    *,
    cut: datetime,
    hour_multiplier: Decimal,
    spike_multiplier: Decimal,
    drift: Decimal,
    spike_minutes: int = 5,
    hour_minutes: int = 60,
) -> list[dict[str, Any]]:
    """The last hour of the series, amplified and drifted — deterministically.

    * every minute in ``[cut - hour_minutes, cut)`` has its volume multiplied by
      ``hour_multiplier``, and the last ``spike_minutes`` by
      ``spike_multiplier`` instead: that is the injected volume spike;
    * prices in the same hour move linearly from the last base close to
      ``close * (1 + drift)``, with ``high``/``low`` pinched onto the close, so
      ``return_1h`` is a number this test can state exactly instead of a draw
      from the walk.
    """
    hour_start = cut - timedelta(minutes=hour_minutes)
    spike_start = cut - timedelta(minutes=spike_minutes)
    anchor = next(row["close"] for row in reversed(rows) if row["open_time"] < hour_start)
    shaped: list[dict[str, Any]] = []
    for row in rows:
        stamp: datetime = row["open_time"]
        if stamp < hour_start:
            shaped.append(row)
            continue
        step = int((stamp - hour_start).total_seconds() // 60) + 1
        price = (anchor * (Decimal(1) + drift * Decimal(step) / Decimal(hour_minutes))).quantize(
            Decimal("0.0001")
        )
        multiplier = spike_multiplier if stamp >= spike_start else hour_multiplier
        volume = (row["volume"] * multiplier).quantize(Decimal("0.0001"))
        shaped.append(
            {
                **row,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume,
                "quote_volume": (volume * price).quantize(Decimal("0.0001")),
                "taker_buy_volume": (volume / 2).quantize(Decimal("0.0001")),
            }
        )
    return shaped


def trade_rows(
    *, until: datetime, seconds: int, per_second: int, buys_per_four: int
) -> list[bytes]:
    """A deterministic tape: ``per_second`` trades a second, newest first.

    ``buys_per_four`` of every four consecutive trades are buys, so **every**
    window longer than four trades carries the same taker pressure — a ratio
    that depended on where the window fell would make ``buy_pressure_5m`` a
    function of the cut instead of of the tape.
    """
    rows: list[bytes] = []
    total = seconds * per_second
    for index in range(total):
        stamp = until - timedelta(seconds=index / per_second)
        side = OrderSide.BUY if index % 4 < buys_per_four else OrderSide.SELL
        rows.append(
            _packb(
                {
                    "ts": stamp.isoformat(),
                    "price": "100",
                    "qty": "1",
                    "side": side.value,
                    "trade_id": str(index),
                }
            )
        )
    return rows


# --- writing the hot state into a real Redis --------------------------------


async def write_hot_state(
    redis: Any,
    *,
    exchange: str,
    symbol: str,
    candles: Sequence[NormalizedCandle],
    trades: Sequence[bytes],
    as_of: datetime,
) -> None:
    """The four keys ``read_hot_state`` reads, in the market-worker's own bytes."""
    candles_key = keys.candles_1m(exchange, symbol)
    trades_key = keys.trades(exchange, symbol)
    await redis.delete(candles_key, trades_key)
    await redis.rpush(candles_key, *candle_rows(list(candles)))
    await redis.rpush(trades_key, *trades)
    await redis.set(keys.book(exchange, symbol), book_payload(ts=as_of))
    await redis.hset(keys.derivatives(exchange, symbol), mapping=deriv_hash(ts=as_of))


async def publish_coverage(
    redis: Any, *, exchange: str, symbol: str, session_since: datetime, covered_until: datetime
) -> None:
    """``mkt:{exchange}:coverage`` — the collector's proof, without which the
    tape features refuse themselves (and no EARLY can ever be published)."""
    await redis.hset(
        keys.tape_coverage(exchange),
        mapping={
            "session_since": session_since.isoformat(),
            "covered_until": covered_until.isoformat(),
            f"sym:{symbol}": session_since.isoformat(),
        },
    )


# --- the one baseline a candle bootstrap cannot produce ---------------------


def live_revision(
    *,
    market_id: UUID,
    feature: str,
    hour_of_day: int,
    median: Decimal,
    mad: Decimal,
    window_end: datetime,
    available_at: datetime,
    sample_size: int = 420,
) -> BaselineRevision:
    """A ``LIVE``-sourced revision, exactly as the hourly refresh writes one.

    ``trade_velocity_1m`` has no bootstrap baseline by design
    (``historical_source_unavailable``: candles do not carry the tape), and the
    EARLY confirmation reads its median. Rather than skip that confirmation,
    this test writes the revision the *live* refresh would have written after
    seven days of ``feature_snapshots`` — through ``SqlBaselineStore.append``,
    the same writer, never a hand-rolled INSERT.
    """
    return BaselineRevision(
        key=BaselineKey(market_id=market_id, feature=feature, hour_of_day=hour_of_day),
        feature_version=1,
        algo_version=ALGO_VERSION,
        window_start=window_end - timedelta(days=7),
        window_end=window_end,
        available_at=available_at,
        median=median,
        mad=mad,
        sample_size=sample_size,
        expected_size=420,
        distinct_days=7,
        coverage=Decimal(sample_size) / Decimal(420),
        source=BaselineSource.LIVE,
        sampling=BaselineSampling.PER_MINUTE,
        input_fingerprint=f"m2-pipeline:{feature}:{hour_of_day}",
    )
