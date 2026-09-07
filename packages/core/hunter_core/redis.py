"""Redis client factory, hot-state key builders and a distributed lock.

Key layout mirrors ARCHITECTURE.md §5.3 exactly. Everything here can be lost
without harm (ARCHITECTURE.md §5.3: "O que esta em Redis pode ser perdido.")
— nothing that matters for audit or accounting lives only in Redis.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import redis.asyncio as redis_asyncio
from redis.backoff import ExponentialWithJitterBackoff
from redis.retry import Retry

from hunter_core.domain.enums import MarketType

if TYPE_CHECKING:
    from datetime import date

    from hunter_core.settings import Settings

_RELEASE_IF_OWNER_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


# --- HIGH-4: bounded socket budgets and self-healing ------------------------
# redis-py defaults BOTH socket timeouts to ``None`` — block forever. With that
# default an ``await`` on a connection the server silently dropped (a Redis
# restart, or the half-open TCP a container network leaves behind) never
# returns and never raises: the task simply parks, so supervision sees no
# failure and ``restart: unless-stopped`` never fires because nothing died.
# Reproduced against the live stack — after an 81s ``stop redis`` /
# ``start redis`` the market-worker sat at 0.23% CPU with ``/ready`` 503, no
# log line for 19 minutes and no exchange WebSockets left. Every value below
# turns that silent park into an error a supervisor can act on. This client is
# shared with ``apps/api`` (a request-serving process), so each is sized to be
# safe there too.

_SOCKET_CONNECT_TIMEOUT_S = 5.0
"""Bounds the TCP + Redis handshake.

Scenario: the Redis container is down or still booting, so ``connect()`` is
handshaking against a socket that may not be listening yet. A refused
connection returns instantly; this bounds the case where the SYN goes nowhere
(container mid-restart, DNS re-resolution). A live Redis accepts in
milliseconds, so 5s never misreads a merely-loaded Docker network as "down".
"""

_SOCKET_TIMEOUT_S = 5.0
"""Bounds every read/write on an established connection — the exact ``await``
that hung forever.

Scenario: the command was written to a connection the server then dropped
mid-flight; the caller now gets a ``TimeoutError`` in 5s instead of never. NOT
1s on purpose: the market-worker saturates a CPU core, and its own ``/ready``
latency was measured swinging between 0.02s and 2.25s under that load. asyncio
timeouts are wall-clock, so an event-loop stall of ~2.25s would trip a 1s
budget even when Redis answered instantly. 5s keeps ~2.2x headroom over the
worst stall observed while still surfacing a dead connection in single-digit
seconds rather than 19 minutes.
"""

_HEALTH_CHECK_INTERVAL_S = 30.0
"""Revalidates an idle pooled connection before it is reused.

Scenario: a pooled connection sat idle across a Redis restart. Before handing
back out a connection idle longer than this, redis-py PINGs it and reconnects
if the PING fails, so a real command is not the thing that discovers the
corpse. Comfortably above the market-worker heartbeat's 5s write cadence (busy
connections are never probed needlessly) and cheap: one PING per idle
connection per 30s.
"""

# Scenario: one blip — a single dropped connection, a failover — should heal
# itself instead of becoming an exception every call site has to handle. 3 is
# redis-py's own default retry count; the backoff is deliberately far tighter
# than redis-py's default (cap 0.5s vs 10s) so the total sleep added is
# <= ~1.5s. Jitter matters because every service in this stack reconnects at
# the same instant after a Redis restart, and un-jittered backoff would sync
# them into a thundering herd against a just-booted server. The absolute
# ceiling for one command is therefore ~(4 attempts x 5s) + ~1.5s of backoff;
# the common failure (connection refused) fails instantly, so the real cost of
# a retry is the backoff alone. Bounded and loud beats unbounded and silent.
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_BASE_S = 0.05
_RETRY_BACKOFF_CAP_S = 0.5


def create_redis(settings: Settings) -> redis_asyncio.Redis:
    """A ``redis.asyncio`` client for ``REDIS_URL``. Bytes in, bytes out —
    callers that need text decode themselves (payloads are orjson bytes).

    Bounded timeouts and a retry policy (HIGH-4, see the module constants
    above): a connection dropped by a Redis restart must surface as an
    exception in seconds, not hang the awaiting task forever.
    """
    redis_url = settings.redis_url
    if redis_url is None:
        raise ValueError("REDIS_URL is not configured")
    return redis_asyncio.from_url(
        redis_url.get_secret_value(),
        decode_responses=False,
        socket_connect_timeout=_SOCKET_CONNECT_TIMEOUT_S,
        socket_timeout=_SOCKET_TIMEOUT_S,
        health_check_interval=_HEALTH_CHECK_INTERVAL_S,
        # ``retry_on_timeout`` adds TimeoutError to the retryable set (redis-py
        # retries ConnectionError by default); ``retry`` replaces redis-py's
        # implicit ``Retry(NoBackoff(), 1)`` fallback with a jittered,
        # explicitly bounded policy. Together: the instant Redis restarts
        # becomes a retried command on a fresh pooled connection instead of a
        # bare TimeoutError every caller has to special-case.
        retry_on_timeout=True,
        retry=Retry(
            ExponentialWithJitterBackoff(base=_RETRY_BACKOFF_BASE_S, cap=_RETRY_BACKOFF_CAP_S),
            retries=_RETRY_ATTEMPTS,
        ),
    )


async def check_redis(client: redis_asyncio.Redis) -> bool:
    """``PING`` — true if Redis answers, false on any error."""
    try:
        pong = await client.ping()  # type: ignore[reportUnknownMemberType]
    except Exception:
        return False
    return bool(pong)


# --- market identity in a key (T3.0b) ----------------------------------------
# ``BTCUSDT`` is two markets on Binance: the spot pair and the USDS-M
# perpetual. One venue, two instruments — so the *venue segment* of every
# market key carries the type, and the perpetual's segment stays what it was:
# ``mkt:binance:BTCUSDT:ticker`` (perpetual, in Redis right now) next to
# ``mkt:binance:spot:BTCUSDT:ticker``. Nothing migrates — four collector
# shards, the scanner, the strategy worker and the API are all reading the
# first form as this ships — so ``PERPETUAL`` is both the default and the
# byte-identical key. Spot is the variant that has to say its name.


_PERP = MarketType.PERPETUAL
"""The default of every builder below — spelled once so the signatures fit."""


def _venue(exchange: str, market_type: MarketType) -> str:
    """``binance`` for perpetuals, ``binance:spot`` for spot."""
    if market_type is _PERP:
        return exchange
    return f"{exchange}:{market_type.value}"


def _venue_prefix(market_type: MarketType) -> str:
    """``""`` for perpetuals, ``"spot:"`` for spot — the type *before* the
    exchange, which only ``hb:market:*`` needs (see :meth:`keys.market_heartbeat`)."""
    return "" if market_type is _PERP else f"{market_type.value}:"


class keys:
    """Hot-state key builders — one per row of ARCHITECTURE.md §5.3."""

    @staticmethod
    def ticker(exchange: str, symbol: str, market_type: MarketType = _PERP) -> str:
        return f"mkt:{_venue(exchange, market_type)}:{symbol}:ticker"

    @staticmethod
    def book(exchange: str, symbol: str, market_type: MarketType = _PERP) -> str:
        return f"mkt:{_venue(exchange, market_type)}:{symbol}:book"

    @staticmethod
    def trades(exchange: str, symbol: str, market_type: MarketType = _PERP) -> str:
        return f"mkt:{_venue(exchange, market_type)}:{symbol}:trades"

    @staticmethod
    def candles_1m(exchange: str, symbol: str, market_type: MarketType = _PERP) -> str:
        return f"mkt:{_venue(exchange, market_type)}:{symbol}:candles:1m"

    @staticmethod
    def derivatives(exchange: str, symbol: str, market_type: MarketType = _PERP) -> str:
        """``mkt:{venue}:{symbol}:deriv``. Built for spot too, and deliberately:
        the reader that asks for a spot market's funding must find an empty
        hash, never the perpetual's."""
        return f"mkt:{_venue(exchange, market_type)}:{symbol}:deriv"

    @staticmethod
    def features(exchange: str, symbol: str, market_type: MarketType = _PERP) -> str:
        return f"feat:{_venue(exchange, market_type)}:{symbol}"

    @staticmethod
    def opportunity(exchange: str, symbol: str, market_type: MarketType = _PERP) -> str:
        return f"opp:{_venue(exchange, market_type)}:{symbol}"

    @staticmethod
    def market_slug(exchange: str, symbol: str, market_type: MarketType = _PERP) -> str:
        """One market's identity as a single string: ``binance:BTCUSDT`` for the
        perpetual, ``binance:spot:BTCUSDT`` for the spot pair.

        Not a Redis key, but the same identity problem wherever a market is a
        *name*: the ``radar:scores`` ZSET member (two rows for one symbol would
        be one member, and the last writer would set the score of a market it
        knows nothing about) and any per-market map built from a page of rows.
        """
        return f"{_venue(exchange, market_type)}:{symbol}"

    @staticmethod
    def tape_coverage(exchange: str, market_type: MarketType = _PERP) -> str:
        """``mkt:{exchange}:coverage`` — the collector's own proof of continuity.

        Written by the market-worker (the only process that knows whether it
        stayed subscribed and dropped nothing) and read by the scanner to fill
        ``SourceEntry.covered_until``. Deliberately *not* derived from
        ``hb:{role}:{instance}``: that hash reports a live socket next to a
        cumulative drop counter, and a connected socket that lost a trade would
        read as "covered" (T2.5 design review).

        One hash per venue **and market type** (T3.0b), so the ``sym:*`` fields
        inside it stay unambiguous with a plain symbol as their name.
        """
        return f"mkt:{_venue(exchange, market_type)}:coverage"

    @staticmethod
    def scanner_state(exchange: str, symbol: str, market_type: MarketType = _PERP) -> str:
        """``scan:state:{exchange}:{symbol}`` — the scanner's warm checkpoint.

        The ATR anchor and the stage hysteresis of one market. Losable by
        contract (ARCHITECTURE.md §5.3): losing it re-anchors the ATR and costs
        the stage two observations, and the scanner says so in the sample it
        writes rather than pretending the state survived.
        """
        return f"scan:state:{_venue(exchange, market_type)}:{symbol}"

    @staticmethod
    def baseline_projection(exchange: str, symbol: str, market_type: MarketType = _PERP) -> str:
        """``scan:baseline:{exchange}:{symbol}`` — the cached current projection."""
        return f"scan:baseline:{_venue(exchange, market_type)}:{symbol}"

    @staticmethod
    def radar_scores() -> str:
        return "radar:scores"

    @staticmethod
    def regime_current() -> str:
        return "regime:current"

    @staticmethod
    def kill_switch_system() -> str:
        return "ks:system"

    @staticmethod
    def kill_switch_org(org_id: str) -> str:
        return f"ks:org:{org_id}"

    @staticmethod
    def kill_switch_portfolio(portfolio_id: str) -> str:
        return f"ks:pf:{portfolio_id}"

    @staticmethod
    def heartbeat(role: str, instance: str) -> str:
        return f"hb:{role}:{instance}"

    @staticmethod
    def market_heartbeat(
        exchange: str,
        shard_index: int = 0,
        shard_total: int = 1,
        *,
        market_type: MarketType = _PERP,
    ) -> str:
        """The collector's per-exchange heartbeat — one key **per shard**.

        T2.5g: with ``MARKET_SHARD=i/N`` and ``N > 1`` each shard owns
        ``hb:market:{exchange}:{i}of{N}``; the API unions them
        (``hunter_api.services.market_shards``). A single shared
        ``hb:market:{exchange}`` is what kept the 200 already-proven markets
        undelivered in M1: four shards writing one hash makes a dead shard
        invisible. ``N == 1`` keeps the classic key byte for byte.

        T3.0b — **this is the one place where the type goes before the
        exchange** (``hb:market:spot:binance:0of4``), against the layout of
        every ``mkt:`` key. The reason is the ``SCAN`` pattern below: Redis
        globs match ``:`` with ``*``, so ``hb:market:binance:spot:0of4`` would
        be swept up by the perpetual's ``hb:market:binance:*of*``, pass the
        ``{i}of{N}`` suffix check and be counted as a USDS-M shard.
        """
        prefix = f"hb:market:{_venue_prefix(market_type)}{exchange}"
        if shard_total <= 1:
            return prefix
        return f"{prefix}:{shard_index}of{shard_total}"

    @staticmethod
    def market_heartbeat_shard_pattern(exchange: str, market_type: MarketType = _PERP) -> str:
        """``SCAN MATCH`` pattern for every shard key of one exchange. Never
        matches the classic solo key (which has no trailing segment) nor
        ``WorkerRuntime``'s generic ``hb:market:{hostname}:{pid}`` — that one
        lives under ``hb:market:`` too, so a consumer must still validate the
        ``{i}of{N}`` suffix and the hash's own ``shard_index``/``shard_total``
        fields instead of trusting the pattern alone."""
        return f"hb:market:{_venue_prefix(market_type)}{exchange}:*of*"

    @staticmethod
    def rate_limit(exchange: str, bucket: str) -> str:
        return f"rl:{exchange}:{bucket}"

    @staticmethod
    def lock(name: str) -> str:
        return f"lock:{name}"

    @staticmethod
    def processed(consumer: str, day: date) -> str:
        """``hunter:processed:{consumer}:{YYYYMMDD}`` — idempotency SET (consume.py).

        One set per **UTC day**, not one per consumer group. A single key was
        given a fresh TTL on every ``ack``, so it never expired: it grew for the
        lifetime of the deployment, and the only way it could ever have expired
        would have been to drop every event id at once, on an idle stream, which
        is precisely when a redelivery is most likely. A daily key stops being
        written at midnight and then expires on its own, and the guard reads the
        last two of them so the window never has a seam (:mod:`.events.consume`).
        """
        return f"hunter:processed:{consumer}:{day:%Y%m%d}"


@asynccontextmanager
async def acquire_lock(
    client: redis_asyncio.Redis, name: str, ttl_ms: int
) -> AsyncGenerator[bool, None]:
    """A distributed lock via ``SET NX PX``.

    Yields ``True`` if the lock was acquired, ``False`` otherwise — callers
    must check the yielded value; the body still runs either way so callers
    can decide (log and skip, wait, etc.) instead of the lock silently
    swallowing contention. Release is a Lua script that only deletes the key
    if it still holds this holder's token, so a lock that outlived its TTL
    and was re-acquired by someone else is never deleted out from under them.
    """
    token = secrets.token_hex(16)
    key = keys.lock(name)
    acquired = bool(await client.set(key, token, nx=True, px=ttl_ms))
    try:
        yield acquired
    finally:
        if acquired:
            await client.eval(_RELEASE_IF_OWNER_SCRIPT, 1, key, token)
