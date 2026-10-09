"""The state of one ``ChainLeaderSource.stream()`` call (H-037): subscriptions, notifications, the
reconnect monitor and the REST recovery. Split from :mod:`leader_source_chain` for the file-size budget;
it takes its collaborators explicitly and touches nothing private of the source.

**Recovery model.** Per wallet an *anchor* (the newest signature seen while the feed was healthy) is the
frozen cut: it does not advance while the feed is degraded (not connected, a reconnect not yet
recovered, or a gap open), so a notification that arrives right after a reconnect cannot hide what the
dead socket missed. Recovery pages ``getSignaturesForAddress`` (newest first, ``before`` the last page's
end, ``until`` the anchor) until the anchor is reached, then processes the signatures oldest first. At
start the same machinery runs once per wallet from an anchor read **before** subscribing, which also
catches a notification the client dropped for a subscription whose id it had not yet registered.
A gap is closed only after a recovery that finished; if it cannot, the gap closes with an extra
``chain_recovery_failed`` gap over the same interval, so the loss stays on record.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from datetime import datetime
from typing import Protocol

from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.leader_events import LeaderItem
from hunter_exchanges.pumpfun.leader_source_chain_derive import ChainRead
from hunter_exchanges.pumpfun.leader_source_gaps import GapTracker, loss_gap
from hunter_exchanges.pumpfun.leader_source_stats import LeaderSourceStats
from hunter_exchanges.pumpfun.rpc_wallet import SignatureInfo
from hunter_exchanges.pumpfun.rpc_ws_models import ConnectionState, LogsNotification, Notification

logger = get_logger(__name__)

RECOVERY_PAGE = 100
RECOVERY_PAGES_MAX = 20
RECOVERY_ATTEMPTS = 5
SEEN_MAX = 4096

ListSignatures = Callable[[str, str | None, int, str | None], Awaitable[Sequence[SignatureInfo]]]
"""``(wallet, until, limit, before)``, newest first; ``until`` exclusive anchor, ``before`` cursor."""
ReadTx = Callable[..., Awaitable[ChainRead]]
_NAMED_LOSS = {
    "not_found": "chain_tx_not_found",
    "rate_limited": "chain_rate_limited",
    "unavailable": "chain_tx_unavailable",
    "logs_unreadable": "chain_logs_unreadable",
    "mint_unresolved": "chain_mint_unresolved",
    "sign_mismatch": "chain_sign_mismatch",
}


class LogsFeed(Protocol):
    """What the source needs of :class:`hunter_exchanges.pumpfun.rpc_ws.SolanaWsClient`."""

    state: ConnectionState

    async def subscribe_logs(self, *, mentions: Sequence[str], commitment: str = ...) -> int: ...
    def listen(self) -> AsyncIterator[Notification]: ...
    async def aclose(self) -> None: ...


class ChainRun:
    def __init__(
        self,
        *,
        followed: frozenset[str],
        feed: LogsFeed,
        read: ReadTx,
        lister: ListSignatures | None,
        stats: LeaderSourceStats,
        wall: Callable[[], datetime],
        sleep: Callable[[float], Awaitable[None]],
        interval_s: float,
        settle_s: float,
    ) -> None:
        self.followed, self.feed, self.read, self.lister = followed, feed, read, lister
        self.stats, self.wall, self.sleep = stats, wall, sleep
        self.interval_s, self.settle_s = interval_s, settle_s
        self.queue: asyncio.Queue[LeaderItem] = asyncio.Queue()
        self.gaps = GapTracker()
        self.wallet_of: dict[int, str] = {}
        self.pending: dict[int, list[LogsNotification]] = {}
        self.seen: OrderedDict[tuple[str, str], None] = OrderedDict()
        self.anchor: dict[str, tuple[int, str]] = {}
        self.inflight: set[asyncio.Task[None]] = set()
        self.ready = asyncio.Event()
        self.seen_reconnects: int = 0
        self.seen_dropped: int = 0
        self.empty: set[str] = set()  # wallets whose history was read and is empty
        self.unknown_cut: set[str] = set()  # wallets whose start cut could not be read
        self.start_failed = False
        opened = self.gaps.open("chain_connect", wall())
        if opened is not None:
            self.queue.put_nowait(opened)

    def degraded(self) -> bool:
        state = self.feed.state
        return (
            self.gaps.is_open()
            or state.ws_state != "connected"
            or state.reconnects != self.seen_reconnects
            or state.dropped != self.seen_dropped
        )

    # -- subscriptions -------------------------------------------------------
    async def setup(self) -> None:
        self.seen_reconnects = self.feed.state.reconnects
        self.seen_dropped = int(self.feed.state.dropped)
        for wallet in sorted(self.followed):
            before, cut_state = await self._newest(wallet)  # BEFORE subscribing: the start cut
            if cut_state == "empty":
                self.empty.add(wallet)
            elif cut_state == "error":
                self.unknown_cut.add(wallet)
            attempt = 0
            while True:
                try:
                    sub = await self.feed.subscribe_logs(mentions=[wallet], commitment="confirmed")
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.stats.count("subscribe_failed")
                    logger.warning("leader_chain_subscribe_failed", error=type(exc).__name__)
                    await self.sleep(min(1.0 * 2 ** min(attempt, 30), 30.0))
                    attempt += 1
            self.wallet_of[sub] = wallet
            for note in self.pending.pop(sub, []):
                self.on_notification(note, wallet)
            if before is not None:
                self.anchor.setdefault(wallet, before)
            if cut_state == "error":
                self.start_failed = True  # no cut: whatever the subscribe missed is unknowable
            elif not await self._recover_wallet(
                wallet
            ):  # also after an EMPTY cut: it is only as old
                self.start_failed = True  # as that read, and a first trade may have landed since
        closed = self.gaps.close_all(self.wall())
        for gap in closed:
            self.queue.put_nowait(gap)
        if self.start_failed and closed:
            self.stats.count("start_recovery_failed")
            start = min(g.start for g in closed)
            self.queue.put_nowait(loss_gap(None, start, self.wall(), "chain_recovery_failed"))
        self.ready.set()

    async def _newest(self, wallet: str) -> tuple[tuple[int, str] | None, str]:
        """``(cut, 'ok')`` | ``(None, 'empty')`` (proven: no history) | ``(None, 'error')``."""
        if self.lister is None:
            return None, "error"
        try:
            newest = await self.lister(wallet, None, 1, None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.stats.count("anchor_failed")
            logger.warning("leader_chain_anchor_failed", error=type(exc).__name__)
            return None, "error"
        if not newest:
            return None, "empty"
        return (newest[0].slot, newest[0].signature), "ok"

    # -- notifications -------------------------------------------------------
    async def listen(self) -> None:
        async for note in self.feed.listen():
            if not isinstance(note, LogsNotification):
                continue
            wallet = self.wallet_of.get(note.subscription_id)
            if wallet is None:  # a notification that beat the subscribe response
                bucket = self.pending.setdefault(note.subscription_id, [])
                if len(bucket) < SEEN_MAX:
                    bucket.append(note)
                continue
            self.on_notification(note, wallet)

    def on_notification(self, note: LogsNotification, wallet: str) -> None:
        if note.err is not None:
            self.stats.count("logs_err")
            return
        if self.seen_before(wallet, note.signature):
            self.stats.count("duplicate")
            return
        current = self.anchor.get(wallet)
        if not self.degraded() and (current is None or note.slot >= current[0]):
            self.anchor[wallet] = (note.slot, note.signature)  # frozen while degraded
        task = asyncio.ensure_future(self.process(wallet, note.signature, note.received_at))
        self.inflight.add(task)
        task.add_done_callback(self.inflight.discard)

    def seen_before(self, wallet: str, signature: str) -> bool:
        key = (wallet, signature)
        if key in self.seen:
            return True
        self.seen[key] = None
        while len(self.seen) > SEEN_MAX:
            self.seen.popitem(last=False)
        return False

    async def process(self, wallet: str, signature: str, first_seen_at: datetime) -> None:
        try:
            read = await self.read(wallet, signature, first_seen_at=first_seen_at)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.stats.count("process_crashed")
            logger.warning("leader_chain_process_crashed", error=type(exc).__name__)
            read = ChainRead((), "unavailable")
        if read.partial:  # real events, but part of the logs was lost: another trade may be hidden
            self.stats.count("logs_partial")  # announced BEFORE the events it qualifies
            self.queue.put_nowait(
                loss_gap(wallet, first_seen_at, self.wall(), "chain_logs_partial")
            )
        for event in read.events:
            self.queue.put_nowait(event)
        if read.events:
            return
        reason = read.reason or "not_a_trade"
        self.stats.count(reason)
        named = _NAMED_LOSS.get(reason)
        if named is None and reason.startswith("refused_"):
            named = f"chain_{reason}"
        if named is not None:  # coverage really lost for this transaction
            self.queue.put_nowait(loss_gap(wallet, first_seen_at, self.wall(), named))

    # -- reconnects ----------------------------------------------------------
    async def monitor(self) -> None:
        await self.ready.wait()
        state = self.feed.state
        last_ok = self.wall()
        while True:
            await asyncio.sleep(self.interval_s)
            healthy = (
                state.ws_state == "connected"
                and state.reconnects == self.seen_reconnects
                and state.dropped == self.seen_dropped
            )
            if healthy and not self.gaps.is_open():
                last_ok = self.wall()
                continue
            opened = self.gaps.open("chain_ws_down", last_ok)
            if opened is not None:
                self.queue.put_nowait(opened)
            if state.ws_state != "connected":
                continue
            await asyncio.sleep(self.settle_s)  # let the client resubscribe
            reconnects: int = state.reconnects
            dropped: int = state.dropped
            recovered = await self.recover_all()
            self.seen_reconnects, self.seen_dropped = reconnects, dropped
            now = self.wall()
            closed = self.gaps.close_all(now)
            for gap in closed:
                self.queue.put_nowait(gap)
            if not recovered and closed:
                start = min(g.start for g in closed)
                self.queue.put_nowait(loss_gap(None, start, now, "chain_recovery_failed"))

    async def recover_all(self) -> bool:
        """Retry the backfill with backoff; ``True`` only when every wallet finished."""
        for attempt in range(RECOVERY_ATTEMPTS):
            results = [await self._recover_wallet(w) for w in sorted(self.followed)]
            if all(results):
                return True
            self.stats.count("recovery_retry")
            await self.sleep(min(1.0 * 2**attempt, 8.0))
        self.stats.count("recovery_failed")
        return False

    async def _recover_wallet(self, wallet: str) -> bool:
        """Page back from the newest to the frozen anchor, then process oldest first."""
        if self.lister is None:
            return False  # nothing to recover with: the loss stays on record
        anchor = self.anchor.get(wallet)
        if anchor is None:
            if wallet in self.unknown_cut:  # the cut was never read: what was missed is unknowable
                cut, _ = await self._newest(wallet)
                if cut is not None:
                    self.anchor[wallet] = cut
                    self.unknown_cut.discard(wallet)
                return False
            if wallet not in self.empty:
                return False
        until = anchor[1] if anchor is not None else None  # an empty cut: anything listed is new
        collected: list[SignatureInfo] = []
        cursor: str | None = None
        try:
            for _ in range(RECOVERY_PAGES_MAX):
                page = await self.lister(wallet, until, RECOVERY_PAGE, cursor)
                collected.extend(page)
                if len(page) < RECOVERY_PAGE:
                    break
                cursor = page[-1].signature
            else:
                self.stats.count("recovery_pages_exhausted")
                return False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("leader_chain_recovery_failed", error=type(exc).__name__)
            return False
        for info in reversed(collected):
            if not info.failed and not self.seen_before(wallet, info.signature):
                await self.process(wallet, info.signature, self.wall())
        if collected:
            self.anchor[wallet] = (collected[0].slot, collected[0].signature)
            self.empty.discard(wallet)
        return True
