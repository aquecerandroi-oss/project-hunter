"""``bridge_universe.radar_score`` over a ``history_v2`` series (27/09/2026).

The scanner now keeps one ``opportunity_history`` sample per episode every five
minutes (plus status/stage changes) instead of ~50 an hour
(``docs/design/retencao-e-disco-2026-09-27.md`` §6, step 3(a)). The bridge reads
"the last sample at or before the source bar" — this proves, against a real
Postgres, that it still does with samples five minutes apart: never a later
sample (no look-ahead), the open episode only once its own ``last_updated_at``
is at or before the cut, and ``None`` before anything existed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_execution_worker.bridge_universe import radar_score

from .builders import NOW, create_tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

T0 = NOW.replace(second=0, microsecond=0)
_M = timedelta(minutes=1)


async def test_the_bridge_reads_the_last_sparse_sample_before_the_cut(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant = await create_tenant(db_engine)
    opportunity_id = uuid.uuid4()
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO opportunities (id, market_id, direction, score, confidence, "
                "status, first_seen_at, last_updated_at) VALUES (:id, :market, 'long', 71, "
                "0.5, 'WATCHING', :first, :last)"
            ),
            {"id": opportunity_id, "market": tenant.market_id, "first": T0, "last": T0 + 7 * _M},
        )
        for minutes, score in ((0, "60"), (5, "65")):
            await connection.execute(
                text(
                    "INSERT INTO opportunity_history (opportunity_id, ts, score, confidence, "
                    "status) VALUES (:id, :ts, :score, 0.5, 'WATCHING')"
                ),
                {"id": opportunity_id, "ts": T0 + minutes * _M, "score": Decimal(score)},
            )

    async def at(offset: timedelta) -> tuple[Decimal | None, datetime | None]:
        async with db_session_factory() as session:
            return await radar_score(session, market_id=tenant.market_id, at=T0 + offset)

    assert await at(-_M) == (None, None)
    # the T0 sample, not the T0+5 min one -- and *when* it was taken, so the
    # caller can say how old the score it ranked by was (quant review, F3)
    assert await at(4 * _M) == (Decimal("60"), T0)
    assert await at(6 * _M) == (Decimal("65"), T0 + 5 * _M)
    assert await at(8 * _M) == (Decimal("71"), T0 + 7 * _M)  # the open episode
