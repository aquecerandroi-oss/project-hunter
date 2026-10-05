"""Reading a ``logsSubscribe`` notification without going blind (T4.8e).

A notification with no ``TradeEvent`` (a non-trade instruction on the same PDA) is normal. A
``TradeEvent`` the decoder cannot read is **lost data**: the pump program's redeploy of
2026-10-02 made every real one undecodable, and ``trade_events_from_logs`` swallowed them — the
event gate, the launch lane and the exits kept judging mints off account notifications while
every trade, creator sell and early buyer vanished from the tape, with no gap and no counter.

:func:`logs_trades` yields the decoded trades and, once they are consumed, marks the mint's
coverage gap (``MintEventState.mark_gap``: the windows warm again, every reading that needs the
tape answers "unknown" — fail closed), counts the loss in a :class:`LostTrades` and logs it
(rate-limited; the counter stays exact). The gap is marked **after** the trades of the same
notification are applied, so the readable ones do not outlive it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.trade_event import normalized_curve_trade, scan_trade_event_logs

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hunter_exchanges.pumpfun.models import NormalizedCurveTrade
    from hunter_exchanges.pumpfun.rpc_ws_models import LogsNotification
    from hunter_exchanges.pumpfun.trade_event import TradeLogScan
    from hunter_meme_worker.event_state import MintEventState

__all__ = ["LostTrades", "logs_trades"]

logger = get_logger(__name__)

WINDOW_S = 60
LOG_INTERVAL_S = 30
"""Minimum gap between two ``meme_trade_event_undecodable`` log lines — the counters still
count every loss."""


@dataclass(slots=True)
class LostTrades:
    """Trades the chain emitted and this lane could not read — one object per lane."""

    trades_total: int = 0
    """``TradeEvent``-shaped log lines that failed to decode, since boot."""
    notifications_total: int = 0
    """Notifications that carried at least one of them."""
    window: deque[datetime] = field(default_factory=lambda: deque[datetime]())
    """Receipt instants of the lost trades, for the 60 s rate."""
    last_error: str = ""
    _last_logged_at: datetime | None = field(default=None, repr=False)

    def record(self, now: datetime, scan: TradeLogScan) -> bool:
        """Counts the loss; returns whether *this one* should be logged."""
        count = len(scan.undecodable)
        self.trades_total += count
        self.notifications_total += 1
        self.window.extend([now] * count)
        self.last_error = scan.undecodable[-1] if scan.undecodable else self.last_error
        last = self._last_logged_at
        if last is not None and (now - last).total_seconds() < LOG_INTERVAL_S:
            return False
        self._last_logged_at = now
        return True

    def heartbeat_fields(self, now: datetime) -> dict[str, str]:
        """Without the lane's own prefix. An empty ``last_undecodable_error`` is "none seen"."""
        horizon = now - timedelta(seconds=WINDOW_S)
        while self.window and self.window[0] < horizon:
            self.window.popleft()
        return {
            "undecodable_trades_total": str(self.trades_total),
            "undecodable_notifications_total": str(self.notifications_total),
            "undecodable_trades_60s": str(len(self.window)),
            "last_undecodable_error": self.last_error,
        }


def logs_trades(
    lost: LostTrades, state: MintEventState, notif: LogsNotification, *, lane: str, mint: str
) -> Iterator[NormalizedCurveTrade]:
    """The trades of one notification; on exhaustion, the gap and the count of any that were lost.

    The caller must iterate it to the end (a ``for`` loop does): the gap is the code after
    the last ``yield``."""
    scan = scan_trade_event_logs(notif.logs)
    for event in scan.events:
        yield normalized_curve_trade(
            event, slot=notif.slot, signature=notif.signature, received_at=notif.received_at
        )
    if not scan.lost:
        return
    state.mark_gap(notif.received_at)
    if lost.record(notif.received_at, scan):
        logger.warning(
            "meme_trade_event_undecodable",
            lane=lane,
            mint=mint,
            slot=notif.slot,
            signature=notif.signature,
            lost=len(scan.undecodable),
            decoded=len(scan.events),
            error=scan.undecodable[-1],
            total=lost.trades_total,
        )
