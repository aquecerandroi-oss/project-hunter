"""Open/close bookkeeping of :class:`LeaderGap` for the leader sources (H-037): a loss of coverage is
announced once when it starts (``end=None``) and once more, with its original ``start``, when it
ends — the lane records both and censors any copy whose entry or exit falls inside."""

from __future__ import annotations

from datetime import datetime, timedelta

from hunter_exchanges.pumpfun.leader_events import LeaderGap

_MIN_LOSS = timedelta(milliseconds=1)


def loss_gap(wallet: str | None, start: datetime, end: datetime, reason: str) -> LeaderGap:
    """A loss that happened at one instant, as an interval a consumer can test (``[start, end)`` must
    be non-empty to cover anything): at least one millisecond long."""
    return LeaderGap(wallet, start, max(end, start + _MIN_LOSS), reason)


class GapTracker:
    def __init__(self) -> None:
        self._open: dict[tuple[str | None, str], datetime] = {}

    def is_open(self) -> bool:
        return bool(self._open)

    def open(self, reason: str, now: datetime, *, wallet: str | None = None) -> LeaderGap | None:
        """The open-ended gap to emit, or ``None`` when this loss is already announced."""
        key = (wallet, reason)
        if key in self._open:
            return None
        self._open[key] = now
        return LeaderGap(wallet, now, None, reason)

    def close(self, reason: str, now: datetime, *, wallet: str | None = None) -> LeaderGap | None:
        """The closed version of one open gap, or ``None`` when it was not open."""
        start = self._open.pop((wallet, reason), None)
        return None if start is None else LeaderGap(wallet, start, max(now, start), reason)

    def close_all(self, now: datetime) -> list[LeaderGap]:
        """The closed versions of every open gap, oldest first."""
        closed: list[LeaderGap] = []
        for (wallet, reason), start in sorted(self._open.items(), key=lambda kv: kv[1]):
            closed.append(LeaderGap(wallet, start, max(now, start), reason))
            del self._open[(wallet, reason)]
        return closed
