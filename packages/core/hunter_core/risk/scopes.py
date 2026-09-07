"""Who is blocked, at which scope, and where the lock lives.

The effective kill switch is the most restrictive of **system**, **organization**
and **portfolio** (RISK_ENGINE.md §5). Two of the three are durable rows;
the system scope is process configuration, and this module says so out loud
instead of pretending a row exists.

It also owns :func:`load_locked_state`, the ``SELECT ... FOR UPDATE`` on
``portfolio_risk_state`` that DATABASE.md §18.7 designates as *the* wallet lock —
the FIFO counter, the daily reference and the peak all live on that one row so
they serialise together instead of in four different orders.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from hunter_core.db.models.identity import Organization
from hunter_core.db.models.paper_wallet import PortfolioRiskState
from hunter_core.db.models.portfolios import Portfolio
from hunter_core.domain.enums import KillSwitchState
from hunter_core.risk.daily import PersistedRiskState
from hunter_core.risk.transitions import organization_kill_switch
from hunter_core.settings import get_settings
from hunter_risk.kill_switch import blocks_entries, most_restrictive

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "EffectiveKillSwitch",
    "RiskStateMissing",
    "effective_state",
    "load_locked_state",
]


class RiskStateMissing(LookupError):
    """The wallet has no ``portfolio_risk_state`` row, so there is nothing to lock.

    ``SELECT ... FOR UPDATE`` on a row that does not exist serialises nothing, so
    continuing on defaults would run two concurrent evaluations side by side
    (Astra, T3.6 review). The wallet's opening writes this row (T3.3).
    """


@dataclass(frozen=True, slots=True)
class EffectiveKillSwitch:
    """The three scopes and the one state that follows from them."""

    portfolio_id: uuid.UUID
    organization_id: uuid.UUID
    system: KillSwitchState
    organization: KillSwitchState
    portfolio: KillSwitchState

    @property
    def effective(self) -> KillSwitchState:
        """The most restrictive of the three — RISK_ENGINE.md §5."""
        return most_restrictive(self.system, self.organization, self.portfolio)

    @property
    def blocks_entries(self) -> bool:
        return blocks_entries(self.effective)


async def load_locked_state(session: AsyncSession, portfolio_id: uuid.UUID) -> PersistedRiskState:
    """The wallet's lock row, taken ``FOR UPDATE``. Scalars, never an ORM identity.

    Read as columns so a session that already loaded the entity cannot answer
    from its identity map with a value another transaction has since replaced
    (``expire_on_commit=False``; Astra, T3.6 review).
    """
    row = (
        await session.execute(
            select(
                PortfolioRiskState.organization_id,
                PortfolioRiskState.portfolio_id,
                PortfolioRiskState.trading_day,
                PortfolioRiskState.trading_day_timezone,
                PortfolioRiskState.trading_day_start_utc,
                PortfolioRiskState.equity_day_start,
                PortfolioRiskState.day_reference_observed_at,
                PortfolioRiskState.peak_equity,
                PortfolioRiskState.peak_equity_at,
                PortfolioRiskState.peak_sampling_interval_s,
            )
            .where(PortfolioRiskState.portfolio_id == portfolio_id)
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        raise RiskStateMissing(
            f"portfolio {portfolio_id} has no portfolio_risk_state row: the wallet was never "
            "opened, or this transaction cannot see it (RLS). Nothing may proceed on defaults — "
            "an unlocked evaluation is two concurrent evaluations."
        )
    return PersistedRiskState(*row)


async def effective_state(
    session: AsyncSession,
    portfolio_id: uuid.UUID,
    *,
    system: KillSwitchState | None = None,
    lock: bool = False,
) -> EffectiveKillSwitch:
    """The effective state, cheaply — the execution worker's 10 s re-read.

    ``lock=True`` is the same read *inside the transaction applying an entry
    effect*, acquiring in the contract's fixed order (system -> organization ->
    portfolio): ``FOR SHARE`` on the tenant row, ``FOR UPDATE`` on the wallet's
    lock row. That closes the race §5 names — the worker reads ACTIVE, another
    session commits ``TRADING_DISABLED`` on the organization, and the fill lands
    after it because the two never contended for a lock.

    The system scope has **no durable row**: it is process configuration
    (``Settings.system_kill_switch``), so it cannot be locked and two processes
    can disagree. Recorded in ``.claude/state/notes-T3.6.md``.
    """
    resolved_system = system if system is not None else get_settings().system_kill_switch
    row = (
        await session.execute(
            select(
                Portfolio.organization_id,
                Portfolio.kill_switch_state,
                Organization.kill_switch_state,
            )
            .join(Organization, Organization.id == Portfolio.organization_id)
            .where(Portfolio.id == portfolio_id)
        )
    ).one_or_none()
    if row is None:
        raise RiskStateMissing(f"portfolio {portfolio_id} is not visible to this transaction")
    organization_id, latch, organization = row
    if lock:
        organization = await organization_kill_switch(session, organization_id, lock=True)
        await load_locked_state(session, portfolio_id)
        latch = await session.scalar(
            select(Portfolio.kill_switch_state).where(Portfolio.id == portfolio_id)
        )
    return EffectiveKillSwitch(
        portfolio_id=portfolio_id,
        organization_id=organization_id,
        system=resolved_system,
        organization=organization,
        portfolio=latch or KillSwitchState.ACTIVE,
    )
