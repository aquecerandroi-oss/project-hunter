"""One NATS connection of the leader source (H-037): handshake, subscriptions, the millisecond path.

Split from :mod:`leader_source_nats` (which owns the reconnect loop and the credential) for the
file-size budget. :meth:`NatsSession.run` returns only by raising: the loop above decides what the
failure means.

**The millisecond path** (:meth:`NatsSession._on_message`): the frame is stamped the instant ``recv``
returns (``first_seen_at`` on the wall clock, a monotonic stamp for the latency distribution), then parsed
and handed to the queue in the same synchronous step — no await, no HTTP, no batching. The one wait there
is, a buy whose SOL leg has not arrived, is bounded by :data:`PAIR_WAIT_S` and driven by a timer, never by
the next frame.

**Coverage the session itself announces:** a wallet is ``nats_unseeded`` from ready until its balance
snapshot lands (the seed is retried with backoff); a frame that cannot be read, or a message whose
handling failed, is a one-instant ``nats_malformed`` / ``nats_message_error`` gap for that wallet
(a leg of a followed wallet was lost); a refused subscription is ``nats_subscription_refused``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.leader_events import LeaderGap, LeaderItem
from hunter_exchanges.pumpfun.leader_source_gaps import GapTracker, loss_gap
from hunter_exchanges.pumpfun.leader_source_nats_io import (
    OPEN_TIMEOUT_S,
    ConnectFn,
    Seeder,
    WsLike,
    to_bytes,
)
from hunter_exchanges.pumpfun.leader_source_nats_state import (
    PAIR_WAIT_S,
    LegProcessor,
)
from hunter_exchanges.pumpfun.leader_source_nats_wire import (
    BALANCE_SUBJECT,
    NatsAuthError,
    NatsConfig,
    NatsParser,
    classify_err,
    connect_line,
    decode_payload,
    parse_balance_leg,
    refused_for_scale,
)
from hunter_exchanges.pumpfun.leader_source_stats import LeaderSourceStats

logger = get_logger(__name__)

SEED_RETRY_MAX_S = 30.0
SILENCE_S = 60.0
ACTIVE_WINDOW_S = 3600.0
WATCH_INTERVAL_S = 5.0
_RESYNC_REASONS = ("nats_unseeded", "nats_malformed", "nats_message_error")

__all__ = ["NatsSession"]


class NatsSession:
    def __init__(
        self,
        *,
        cfg: NatsConfig,
        followed: frozenset[str],
        queue: asyncio.Queue[LeaderItem],
        gaps: GapTracker,
        proc: LegProcessor,
        stats: LeaderSourceStats,
        connect: ConnectFn,
        seeder: Seeder | None,
        wall: Callable[[], datetime],
        mono: Callable[[], float],
        sleep: Callable[[float], Awaitable[None]],
        idle_s: float,
        ping_s: float,
        silence_s: float = SILENCE_S,
        active_s: float = ACTIVE_WINDOW_S,
        watch_s: float = WATCH_INTERVAL_S,
    ) -> None:
        self.cfg, self.followed, self.queue, self.gaps, self.proc = cfg, followed, queue, gaps, proc
        self.stats, self._connect, self._seeder = stats, connect, seeder
        self._wall, self._mono, self._sleep = wall, mono, sleep
        self._idle_s, self._ping_s = idle_s, ping_s
        self._silence_s, self._active_s, self._watch_s = silence_s, active_s, watch_s
        self._last_leg: dict[str, float] = {}
        self._seeding: dict[str, asyncio.Task[None]] = {}
        self.parser = NatsParser()
        self.ready = False
        self.ready_at: float | None = None
        self.tasks: set[asyncio.Task[None]] = set()
        self.timers: set[asyncio.TimerHandle] = set()
        self._ws: WsLike | None = None

    # ------------------------------------------------------------------ the connection
    async def run(self) -> None:
        async with self._connect(self.cfg.servers) as ws:
            self._ws = ws
            self.parser.push(to_bytes(await asyncio.wait_for(ws.recv(), OPEN_TIMEOUT_S)))  # INFO
            await ws.send(connect_line(self.cfg))
            self.tasks.add(asyncio.create_task(self._heartbeat(ws)))
            self.tasks.add(asyncio.create_task(self._watchdog()))
            try:
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), self._idle_s)
                    except TimeoutError:
                        raise ConnectionError("idle socket") from None
                    t0, seen_at = self._mono(), self._wall()  # first thing after receive
                    ops = self.parser.push(to_bytes(raw))
                    for op in ops:
                        if op.kind == "msg":
                            self._on_message(op.subject, op.payload, t0, seen_at)
                    for op in ops:
                        if op.kind != "msg":
                            await self._on_control(op.kind, op.text)
            finally:
                for handle in self.timers:
                    handle.cancel()
                for task in self.tasks:
                    task.cancel()
                # gather, not a suppressed await: a cancel aimed at THIS task must not be swallowed
                await asyncio.gather(*self.tasks, return_exceptions=True)

    # ------------------------------------------------------------------ the millisecond path
    def _lost(self, subject: str, reason: str, at: datetime) -> None:
        """A leg of a followed wallet was lost, so its baseline can no longer be trusted: reset it and
        keep the wallet degraded (an open gap) until a fresh snapshot lands. Without a seeder there is
        nothing to wait for: an interval gap, and the baseline is relearned from the next leg."""
        parts = subject.split(".")
        wallet = parts[1] if len(parts) >= 3 and parts[1] in self.followed else None
        if wallet is None:
            return
        self.proc.book.forget(wallet)
        self.proc.drop_wallet(wallet)
        if self._seeder is None:
            self.queue.put_nowait(loss_gap(wallet, at, self._wall(), reason))
            return
        self._announce(self.gaps.open(reason, at, wallet=wallet))
        self._start_seed(
            wallet, self._seeder
        )  # restarts any read still in flight: it may predate this

    def _on_message(self, subject: str, payload: bytes, t0: float, seen_at: datetime) -> None:
        body = decode_payload(payload)
        leg = None if body is None else parse_balance_leg(subject, body)
        if leg is None:
            if body is not None and refused_for_scale(subject, body):
                self.stats.count("unsupported_scale")  # another mint's scale: not a pump token
            else:
                self.stats.count("malformed")
                self._lost(subject, "nats_malformed", seen_at)
            return
        if leg.wallet not in self.followed:
            self.stats.count("not_followed")
            return
        self._heard(leg.wallet, t0, seen_at)
        try:
            out = self.proc.on_leg(leg, seen_at=seen_at, now_mono=t0)
        except Exception as exc:  # a bug here must cost one message, not the socket
            self.stats.count("message_error")
            logger.error("leader_nats_message_error", error=type(exc).__name__)
            self._lost(subject, "nats_message_error", seen_at)
            return
        self.stats.count(out.reason)
        for event in out.events:
            self.queue.put_nowait(event)
            self.stats.receive_to_emit.record(self._mono() - t0)
        if out.deadline_mono is not None:
            deadline = out.deadline_mono

            def fire() -> None:
                self.timers.discard(handle)
                self.flush_pairing(deadline)

            handle = asyncio.get_running_loop().call_later(PAIR_WAIT_S, fire)
            self.timers.add(handle)

    def flush_pairing(self, deadline: float) -> None:
        """The pairing wait of some buy is over: emit what is still waiting with the SOL leg unknown."""
        for event in self.proc.expire(now_mono=deadline, now_wall=self._wall()):
            self.queue.put_nowait(event)
            self.stats.count("pair_timeout")

    # ------------------------------------------------------------------ control
    async def _on_control(self, kind: str, text: str) -> None:
        ws = self._ws
        assert ws is not None
        if kind == "ping":
            await ws.send("PONG\r\n")
        elif kind == "pong" and not self.ready:
            self.ready = True
            self.ready_at = self._mono()
            for n, wallet in enumerate(sorted(self.followed), start=1):
                await ws.send(f"SUB {BALANCE_SUBJECT}.{wallet}.* {n}\r\n")
            for closed in self.gaps.close_all(self._wall()):
                self.queue.put_nowait(closed)
            if self._seeder is not None:
                for wallet in sorted(self.followed):
                    self._announce(self.gaps.open("nats_unseeded", self._wall(), wallet=wallet))
                    self._start_seed(wallet, self._seeder)
        elif kind == "err":
            err = classify_err(text)
            if err == "auth":
                raise NatsAuthError("server refused the credential")
            if err in ("permissions", "subscription_limit"):
                named = [w for w in sorted(self.followed) if f"{BALANCE_SUBJECT}.{w}." in text]
                for wallet in named or [None]:  # the server did not say which: all of them
                    reason = "nats_subscription_refused"
                    self._announce(self.gaps.open(reason, self._wall(), wallet=wallet))
            else:
                self.stats.count("nats_err_other")

    def _announce(self, gap: LeaderGap | None) -> None:
        if gap is not None:
            self.queue.put_nowait(gap)

    def _start_seed(self, wallet: str, seeder: Seeder) -> None:
        previous = self._seeding.pop(wallet, None)
        if previous is not None:
            previous.cancel()  # a read that began before the latest loss must not seed the baseline
        task = asyncio.create_task(self._seed(wallet, seeder))
        self._seeding[wallet] = task
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _heard(self, wallet: str, t0: float, seen_at: datetime) -> None:
        """A leg of ``wallet``: the silence (if announced) ends BEFORE the event it brings."""
        self._last_leg[wallet] = t0
        self._announce(self.gaps.close("nats_silent", seen_at, wallet=wallet))

    def check_silence(self, now_mono: float, now_wall: datetime) -> None:
        """Announce a wallet that spoke within the active window but has been silent too long (the
        design's rule: the connection being alive does not prove this wallet's channel is)."""
        for wallet, last in self._last_leg.items():
            quiet = now_mono - last
            if self._silence_s < quiet <= self._active_s:
                start = now_wall - timedelta(seconds=quiet - self._silence_s)
                opened = self.gaps.open("nats_silent", start, wallet=wallet)
                if opened is not None:
                    self._announce(opened)
                    if self._seeder is not None:
                        # a leg may have been lost in the quiet: retake the snapshot NOW, so the first
                        # leg after the silence is compared with a fresh baseline, not a stale one
                        self.proc.book.forget(wallet)
                        self.proc.drop_wallet(wallet)
                        self._start_seed(wallet, self._seeder)

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(self._watch_s)
            self.check_silence(self._mono(), self._wall())

    async def _seed(self, wallet: str, seeder: Seeder) -> None:
        """Snapshot the wallet's balances; retried with backoff until it lands (the gap stays open)."""
        attempt = 0
        while True:
            try:
                snap = await seeder(wallet)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.stats.count("seed_failed")
                logger.warning("leader_nats_seed_failed", error=type(exc).__name__)
                await self._sleep(min(1.0 * 2 ** min(attempt, 30), SEED_RETRY_MAX_S))
                attempt += 1
                continue
            self.proc.book.seed(wallet, snap)
            for reason in _RESYNC_REASONS:
                self._announce(self.gaps.close(reason, self._wall(), wallet=wallet))
            self._seeding.pop(wallet, None)
            return

    async def _heartbeat(self, ws: WsLike) -> None:
        """Client PING: a silent socket must still show traffic (a dead one is ``recv``'s to notice)."""
        while True:
            await asyncio.sleep(self._ping_s)
            with contextlib.suppress(Exception):
                await ws.send("PING\r\n")
