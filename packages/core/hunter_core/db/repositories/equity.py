"""``portfolio_equity_snapshots`` — the equity curve and the day's reference point.

Every point of the curve names the FX observation it was converted with, so the
past is never recomputed with today's rate (M3 joint decision, item 1). The
column is nullable on purpose: with FX unavailable after the opening the USDT
side stays computable and the BRL side becomes *unavailable with a reason*,
never extrapolated — so a point with no observation is a legitimate point, and
this repository writes it rather than refusing.

:data:`REFERENCE_RESOLUTION` is the ledger's own lane on the curve. The table is
``LIST (resolution)`` partitioned so ``1m`` can be pruned at 30 days while ``1h``
is kept for ever (DATABASE.md §1.3); the opening of a permanent wallet and the
daily reference are both things that must still be readable in a year, so they
go in the lane that is never pruned. The intraday cadence of T3.5 is a different
lane and does not collide with these.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from hunter_core.db.models.portfolios import PortfolioEquitySnapshot
from hunter_core.db.repositories.base import TenantRepository
from hunter_core.domain.enums import Timeframe

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal

REFERENCE_RESOLUTION = Timeframe.H1
"""The lane the opening point and the daily reference point live in."""


class EquitySnapshotRepository(TenantRepository):
    """Appends to the curve, and reads the two points the ledger needs back."""

    async def record(
        self,
        *,
        portfolio_id: uuid.UUID,
        ts: datetime,
        cash: Decimal,
        equity: Decimal,
        exposure_notional: Decimal,
        exposure_pct: Decimal | None,
        unrealized_pnl: Decimal,
        realized_pnl_cum: Decimal,
        peak_equity: Decimal,
        drawdown_pct: Decimal | None,
        open_positions: int,
        fx_observation_id: uuid.UUID | None,
        resolution: Timeframe = REFERENCE_RESOLUTION,
    ) -> PortfolioEquitySnapshot:
        """Append one point. The primary key is ``(portfolio, resolution, ts)``,
        so re-recording the same instant in the same lane is a conflict rather
        than a silent second version of the same moment."""
        snapshot = PortfolioEquitySnapshot(
            organization_id=self.organization_id,
            portfolio_id=portfolio_id,
            resolution=resolution,
            ts=ts,
            cash=cash,
            equity=equity,
            exposure_notional=exposure_notional,
            exposure_pct=exposure_pct,
            unrealized_pnl=unrealized_pnl,
            realized_pnl_cum=realized_pnl_cum,
            peak_equity=peak_equity,
            drawdown_pct=drawdown_pct,
            open_positions=open_positions,
            fx_observation_id=fx_observation_id,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def at(
        self,
        *,
        portfolio_id: uuid.UUID,
        ts: datetime,
        resolution: Timeframe = REFERENCE_RESOLUTION,
    ) -> PortfolioEquitySnapshot | None:
        """The point recorded **at exactly** ``ts`` in ``resolution``, or ``None``.

        Exact, never "the latest one at or before": a predecessor proves
        temporal order, not accounting identity. Astra's counter-example (T3.3
        policy review, must-fix 2): the last point of the night carries an
        unrealized of 8 while the reference the day was opened with carries 10;
        selling that position today for its midnight mark then reports a daily
        result of 2 on a patrimony that did not move. When the point bound to
        the reference is absent, the ledger reports the decomposition as
        *unavailable* instead of substituting a neighbour.
        """
        statement = select(PortfolioEquitySnapshot).where(
            PortfolioEquitySnapshot.organization_id == self.organization_id,
            PortfolioEquitySnapshot.portfolio_id == portfolio_id,
            PortfolioEquitySnapshot.resolution == resolution,
            PortfolioEquitySnapshot.ts == ts,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()
