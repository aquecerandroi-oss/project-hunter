"""The bounded dict of :class:`~hunter_meme_worker.event_state.MintEventState`
(T4.52b-2, ``MEME_EVENT_GATE_MAX_MINTS``): pure, no clock — every instant is
an argument. Over the cap ``touch`` refuses and counts (``refused``); the
caller decides what to drop, nothing is evicted behind its back.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from hunter_meme_worker.event_state import MintEventState

__all__ = ["EventBook"]


class EventBook:
    __slots__ = ("_states", "max_mints", "refused")

    def __init__(self, *, max_mints: int) -> None:
        if max_mints <= 0:
            raise ValueError("max_mints must be positive")
        self.max_mints = max_mints
        self.refused = 0
        self._states: dict[str, MintEventState] = {}

    def __len__(self) -> int:
        return len(self._states)

    def __contains__(self, mint: str) -> bool:
        return mint in self._states

    def get(self, mint: str) -> MintEventState | None:
        return self._states.get(mint)

    def mints(self) -> list[str]:
        return list(self._states)

    def touch(
        self,
        mint: str,
        *,
        at: datetime,
        first_seen_at: datetime | None = None,
        total_supply: Decimal | None = None,
    ) -> MintEventState | None:
        """The state of ``mint``, created (subscribed) at ``at`` when absent;
        ``None`` when the book is full — counted in ``refused``."""
        state = self._states.get(mint)
        if state is not None:
            return state
        if len(self._states) >= self.max_mints:
            self.refused += 1
            return None
        state = MintEventState(
            mint=mint, subscribed_at=at, first_seen_at=first_seen_at, total_supply=total_supply
        )
        self._states[mint] = state
        return state

    def evict(self, mint: str) -> MintEventState | None:
        return self._states.pop(mint, None)

    def evict_older_than(self, *, at: datetime, max_idle_s: int) -> list[str]:
        """Drop every mint whose last event (or, without one, its subscription)
        is older than ``max_idle_s`` at ``at``; returns the mints dropped."""
        horizon = at - timedelta(seconds=max_idle_s)
        stale = [
            mint
            for mint, state in self._states.items()
            if (state.last_event_at or state.subscribed_at) < horizon
        ]
        for mint in stale:
            del self._states[mint]
        return stale
