"""D12 — the exit-only hysteresis band around the spot floor (T3.0e).

Pure-function tests for ``spot_band.py``: no Redis, no Postgres. The durable
counter itself (survives a restart of the shard 0 process) is proved against
real Redis in ``test_spot_universe.py``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_core.domain.enums import MarketStatus, MarketType
from hunter_core.domain.market import NormalizedMarket, NormalizedTicker
from hunter_market_worker import spot_band

from . import builders

pytestmark = pytest.mark.unit


def _market(
    symbol: str = "PROMUSDT", *, quote: str = "USDT", **overrides: object
) -> NormalizedMarket:
    base = symbol.removesuffix(quote) or "X"
    return builders.market(symbol, base, quote, market_type=MarketType.SPOT, **overrides)


def _ticker(symbol: str, volume: str | None) -> NormalizedTicker:
    return builders.ticker_rest(
        symbol, "1", quote_volume_24h=None if volume is None else Decimal(volume)
    )


# --------------------------------------------------------------------------
# permanence_observation
# --------------------------------------------------------------------------


def test_a_pair_oscillating_at_49_and_51_million_is_always_above_the_exit_floor() -> None:
    """``PROMUSDT`` (notes-T3.0c.md §8): the exit floor is 40M, not 50M --
    oscillating around the *admission* floor never even touches the band."""
    market = _market()
    assert spot_band.permanence_observation(market, _ticker("PROMUSDT", "49000000")) == "above"
    assert spot_band.permanence_observation(market, _ticker("PROMUSDT", "51000000")) == "above"


def test_below_the_exit_floor_is_below_and_on_it_is_above() -> None:
    floor = spot_band.SPOT_EXIT_FLOOR_USDT
    market = _market()
    assert spot_band.permanence_observation(market, _ticker("PROMUSDT", str(floor))) == "above"
    below = _ticker("PROMUSDT", str(floor - Decimal("0.01")))
    assert spot_band.permanence_observation(market, below) == "below"


def test_an_unreadable_ticker_is_an_observation_below_never_above() -> None:
    market = _market()
    assert spot_band.permanence_observation(market, None) == "below"
    assert spot_band.permanence_observation(market, _ticker("PROMUSDT", None)) == "below"


def test_a_market_absent_from_the_current_listing_is_not_trading() -> None:
    """Vanished from the exchange's listing entirely -- ``mark_delisted``
    treats this the same way, and so does the band: immediate, no count."""
    assert spot_band.permanence_observation(None, _ticker("PROMUSDT", "999999999")) == (
        spot_band.REASON_NOT_TRADING
    )


def test_suspended_is_not_trading_regardless_of_volume() -> None:
    market = _market(status=MarketStatus.SUSPENDED)
    ticker = _ticker("PROMUSDT", "999999999")
    assert spot_band.permanence_observation(market, ticker) == spot_band.REASON_NOT_TRADING


def test_a_quote_that_stopped_being_usdt_is_immediate() -> None:
    market = _market(quote="BTC")
    ticker = _ticker("PROMUSDT", "999999999")
    assert spot_band.permanence_observation(market, ticker) == spot_band.REASON_QUOTE_NOT_USDT


def test_a_blocklisted_symbol_is_immediate() -> None:
    market = _market()
    ticker = _ticker("PROMUSDT", "999999999")
    observation = spot_band.permanence_observation(market, ticker, blocklist={"promusdt"})
    assert observation == spot_band.REASON_BLOCKLISTED


# --------------------------------------------------------------------------
# resolve_band
# --------------------------------------------------------------------------


def test_three_consecutive_below_readings_remove_with_below_band_3x() -> None:
    streak, reason = 0, None
    for _ in range(spot_band.SPOT_EXIT_STREAK):
        streak, reason = spot_band.resolve_band(streak, "below")
    assert reason == spot_band.REASON_BELOW_BAND
    assert streak == 0


def test_two_below_then_one_above_resets_the_count() -> None:
    streak, _ = spot_band.resolve_band(0, "below")
    streak, _ = spot_band.resolve_band(streak, "below")
    assert streak == 2
    streak, reason = spot_band.resolve_band(streak, "above")
    assert (streak, reason) == (0, None)
    # The reset actually took: a fresh "below" starts the count over at 1,
    # not where the interrupted streak left off.
    streak, reason = spot_band.resolve_band(streak, "below")
    assert (streak, reason) == (1, None)


def test_a_hard_exit_reason_removes_regardless_of_an_in_progress_streak() -> None:
    streak, _ = spot_band.resolve_band(0, "below")
    streak, _ = spot_band.resolve_band(streak, "below")
    streak, reason = spot_band.resolve_band(streak, spot_band.REASON_NOT_TRADING)
    assert (streak, reason) == (0, spot_band.REASON_NOT_TRADING)


@pytest.mark.parametrize(
    "reason",
    [spot_band.REASON_NOT_TRADING, spot_band.REASON_QUOTE_NOT_USDT, spot_band.REASON_BLOCKLISTED],
)
def test_every_hard_exit_reason_is_immediate_from_a_clean_streak(reason: str) -> None:
    assert spot_band.resolve_band(0, reason) == (0, reason)


def test_a_single_above_from_a_clean_streak_stays_at_zero() -> None:
    assert spot_band.resolve_band(0, "above") == (0, None)
