"""Unit tests: heartbeat age classification and ``hb:*`` key/hash parsing —
no IO, no Redis.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import redis.exceptions

from hunter_api.schemas.system import WorkerLivenessStatus
from hunter_api.services.system_status import (
    ALIVE_AFTER_S,
    CLOCK_SKEW_TOLERANCE_S,
    HEARTBEAT_SCAN_COUNT,
    LATE_AFTER_S,
    anonymize_instance,
    build_market_status,
    classify_liveness,
    heartbeat_from_hash,
    parse_heartbeat_datetime,
    parse_heartbeat_int,
    parse_heartbeat_key,
    scan_heartbeats,
)
from hunter_core.redis import keys

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


def test_classify_liveness_alive_at_the_boundary() -> None:
    assert classify_liveness(ALIVE_AFTER_S) is WorkerLivenessStatus.ALIVE


def test_classify_liveness_late_just_past_alive() -> None:
    assert classify_liveness(ALIVE_AFTER_S + 0.001) is WorkerLivenessStatus.LATE


def test_classify_liveness_late_at_the_boundary() -> None:
    assert classify_liveness(LATE_AFTER_S) is WorkerLivenessStatus.LATE


def test_classify_liveness_dead_past_late() -> None:
    assert classify_liveness(LATE_AFTER_S + 0.001) is WorkerLivenessStatus.DEAD


def test_classify_liveness_future_ts_beyond_skew_tolerance_is_dead_not_alive() -> None:
    """(F3) A ``ts`` far in the future (clock skew) reads ``dead``, not
    ``alive`` -- a naive ``age_s <= ALIVE_AFTER_S`` check would otherwise
    accept any negative age as "fresher than fresh".
    """
    skewed_age_s = -(CLOCK_SKEW_TOLERANCE_S + 3600)
    assert classify_liveness(skewed_age_s) is WorkerLivenessStatus.DEAD


def test_classify_liveness_mildly_future_ts_within_tolerance_is_still_alive() -> None:
    assert classify_liveness(-1.0) is WorkerLivenessStatus.ALIVE


@pytest.mark.parametrize(
    ("key", "expected_role", "expected_instance"),
    [
        (b"hb:market:binance", "market", "binance"),
        (b"hb:api:my-host:12345", "api", "my-host:12345"),
        (b"hb:scanner:", "scanner", ""),
    ],
)
def test_parse_heartbeat_key_splits_once_on_the_first_colon(
    key: bytes, expected_role: str, expected_instance: str
) -> None:
    assert parse_heartbeat_key(key) == (expected_role, expected_instance)


def test_parse_heartbeat_datetime_rejects_a_naive_or_malformed_string() -> None:
    """(G8) The previous version of this test never actually passed a naive
    datetime -- only ``None``/``""``/a non-date string, none of which
    exercise ``ensure_utc``'s "naive datetime is not allowed" branch at all.
    """
    assert parse_heartbeat_datetime(None) is None
    assert parse_heartbeat_datetime("") is None
    assert parse_heartbeat_datetime("not-a-date") is None
    assert parse_heartbeat_datetime("2026-09-05T12:00:00") is None


def test_parse_heartbeat_datetime_accepts_an_iso_utc_string() -> None:
    parsed = parse_heartbeat_datetime("2026-09-05T12:00:00+00:00")
    assert parsed == NOW


def test_parse_heartbeat_int_tolerates_missing_or_garbage_values() -> None:
    assert parse_heartbeat_int(None) is None
    assert parse_heartbeat_int("") is None
    assert parse_heartbeat_int("not-a-number") is None
    assert parse_heartbeat_int("42") == 42


def test_heartbeat_from_hash_is_none_without_a_ts_field() -> None:
    """A key caught mid-expiry between SCAN and HGETALL never becomes a
    heartbeat with no timestamp to compute age from.
    """
    assert heartbeat_from_hash("api", "host:1", {}, now=NOW) is None


def test_heartbeat_from_hash_computes_age_and_status() -> None:
    fields = {
        "ts": (NOW - timedelta(seconds=5)).isoformat(),
        "last_success": (NOW - timedelta(seconds=20)).isoformat(),
        "errors": "3",
        "version": "0.0.0",
    }
    heartbeat = heartbeat_from_hash("api", "host:1", fields, now=NOW)
    assert heartbeat is not None
    assert heartbeat.age_s == pytest.approx(5.0)
    assert heartbeat.status is WorkerLivenessStatus.ALIVE
    assert heartbeat.errors == 3
    assert heartbeat.version == "0.0.0"
    assert heartbeat.last_event_at is None
    assert heartbeat.ws_state is None


def test_heartbeat_from_hash_reads_the_market_extension_fields_when_present() -> None:
    fields = {
        "ts": NOW.isoformat(),
        "errors": "0",
        "last_event_at": (NOW - timedelta(seconds=1)).isoformat(),
        "ws_state": "connected",
        "subscriptions": "180",
        "reconnects": "2",
        "markets_monitored": "180",
        "open_gaps": "3",
    }
    heartbeat = heartbeat_from_hash("market", "binance", fields, now=NOW)
    assert heartbeat is not None
    assert heartbeat.ws_state == "connected"
    assert heartbeat.subscriptions == 180
    assert heartbeat.reconnects == 2
    assert heartbeat.last_event_at == NOW - timedelta(seconds=1)
    assert heartbeat.markets_monitored == 180
    assert heartbeat.open_gaps == 3


def test_heartbeat_from_hash_missing_errors_defaults_to_zero() -> None:
    heartbeat = heartbeat_from_hash("api", "host:1", {"ts": NOW.isoformat()}, now=NOW)
    assert heartbeat is not None
    assert heartbeat.errors == 0


def test_heartbeat_from_hash_future_ts_beyond_skew_tolerance_is_not_alive() -> None:
    """(F3) A worker with clock skew writing a ``ts`` an hour in the future
    must not read ``alive`` -- and ``age_s`` is clamped at 0, never negative.
    """
    fields = {"ts": (NOW + timedelta(hours=1)).isoformat(), "errors": "0"}
    heartbeat = heartbeat_from_hash("api", "host:1", fields, now=NOW)
    assert heartbeat is not None
    assert heartbeat.status is not WorkerLivenessStatus.ALIVE
    assert heartbeat.status is WorkerLivenessStatus.DEAD
    assert heartbeat.age_s == 0.0


def test_anonymize_instance_passes_market_role_through_verbatim() -> None:
    """(F5) The exchange code is meaningful, non-sensitive UI data."""
    assert anonymize_instance("market", "binance") == "binance"


def test_anonymize_instance_hashes_every_other_role() -> None:
    digest = anonymize_instance("api", "myhost:4242")
    assert digest != "myhost:4242"
    assert len(digest) == 12
    assert "myhost" not in digest
    assert "4242" not in digest


def test_anonymize_instance_is_deterministic_for_the_same_role_and_instance() -> None:
    """Two reads of the same process must still correlate."""
    assert anonymize_instance("api", "myhost:4242") == anonymize_instance("api", "myhost:4242")


def test_anonymize_instance_produces_different_digests_for_different_instances() -> None:
    """(G8) The other half of "deterministic": two *different* instances must
    not collide onto the same digest -- a function that always returned a
    constant (e.g. always ``"000000000000"``) would satisfy the
    same-input-same-output test above but not this one.
    """
    assert anonymize_instance("api", "myhost:4242") != anonymize_instance("api", "otherhost:1")


def test_anonymize_instance_hashes_the_market_role_when_the_instance_has_a_colon() -> None:
    """(G2) The exception is keyed on the *shape* of ``instance``, never on
    ``role``. The market worker entrypoint constructs
    ``WorkerRuntime(role="market")`` without an explicit ``instance``, so it
    still falls back to the generic ``hostname:pid`` default and writes it
    under ``hb:market:{hostname}:{pid}`` -- a role-only exception ("pass it
    through when role == market") would leak that verbatim.
    """
    digest = anonymize_instance("market", "myhost:4242")
    assert digest != "myhost:4242"
    assert "myhost" not in digest
    assert "4242" not in digest
    assert len(digest) == 12


def test_heartbeat_from_hash_anonymizes_instance_for_non_market_roles() -> None:
    fields = {"ts": NOW.isoformat(), "errors": "0"}
    heartbeat = heartbeat_from_hash("api", "myhost:4242", fields, now=NOW)
    assert heartbeat is not None
    assert heartbeat.instance != "myhost:4242"
    assert "myhost" not in heartbeat.instance
    assert "4242" not in heartbeat.instance
    assert len(heartbeat.instance) == 12


def test_heartbeat_from_hash_keeps_market_instance_verbatim() -> None:
    fields = {"ts": NOW.isoformat(), "errors": "0"}
    heartbeat = heartbeat_from_hash("market", "binance", fields, now=NOW)
    assert heartbeat is not None
    assert heartbeat.instance == "binance"


class _RaisingScanRedis:
    """A fake ``redis.asyncio.Redis`` whose ``scan_iter`` raises mid-iteration
    -- for the F2/G4 "Redis unavailable" scenario, without a real connection.

    (F7/G8) Asserts the ``count`` it receives instead of discarding it: a
    reverted F7 fix (redis-py's default ``SCAN COUNT`` of 10, instead of
    ``HEARTBEAT_SCAN_COUNT``) would otherwise pass this fake silently.
    """

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def scan_iter(self, match: str | None = None, count: int | None = None):
        assert count == HEARTBEAT_SCAN_COUNT
        del match
        exc = self._exc

        async def _gen():
            raise exc
            yield  # pragma: no cover - unreachable; keeps this an async generator

        return _gen()


async def test_scan_heartbeats_reraises_when_redis_is_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """(G4) Redis being unavailable must not read the same as "no worker has
    ever reported in" -- both would otherwise render as an identical
    ``200 []``. This function re-raises so the router can answer an explicit
    ``503`` instead; only the error's type is logged, never ``str(exc)``.
    """
    fake_redis = _RaisingScanRedis(redis.exceptions.ConnectionError("connection refused"))
    with (
        caplog.at_level(logging.WARNING, logger="hunter_api.services.system_status"),
        pytest.raises(redis.exceptions.ConnectionError),
    ):
        await scan_heartbeats(fake_redis)  # pyright: ignore[reportArgumentType]
    assert "ConnectionError" in caplog.text


def test_decode_never_raises_on_invalid_utf8_hash_values() -> None:
    """(G7) A hash value that is not valid UTF-8 must decode to *something*
    rather than raise ``UnicodeDecodeError`` past this boundary.
    """
    from hunter_api.services.system_status import _decode  # pyright: ignore[reportPrivateUsage]

    decoded = _decode({b"ws_state": b"\xff\xfe not valid utf-8"})
    assert isinstance(decoded["ws_state"], str)


class _StaticHgetallRedis:
    """A fake ``redis.asyncio.Redis`` whose ``hgetall`` returns a fixed
    mapping per key, or raises a configured exception for that key -- for
    ``build_market_status`` unit tests that need per-exchange control
    without a real Redis connection.
    """

    def __init__(self, responses: dict[bytes | str, dict[bytes, bytes] | Exception]) -> None:
        self._responses = responses

    async def hgetall(self, key: bytes | str) -> dict[bytes, bytes]:
        value = self._responses.get(key, {})
        if isinstance(value, Exception):
            raise value
        return value


def _patched_repository(*, exchange_codes: list[str], monitored: dict[str, int] | None = None):
    """A ``patch`` context manager for ``system_status.MarketRepository`` --
    ``build_market_status``'s own Postgres calls never run in these tests.
    """
    patcher = patch("hunter_api.services.system_status.MarketRepository")
    repo_cls = patcher.start()
    repo = repo_cls.return_value
    repo.list_exchange_codes = AsyncMock(return_value=exchange_codes)
    repo.monitored_market_counts = AsyncMock(return_value=monitored or {})
    repo.open_gap_counts = AsyncMock(return_value={})
    return patcher


async def test_build_market_status_reraises_when_every_exchange_heartbeat_read_fails() -> None:
    """(G4) Every exchange's own heartbeat read failing is a genuine Redis
    outage, not "no worker has reported for any exchange yet" -- this must
    propagate so the router can answer ``503``, never render as a healthy
    ``200`` indistinguishable from an idle cluster.
    """
    patcher = _patched_repository(exchange_codes=["binance", "bybit"])
    try:
        fake_redis = _StaticHgetallRedis(
            {
                keys.heartbeat("market", "binance"): redis.exceptions.ConnectionError("down"),
                keys.heartbeat("market", "bybit"): redis.exceptions.ConnectionError("down"),
            }
        )
        with pytest.raises(redis.exceptions.RedisError):
            await build_market_status(object(), fake_redis)  # pyright: ignore[reportArgumentType]
    finally:
        patcher.stop()


async def test_build_market_status_isolates_a_single_exchange_heartbeat_failure() -> None:
    """(G4) One exchange's own heartbeat hash misbehaving must not take the
    whole response down with it -- every other exchange still renders.
    """
    patcher = _patched_repository(
        exchange_codes=["binance", "bybit"], monitored={"binance": 1, "bybit": 1}
    )
    try:
        fake_redis = _StaticHgetallRedis(
            {
                keys.heartbeat("market", "binance"): redis.exceptions.ResponseError("WRONGTYPE"),
                keys.heartbeat("market", "bybit"): {b"ws_state": b"connected"},
            }
        )
        result = await build_market_status(object(), fake_redis)  # pyright: ignore[reportArgumentType]
    finally:
        patcher.stop()
    by_code = {row.exchange: row for row in result.exchanges}
    assert by_code["binance"].ws_state == "unavailable"
    assert by_code["bybit"].ws_state == "connected"


async def test_build_market_status_future_last_event_at_is_not_a_healthy_live_feed() -> None:
    """(G6) A ``last_event_at`` far in the future must not read as evidence
    of a live feed: the previous code only clamped the age at 0 and left
    ``ws_state`` free to still say "connected" off a timestamp that cannot be
    real. Now the row's ``last_event_at``/``last_event_age_ms`` come back
    absent and ``ws_state`` is forced to ``"unavailable"``.
    """
    patcher = _patched_repository(exchange_codes=["binance"], monitored={"binance": 1})
    try:
        far_future = (datetime.now(UTC) + timedelta(hours=1)).isoformat().encode()
        fake_redis = _StaticHgetallRedis(
            {
                keys.heartbeat("market", "binance"): {
                    b"ws_state": b"connected",
                    b"last_event_at": far_future,
                },
            }
        )
        result = await build_market_status(object(), fake_redis)  # pyright: ignore[reportArgumentType]
    finally:
        patcher.stop()
    row = result.exchanges[0]
    assert row.ws_state != "connected"
    assert row.ws_state == "unavailable"
    assert row.last_event_at is None
    assert row.last_event_age_ms is None
