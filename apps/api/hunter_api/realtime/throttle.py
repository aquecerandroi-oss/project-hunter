"""Per-channel coalescing so the api never pushes realtime updates to
browsers faster than ARCHITECTURE.md §5.2 allows: 250 ms for prices, 1 s for
radar, immediate (0 ms) for risk events.
"""

from __future__ import annotations

import time

PRICE_INTERVAL_MS = 250
RADAR_INTERVAL_MS = 1000
RISK_INTERVAL_MS = 0

DEFAULT_INTERVALS_MS: dict[str, int] = {
    "prices": PRICE_INTERVAL_MS,
    "radar": RADAR_INTERVAL_MS,
    "risk": RISK_INTERVAL_MS,
}


class Throttle:
    """Coalesces updates per channel: ``should_emit(channel)`` is ``True`` at
    most once per the channel's configured interval; calls in between return
    ``False`` (the caller drops that update in favor of the next one that
    passes — coalescing keeps only the newest value, it never queues).
    """

    def __init__(self, intervals_ms: dict[str, int], *, default_ms: int = 0) -> None:
        self._intervals_ms = intervals_ms
        self._default_ms = default_ms
        self._last_emit: dict[str, float] = {}

    def interval_ms(self, channel: str) -> int:
        return self._intervals_ms.get(channel, self._default_ms)

    def should_emit(self, channel: str, *, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        interval_s = self.interval_ms(channel) / 1000
        last = self._last_emit.get(channel)
        if last is not None and (moment - last) < interval_s:
            return False
        self._last_emit[channel] = moment
        return True
