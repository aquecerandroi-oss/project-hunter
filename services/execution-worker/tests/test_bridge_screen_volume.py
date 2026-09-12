"""A3.86b: the screen uses observed SPOT candles, never the ticker column."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from hunter_core.strategies.envelope import AssumedCosts
from hunter_execution_worker import bridge_screen
from hunter_execution_worker.bridge_inputs import VolumeWindow
from hunter_execution_worker.bridge_universe import SpotPair
from hunter_execution_worker.wallet import WalletRef

# Reuse the existing test signal fixture; this is not a production dependency.
from .test_bridge_refusal_dedupe import NOW, _signal  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.mark.parametrize(
    ("ticker", "candles", "reason"),
    [
        (Decimal(120_000_000), Decimal(31_000_000), "spot_volume_below_floor"),
        (Decimal(45_000_000), Decimal(60_000_000), None),
        (Decimal(120_000_000), None, "liquidity_unproven"),
        (None, Decimal(50_000_000), None),
        (Decimal(120_000_000), Decimal(0), "spot_volume_below_floor"),
    ],
)
async def test_screen_uses_candle_volume(
    monkeypatch: pytest.MonkeyPatch,
    ticker: Decimal | None,
    candles: Decimal | None,
    reason: str | None,
) -> None:
    signal = replace(
        _signal(),
        assumed_costs=AssumedCosts(
            spread_bps=Decimal(2),
            slippage_bps=Decimal(5),
            fee_bps=Decimal(4),
            max_entry_delay_s=60,
        ),
    )
    spot = SpotPair(uuid4(), "TESTUSDT", signal.base_asset_id, True, ticker)
    session = cast("AsyncSession", object())
    volume = AsyncMock(
        return_value=VolumeWindow(
            last_minute=None,
            median=None,
            complete=False,
            volume_ts=NOW,
            quote_volume_24h=candles,
        )
    )
    monkeypatch.setattr(bridge_screen, "volume_window", volume, raising=False)
    monkeypatch.setattr(bridge_screen, "spot_pair_for", AsyncMock(return_value=spot))
    beta = AsyncMock(return_value=object())
    monkeypatch.setattr(bridge_screen, "current_beta", beta)
    monkeypatch.setattr(bridge_screen, "coin_commitment", AsyncMock(return_value=None))
    monkeypatch.setattr(bridge_screen, "_agent_for", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(bridge_screen, "radar_score", AsyncMock(return_value=Decimal(80)))

    screened = await bridge_screen.screen_signal(
        session,
        wallet=WalletRef(uuid4(), uuid4()),
        signal=signal,
        now=NOW,
    )

    assert screened.refused == reason
    assert screened.eligible is (reason is None)
    volume.assert_awaited_once_with(session, market_id=spot.market_id, now=NOW)
    if reason is None:
        assert screened.spot_market_id == spot.market_id
        beta.assert_awaited_once()
    else:
        beta.assert_not_awaited()
