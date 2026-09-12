"""T4.11 — marking and selling on the pool's tape, pure, with known numbers:
the mark by the last trade, the impact by participation, the fee of the
band **of that price**, the sale on the next trade, and the ``dead`` write-off.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.pool import PoolTrade
from hunter_meme_worker.lab_models import MARK_POOL_TAPE, BetState, EffectiveParams, SolUsd
from hunter_meme_worker.pool_mark import (
    POOL_VENUE,
    close_dead_without_trade,
    close_on_pool,
    mark_on_pool,
    path_fee_pct,
    stale_seconds,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
SUPPLY = Decimal(1_000_000_000)
PARAMS = EffectiveParams(
    size_sol=Decimal("0.02"),
    target_x=Decimal(10),
    trailing_pct=Decimal(50),
    max_hold_s=7200,
    max_loss_pct=Decimal(100),
    exit_on_migration=False,
    trailing_arm_x=Decimal(3),
    exit_on_dead=True,
)
BET = BetState(
    id="bet-1",
    proposal_id="prop-1",
    rule_set_id="rs-1",
    mint="MINT",
    entry_at=T0,
    tokens=Decimal(1000),
    sol_spent=Decimal("0.02"),
    initial_risk_sol=Decimal("0.02"),
    params=PARAMS,
    high_water_x=Decimal("0.9"),
    mark_sol=Decimal("0.018"),
    mark_at=T0,
    exit_intent=None,
    fee_pct=Decimal("1.75"),
    priority_fee_sol=Decimal(0),
)
SOL_USD = SolUsd(
    price_usd=Decimal("101.4445"),
    source="pumpfun_rest:/sol-price",
    as_of=T0,
    observed_at=T0,
    stale=False,
)


def _trade(seconds: int, sol: str, tokens: str = "1000") -> PoolTrade:
    at = T0 + timedelta(seconds=seconds)
    return PoolTrade(
        block_time=at,
        received_at=at + timedelta(seconds=1),
        side="buy",
        sol=Decimal(sol),
        tokens=Decimal(tokens),
    )


def test_the_path_fee_is_what_the_rule_set_carries_above_the_curve() -> None:
    assert path_fee_pct(Decimal("1.75")) == Decimal("0.5")
    assert path_fee_pct(Decimal("1.25")) == 0
    assert path_fee_pct(Decimal(1)) == 0, "never negative"


def test_the_mark_is_the_last_price_minus_impact_minus_the_band_fee() -> None:
    """Price 0,00001 (mcap 10 000 → 0,95 %), five minutes of 5 SOL → impact 0,2 %."""
    known = [_trade(-200, "2"), _trade(-100, "2.99"), _trade(0, "0.01")]
    marked = mark_on_pool(BET, known[-1], known, total_supply=SUPPLY)
    assert marked.quote.volume_5m_sol == Decimal(5)
    assert marked.quote.tier_fee_pct == Decimal("0.950") and marked.quote.path_fee_pct == Decimal(
        "0.5"
    )
    assert marked.mark.mark_sol == Decimal("0.00983529")
    assert marked.mark.high_water_x == Decimal("0.9"), "a lower mark never lowers the high water"
    assert marked.total_supply_source == "meme_tokens"
    up = mark_on_pool(BET, _trade(60, "1", "1000"), known, total_supply=SUPPLY)  # price 0,001
    assert up.mark.high_water_x > Decimal("0.9") and up.quote.mcap_sol == Decimal(1_000_000)
    assert up.quote.tier_fee_pct == Decimal("0.300"), "≥ 98 240 SOL of market cap"


def test_the_band_follows_the_price_of_each_trade_and_the_supply_is_named_when_assumed() -> None:
    just_graduated = mark_on_pool(
        BET, _trade(0, "0.0004", "1000"), [], total_supply=None
    )  # mcap 400
    assert just_graduated.quote.tier_fee_pct == Decimal("1.250")
    assert just_graduated.total_supply_source == "assumed_1e9"
    assert just_graduated.quote.impact_reason == "no_volume_5m"
    later = mark_on_pool(BET, _trade(0, "0.0005", "1000"), [], total_supply=SUPPLY)  # mcap 500
    assert later.quote.tier_fee_pct == Decimal("1.200")


def test_a_close_on_the_next_trade_books_the_net_and_r_over_everything_spent() -> None:
    known = [_trade(-100, "5"), _trade(0, "0.25")]  # price 0,00025 → gross 0,25 (12,5×)
    marked = mark_on_pool(BET, known[-1], known, total_supply=SUPPLY)
    closed = close_on_pool(
        BET,
        marked,
        "target",
        SOL_USD,
        intent_trade_at=T0 - timedelta(seconds=100),
        mark_stale_s=100,
    )
    assert closed.exit_at == known[-1].block_time
    assert closed.exit["reason"] == "target" and closed.exit["fill"] == "next_trade"
    assert closed.exit["venue"] == POOL_VENUE and closed.exit["mark_source"] == MARK_POOL_TAPE
    assert Decimal(closed.exit["sol_received"]) == marked.quote.net_sol
    assert closed.pnl_sol == marked.quote.net_sol - Decimal("0.02")
    assert closed.r_multiple == closed.pnl_sol / Decimal("0.02")
    assert closed.exit["intent_trade_at"] == (T0 - timedelta(seconds=100)).isoformat()
    assert closed.exit["trade"]["price_sol"] == "0.00025" and closed.exit["mark_stale_s"] == 100
    assert closed.exit["tier_fee_pct"] == "0.3" and closed.exit["impact_pct"] == "1", (
        "mcap 250 000 SOL → the floor band; 0,25 of 5,25 SOL → 4,76 % participation, capped"
    )
    assert closed.sol_usd_at_exit == Decimal("101.4445")


def test_a_dead_close_without_a_trade_is_the_whole_stake_named_dead() -> None:
    closed = close_dead_without_trade(
        BET,
        now=T0 + timedelta(seconds=1200),
        mark_stale_s=1200,
        last_trade_at=T0,
        last_mark_sol=Decimal("0.005"),
    )
    assert closed.exit["reason"] == "dead" and closed.exit["fill"] == "none"
    assert closed.exit["sol_received"] == "0" and closed.exit["last_mark_sol"] == "0.005"
    assert closed.exit["mark_stale_s"] == 1200 and closed.exit["last_trade_at"] == T0.isoformat()
    assert closed.pnl_sol == Decimal("-0.02") and closed.r_multiple == Decimal(-1)
    assert closed.sol_usd_at_exit is None and closed.exit["sol_usd_reason"] == "no_sale_to_price"


def test_staleness_is_seconds_since_the_last_trade_never_negative() -> None:
    assert stale_seconds(T0 + timedelta(seconds=901), T0) == 901
    assert stale_seconds(T0, T0 + timedelta(seconds=5)) == 0
