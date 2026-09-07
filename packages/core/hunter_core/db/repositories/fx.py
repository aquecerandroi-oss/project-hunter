"""``fx_observations`` — read access to the rates the BRL side is anchored to.

Global and immutable (DATABASE.md §18.2), so this repository is deliberately
**not** a :class:`~hunter_core.db.repositories.base.TenantRepository`: an
exchange rate belongs to no organization, and the API role only holds ``SELECT``
on the table — the market-worker of T3.11 is the only writer.

There is no "get me a rate" convenience that hides the freshness question. The
two readers here return an observation and nothing else; whether it may open a
wallet is decided by :func:`hunter_core.portfolio.opening.validate_fx_observation`
against a declared policy, at the instant of the act.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from hunter_core.db.models.fx import FxObservation

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


class FxObservationRepository:
    """Reads of the global FX table, inside the caller's transaction."""

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, observation_id: uuid.UUID) -> FxObservation | None:
        """One observation by id — the one an anchor or a curve point names."""
        return await self._session.get(FxObservation, observation_id)

    async def latest_available(
        self, *, pair: str, source: str, as_of: datetime
    ) -> FxObservation | None:
        """The newest observation of ``pair`` from ``source`` we could have acted on.

        Ordered and filtered by ``available_at``, never by ``observed_at``: a
        rate that only reached us at 10:02 cannot explain a decision taken at
        10:00, which is the causal cut ``ix_fx_observations_lookup`` indexes.
        """
        statement = (
            select(FxObservation)
            .where(
                FxObservation.pair == pair,
                FxObservation.source == source,
                FxObservation.available_at <= as_of,
            )
            .order_by(FxObservation.available_at.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()
