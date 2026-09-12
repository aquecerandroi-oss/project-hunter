"""What the four loops share: the config, the session factory, the tracked set and
the little mutable state a minute needs.

Kept in its own module so ``discovery.py`` and ``collect.py`` can both see it
without importing each other, and so the protocols below are declared once. The
protocols are why the loops are testable without a socket: a fake that answers
``get_curve_state`` is a legitimate ``CurveSource``, and nothing in the loops asks
whether it was the real client.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from hunter_meme_worker.features import CurveObservation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.models import NormalizedCurveState
    from hunter_exchanges.pumpfun.ws import ConnectionState, MemeEvent
    from hunter_meme_worker.config import MemeConfig
    from hunter_meme_worker.tracker import MintTracker


class EventSource(Protocol):
    """The PumpPortal client, as the discovery loop needs it."""

    state: ConnectionState

    def stream(self) -> AsyncIterator[MemeEvent]: ...


class CurveSource(Protocol):
    """``frontend-api-v3.pump.fun`` — best effort, 60 requests/60 s, no key."""

    async def get_curve_state(self, mint: str) -> NormalizedCurveState: ...


class ChainSource(Protocol):
    """The Solana RPC — the truth, and the scarcest budget of the three."""

    async def get_curve_state(self, mint: str, bonding_curve: str) -> NormalizedCurveState: ...


@dataclass
class RadarState:
    """The only mutable state, and every field is there because a restart or a
    minute boundary needs it."""

    last_folded_minute: datetime | None = None
    """The last minute end the folder wrote. ``None`` on start: the first boundary
    the process sees is the first minute it folds, and the minutes before it are
    honestly absent rather than back-filled from nothing."""

    observations: dict[str, CurveObservation] = field(default_factory=dict[str, CurveObservation])
    """The newest curve observation of the *current* minute, per mint. Drained by
    the folder at the boundary; a mint absent from it is a mint the minute has no
    observation for, which becomes a NULL with a reason and never a zero."""

    absences: dict[str, str] = field(default_factory=dict[str, str])
    """Per-mint reason for a missing observation this minute (``rate_limited``,
    ``not_polled``). Set by whoever failed, read by the folder."""

    ws_generation: int = 0
    last_event_at: datetime | None = None
    """Liveness, split in two on purpose (T4.1's acceptance criterion): a connected
    socket with no new tokens is not a dropped socket, so readiness reads
    ``ws_state`` and the *staleness* detail reads this."""

    def observe(self, mint: str, observation: CurveObservation) -> None:
        current = self.observations.get(mint)
        if current is None or observation.observed_at >= current.observed_at:
            self.observations[mint] = observation
        self.absences.pop(mint, None)

    def drain(self) -> tuple[dict[str, CurveObservation], dict[str, str]]:
        observations, absences = self.observations, self.absences
        self.observations, self.absences = {}, {}
        return observations, absences


@dataclass(frozen=True, slots=True)
class RadarContext:
    """Everything a loop is allowed to reach. Built once, in ``main``."""

    config: MemeConfig
    session_factory: async_sessionmaker[AsyncSession]
    tracker: MintTracker
    state: RadarState
    events: EventSource
    curves: CurveSource
    chain: ChainSource
