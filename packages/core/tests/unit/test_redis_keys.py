"""Unit tests for hunter_core.redis: key builders and lock logic against a fake client."""

from typing import Any

import pytest
import redis.exceptions as redis_exceptions
from pydantic import SecretStr
from redis.backoff import ExponentialWithJitterBackoff
from redis.retry import Retry

from hunter_core.redis import acquire_lock, check_redis, create_redis, keys
from hunter_core.settings import Settings

pytestmark = pytest.mark.unit


def test_key_builders_match_architecture_md_5_3() -> None:
    assert keys.ticker("binance", "BTCUSDT") == "mkt:binance:BTCUSDT:ticker"
    assert keys.book("binance", "BTCUSDT") == "mkt:binance:BTCUSDT:book"
    assert keys.trades("binance", "BTCUSDT") == "mkt:binance:BTCUSDT:trades"
    assert keys.candles_1m("binance", "BTCUSDT") == "mkt:binance:BTCUSDT:candles:1m"
    assert keys.derivatives("binance", "BTCUSDT") == "mkt:binance:BTCUSDT:deriv"
    assert keys.features("binance", "BTCUSDT") == "feat:binance:BTCUSDT"
    assert keys.opportunity("binance", "BTCUSDT") == "opp:binance:BTCUSDT"
    assert keys.radar_scores() == "radar:scores"
    assert keys.regime_current() == "regime:current"
    assert keys.kill_switch_system() == "ks:system"
    assert keys.kill_switch_org("org-1") == "ks:org:org-1"
    assert keys.kill_switch_portfolio("pf-1") == "ks:pf:pf-1"
    assert keys.heartbeat("market", "host-1") == "hb:market:host-1"
    assert keys.rate_limit("binance", "rest") == "rl:binance:rest"
    assert keys.lock("universe-refresh") == "lock:universe-refresh"
    assert keys.processed("scanner-worker") == "hunter:processed:scanner-worker"


def test_create_redis_raises_when_redis_url_missing() -> None:
    settings = Settings(redis_url=None)
    with pytest.raises(ValueError, match="REDIS_URL"):
        create_redis(settings)


def test_create_redis_builds_a_client_with_bounded_timeouts() -> None:
    """HIGH-4: with no ``socket_timeout``, an ``await`` on a connection the
    server dropped (e.g. a Redis restart) blocks forever — the awaiting task
    never returns and never raises, so nothing downstream of it (ingestion,
    the heartbeat loop) ever notices the outage or gets a chance to fail
    fatally so the supervisor can restart the process.

    Asserts the *real* connection-pool kwargs the client carries, not a mock
    built here, so a regression that silently drops a timeout is caught.
    """
    settings = Settings(redis_url=SecretStr("redis://localhost:6379/0"))
    client = create_redis(settings)
    kwargs = client.connection_pool.connection_kwargs

    # Unchanged contract: bytes in, bytes out.
    assert kwargs["decode_responses"] is False

    # Bounded, and never the redis-py default of None (block forever).
    assert kwargs["socket_connect_timeout"] == 5.0
    # Must clear the worst observed /ready latency under full CPU saturation
    # (2.25s, HIGH-4 repro) with margin, while staying single-digit seconds.
    assert kwargs["socket_timeout"] == 5.0
    assert 2.25 < kwargs["socket_timeout"] <= 15.0

    # Idle pooled connections are revalidated before reuse.
    assert kwargs["health_check_interval"] == 30.0

    # One blip self-heals instead of surfacing to every caller.
    assert kwargs["retry_on_timeout"] is True
    retry = kwargs["retry"]
    assert isinstance(retry, Retry)
    assert retry.get_retries() == 3
    assert isinstance(retry._backoff, ExponentialWithJitterBackoff)  # pyright: ignore[reportPrivateUsage]


def test_create_redis_retry_covers_timeout_and_connection_errors() -> None:
    """The retry policy must cover both halves of a Redis restart: the
    ``TimeoutError`` from a socket that stopped answering and the
    ``ConnectionError`` from one that is refused while the server reboots.

    Reads the connection object the pool actually builds (``make_connection``
    constructs it without dialing, so this stays a unit test), because
    redis-py deep-copies and mutates the retry per connection — asserting only
    on the kwargs would miss a policy that does not survive that step.
    """
    settings = Settings(redis_url=SecretStr("redis://localhost:6379/0"))
    client = create_redis(settings)
    connection = client.connection_pool.make_connection()

    assert connection.socket_timeout == 5.0
    assert connection.socket_connect_timeout == 5.0
    assert connection.health_check_interval == 30.0

    supported = connection.retry._supported_errors  # pyright: ignore[reportPrivateUsage]
    assert redis_exceptions.TimeoutError in supported
    assert redis_exceptions.ConnectionError in supported
    assert connection.retry.get_retries() == 3


class _FakeRedis:
    def __init__(self, ping_ok: bool = True) -> None:
        self._ping_ok = ping_ok
        self.store: dict[str, str] = {}
        self.eval_calls: list[tuple[str, tuple[Any, ...]]] = []

    async def ping(self) -> bool:
        if not self._ping_ok:
            raise ConnectionError("down")
        return True

    async def set(self, key: str, value: str, nx: bool = False, px: int | None = None) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> int:
        key, token = keys_and_args
        self.eval_calls.append((script, keys_and_args))
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0


async def test_check_redis_true_when_ping_succeeds() -> None:
    assert await check_redis(_FakeRedis(ping_ok=True)) is True  # type: ignore[arg-type]


async def test_check_redis_false_when_ping_fails() -> None:
    assert await check_redis(_FakeRedis(ping_ok=False)) is False  # type: ignore[arg-type]


async def test_acquire_lock_yields_true_and_releases_on_exit() -> None:
    client = _FakeRedis()
    async with acquire_lock(client, "job", ttl_ms=1000) as acquired:  # type: ignore[arg-type]
        assert acquired is True
        assert "lock:job" in client.store
    assert "lock:job" not in client.store


async def test_acquire_lock_yields_false_when_already_held() -> None:
    client = _FakeRedis()
    client.store["lock:job"] = "someone-elses-token"
    async with acquire_lock(client, "job", ttl_ms=1000) as acquired:  # type: ignore[arg-type]
        assert acquired is False
    # release must not touch a lock this holder never acquired
    assert client.store["lock:job"] == "someone-elses-token"
