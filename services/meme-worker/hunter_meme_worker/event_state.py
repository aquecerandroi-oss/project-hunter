"""The in-memory state of one young mint fed by chain events (T4.52b-2,
``plan-T4.52b.md`` §2) — pure, bounded, no I/O, no clock: every instant is an
argument, every number a ``Decimal``.

One :class:`MintEventState` per subscribed mint holds (a) ``points``: the last
120 s of curve photos — one per ``TradeEvent`` (post-trade reserves),
``accountNotification`` or fast-lane read; (b) ``trades``: the last 60 s of
fills as the tape fold reads them (:class:`TapeTrade`); (c) the creator's flow
since the subscription; (d) ``subscribed_at``, ``last_event_at``, ``slot``;
(e) a monotonic deque of ``real_sol`` (:class:`PeakDeque`) for the peak of
the last 60 s. The bounded dict of them is :mod:`hunter_meme_worker.event_book`.

**Reuse, not reimplementation.** ``tape_minute`` folds the trades with
:func:`hunter_meme_worker.features_tape.tape_for` — the same function, the same
:class:`TapeMinute` — with ``covered_since = subscribed_at``; ``fast_points``
hands the photos to :func:`hunter_indicators.meme.fast.compute_fast`;
``recent_drawdown`` is :func:`hunter_indicators.meme.drawdown.recent_drawdown`.

**Non-anticipation.** Every entry carries ``received_at``; a fold at ``as_of``
earlier than the newest receipt ignores what came later (the tape and the fast
series filter; the creator flow subtracts it; the drawdown falls back from the
O(1) deque to the exact fold over ``points``).

**Fail closed.** Coverage shorter than 60 s is not a minute: ``tape_minute``
answers ``(None, "event_feed_warming")``; a coverage gap (``mark_gap``) moves
``covered_since`` forward and the tape warms again. The creator booleans are
``True`` at the first creator sell seen, ``False`` only when the subscription
covers the mint from within :data:`COVERAGE_GRACE_S` of ``first_seen_at``,
else ``None`` (the plan's event-lane rule; the admission re-reads the ATA).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final

from hunter_exchanges.pumpfun.curve import (
    market_cap_sol,
    raw_lamports_to_sol,
    raw_subunits_to_tokens,
)
from hunter_exchanges.pumpfun.decode import BondingCurveAccount
from hunter_exchanges.pumpfun.models import NormalizedCurveTrade
from hunter_indicators.meme.drawdown import (
    DEFAULT_MAX_GAP_S,
    DEFAULT_WINDOW_S,
    PeakDeque,
    RecentDrawdown,
    ReservePoint,
    recent_drawdown,
)
from hunter_indicators.meme.fast import WINDOW_S, FastPoint
from hunter_meme_worker.features_tape import TapeMinute, TapeTrade, tape_for

__all__ = [
    "COVERAGE_GRACE_S",
    "EVENT_FEED_WARMING",
    "POINTS_WINDOW_S",
    "TAPE_WINDOW_S",
    "CreatorFlow",
    "CurvePoint",
    "MintEventState",
]

EVENT_FEED_WARMING: Final = "event_feed_warming"
"""``tape_reason`` while the coverage is younger than a minute."""
TAPE_WINDOW_S: Final = 60
POINTS_WINDOW_S: Final = WINDOW_S
COVERAGE_GRACE_S: Final = 5
MAX_TRADES: Final = 4000
MAX_POINTS: Final = 4096
"""Hard caps behind the time windows (plan §4: ≤ 2 000 trades/60 s expected);
a trades overflow is a coverage gap, never a silent undercount."""


@dataclass(frozen=True, slots=True)
class CurvePoint:
    """One photo of the curve with its two clocks, from whichever source."""

    observed_at: datetime
    received_at: datetime
    mcap_sol: Decimal | None
    real_sol: Decimal
    real_token: Decimal
    mayhem: bool | None
    slot: int | None = None
    source: str = "trade_event"

    def as_fast_point(self) -> FastPoint:
        return FastPoint(
            observed_at=self.observed_at,
            received_at=self.received_at,
            mcap_sol=self.mcap_sol,
            real_token_reserves=self.real_token,
            real_sol_reserves=self.real_sol,
            mayhem_enabled=self.mayhem,
        )


@dataclass(frozen=True, slots=True)
class CreatorFlow:
    """Σ of the creator's fills seen since ``since`` (lamports, counts)."""

    since: datetime
    bought_lamports: int
    sold_lamports: int
    buys: int
    sells: int
    last_sell_at: datetime | None
    covered_from_birth: bool
    """The subscription began within :data:`COVERAGE_GRACE_S` of
    ``first_seen_at``: a zero here is a zero the feed stated."""

    @property
    def sold_any(self) -> bool | None:
        if self.sells > 0:
            return True
        return False if self.covered_from_birth else None

    @property
    def net_seller(self) -> bool | None:
        """The plan's event-lane rule: ``True`` at the first creator sell."""
        return self.sold_any


@dataclass(slots=True)
class MintEventState:
    """Everything the event gate reads about one mint, bounded in time and size."""

    mint: str
    subscribed_at: datetime
    first_seen_at: datetime | None = None
    total_supply: Decimal | None = None
    creator: str | None = None
    covered_since: datetime = field(init=False)
    last_event_at: datetime | None = None
    slot: int | None = None
    complete: bool | None = None
    mayhem: bool | None = None
    points: deque[CurvePoint] = field(default_factory=lambda: deque[CurvePoint]())
    trades: deque[TapeTrade] = field(default_factory=lambda: deque[TapeTrade]())
    peaks: PeakDeque = field(default_factory=PeakDeque)
    creator_trades: deque[TapeTrade] = field(default_factory=lambda: deque[TapeTrade]())
    """Every creator fill since the subscription — the flow's audit trail,
    bounded by :data:`MAX_TRADES` (a creator rarely fills more than a few times)."""
    gaps: int = 0
    block_time_missing: int = 0

    def __post_init__(self) -> None:
        self.covered_since = self.subscribed_at

    # -- feeding ---------------------------------------------------------

    def apply_trade(self, trade: NormalizedCurveTrade) -> None:
        """One ``TradeEvent`` from ``logsSubscribe``: a tape entry, a photo
        (post-trade reserves), the creator's flow, the peak deque."""
        block_time = trade.block_time
        if block_time is None:
            block_time, self.block_time_missing = trade.received_at, self.block_time_missing + 1
        if self.creator is None:
            self.creator = trade.creator
        self.mayhem = trade.mayhem
        tape = TapeTrade(
            block_time=block_time,
            received_at=trade.received_at,
            trader=trade.trader,
            side=trade.side,
            sol_lamports=int(trade.lamports),
        )
        self._push_trade(tape)
        if tape.trader == self.creator:
            if len(self.creator_trades) >= MAX_TRADES:
                self.creator_trades.popleft()
            self.creator_trades.append(tape)
        self._push_point(
            CurvePoint(
                observed_at=block_time,
                received_at=trade.received_at,
                mcap_sol=self._mcap(trade.virtual_sol_reserves, trade.virtual_token_reserves),
                real_sol=trade.real_sol_reserves,
                real_token=trade.real_token_reserves,
                mayhem=trade.mayhem,
                slot=trade.slot,
            )
        )
        self._seen(trade.received_at, trade.slot)

    def apply_account(
        self,
        account: BondingCurveAccount,
        *,
        slot: int,
        received_at: datetime,
        observed_at: datetime | None = None,
    ) -> None:
        """One ``accountNotification`` decoded by ``decode_bonding_curve_account``:
        the exact state at ``slot``. The notification carries no block time,
        so ``observed_at`` defaults to ``received_at`` (as ``rpc_curves`` does)."""
        self.total_supply = raw_subunits_to_tokens(account.token_total_supply)
        self.creator = self.creator or account.creator
        self.complete = account.complete
        self.mayhem = account.is_mayhem_mode
        virtual_sol = raw_lamports_to_sol(account.virtual_sol_reserves)
        virtual_token = raw_subunits_to_tokens(account.virtual_token_reserves)
        self._push_point(
            CurvePoint(
                observed_at=observed_at or received_at,
                received_at=received_at,
                mcap_sol=self._mcap(virtual_sol, virtual_token),
                real_sol=raw_lamports_to_sol(account.real_sol_reserves),
                real_token=raw_subunits_to_tokens(account.real_token_reserves),
                mayhem=account.is_mayhem_mode,
                slot=slot,
                source="account",
            )
        )
        self._seen(received_at, slot)

    def apply_photo(self, point: CurvePoint) -> None:
        """A fast-lane read (``getMultipleAccounts``) folded into the same series."""
        self._push_point(point)
        self._seen(point.received_at, point.slot)

    def mark_gap(self, at: datetime) -> None:
        """A dropped frame or a reconnect: the windows no longer prove
        coverage — the tape warms again from ``at`` (plan §4)."""
        self.gaps += 1
        self.covered_since = max(self.covered_since, at)
        self.trades.clear()

    # -- reading ---------------------------------------------------------

    def fast_points(self) -> list[FastPoint]:
        """The photos as :func:`compute_fast` reads them (it filters by ``as_of``)."""
        return [p.as_fast_point() for p in self.points]

    def tape_minute(
        self, as_of: datetime, *, warmup_s: int = TAPE_WINDOW_S
    ) -> tuple[TapeMinute | None, str | None]:
        """The last minute of trades at ``as_of`` as :func:`tape_for` folds it,
        or ``(None, event_feed_warming)`` while coverage is shorter than a
        minute. The creator booleans come from the flow since the subscription,
        never from the 60 s deque (a sell that aged out is still a sell)."""
        if as_of - self.covered_since < timedelta(seconds=warmup_s):
            return None, EVENT_FEED_WARMING
        tape = tape_for(
            list(self.trades),
            end_time=as_of,
            creator=self.creator,
            covered_since=self.covered_since,
        )
        if tape is None:
            return None, EVENT_FEED_WARMING
        flow = self.creator_flow(as_of)
        return replace(tape, creator_sold=flow.sold_any, creator_net_seller=flow.net_seller), None

    def creator_flow(self, as_of: datetime | None = None) -> CreatorFlow:
        """Σ of the creator's fills since the subscription that had reached us
        by ``as_of`` (every fill, when ``None``)."""
        mine = [t for t in self.creator_trades if as_of is None or t.received_at <= as_of]
        sells = [t for t in mine if t.side == "sell"]
        buys = [t for t in mine if t.side == "buy"]
        return CreatorFlow(
            since=self.subscribed_at,
            bought_lamports=sum(t.sol_lamports for t in buys),
            sold_lamports=sum(t.sol_lamports for t in sells),
            buys=len(buys),
            sells=len(sells),
            last_sell_at=max((t.block_time for t in sells), default=None),
            covered_from_birth=self.covered_from_birth,
        )

    def recent_drawdown(
        self,
        as_of: datetime,
        *,
        window_s: int = DEFAULT_WINDOW_S,
        max_gap_s: int = DEFAULT_MAX_GAP_S,
    ) -> RecentDrawdown:
        """EXP-M13's guard over the real SOL: O(1) amortized at the instant of
        the newest event, the exact fold over ``points`` for an earlier ``as_of``."""
        received_by = self.peaks.received_by
        if received_by is None or received_by <= as_of:
            return recent_drawdown(self.peaks, as_of=as_of, window_s=window_s, max_gap_s=max_gap_s)
        history = [ReservePoint(p.observed_at, p.received_at, p.real_sol) for p in self.points]
        return recent_drawdown(history, as_of=as_of, window_s=window_s, max_gap_s=max_gap_s)

    @property
    def covered_from_birth(self) -> bool:
        if self.first_seen_at is None:
            return False
        return self.covered_since <= self.first_seen_at + timedelta(seconds=COVERAGE_GRACE_S)

    @property
    def newest_point(self) -> CurvePoint | None:
        return self.points[-1] if self.points else None

    # -- internals -------------------------------------------------------

    def _mcap(self, virtual_sol: Decimal, virtual_token: Decimal) -> Decimal | None:
        if self.total_supply is None or virtual_token <= 0:
            return None
        return market_cap_sol(virtual_sol, virtual_token, self.total_supply)

    def _seen(self, received_at: datetime, slot: int | None) -> None:
        if self.last_event_at is None or received_at > self.last_event_at:
            self.last_event_at = received_at
        if slot is not None:
            self.slot = slot if self.slot is None else max(self.slot, slot)

    def _horizon(self, received_at: datetime, window_s: int) -> datetime:
        newest = received_at if self.last_event_at is None else max(received_at, self.last_event_at)
        return newest - timedelta(seconds=window_s)

    def _push_trade(self, trade: TapeTrade) -> None:
        if len(self.trades) >= MAX_TRADES:
            self.mark_gap(trade.received_at)
        self.trades.append(trade)
        horizon = self._horizon(trade.received_at, TAPE_WINDOW_S)
        while self.trades and self.trades[0].block_time <= horizon:
            self.trades.popleft()

    def _push_point(self, point: CurvePoint) -> None:
        if len(self.points) >= MAX_POINTS:
            self.points.popleft()
        self.points.append(point)
        self.peaks.push(ReservePoint(point.observed_at, point.received_at, point.real_sol))
        horizon = self._horizon(point.received_at, POINTS_WINDOW_S)
        while self.points and self.points[0].observed_at <= horizon:
            self.points.popleft()
        self.peaks.expire(horizon)  # bounded like ``points``: a window ≤ 120 s is exact
