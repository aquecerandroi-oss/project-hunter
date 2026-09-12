"""A3.86b: real candle queries decide eligibility, including missing SPOT history."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from . import shadow_builders as shadow

# Reuse the eligibility suite's database fixtures and tenant-scoped screen reader.
from .test_bridge_eligibility import BAR, _screen, _setup  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize(
    ("ticker", "minutes", "reason"),
    [
        (Decimal(120_000_000), 31, "spot_volume_below_floor"),
        (Decimal(45_000_000), 60, None),
        (Decimal(120_000_000), 0, "liquidity_unproven"),
    ],
)
async def test_screen_reads_spot_candles(
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    ticker: Decimal,
    minutes: int,
    reason: str | None,
) -> None:
    fixture = await _setup(
        db_session_factory,
        db_engine,
        spot_volume=ticker,
        candle_volume=Decimal(1_000_000),
        candle_minutes=minutes,
    )
    await shadow.emit_signal(
        db_engine,
        version_id=fixture.version_id,
        market_id=fixture.perp_market_id,
        source_bar_close=BAR,
        purpose=shadow.PURPOSE_PAPER,
    )

    screened = await _screen(db_session_factory, fixture)

    assert len(screened) == 1
    assert screened[0].refused == reason
    assert screened[0].eligible is (reason is None)
    if reason is None:
        assert screened[0].spot_market_id == fixture.tenant.market_id
        assert screened[0].agent_id is not None
