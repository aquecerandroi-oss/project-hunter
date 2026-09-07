"""The wallet's own rows: the portfolio, its lock row and its anchor.

Three tables, one repository, because they are one object with three lifetimes:
``portfolios`` is the container, ``portfolio_risk_state`` is the row every
admission, expiry and kill-switch evaluation takes ``FOR UPDATE`` on (the
``portfolio`` step of the system -> organization -> portfolio lock order), and
``portfolio_currency_anchor`` is the opening, written once.

:meth:`PortfolioRepository.lock_risk_state` is the only place in the ledger that
takes a lock, and it takes a **row** lock rather than a session advisory lock:
the transaction pooler makes session state unusable (DATABASE.md §1.2).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from hunter_core.db.models.paper_wallet import PortfolioCurrencyAnchor, PortfolioRiskState
from hunter_core.db.models.portfolios import Portfolio
from hunter_core.db.repositories.base import TenantRepository
from hunter_core.domain.enums import PortfolioType

if TYPE_CHECKING:
    from datetime import date, datetime
    from decimal import Decimal

_PRINCIPAL_PAPER = "type = 'paper' AND NOT is_arena"
"""The predicate of ``uq_portfolios_principal_paper`` — deliberately without
``status`` and without excluding ``deleted_at``: pausing, archiving or
soft-deleting the wallet must not free a second one (M3 joint decision, item 2).
"""

PRINCIPAL_PAPER_SCOPE = "organization"
"""What ``uq_portfolios_principal_paper`` is keyed on, named once.

T3.1b's security review of ``0006`` (blocking 2) moved the index from
``(organization_id, workspace_id)`` to ``organization_id`` alone: a workspace is
a grouping a request handler can create, not the permanence guarantee D7 asks
for ("uma carteira principal"). :meth:`PortfolioRepository.principal_paper_id`
reads the index's own scope, and every ``WalletAlreadyOpen`` message names this
constant rather than a hand-written word — so the code and the word can only
change together, in this one place."""


class PortfolioRepository(TenantRepository):
    """Reads and writes of one organization's wallets."""

    async def get(self, portfolio_id: uuid.UUID) -> Portfolio | None:
        statement = select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.organization_id == self.organization_id,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def principal_paper_id(self) -> uuid.UUID | None:
        """The id of the organization's principal paper wallet, if it exists.

        Scoped by :data:`PRINCIPAL_PAPER_SCOPE` (``organization_id`` alone,
        T3.1b) using the index's own predicate, so what this reads and what the
        unique index enforces cannot drift apart. Takes no ``workspace_id``: a
        wallet in *any* workspace of this organization is the same principal
        wallet the index refuses to duplicate.
        """
        # S608: ``_PRINCIPAL_PAPER`` is a module constant copied from the index
        # definition; the organization is a bound parameter.
        statement = text(
            "SELECT id FROM portfolios WHERE organization_id = :org "  # noqa: S608
            f"AND {_PRINCIPAL_PAPER} LIMIT 1"
        )
        found = await self.session.scalar(statement, {"org": self.organization_id})
        return found

    async def create_wallet(
        self,
        *,
        portfolio_id: uuid.UUID,
        workspace_id: uuid.UUID,
        name: str,
        base_currency: str,
        initial_capital: Decimal,
        risk_profile_id: uuid.UUID | None,
        created_by: uuid.UUID | None,
    ) -> Portfolio:
        """Insert the container. ``initial_capital`` is what will actually be
        credited: the anchor's trigger refuses two persisted sources disagreeing
        about the opening capital (DATABASE.md §18.2)."""
        wallet = Portfolio(
            id=portfolio_id,
            organization_id=self.organization_id,
            workspace_id=workspace_id,
            name=name,
            type=PortfolioType.PAPER,
            base_currency=base_currency,
            initial_capital=initial_capital,
            risk_profile_id=risk_profile_id,
            created_by=created_by,
            is_arena=False,
        )
        self.session.add(wallet)
        await self.session.flush()
        return wallet

    async def create_risk_state(
        self,
        *,
        portfolio_id: uuid.UUID,
        equity: Decimal,
        as_of: datetime,
        trading_day: date,
        trading_day_start_utc: datetime,
    ) -> PortfolioRiskState:
        """Insert the lock row, with the day reference and the peak of an opening.

        The peak starts at the opening equity rather than at zero: a peak of zero
        would make the first drawdown reading meaningless, and the peak only ever
        rises from here (``portfolio_risk_state_guard``).
        """
        state = PortfolioRiskState(
            organization_id=self.organization_id,
            portfolio_id=portfolio_id,
            peak_equity=equity,
            peak_equity_at=as_of,
            trading_day=trading_day,
            trading_day_start_utc=trading_day_start_utc,
            equity_day_start=equity,
            day_reference_observed_at=as_of,
        )
        self.session.add(state)
        await self.session.flush()
        return state

    async def create_anchor(
        self,
        *,
        portfolio_id: uuid.UUID,
        origin_currency: str,
        origin_amount: Decimal,
        operating_currency: str,
        credited_amount: Decimal,
        fx_observation_id: uuid.UUID,
        rate: Decimal,
        conversion_residual: Decimal,
        rounding_policy: str,
        anchored_at: datetime,
    ) -> PortfolioCurrencyAnchor:
        """Insert the opening conversion. One per wallet, for ever."""
        anchor = PortfolioCurrencyAnchor(
            id=uuid.uuid4(),
            organization_id=self.organization_id,
            portfolio_id=portfolio_id,
            origin_currency=origin_currency,
            origin_amount=origin_amount,
            operating_currency=operating_currency,
            credited_amount=credited_amount,
            fx_observation_id=fx_observation_id,
            rate=rate,
            conversion_residual=conversion_residual,
            rounding_policy=rounding_policy,
            anchored_at=anchored_at,
        )
        self.session.add(anchor)
        await self.session.flush()
        return anchor

    async def get_anchor(self, portfolio_id: uuid.UUID) -> PortfolioCurrencyAnchor | None:
        statement = select(PortfolioCurrencyAnchor).where(
            PortfolioCurrencyAnchor.portfolio_id == portfolio_id,
            PortfolioCurrencyAnchor.organization_id == self.organization_id,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def lock_risk_state(self, portfolio_id: uuid.UUID) -> PortfolioRiskState | None:
        """``SELECT ... FOR UPDATE`` the wallet's lock row.

        Everything that reads the effective state and then applies an effect —
        building the state, admitting a proposal, expiring a reservation,
        evaluating the kill switch — serialises here, in the same transaction
        that applies the effect (M3 joint decision, item 4).
        """
        statement = (
            select(PortfolioRiskState)
            .where(
                PortfolioRiskState.portfolio_id == portfolio_id,
                PortfolioRiskState.organization_id == self.organization_id,
            )
            .with_for_update()
        )
        return (await self.session.execute(statement)).scalar_one_or_none()
