"""Whether one shadow signal may become a proposal — and, when not, *why*.

The whole point of this module is that "no" is never silent. Every signal that
does not become a candidate leaves a named reason behind, logged with the signal
id and counted in ``hunter_bridge_candidates_total{outcome}``: a bridge that
admits nothing because the beta job is down and a bridge that admits nothing
because nobody is emitting signals are the same silence otherwise.

There is no table for the refusals. Creating one would mean a migration, which
this task may not write, and the reason of a refusal is a *fact about an
instant*, not durable state the wallet depends on — so it lives in the
structured log and the counter (T3.14 item 2 allows either).

Order matters. The cheapest and most categorical refusals come first — a
``research_only`` signal or an inactive version is refused **at the door**,
before any market data is read (item 5) — and only then the ones that need the
reference tables.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.domain.enums import TradeDirection
from hunter_core.logging import get_logger
from hunter_core.strategies.envelope import AssumedCosts
from hunter_execution_worker.bridge_repo import ENTRY_WINDOW, ShadowSignal
from hunter_execution_worker.bridge_universe import (
    SPOT_VOLUME_FLOOR_USDT,
    SpotPair,
    coin_commitment,
    current_beta,
    radar_score,
    spot_pair_for,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_execution_worker.wallet import WalletRef
    from hunter_risk.inputs import BetaEstimate

__all__ = ["PURPOSE_LIVE", "Screened", "screen_signal"]

logger = get_logger(__name__)

PURPOSE_LIVE = "live"
"""The only purpose that reaches the wallet, named here as well as in
``hunter_core.admission.sources`` so a new label upstream fails closed."""


@dataclass(frozen=True, slots=True)
class Screened:
    """One screened signal: a candidate, or a refusal with its reason.

    The geometry is read back off the signal rather than copied: an eligible
    candidate is exactly one whose frozen levels were already validated by
    :func:`_geometry_reason`, so there is no second copy of the numbers that
    decide money to keep in step with the first.
    """

    signal: ShadowSignal
    refused: str | None = None
    spot: SpotPair | None = None
    beta: BetaEstimate | None = None
    score: Decimal | None = None
    agent_id: uuid.UUID | None = None

    @property
    def signal_id(self) -> uuid.UUID:
        return self.signal.signal_id

    @property
    def eligible(self) -> bool:
        return self.refused is None

    @property
    def spot_market_id(self) -> uuid.UUID | None:
        return None if self.spot is None else self.spot.market_id

    @property
    def entry_ref(self) -> Decimal | None:
        return self.signal.entry_ref

    @property
    def stop(self) -> Decimal | None:
        return self.signal.stop

    @property
    def target(self) -> Decimal | None:
        return self.signal.target

    @property
    def assumed_costs(self) -> AssumedCosts | None:
        return self.signal.assumed_costs


def _refuse(signal: ShadowSignal, reason: str, **extra: object) -> Screened:
    logger.info(
        "bridge_candidate_refused",
        signal_id=str(signal.signal_id),
        market_id=str(signal.perp_market_id),
        reason=reason,
        **extra,
    )
    return Screened(signal=signal, refused=reason)


def _geometry_reason(signal: ShadowSignal) -> str | None:
    """What is missing or malformed in the frozen levels, if anything."""
    if signal.entry_ref is None or signal.stop is None:
        return "geometry_unavailable"
    if signal.assumed_costs is None:
        return "assumed_costs_unavailable"
    if signal.direction is not TradeDirection.LONG:
        # Spot, long-only in M3. A short would need a borrow the wallet does not
        # have, so it is refused by name rather than sized to zero.
        return "direction_unsupported"
    if signal.stop >= signal.entry_ref:
        return "stop_geometry"
    return None


async def _agent_for(
    session: AsyncSession, *, wallet: WalletRef, strategy_version_id: uuid.UUID
) -> uuid.UUID | None:
    """The enabled agent running this version inside this wallet.

    ``admission.sources`` refuses an ``agent`` proposal that does not name its
    agent, and rightly: the origin says *which path* admitted the entry, the
    agent says *who asked*, and an audited decision about capital needs both. So
    the bridge does not invent one — a version with no enabled agent in this
    wallet is a version this wallet did not authorise, and the signal is refused
    with ``agent_unavailable``.
    """
    return await session.scalar(
        text(
            "SELECT id FROM agents WHERE organization_id = :org AND portfolio_id = :pf "
            "AND strategy_version_id = :version AND status = 'enabled' AND deleted_at IS NULL "
            "ORDER BY created_at LIMIT 1"
        ),
        {"org": wallet.organization_id, "pf": wallet.portfolio_id, "version": strategy_version_id},
    )


async def screen_signal(
    session: AsyncSession, *, wallet: WalletRef, signal: ShadowSignal, now: datetime
) -> Screened:
    """Apply the whole eligibility of T3.14 item 2 to one signal."""
    if signal.purpose != PURPOSE_LIVE:
        return _refuse(signal, "research_only", purpose=signal.purpose)
    if not signal.version_active:
        return _refuse(signal, "version_inactive")
    closes_at = signal.window_closes_at()
    if closes_at is None:
        return _refuse(signal, "source_bar_unavailable")
    if now > closes_at:
        return _refuse(
            signal,
            "entry_window_closed",
            window_s=int(ENTRY_WINDOW.total_seconds()),
            source_bar_close=signal.source_bar_close.isoformat() if signal.source_bar_close else "",
        )
    malformed = _geometry_reason(signal)
    if malformed is not None:
        return _refuse(signal, malformed)

    spot = await spot_pair_for(session, signal)
    if spot is None:
        return _refuse(signal, "spot_pair_unavailable")
    if not spot.is_monitored:
        return _refuse(signal, "spot_not_monitored", spot=spot.symbol)
    if spot.volume_24h_usd is None:
        return _refuse(signal, "spot_volume_unavailable", spot=spot.symbol)
    if spot.volume_24h_usd < SPOT_VOLUME_FLOOR_USDT:
        return _refuse(signal, "spot_volume_below_floor", spot=spot.symbol)

    beta = await current_beta(session, market_id=spot.market_id, now=now)
    if beta is None:
        return _refuse(signal, "beta_unavailable", spot=spot.symbol)

    committed = await coin_commitment(session, wallet=wallet, base_asset_id=spot.base_asset_id)
    if committed is not None:
        return _refuse(signal, "duplicate_position", held_by=committed.kind)

    agent_id = await _agent_for(
        session, wallet=wallet, strategy_version_id=signal.strategy_version_id
    )
    if agent_id is None:
        return _refuse(signal, "agent_unavailable")

    score = await radar_score(
        session, market_id=signal.perp_market_id, at=signal.source_bar_close or now
    )
    return Screened(signal=signal, spot=spot, beta=beta, score=score, agent_id=agent_id)
