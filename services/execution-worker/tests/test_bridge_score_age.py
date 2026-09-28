"""``bridge_proposal_submitted`` says how old the Radar score it ranked by was.

Quant review of ``history_v2`` (27/09/2026, F3): with ``opportunity_history``
sampled every five minutes, the score ``bridge_universe.radar_score`` returns for
a source bar can be minutes older than the bar. The ordering is unchanged (the
last sample at or before the cut, never a later one); the log now carries the
sample's instant and its age against that cut so a reader can see it.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from structlog.testing import capture_logs

from . import shadow_builders as shadow
from . import test_bridge_cycle as cycle
from .test_bridge_cycle import BAR

_lab = cycle._lab  # pyright: ignore[reportPrivateUsage]
_data = cycle._data  # pyright: ignore[reportPrivateUsage]
_cycle = cycle._cycle  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_the_submission_log_carries_the_score_instant_and_its_age(
    db_session_factory: async_sessionmaker[AsyncSession], db_engine: AsyncEngine
) -> None:
    lab = await _lab(db_session_factory, db_engine)
    sampled_at = BAR - timedelta(minutes=4)
    opportunity_id = uuid.uuid4()
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO opportunities (id, market_id, direction, score, confidence, status, "
                "first_seen_at, last_updated_at) VALUES (:id, :market, 'long', 72, 0.5, "
                "'WATCHING', :first, :last)"
            ),
            {
                "id": opportunity_id,
                "market": lab.perp_market_id,
                "first": sampled_at - timedelta(minutes=10),
                "last": BAR + timedelta(minutes=1),  # after the cut: never read for this bar
            },
        )
        await connection.execute(
            text(
                "INSERT INTO opportunity_history (opportunity_id, ts, score, confidence, status) "
                "VALUES (:id, :ts, 65, 0.5, 'WATCHING')"
            ),
            {"id": opportunity_id, "ts": sampled_at},
        )
    await shadow.emit_signal(
        db_engine,
        version_id=lab.version_id,
        market_id=lab.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_PAPER,
    )

    with capture_logs() as logs:
        outcome = await _cycle(db_session_factory, lab, _data(lab))

    assert outcome.submitted is not None
    (submitted,) = [entry for entry in logs if entry["event"] == "bridge_proposal_submitted"]
    assert Decimal(submitted["score"]) == Decimal(65)
    assert submitted["score_ts"] == sampled_at.isoformat()
    assert submitted["score_age_s"] == 240
