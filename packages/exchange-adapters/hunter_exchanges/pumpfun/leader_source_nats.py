"""Production :class:`LeaderSource` over pump.fun's anonymous NATS (H-037; KB-0186; decision 2026-10-06).

One persistent connection to the site's ``CORE`` instance, exactly like the anonymous site: the
credential comes from the public home page props at run time, is kept **in memory only** (reused by the
next reconnects for :data:`CONFIG_TTL_S` so a reconnect is fast, re-read at once if the server refuses
it, i.e. on rotation) and is never stored, logged or put in an exception message. Subject
``account_balance_change.<wallet>.*`` per followed wallet, nothing wider. The session itself (handshake,
the millisecond path, seeding) is :mod:`leader_source_nats_session`; the legs-to-event rules are
:mod:`leader_source_nats_state`. The previews are ``confirmed=False`` / ``source="nats"``; confirming
them against the chain is the combinator's asynchronous job (:mod:`leader_source`).

**Never silent.** Every loss of coverage is a :class:`LeaderGap`: ``nats_connect`` until the first ready,
``nats_disconnect`` on a dropped or idle socket, ``nats_auth`` when the page no longer carries the
credential or the server refuses a fresh one, ``nats_refused_<status>`` on 401/403/418/429 (60..600 s
backoff and a ``system_event`` log, never a retry loop), and the per-wallet gaps of the session. A gap is
announced open, then again closed with its original start when the socket is ready. Baselines are
dropped on every reconnect: legs may have been missed, so a delta against the old balance would be a lie.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Collection
from datetime import datetime

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.leader_events import LeaderItem
from hunter_exchanges.pumpfun.leader_source_gaps import GapTracker
from hunter_exchanges.pumpfun.leader_source_nats_io import (
    ConnectFn,
    FetchConfig,
    Seeder,
    WalletSnapshot,
    default_connect,
    default_fetch_config,
    is_refusal,
)
from hunter_exchanges.pumpfun.leader_source_nats_session import (
    ACTIVE_WINDOW_S,
    SEED_MIN_INTERVAL_S,
    SILENCE_S,
    WATCH_INTERVAL_S,
    NatsSession,
    SeedPolicy,
)
from hunter_exchanges.pumpfun.leader_source_nats_state import BalanceBook, LegProcessor
from hunter_exchanges.pumpfun.leader_source_nats_wire import (
    NatsAuthError,
    NatsConfig,
    NatsProtocolError,
    NatsRefused,
)
from hunter_exchanges.pumpfun.leader_source_queue import QUEUE_MAX, OverflowQueue
from hunter_exchanges.pumpfun.leader_source_stats import LeaderSourceStats
from hunter_exchanges.pumpfun.leader_source_wallets import validate_wallets

logger = get_logger(__name__)

RECONNECT_BASE_S = 0.1
RECONNECT_MAX_S = 30.0
AUTH_BASE_S, AUTH_MAX_S = 5.0, 60.0
REFUSED_BASE_S, REFUSED_MAX_S = 60.0, 600.0
MAX_STRIKES = 3
"""Consecutive refusals of a FRESH credential after which the NATS side stops (decision 06/10: stop at the
first block, never evade). The chain fallback keeps covering the wallets."""
STOP_COOLDOWN_S = 3600.0
IDLE_TIMEOUT_S = 60.0
PING_INTERVAL_S = 20.0
STABLE_S = 30.0
"""A session must stay ready this long before the failure counters reset: a server that accepts and
drops at once must not make the reconnect loop (and the home-page fetch) run at the fast base delay."""
CONFIG_TTL_S = 600.0
"""How long the credential read from the home page is reused in memory by the next reconnects: the page
fetch alone took ~3.6 s on 09/10 (a reconnect must be fast), and the site's own client keeps its credential
for the life of the page. A refusal re-reads the page at once; nothing is ever written anywhere."""

__all__ = ["NatsLeaderSource", "WalletSnapshot", "default_connect", "default_fetch_config"]


class NatsLeaderSource:
    def __init__(
        self,
        *,
        fetch_config: FetchConfig = default_fetch_config,
        connect: ConnectFn = default_connect,
        seeder: Seeder | None = None,
        stats: LeaderSourceStats | None = None,
        wall: Callable[[], datetime] = utcnow,
        mono: Callable[[], float] = time.perf_counter,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
        idle_timeout_s: float = IDLE_TIMEOUT_S,
        ping_interval_s: float = PING_INTERVAL_S,
        silence_s: float = SILENCE_S,
        active_s: float = ACTIVE_WINDOW_S,
        watch_interval_s: float = WATCH_INTERVAL_S,
        seed_min_interval_s: float = SEED_MIN_INTERVAL_S,
    ) -> None:
        self._fetch, self._connect, self._seeder = fetch_config, connect, seeder
        self.stats = stats or LeaderSourceStats()
        self._wall, self._mono, self._sleep, self._rand = wall, mono, sleep, rand
        self._idle_s, self._ping_s = idle_timeout_s, ping_interval_s
        self._silence = (silence_s, active_s, watch_interval_s)
        self._seed_policy = SeedPolicy(seed_min_interval_s)  # survives reconnects
        self._strikes = 0  # consecutive refusals of a FRESH credential
        self._cfg: NatsConfig | None = None  # memory only, never persisted or logged
        self._cfg_at = 0.0

    # ------------------------------------------------------------------ stream
    async def stream(self, wallets: Collection[str]) -> AsyncIterator[LeaderItem]:
        followed = validate_wallets(wallets)  # fail closed: only real keys reach a SUB line
        queue = OverflowQueue("nats_queue", cap=QUEUE_MAX, wall=self._wall)
        runner = asyncio.create_task(self._run(followed, queue))
        try:
            while True:
                yield await queue.get()
        finally:
            runner.cancel()
            await asyncio.gather(runner, return_exceptions=True)

    # ------------------------------------------------------------------ reconnect loop
    def delay_for(self, base: float, cap: float, n: int) -> float:
        """Exponential from ``base``, capped. Below the ceiling the jitter goes UP by up to 25 % (the first
        refusal really waits at least ``base``); at the ceiling it goes DOWN by up to 25 %, so persistent
        reconnects do not synchronise and ``cap`` stays a real ceiling."""
        capped = min(cap, base * 2 ** min(n, 30))
        if (
            capped >= cap
        ):  # at the ceiling the jitter goes down: persistent reconnects do not synchronise
            return cap * (1.0 - 0.25 * self._rand())
        return min(cap, capped * (1.0 + 0.25 * self._rand()))

    async def _config(self) -> tuple[NatsConfig, bool]:
        """The credential and whether it was reused from memory."""
        if self._cfg is not None and self._mono() - self._cfg_at < CONFIG_TTL_S:
            return self._cfg, True
        cfg = await self._fetch()
        self._cfg, self._cfg_at = cfg, self._mono()
        return cfg, False

    async def _run(self, followed: frozenset[str], queue: asyncio.Queue[LeaderItem]) -> None:
        gaps = GapTracker()
        proc = LegProcessor(BalanceBook())
        first = gaps.open("nats_connect", self._wall())
        if first is not None:
            queue.put_nowait(first)
        failures = {"plain": 0, "auth": 0, "refused": 0}
        while True:
            kind, reason, reused = "plain", "nats_disconnect", False
            retry_after: float | None = None
            session: NatsSession | None = None
            try:
                cfg, reused = await self._config()
                session = NatsSession(
                    cfg=cfg,
                    followed=followed,
                    queue=queue,
                    gaps=gaps,
                    proc=proc,
                    stats=self.stats,
                    connect=self._connect,
                    seeder=self._seeder,
                    wall=self._wall,
                    mono=self._mono,
                    sleep=self._sleep,
                    idle_s=self._idle_s,
                    ping_s=self._ping_s,
                    silence_s=self._silence[0],
                    active_s=self._silence[1],
                    watch_s=self._silence[2],
                    seed_policy=self._seed_policy,
                )
                await session.run()
            except asyncio.CancelledError:
                raise
            except NatsAuthError:
                kind, reason = "auth", "nats_auth"
                self._cfg = None  # rotated or revoked: the next attempt re-reads the page
            except NatsRefused as exc:
                kind, reason, retry_after = (
                    "refused",
                    f"nats_refused_{exc.status}",
                    exc.retry_after_s,
                )
            except NatsProtocolError:
                reason = "nats_protocol_error"  # a hostile or broken server: drop it, name it
                self.stats.count("protocol_errors")
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if is_refusal(status):
                    kind, reason = "refused", f"nats_refused_{status}"
                else:  # the class only: transport messages are free text we do not trust
                    self.stats.count("disconnects")
                    logger.warning("leader_nats_disconnect", error=type(exc).__name__)
            if session is not None and self._stable(session):
                failures = dict.fromkeys(failures, 0)
                self._strikes = 0
            for wallet in followed:
                proc.book.forget(wallet)
            proc.reset()
            gap = gaps.open(reason, self._wall())
            if gap is not None:
                queue.put_nowait(gap)
            if kind == "refused":
                logger.warning("system_event", kind="leader_nats_refused", reason=reason)
            if kind == "auth" and reused:
                kind = (
                    "plain"  # a reused credential was refused: rotation is normal, re-read at once
                )
                failures["plain"] = 0
            fresh_refusal = kind == "refused" or (kind == "auth" and not reused)
            self._strikes = self._strikes + 1 if fresh_refusal else self._strikes
            if self._strikes >= MAX_STRIKES:
                await self._stop_for_a_while(gaps, queue, retry_after)
                failures = dict.fromkeys(failures, 0)
                continue
            delay = self._backoff(kind, failures)
            if retry_after is not None:
                delay = max(delay, retry_after)  # the page asked for more: give it
            await self._sleep(delay)

    async def _stop_for_a_while(
        self, gaps: GapTracker, queue: asyncio.Queue[LeaderItem], retry_after: float | None
    ) -> None:
        """Too many refusals in a row: stop the NATS side for an hour, say so, and leave the chain
        fallback to cover the wallets (the combinator reports ``no_coverage`` if it cannot)."""
        self.stats.count("nats_stopped")
        logger.warning(
            "system_event",
            kind="leader_nats_stopped",
            strikes=self._strikes,
            cool_s=STOP_COOLDOWN_S,
        )
        gap = gaps.open("nats_stopped", self._wall())
        if gap is not None:
            queue.put_nowait(gap)
        self._strikes = 0
        self._cfg = None
        await self._sleep(
            max(STOP_COOLDOWN_S, retry_after or 0.0)
        )  # never before the server's deadline

    def _stable(self, session: NatsSession) -> bool:
        return session.ready_at is not None and self._mono() - session.ready_at >= STABLE_S

    def _backoff(self, kind: str, failures: dict[str, int]) -> float:
        n = failures[kind]
        failures[kind] += 1
        for other in failures:
            if other != kind:
                failures[other] = 0
        if kind == "auth":
            return self.delay_for(AUTH_BASE_S, AUTH_MAX_S, n)
        if kind == "refused":
            return self.delay_for(REFUSED_BASE_S, REFUSED_MAX_S, n)
        return self.delay_for(RECONNECT_BASE_S, RECONNECT_MAX_S, n)
