"""Eligibility metrics (§1, §1.1): activity, money, drawdown, concentration,
holding time, unmatched share, and the historical exclusions (creator, create
block, MEV, volume bot). Episodes are built directly with chosen numbers.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from hunter_indicators.meme.wallets.episodes import Episode, OwnerBook
from hunter_indicators.meme.wallets.metrics import (
    EntityFacts,
    entity_metrics,
    failing_reasons,
    max_drawdown,
)
from hunter_indicators.meme.wallets.params import RankingParams
from packages.indicators.tests.meme.test_wallets_builders import SOL, T0, create

pytestmark = pytest.mark.unit

P = RankingParams()


def _ep(
    i: int,
    result: int,
    *,
    day: int | None = None,
    hold: float = 120.0,
    mint: str | None = None,
    slot: int = 1_000,
) -> Episode:
    d = i % 7 if day is None else day
    ep = Episode("E", mint or f"M{i}", slot, T0 + timedelta(days=d), False, 7, first_buy_slot=slot)
    ep.closed_slot, ep.closed_at = slot + 500, T0 + timedelta(days=d, seconds=hold)
    ep.cost_lamports = SOL
    ep.add(d, result)
    ep.hold_seconds, ep.hold_slots = hold, int(hold / 0.4)
    return ep


def _good_book() -> OwnerBook:
    # 21 closed winners of +0.2 SOL over 21 mints, 3 per day → E = 4.2 SOL, 7/7 positive days
    return OwnerBook("E", [_ep(i, SOL // 5) for i in range(21)], sold_atoms=100, unmatched_atoms=0)


FACTS = EntityFacts(wallets=frozenset({"E"}), c_pnl_lamports=SOL, trades_previous_day=10)


def test_a_clean_profitable_entity_passes_every_check() -> None:
    m = entity_metrics(_good_book(), FACTS, creates={}, funded_by={}, params=P)
    assert m.e_pnl_lamports == 21 * (SOL // 5)
    assert (m.closed_non_neutral, m.mints, m.active_days, m.positive_days) == (21, 21, 7, 7)
    assert m.median_hold_seconds == 120.0
    assert failing_reasons(m, P) == ()


def test_max_drawdown_of_the_cumulative_daily_curve() -> None:
    assert max_drawdown((3, -1, -1, 4, -6, 1, 0)) == 6  # peak 5 after day 4, trough −1
    assert max_drawdown((-2, 1)) == 2  # the peak starts at zero


def test_activity_money_and_concentration_thresholds() -> None:
    few = OwnerBook("E", [_ep(i, SOL // 5) for i in range(19)])
    assert "activity_episodes" in failing_reasons(
        entity_metrics(few, FACTS, creates={}, funded_by={}, params=P), P
    )
    small = OwnerBook("E", [_ep(i, SOL // 20) for i in range(21)])  # E = 1.05 SOL
    assert "e_pnl_below_min" in failing_reasons(
        entity_metrics(small, FACTS, creates={}, funded_by={}, params=P), P
    )
    whale = _good_book()
    whale.episodes.append(_ep(30, 5 * SOL))  # one episode = 5 of 9.2 SOL > 50 %
    assert "largest_episode_share" in failing_reasons(
        entity_metrics(whale, FACTS, creates={}, funded_by={}, params=P), P
    )


def test_neutral_episodes_do_not_count_as_activity() -> None:
    book = _good_book()
    book.episodes[0] = _ep(0, SOL // 200)  # 0.5 % of a 1 SOL cost: neutral
    m = entity_metrics(book, FACTS, creates={}, funded_by={}, params=P)
    assert m.closed_non_neutral == 20


def test_drawdown_and_positive_day_rules() -> None:
    eps = [_ep(i, SOL, day=0) for i in range(20)] + [
        _ep(20 + i, -SOL // 2, day=1 + i) for i in range(6)
    ]
    m = entity_metrics(OwnerBook("E", eps), FACTS, creates={}, funded_by={}, params=P)
    reasons = failing_reasons(m, P)
    assert "positive_days" in reasons
    assert m.max_drawdown_lamports == 3 * SOL  # 20 → 17 SOL; 3 SOL ≤ max(1; 50 % of 17) passes
    assert "drawdown" not in reasons


def test_short_holders_fail_on_median_and_on_the_share_under_ten_seconds() -> None:
    book = OwnerBook("E", [_ep(i, SOL // 5, hold=5.0 if i < 6 else 120.0) for i in range(21)])
    m = entity_metrics(book, FACTS, creates={}, funded_by={}, params=P)
    assert m.short_hold_share == pytest.approx(6 / 21)
    assert "short_hold_share" in failing_reasons(m, P)


def test_creator_episodes_leave_and_too_many_exclude_the_entity() -> None:
    book = _good_book()
    creates = {f"M{i}": create(f"M{i}", "FUNDER" if i < 3 else "someone", 1) for i in range(21)}
    m = entity_metrics(book, FACTS, creates=creates, funded_by={"E": "FUNDER"}, params=P)
    assert m.creator_share == pytest.approx(3 / 21)
    assert m.closed_non_neutral == 18  # creator episodes are out of the metrics
    creates_all = {f"M{i}": create(f"M{i}", "E" if i < 6 else "x", 1) for i in range(21)}
    m2 = entity_metrics(book, FACTS, creates=creates_all, funded_by={}, params=P)
    assert "creator_share" in failing_reasons(m2, P)


def test_create_block_buys_leave_and_a_sniper_majority_excludes() -> None:
    book = OwnerBook("E", [_ep(i, SOL // 5, slot=102 if i < 7 else 1_000) for i in range(21)])
    creates = {f"M{i}": create(f"M{i}", "x", 100) for i in range(21)}
    m = entity_metrics(book, FACTS, creates=creates, funded_by={}, params=P)
    assert m.create_block_share == pytest.approx(7 / 21)
    assert "create_block_share" in failing_reasons(m, P)


def test_mev_round_trips_leave_the_metrics() -> None:
    book = _good_book()
    book.episodes[0].hold_slots = 2
    m = entity_metrics(book, FACTS, creates={}, funded_by={}, params=P)
    assert m.closed_non_neutral == 20


def test_volume_bot_unmatched_and_copyability() -> None:
    bot = EntityFacts(wallets=frozenset({"E"}), c_pnl_lamports=SOL, trades_previous_day=501)
    assert "volume_bot" in failing_reasons(
        entity_metrics(_good_book(), bot, creates={}, funded_by={}, params=P), P
    )
    book = _good_book()
    book.sold_atoms, book.unmatched_atoms = 100, 21
    assert "unmatched_share" in failing_reasons(
        entity_metrics(book, FACTS, creates={}, funded_by={}, params=P), P
    )
    loser = EntityFacts(wallets=frozenset({"E"}), c_pnl_lamports=0, trades_previous_day=0)
    assert "c_pnl_not_positive" in failing_reasons(
        entity_metrics(_good_book(), loser, creates={}, funded_by={}, params=P), P
    )


def test_incomplete_episodes_do_not_count_as_activity_and_are_reported() -> None:
    book = _good_book()
    book.episodes[0].incomplete = True
    m = entity_metrics(book, FACTS, creates={}, funded_by={}, params=P)
    assert (m.closed_non_neutral, m.incomplete_episodes) == (20, 1)


def test_contaminated_episodes_are_counted() -> None:
    book = _good_book()
    book.episodes[3].contaminated = True
    assert (
        entity_metrics(book, FACTS, creates={}, funded_by={}, params=P).contaminated_episodes == 1
    )


def test_a_day_at_exactly_zero_is_not_positive() -> None:
    eps = [_ep(i, SOL // 5, day=i % 3) for i in range(21)]  # days 0-2 positive, 3-6 zero
    m = entity_metrics(OwnerBook("E", eps), FACTS, creates={}, funded_by={}, params=P)
    assert m.positive_days == 3
    assert "positive_days" in failing_reasons(m, P)


def test_exactly_one_percent_is_not_neutral() -> None:
    book = _good_book()
    book.episodes[0] = _ep(0, SOL // 100)
    assert entity_metrics(book, FACTS, creates={}, funded_by={}, params=P).closed_non_neutral == 21
