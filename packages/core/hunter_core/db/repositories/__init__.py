"""Tenant-scoped repositories — the code half of the double tenant isolation.

Every tenant query in ``hunter_core`` goes through one of these *and* through a
transaction that declared ``app.current_org`` for RLS (CLAUDE.md). The base
class refuses the second half being missing instead of returning zero rows.
"""

from hunter_core.db.repositories.base import TenantContextMissing, TenantRepository
from hunter_core.db.repositories.equity import REFERENCE_RESOLUTION, EquitySnapshotRepository
from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.db.repositories.ledger import (
    CashReconciliation,
    LedgerRepository,
    PositionRow,
    ReservationRow,
)
from hunter_core.db.repositories.portfolio import PortfolioRepository

__all__ = [
    "REFERENCE_RESOLUTION",
    "CashReconciliation",
    "EquitySnapshotRepository",
    "FxObservationRepository",
    "LedgerRepository",
    "PortfolioRepository",
    "PositionRow",
    "ReservationRow",
    "TenantContextMissing",
    "TenantRepository",
]
