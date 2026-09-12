"""T4.11 — pricing a position on the PumpSwap pool's tape, with known numbers.

The fee is the band of the market cap **of this price** (``docs/PUMPFUN.md``
§4.1), the impact is the participation in the last five minutes capped at 1 %,
and a trade received after the instant judged is not a trade that instant
could see — the look-ahead test of the pool side.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.pool import (
    IMPACT_CAP_PCT,
    NO_VOLUME_5M,
    POOL_DEFINITIONS,
    POOL_FEE_TIERS_SOL,
    PoolTrade,
    last_trade_at_or_before,
    participation_impact_pct,
    pool_fee_pct,
    quote_pool_sell,
    trades_known_by,
    volume_sol,
)

T0 = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _trade(seconds: int, sol: str, tokens: str = "1000", *, lag_s: int = 1) -> PoolTrade:
    at = T0 + timedelta(seconds=seconds)
    return PoolTrade(
        block_time=at,
        received_at=at + timedelta(seconds=lag_s),
        side="buy",
        sol=Decimal(sol),
        tokens=Decimal(tokens),
    )


@pytest.mark.parametrize(
    ("mcap", "fee"),
    [
        ("0", "1.250"),
        ("419.99", "1.250"),
        ("420", "1.200"),
        ("1469.999", "1.200"),
        ("1470", "1.150"),
        ("4420", "1.000"),
        ("9820", "0.950"),
        ("98239.9", "0.325"),
        ("98240", "0.300"),
        ("5000000", "0.300"),
    ],
)
def test_the_pool_fee_is_the_band_of_the_market_cap(mcap: str, fee: str) -> None:
    """The bands of ``pump.fun/docs/fees`` (20 May 2026), exclusive upper bounds."""
    assert pool_fee_pct(Decimal(mcap)) == Decimal(fee)


def test_the_bands_are_ascending_and_the_fee_only_falls() -> None:
    uppers = [upper for upper, _ in POOL_FEE_TIERS_SOL]
    fees = [fee for _, fee in POOL_FEE_TIERS_SOL]
    assert uppers == sorted(uppers) and len(set(uppers)) == len(uppers)
    assert fees == sorted(fees, reverse=True)
    assert len(POOL_FEE_TIERS_SOL) == 24, "24 bands below the 0,30 % floor"
    with pytest.raises(ValueError, match="negative"):
        pool_fee_pct(Decimal(-1))


def test_the_volume_window_is_five_minutes_ending_at_the_instant() -> None:
    trades = [
        _trade(-360, "5"),
        _trade(-299, "2"),
        _trade(-100, "3"),
        _trade(0, "1"),
        _trade(1, "9"),
    ]
    assert volume_sol(trades, at=T0) == Decimal(6), "(t − 5 min, t]: −299 s, −100 s and t itself"
    assert volume_sol([], at=T0) == 0


def test_a_trade_received_after_the_instant_is_not_known_to_it() -> None:
    """The look-ahead test: same block time, received one second later."""
    early = _trade(-10, "1", lag_s=1)
    late = _trade(-5, "100", lag_s=20)  # received at T0 + 15 s
    known = trades_known_by([late, early], T0)
    assert known == [early]
    assert last_trade_at_or_before(known, T0) is early
    assert volume_sol(known, at=T0) == Decimal(1), "the late trade's 100 SOL do not exist yet"
    assert last_trade_at_or_before(
        trades_known_by([late, early], T0 + timedelta(seconds=15)), T0
    ) is (late)


def test_last_trade_at_or_before_ignores_the_future_block_times() -> None:
    trades = [_trade(-30, "1"), _trade(-10, "2"), _trade(5, "3")]
    assert last_trade_at_or_before(trades, T0) is trades[1]
    assert last_trade_at_or_before(trades, T0 - timedelta(seconds=31)) is None


@pytest.mark.parametrize(
    ("size", "volume", "impact", "reason"),
    [
        ("0.02", "10", "0.2", None),
        ("0.1", "10", "1", None),
        ("1", "10", "1", None),
        ("0.5", "0", "1", NO_VOLUME_5M),
    ],
)
def test_the_impact_is_the_participation_capped_at_one_percent(
    size: str, volume: str, impact: str, reason: str | None
) -> None:
    assert participation_impact_pct(Decimal(size), Decimal(volume)) == (Decimal(impact), reason)
    assert IMPACT_CAP_PCT == 1


def test_a_pool_sell_quote_deducts_impact_then_the_tier_and_path_fees() -> None:
    """1 000 tokens at 0,00001 SOL: gross 0,01; volume 5 → participation 0,2 %
    → 0,00998; mcap 10 000 SOL → band 0,95 % + path 0,5 % = 1,45 % of 0,00998."""
    quote = quote_pool_sell(
        Decimal(1000),
        Decimal("0.00001"),
        volume_5m_sol=Decimal(5),
        total_supply=Decimal(1_000_000_000),
        path_fee_pct=Decimal("0.5"),
    )
    assert quote.gross_sol == Decimal("0.01")
    assert quote.mcap_sol == Decimal(10000)
    assert (quote.impact_pct, quote.impact_reason) == (Decimal("0.2"), None)
    assert quote.impact_sol == Decimal("0.00002")
    assert (quote.tier_fee_pct, quote.path_fee_pct) == (Decimal("0.950"), Decimal("0.5"))
    assert quote.fee_sol == Decimal("0.00998") * Decimal("1.45") / 100
    assert quote.net_sol == Decimal("0.00983529")


def test_a_quote_right_after_graduation_pays_the_top_band_and_the_cap_without_volume() -> None:
    """mcap 400 SOL → 1,25 %; no volume in the window → impact = the cap, named."""
    quote = quote_pool_sell(
        Decimal(2_000_000),
        Decimal("0.0000004"),
        volume_5m_sol=Decimal(0),
        total_supply=Decimal(1_000_000_000),
        path_fee_pct=Decimal("0.5"),
    )
    assert quote.mcap_sol == Decimal(400) and quote.tier_fee_pct == Decimal("1.250")
    assert (quote.impact_pct, quote.impact_reason) == (Decimal(1), NO_VOLUME_5M)
    assert quote.gross_sol == Decimal("0.8")
    assert quote.net_sol == Decimal("0.792") * (1 - Decimal("1.75") / 100)


def test_a_pool_trade_recomputes_its_price_from_the_exact_amounts() -> None:
    trade = _trade(0, "0.054396031", "113499.73695")
    assert trade.price_sol == Decimal("0.054396031") / Decimal("113499.73695")
    with pytest.raises(ValueError, match="tokens"):
        _trade(0, "1", "0")
    with pytest.raises(ValueError, match="price_sol"):
        quote_pool_sell(
            Decimal(1),
            Decimal(0),
            volume_5m_sol=Decimal(1),
            total_supply=Decimal(1),
            path_fee_pct=Decimal(0),
        )


def test_the_pool_features_are_registered_with_their_parameters() -> None:
    keys = {d.key: d for d in POOL_DEFINITIONS}
    assert set(keys) == {"pool_fee_tier_pct", "pool_impact_pct", "pool_mark_sol"}
    assert all(d.version == 1 for d in POOL_DEFINITIONS)
    assert keys["pool_impact_pct"].params == {"window_minutes": 5, "cap_pct": "1"}
    assert keys["pool_fee_tier_pct"].params == {"bands": 25, "floor_pct": "0.300"}
    assert "meme_trades.received_at" in keys["pool_mark_sol"].inputs
