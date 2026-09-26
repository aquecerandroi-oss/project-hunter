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
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Protocol

from hunter_meme_worker.creator_stats import CreatorWatchStats
from hunter_meme_worker.features import CurveObservation
from hunter_meme_worker.identity_breaker import IdentityBreaker

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.models import NormalizedCurveState
    from hunter_exchanges.pumpfun.rpc import CurveBatch, MayhemFlowBatch
    from hunter_exchanges.pumpfun.rpc_wallet import SignatureInfo
    from hunter_exchanges.pumpfun.ws import ConnectionState, MemeEvent
    from hunter_meme_worker.activity import ActivityPuller
    from hunter_meme_worker.boards import BoardCollector
    from hunter_meme_worker.config import MemeConfig
    from hunter_meme_worker.event_gate_runtime import EventGateRuntime
    from hunter_meme_worker.graduation import GlobalParamsStore
    from hunter_meme_worker.launch_lane_runtime import LaunchLaneRuntime
    from hunter_meme_worker.risk import RiskReader
    from hunter_meme_worker.sources import SourcesState
    from hunter_meme_worker.tracker import MintTracker
    from hunter_meme_worker.trades import TradesPuller
    from hunter_meme_worker.wallets_state import WalletsWatcher


class EventSource(Protocol):
    """The PumpPortal client, as the discovery loop needs it."""

    state: ConnectionState

    def stream(self) -> AsyncIterator[MemeEvent]: ...


class CurveSource(Protocol):
    """``frontend-api-v3.pump.fun`` — best effort, 60 requests/60 s, no key."""

    async def get_curve_state(self, mint: str) -> NormalizedCurveState: ...

    async def list_recent(
        self, *, limit: int = 50, sort: str = "created_timestamp", order: str = "DESC"
    ) -> list[NormalizedCurveState]:
        """``GET /coins``: the newest mints, curve and identity together
        (T4.97/R80: the identity sweep's own source, since ``/coins/{mint}``
        stopped answering for any mint on 2026-09-25)."""
        ...


class ChainSource(Protocol):
    """The Solana RPC — the truth, and the scarcest budget of the three."""

    async def get_curve_state(self, mint: str, bonding_curve: str) -> NormalizedCurveState: ...

    async def get_mayhem_flows(self, mints: Sequence[str]) -> MayhemFlowBatch:
        """Four accounts per Mayhem mint, 25 mints per call (T4.2e, ``mayhem.py``)."""
        ...

    async def get_curve_states(
        self, mints: Sequence[str], *, with_block_time: bool = True, commitment: str = "finalized"
    ) -> CurveBatch:
        """The curve of every mint, 100 per call, stamped with the slot's block
        time (T4.2f, ``chain.py``). ``commitment`` defaults to ``finalized``;
        the fast lane (T4.42, ``fast_lane.py``) passes ``confirmed``."""
        ...


class WalletChainSource(Protocol):
    """The Solana RPC as the wallet loop (T4.12) needs it — reads only."""

    async def get_signatures_for_address(
        self, address: str, *, until: str | None = None, limit: int = 100
    ) -> list[SignatureInfo]: ...

    async def get_transaction(self, signature: str) -> dict[str, Any] | None: ...


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

    last_trail_prune_day: date | None = None
    """T4.43: the calendar day (UTC) ``collect.prune_once`` last swept
    ``meme_gate_refusals_by_mint`` — once a day, not every hour like the
    token retention beside it (``lab_trail.should_prune_trail_today``)."""

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
    """Everything a loop is allowed to reach. Built once, in ``main`` — except
    ``event_gate`` (T4.70), wired in once more right after it exists; see
    :func:`attach_event_gate`."""

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
    wallets: WalletsWatcher | None = None
    """The observed wallets (T4.12, ``wallets.py``): ``None`` when
    ``MEME_WATCH_WALLETS`` is empty — no loop, and the readiness body says so."""
    activity: ActivityPuller | None = None
    """The tape by batch (T4.2g, ``activity.py``): ``None`` when
    ``MEME_ACTIVITY_ENABLED`` or the ``swap-api`` itself is off — the folds
    then read only the per-mint tape, and every row without one says why."""
    launch_lane: LaunchLaneRuntime | None = None
    """T4.67a's own runtime: ``None`` when ``MEME_LAUNCH_LANE=off`` — then
    ``discovery.py`` calls nothing extra per create."""
    event_gate: EventGateRuntime | None = None
    """T4.70: wired by :func:`attach_event_gate` **after** construction, not
    passed here like ``launch_lane`` — the event gate needs ``tracker``/
    ``chain`` off this very context (via ``LabContext``) before it can exist,
    so the two cannot be built in the usual order. ``None`` until then, and
    always ``None`` when ``MEME_EVENT_GATE=off``: ``discovery.py`` then calls
    nothing extra per ``create`` either."""
    creator: CreatorWatchStats = field(default_factory=CreatorWatchStats)
    """The creator watch's own gauges and its measured sale → exit latency
    (T4.2h-b, ``creator_stats.py``). Defaulted rather than wired in ``main.py``
    because it holds only counters: whether the loop *runs* is
    ``config.creator_watch_enabled``, which the heartbeat reads at write time —
    so a context built anywhere still reports honestly instead of silently."""
    identity_breaker: IdentityBreaker = field(default_factory=IdentityBreaker)
    """T4.97b/R80: the by-mint identity read's own circuit breaker
    (``identity_breaker.py``) — never ``sources[PUMPFUN_REST]`` itself, whose
    ``consecutive_failures`` the identity sweep's listing successes reset
    every ~20 s. Defaulted like ``creator`` above: a plain counter, not a
    switch, so any context still degrades safely."""


def attach_event_gate(ctx: RadarContext, event_gate: EventGateRuntime | None) -> None:
    """The one-time wiring ``main.py`` performs once the event gate exists
    (T4.70) — ``RadarContext`` is frozen because every *other* field is known
    at construction; this field alone is not, so this function is the
    documented escape hatch instead of a mutable context."""
    object.__setattr__(ctx, "event_gate", event_gate)
