"""``GET /api/v1/orgs/{org_id}/lab/daily-goal`` reads — brief T3.78.

Two kinds of read, on purpose, inside one org-scoped transaction:

- **Global, no-RLS reads** of the Shadow Lab tables (``strategy_versions``,
  ``agent_signals``, ``signal_outcomes``, ``candles``) — same as every other
  Lab repository (DATABASE.md §16). Research is shared across the product.
- **One tenant read**, under RLS: the organization's principal paper wallet
  (DATABASE.md §18.5, ``PortfolioRepository.principal_paper_id``), because
  "how far from R$9.000" is a question about *this org's* real (paper)
  capital, not a property of the research alone.

**Read-only, no lock.** ``hunter_core.portfolio.state.build_portfolio_state``
takes ``SELECT ... FOR UPDATE`` on ``portfolio_risk_state`` (the seam every
mutating path serialises on) — wrong for a GET. Equity here comes from the
latest ``portfolio_equity_snapshots`` row at or before ``as_of`` (plain
indexed read), falling back to the wallet's immutable opening anchor
(``portfolio_currency_anchor.credited_amount``) when no snapshot exists yet.

**Indexed access, per active version.** There is no index on
``signal_outcomes.exit_ts`` (``lab_common.py``'s own docstring names the same
gap for ``tracking_state``), so this repository never filters the global
population by ``exit_ts`` directly. It walks ``strategy_versions.status =
'active'`` (a handful of rows) and, per version, filters
``agent_signals.emitted_at`` — the leading column of
``ix_agent_signals_version_cohort_emitted`` — over a window wide enough to cover the
day plus :data:`_MAX_HOLDING_DAYS` of holding time, then narrows to the exact
``exit_ts`` window in Python. ``EXPLAIN`` in
``tests/integration/test_lab_daily_goal_api.py`` shows the index scan.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from hunter_api.repositories.lab_common import COHORT
from hunter_core.db.models.agents import AgentSignal, SignalOutcome, StrategyVersion
from hunter_core.db.models.fx import FxObservation
from hunter_core.db.models.market_data import Candle
from hunter_core.db.models.portfolios import PortfolioEquitySnapshot
from hunter_core.db.repositories.base import TenantRepository
from hunter_core.db.repositories.equity import REFERENCE_RESOLUTION
from hunter_core.db.repositories.portfolio import PortfolioRepository
from hunter_core.domain.enums import ShadowCohort, StrategyVersionStatus, Timeframe
from hunter_core.portfolio.opening import PAPER_FX_POLICY

__all__ = [
    "DailyOutcomeRow",
    "PortfolioEquityReading",
    "VersionMeta",
    "LabDailyGoalRepository",
]

_MAX_HOLDING_DAYS = 2
"""How far before a window's start ``agent_signals.emitted_at`` may reach and
still have its outcome close inside the window. The strategies this brief
covers hold for minutes to a few hours (``docs/PIPELINE.md`` §2); two days is
a deliberately generous margin, documented as a CONCERN in
``notes-T3.78.md``: a signal held longer would be missed by a query that never
touches the unindexed ``exit_ts`` column directly."""


@dataclass(frozen=True, slots=True)
class VersionMeta:
    id: uuid.UUID
    activated_at: datetime | None


@dataclass(frozen=True, slots=True)
class DailyOutcomeRow:
    """One ``signal_outcomes`` row, joined with enough of its signal and
    version to dedupe and price it — never the money itself (that is
    ``services/lab_daily_goal_sizing.py``'s job)."""

    strategy_version_id: uuid.UUID
    version_activated_at: datetime | None
    signal_id: uuid.UUID
    market_id: uuid.UUID
    source_bar_close: datetime
    exit_ts: datetime
    r_multiple: Decimal | None
    entry_ts: datetime | None
    virtual_entry: Decimal | None
    virtual_stop: Decimal | None
    meta: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PortfolioEquityReading:
    equity_usdt: Decimal | None
    source: str
    """``"equity_snapshot"``, ``"opening_anchor"`` or ``"no_portfolio"``."""


def _observation_ts(supporting_features: dict[str, Any], emitted_at: datetime) -> datetime:
    """``source_bar_close`` — same derivation as ``services/lab_signals.py``
    (T3.38a): the decision bar the signal was computed against, or the
    decision instant itself when the envelope carries no ``observation_ts``.
    """
    raw = supporting_features.get("observation_ts")
    if isinstance(raw, str):
        return datetime.fromisoformat(raw)
    return emitted_at


class LabDailyGoalRepository(TenantRepository):
    async def active_versions(self) -> list[VersionMeta]:
        """Every ``active`` version, oldest activation first — the dedupe
        order the brief asks for, computed once here rather than re-sorted by
        every caller."""
        rows = (
            await self.session.execute(
                select(StrategyVersion.id, StrategyVersion.activated_at)
                .where(StrategyVersion.status == StrategyVersionStatus.ACTIVE)
                .order_by(StrategyVersion.activated_at.asc().nulls_last(), StrategyVersion.id.asc())
            )
        ).all()
        return [VersionMeta(id=row.id, activated_at=row.activated_at) for row in rows]

    async def outcomes_for_version(
        self, version: VersionMeta, *, window_start: datetime, window_end: datetime
    ) -> list[DailyOutcomeRow]:
        """Terminal outcomes of ``version`` whose ``exit_ts`` falls inside
        ``[window_start, window_end)`` — prospective cohort only (D15: replay
        and replication are evidence, never a real calendar day). The SQL
        predicate is on ``emitted_at`` (indexed,
        ``ix_agent_signals_version_cohort_emitted``); the exact ``exit_ts`` cut is
        applied in Python.
        """
        lookback = window_start - timedelta(days=_MAX_HOLDING_DAYS)
        stmt = (
            select(
                AgentSignal.id.label("signal_id"),
                AgentSignal.market_id,
                AgentSignal.emitted_at,
                AgentSignal.supporting_features,
                SignalOutcome.exit_ts,
                SignalOutcome.r_multiple,
                SignalOutcome.entry_ts,
                SignalOutcome.virtual_entry,
                SignalOutcome.virtual_stop,
                SignalOutcome.meta,
            )
            .join(AgentSignal, AgentSignal.id == SignalOutcome.signal_id)
            .where(
                AgentSignal.strategy_version_id == version.id,
                AgentSignal.emitted_at >= lookback,
                AgentSignal.emitted_at < window_end,
                COHORT == ShadowCohort.PROSPECTIVE,
            )
        )
        rows = (await self.session.execute(stmt)).all()
        result: list[DailyOutcomeRow] = []
        for row in rows:
            if row.exit_ts is None or not (window_start <= row.exit_ts < window_end):
                continue
            result.append(
                DailyOutcomeRow(
                    strategy_version_id=version.id,
                    version_activated_at=version.activated_at,
                    signal_id=row.signal_id,
                    market_id=row.market_id,
                    source_bar_close=_observation_ts(row.supporting_features or {}, row.emitted_at),
                    exit_ts=row.exit_ts,
                    r_multiple=row.r_multiple,
                    entry_ts=row.entry_ts,
                    virtual_entry=row.virtual_entry,
                    virtual_stop=row.virtual_stop,
                    meta=row.meta or {},
                )
            )
        return result

    async def entry_minute_quote_volume(
        self, market_id: uuid.UUID, entry_ts: datetime
    ) -> Decimal | None:
        """``candles.quote_volume`` of the last completed 1-minute bar at or
        before ``entry_ts`` — the participation reference, in the market's
        quote currency. The primary key ``(market_id, timeframe, open_time)``
        makes this a backward index scan, never a sequential one.

        Simplification declared in ``notes-T3.78.md`` (CONCERN): T3.60's
        simulator used ``min(last complete minute, median of 30 completed
        bars)`` to damp a single noisy minute; this reads one bar. Both read
        the same ``candles`` table and the same ``max_participation_pct``.
        """
        stmt = (
            select(Candle.quote_volume)
            .where(
                Candle.market_id == market_id,
                Candle.timeframe == Timeframe.M1,
                Candle.open_time <= entry_ts,
                Candle.is_final.is_(True),
            )
            .order_by(Candle.open_time.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def principal_portfolio_equity_usdt(self, as_of: datetime) -> PortfolioEquityReading:
        """The org's real principal paper wallet equity, read-only, no lock."""
        portfolios = PortfolioRepository(self.session, self.organization_id)
        portfolio_id = await portfolios.principal_paper_id()
        if portfolio_id is None:
            return PortfolioEquityReading(equity_usdt=None, source="no_portfolio")
        snapshot_stmt = (
            select(PortfolioEquitySnapshot.equity)
            .where(
                PortfolioEquitySnapshot.organization_id == self.organization_id,
                PortfolioEquitySnapshot.portfolio_id == portfolio_id,
                PortfolioEquitySnapshot.resolution == REFERENCE_RESOLUTION,
                PortfolioEquitySnapshot.ts <= as_of,
            )
            .order_by(PortfolioEquitySnapshot.ts.desc())
            .limit(1)
        )
        equity = (await self.session.execute(snapshot_stmt)).scalar_one_or_none()
        if equity is not None:
            return PortfolioEquityReading(equity_usdt=equity, source="equity_snapshot")
        anchor = await portfolios.get_anchor(portfolio_id)
        if anchor is None:
            return PortfolioEquityReading(equity_usdt=None, source="no_portfolio")
        return PortfolioEquityReading(equity_usdt=anchor.credited_amount, source="opening_anchor")

    async def latest_fx_brl(self, as_of: datetime) -> FxObservation | None:
        """The USDTBRL observation the day's conversion uses — same policy
        pair/source the wallet itself is anchored to
        (``hunter_core.portfolio.opening.PAPER_FX_POLICY``)."""
        stmt = (
            select(FxObservation)
            .where(
                FxObservation.pair == PAPER_FX_POLICY.pair,
                FxObservation.source == PAPER_FX_POLICY.source,
                FxObservation.available_at <= as_of,
            )
            .order_by(FxObservation.available_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
