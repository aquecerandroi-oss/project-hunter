"""The bar-level backlog safety valve — ``ShadowConfig.late_delay_backlog_max_s`` (T3.74c).

Not the fix: a defense-in-depth valve so a real backlog cannot compound past
``eligibility_max_lag_s`` (300 s) into ever-slower processing. Checked once per
bar, before ``load_market``/``load_family_readers``/any per-version cost —
unlike ``consumer_isolation``/``spot_not_in_shadow_universe``'s ``wired``
fixtures, ``load_market`` here is never even monkeypatched to a working stub,
because if the valve fired late it would raise on the unpatched real function
instead of quietly passing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.market import NormalizedCandle, to_wire
from hunter_core.observability import registry
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import ConsumerHealth, handle_candle

pytestmark = pytest.mark.unit

BAR_CLOSE = datetime(2026, 9, 8, 12, 5, tzinfo=UTC)


def _payload() -> dict[str, Any]:
    return to_wire(
        NormalizedCandle(
            exchange="binance",
            symbol="BTCUSDT",
            market_type=MarketType.PERPETUAL,
            timeframe=Timeframe.M1,
            open_time=BAR_CLOSE - timedelta(minutes=1),
            close_time=BAR_CLOSE,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100.5"),
            volume=Decimal("10"),
            is_final=True,
        )
    )


class _Versions:
    """Blows up if ``.get`` is ever called — the valve must fire before the
    version roster is even fetched."""

    async def get(self, _factory: Any) -> list[Any]:
        raise AssertionError("versions.get() called after the backlog valve should have skipped")


def _skipped(reason: str) -> float:
    value = registry.get_sample_value("hunter_shadow_bars_skipped_total", {"reason": reason})
    return 0.0 if value is None else value


async def _run(*, clock_offset_s: float) -> ConsumerHealth:
    health = ConsumerHealth()
    await handle_candle(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        payload=_payload(),
        versions=_Versions(),  # type: ignore[arg-type]
        config=ShadowConfig(),
        health=health,
        clock=lambda: BAR_CLOSE + timedelta(seconds=clock_offset_s),
    )
    return health


async def test_a_bar_within_the_backlog_budget_still_reaches_the_version_roster() -> None:
    """Under the 120 s default, ``versions.get()`` (the next thing after the
    valve) is reached — proven by it raising, since ``_Versions`` has nothing
    real behind it."""
    with pytest.raises(AssertionError, match="versions.get"):
        await _run(clock_offset_s=2.0)


async def test_a_bar_past_the_backlog_budget_is_skipped_before_the_roster() -> None:
    health = await _run(clock_offset_s=121.0)
    assert health.evaluated_bars == 0
    assert health.errors == 0


async def test_the_skip_is_counted_by_name_never_silent() -> None:
    before = _skipped("late_delay_backlog")
    await _run(clock_offset_s=200.0)
    assert _skipped("late_delay_backlog") == before + 1


async def test_the_valve_is_a_strict_greater_than_not_off_by_one() -> None:
    """Exactly at the threshold is still inside the budget — matches
    ``eligibility_max_lag_s``'s own ``>`` in ``decide.py``, not ``>=``."""
    with pytest.raises(AssertionError, match="versions.get"):
        await _run(clock_offset_s=120.0)


async def test_a_healthy_bar_is_unaffected_by_the_valve_existing() -> None:
    """Regression guard: the valve must not fire on the default config's own
    ``ShadowConfig()`` at a realistic (small) lag -- already covered by the
    first test above, restated with the default's exact boundary constant so
    a future change to the default is caught here too."""
    config = ShadowConfig()
    assert config.late_delay_backlog_max_s == 120.0
