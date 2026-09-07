"""The one wallet this worker manages, and how it is found.

M3 is a **single principal paper wallet per organization**
(``uq_portfolios_principal_paper``, DATABASE.md §18.8), so the worker's unit of
work is one ``(organization_id, portfolio_id)`` pair at a time. It is looked up
from the database on every cycle rather than cached at startup: a wallet opened
after the process started has to be picked up without a restart, and a wallet
that was archived has to stop being managed without one either.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["WalletRef", "principal_wallets"]


@dataclass(frozen=True, slots=True)
class WalletRef:
    """A wallet named by both halves of its identity.

    Never just ``portfolio_id``: every tenant query is scoped by organization as
    well, both in the repository and in ``app.current_org`` for RLS, and a
    reference that carried only the wallet would invite one of the two to be
    inferred (CLAUDE.md, "tenant isolation is double").
    """

    organization_id: uuid.UUID
    portfolio_id: uuid.UUID


async def principal_wallets(session: AsyncSession) -> tuple[WalletRef, ...]:
    """Every active principal paper wallet, across organizations.

    Read with the engine's ``BYPASSRLS`` role deliberately: the worker manages
    every tenant's wallet, and the per-organization transaction that follows is
    what re-establishes the tenant scope for the work itself.
    """
    rows = await session.execute(
        text(
            "SELECT organization_id, id AS portfolio_id FROM portfolios "
            "WHERE type = 'paper' AND NOT is_arena AND status = 'active' "
            "AND deleted_at IS NULL ORDER BY created_at"
        )
    )
    return tuple(WalletRef(row.organization_id, row.portfolio_id) for row in rows)
