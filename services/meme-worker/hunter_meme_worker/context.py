"""What the loops share: the config, the session factory, the tracked set, the
little mutable state a minute needs and — since T4.2c — the second collector's
pieces (boards, tape, risk, per-source stats).

Kept in its own module so ``discovery.py``, ``collect.py``, ``fold.py`` and the
T4.2c loops can all see it without importing each other, and so the protocols
below are declared once. The protocols are why the loops are testable without a
socket: a fake that answers ``get_curve_state`` is a legitimate ``CurveSource``,
and nothing in the loops asks whether it was the real client.

The T4.2c fields are optional with ``None`` defaults: a context built for the
T4.2 tests, or a deployment with ``MEME_TRENCHES_ENABLED=false``, still folds
every minute — with ``no_holders_reader``/``no_trade_feed`` where the sources
are absent, which is the truth of that deployment and not a crash.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from hunter_meme_worker.features import CurveObservation

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.models import NormalizedCurveState
    from hunter_exchanges.pumpfun.rpc import CurveBatch, MayhemFlowBatch
    from hunter_exchanges.pumpfun.ws import ConnectionState, MemeEvent
    from hunter_meme_worker.boards import BoardCollector
    from hunter_meme_worker.config import MemeConfig
    from hunter_meme_worker.graduation import GlobalParamsStore
    from hunter_meme_worker.risk import RiskReader
    from hunter_meme_worker.sources import SourcesState
    from hunter_meme_worker.tracker import MintTracker
    from hunter_meme_worker.trades import TradesPuller


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

    async def get_mayhem_flows(self, mints: Sequence[str]) -> MayhemFlowBatch:
        """Four accounts per Mayhem mint, 25 mints per call (T4.2e, ``mayhem.py``)."""
        ...

    async def get_curve_states(
        self, mints: Sequence[str], *, with_block_time: bool = True
    ) -> CurveBatch:
        """The curve of every mint, 100 per call, stamped with the slot's block
        time (T4.2f, ``chain.py``)."""
        ...


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
    ``not_polled``, ``unsupported_quote``). Set by whoever failed, read by the
    folder."""

    ws_generation: int = 0
    last_event_at: datetime | None = None
    """Liveness, split in two on purpose (T4.1's acceptance criterion): a connected
    socket with no new tokens is not a dropped socket, so readiness reads
    ``ws_state`` and the *staleness* detail reads this."""

    open_bets: frozenset[str] = frozenset()
    """Mints with an open paper bet, re-read from ``meme_paper_bets`` by the
    poller every cycle — the top of every priority list (poll, tape, risk)."""

    chain_ok_at: datetime | None = None
    """When the chain loop (T4.2f, ``chain.py``) last photographed the whole
    tracked set. While this is fresh the REST poll narrows to what only the
    mirror can teach (``tracker.needs_rest``); when it goes stale — the RPC is
    down, or the loop never ran — the poll falls back to the full plan."""

    def chain_covers(self, now: datetime, *, within_s: float) -> bool:
        return self.chain_ok_at is not None and (now - self.chain_ok_at).total_seconds() <= within_s

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
    sources: SourcesState | None = None
    boards: BoardCollector | None = None
    trades: TradesPuller | None = None
    risk: RiskReader | None = None
    params: GlobalParamsStore | None = None
    """``/global-params`` (T4.2d): the record the fill threshold and the
    denominator of a mid-life standard curve are derived from. ``None`` in a
    context built without it — every curve reading then claims neither."""
