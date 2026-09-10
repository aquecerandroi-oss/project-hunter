"""``GET /api/v1/system/latency`` — reads three heartbeat sources off Redis
and never fabricates a hop that has not been measured yet.
"""

from __future__ import annotations

import pytest
import redis.exceptions

from hunter_api.schemas.latency import LatencySloStatus
from hunter_api.services.latency import (
    EXECUTION_PAPER_KEY,
    STRATEGY_SHADOW_KEY,
    build_latency,
)

pytestmark = pytest.mark.unit


class _FakeRedis:
    """``scan_iter`` over a fixed key list, ``hgetall`` from a fixed mapping --
    the same shape ``test_system_workers_status.py``'s fakes use, extended
    with ``scan_iter`` since this endpoint scans for the market hop."""

    def __init__(
        self,
        *,
        scan_keys: list[str] | None = None,
        hashes: dict[str, dict[bytes, bytes] | Exception] | None = None,
    ) -> None:
        self._scan_keys = scan_keys or []
        self._hashes = hashes or {}

    async def scan_iter(self, match: str | None = None, count: int | None = None):
        del match, count
        for key in self._scan_keys:
            yield key.encode()

    async def hgetall(self, key: str) -> dict[bytes, bytes]:
        value = self._hashes.get(key, {})
        if isinstance(value, Exception):
            raise value
        return value


def _bytes(fields: dict[str, str]) -> dict[bytes, bytes]:
    return {k.encode(): v.encode() for k, v in fields.items()}


MARKET_KEY = "hb:market:binance"


async def test_build_latency_with_nothing_reporting_is_unknown_everywhere() -> None:
    redis = _FakeRedis()
    result = await build_latency(redis)  # pyright: ignore[reportArgumentType]
    assert {hop.hop: hop.status for hop in result.hops} == {
        "ingest": LatencySloStatus.UNKNOWN,
        "flush": LatencySloStatus.UNKNOWN,
        "decision": LatencySloStatus.UNKNOWN,
        "admission": LatencySloStatus.UNKNOWN,
        "fill": LatencySloStatus.UNKNOWN,
    }
    assert result.end_to_end.status == LatencySloStatus.UNKNOWN
    assert result.end_to_end.p50_s is None
    assert result.end_to_end.p95_s is None


async def test_build_latency_reads_the_market_hop_off_the_first_matching_hash() -> None:
    redis = _FakeRedis(
        scan_keys=[MARKET_KEY],
        hashes={
            MARKET_KEY: _bytes(
                {
                    "ingest_lag_p50_s": "0.100",
                    "ingest_lag_p95_s": "0.300",
                    "flush_lag_p50_s": "0.400",
                    "flush_lag_p95_s": "0.900",
                }
            )
        },
    )
    result = await build_latency(redis)  # pyright: ignore[reportArgumentType]
    by_hop = {hop.hop: hop for hop in result.hops}
    assert by_hop["ingest"].p50_s == pytest.approx(0.1)
    assert by_hop["ingest"].p95_s == pytest.approx(0.3)
    assert by_hop["ingest"].status == LatencySloStatus.OK
    assert by_hop["flush"].p95_s == pytest.approx(0.9)
    assert by_hop["flush"].status == LatencySloStatus.WARN  # past warn_s=0.5, at/under critical=1.0


async def test_build_latency_skips_a_market_hash_without_the_t379_fields() -> None:
    """A ``hb:market:*`` hash from a build that never wired
    ``hunter_market_worker.latency`` (or a stray key matching the glob) must
    not be mistaken for the ingest/flush source."""
    redis = _FakeRedis(
        scan_keys=["hb:market:bybit"],
        hashes={"hb:market:bybit": _bytes({"ws_state": "connected"})},
    )
    result = await build_latency(redis)  # pyright: ignore[reportArgumentType]
    by_hop = {hop.hop: hop for hop in result.hops}
    assert by_hop["ingest"].p95_s is None
    assert by_hop["ingest"].status == LatencySloStatus.UNKNOWN


async def test_build_latency_reads_decision_admission_fill_hops() -> None:
    redis = _FakeRedis(
        hashes={
            STRATEGY_SHADOW_KEY: _bytes(
                {"decision_lag_p50_s": "2.0", "decision_lag_p95_s": "18.0"}
            ),
            EXECUTION_PAPER_KEY: _bytes(
                {
                    "admission_lag_p50_s": "0.5",
                    "admission_lag_p95_s": "1.5",
                    "fill_lag_p50_s": "0.6",
                    "fill_lag_p95_s": "1.9",
                }
            ),
        }
    )
    result = await build_latency(redis)  # pyright: ignore[reportArgumentType]
    by_hop = {hop.hop: hop for hop in result.hops}
    assert by_hop["decision"].p50_s == pytest.approx(2.0)
    assert by_hop["decision"].p95_s == pytest.approx(18.0)
    assert by_hop["decision"].status == LatencySloStatus.WARN  # p95 18 > warn 5, <= critical 20
    assert by_hop["admission"].status == LatencySloStatus.WARN  # p95 1.5 > warn 1.0
    assert by_hop["fill"].status == LatencySloStatus.WARN  # p95 1.9 > warn 1.0, <= critical 2.0


async def test_build_latency_critical_past_the_p95_ceiling() -> None:
    redis = _FakeRedis(
        hashes={
            STRATEGY_SHADOW_KEY: _bytes(
                {"decision_lag_p50_s": "30.0", "decision_lag_p95_s": "45.0"}
            ),
        }
    )
    result = await build_latency(redis)  # pyright: ignore[reportArgumentType]
    by_hop = {hop.hop: hop for hop in result.hops}
    assert by_hop["decision"].status == LatencySloStatus.CRITICAL


async def test_build_latency_end_to_end_sums_only_when_every_hop_has_a_p95() -> None:
    redis = _FakeRedis(
        scan_keys=[MARKET_KEY],
        hashes={
            MARKET_KEY: _bytes(
                {
                    "ingest_lag_p50_s": "0.1",
                    "ingest_lag_p95_s": "0.2",
                    "flush_lag_p50_s": "0.3",
                    "flush_lag_p95_s": "0.4",
                }
            ),
            STRATEGY_SHADOW_KEY: _bytes({"decision_lag_p50_s": "1.0", "decision_lag_p95_s": "2.0"}),
            EXECUTION_PAPER_KEY: _bytes(
                {
                    "admission_lag_p50_s": "0.1",
                    "admission_lag_p95_s": "0.2",
                    "fill_lag_p50_s": "0.1",
                    "fill_lag_p95_s": "0.2",
                }
            ),
        },
    )
    result = await build_latency(redis)  # pyright: ignore[reportArgumentType]
    assert result.end_to_end.p50_s == pytest.approx(0.1 + 0.3 + 1.0 + 0.1 + 0.1)
    assert result.end_to_end.p95_s == pytest.approx(0.2 + 0.4 + 2.0 + 0.2 + 0.2)
    assert result.end_to_end.status == LatencySloStatus.OK


async def test_build_latency_propagates_redis_errors() -> None:
    class _RaisingScan:
        async def scan_iter(self, match: str | None = None, count: int | None = None):
            del match, count
            raise redis.exceptions.ConnectionError("down")
            yield  # pragma: no cover - unreachable; keeps this an async generator

        async def hgetall(self, key: str) -> dict[bytes, bytes]:
            del key
            return {}

    with pytest.raises(redis.exceptions.ConnectionError):
        await build_latency(_RaisingScan())  # pyright: ignore[reportArgumentType]
