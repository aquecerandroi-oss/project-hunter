"""``hunter_indicators.meme.crowd`` (T4.66, EXP-M19) — the early wallets'
retention with partial sells and the clamp at zero, the unknowns by name
(window not covered, gap, no early set, tokens unknown), the quick flips and
the new wallets of the last 30 s, non-anticipation, and the gate: the four
keys off leave every verdict untouched; on, each refuses by its own name."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.crowd import (
    COVERAGE_GAP,
    CROWD_DEFINITIONS,
    NO_EARLY_WALLETS,
    NO_TRADES_IN_WINDOW,
    NOT_COVERED_FROM_BIRTH,
    TOKENS_UNKNOWN,
    WINDOW_NOT_COVERED,
    CrowdLedger,
    CrowdTrade,
)
from hunter_indicators.meme.rules import EntryFeatures, EntryGate, evaluate_entry
from hunter_indicators.meme.rules_crowd import crowd_refusals

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 19, 3, 0, 0, tzinfo=UTC)
"""The create; the subscription covers the mint from here."""
CREATOR = "DEV"
LAG = timedelta(milliseconds=500)


def _t(
    at_s: float, trader: str, side: str, tokens: str | None = "100", *, slot: int | None = None
) -> CrowdTrade:
    at = T0 + timedelta(seconds=at_s)
    return CrowdTrade(
        block_time=at,
        received_at=at + LAG,
        trader=trader,
        side=side,
        tokens=None if tokens is None else Decimal(tokens),
        slot=slot,
    )


def _ledger(trades: list[CrowdTrade], **kwargs: object) -> CrowdLedger:
    ledger = CrowdLedger(covered_since=T0, creator=CREATOR, **kwargs)  # type: ignore[arg-type]
    for trade in trades:
        ledger.push(trade)
    return ledger


def _early_set(n: int = 10, *, start_s: float = 0.4) -> list[CrowdTrade]:
    """The creator's dev buy, then ``n`` snipers buying 100 tokens each."""
    return [_t(0.0, CREATOR, "buy", "5000")] + [
        _t(start_s + i * 0.1, f"S{i}", "buy") for i in range(n)
    ]


def test_definitions_are_registered_with_the_frozen_numbers() -> None:
    keys = {d.key: d for d in CROWD_DEFINITIONS}
    assert set(keys) == {
        "early_retention_pct",
        "early_age_s",
        "new_wallets_30s",
        "quick_flip_share_30s",
    }
    assert keys["early_retention_pct"].params == {"early_slots": 3, "early_buyers": 10}
    assert keys["quick_flip_share_30s"].params == {"window_s": 30, "quick_flip_s": 20}
    assert all(d.version == 1 for d in CROWD_DEFINITIONS)


def test_retention_with_partial_sells_and_the_clamp_at_zero() -> None:
    """Ten early wallets, 100 each (1 000 bought). S0 sells 50, S1 sells all
    100, S2 sells 150 (fed by a transfer the ledger never saw: clamped to 0,
    not −50). Held = 1 000 − 50 − 100 − 100 = 750 → 0,75. The creator's 5 000
    are not in the denominator."""
    trades = _early_set() + [
        _t(70, "S0", "sell", "50"),
        _t(71, "S1", "sell", "100"),
        _t(72, "S2", "sell", "150"),
        _t(73, "LATE", "buy", "900"),  # an 11th buyer: never early
    ]
    ledger = _ledger(trades)
    assert ledger.early_wallets == frozenset(f"S{i}" for i in range(10))
    f = ledger.features(T0 + timedelta(seconds=80), covered_from_birth=True)
    assert f.early_retention_pct == Decimal("0.750000")
    assert f.early_age_s == Decimal("79.600")  # the earliest early buy was at 0,4 s
    assert f.early_wallets == 10
    assert f.early_reason is None


def test_retention_is_one_while_nobody_sold_and_falls_as_they_distribute() -> None:
    ledger = _ledger(_early_set(3))
    at = T0 + timedelta(seconds=40)
    assert ledger.features(at, covered_from_birth=True).early_retention_pct == Decimal("1.000000")
    for i in range(3):
        ledger.push(_t(41 + i, f"S{i}", "sell", "100"))
    at = T0 + timedelta(seconds=50)
    assert ledger.features(at, covered_from_birth=True).early_retention_pct == Decimal("0.000000")


def test_early_wallets_by_slot_when_the_create_slot_is_known() -> None:
    """Blocks 1–3 = the create slot and the two after it; a buyer in the
    fourth slot is not early even though fewer than ten bought."""
    trades = [
        _t(0.0, CREATOR, "buy", "5000", slot=100),
        _t(0.4, "A", "buy", slot=100),
        _t(0.8, "B", "buy", slot=101),
        _t(1.2, "C", "buy", slot=102),
        _t(1.6, "D", "buy", slot=103),
    ]
    ledger = _ledger(trades, create_slot=100)
    assert ledger.early_wallets == frozenset({"A", "B", "C"})


def test_unknown_when_not_covered_from_birth_after_a_gap_or_without_tokens() -> None:
    at = T0 + timedelta(seconds=80)
    ledger = _ledger(_early_set())
    blind = ledger.features(at, covered_from_birth=False)
    assert (blind.early_retention_pct, blind.early_age_s, blind.early_reason) == (
        None,
        None,
        NOT_COVERED_FROM_BIRTH,
    )
    ledger.mark_gap(T0 + timedelta(seconds=30))
    gapped = ledger.features(at, covered_from_birth=True)
    assert gapped.early_reason == COVERAGE_GAP and gapped.early_retention_pct is None
    warming = ledger.features(T0 + timedelta(seconds=59.9), covered_from_birth=True)
    assert warming.window_reason == WINDOW_NOT_COVERED  # 30 s of coverage needed again
    no_tokens = _ledger([_t(0.4, "S0", "buy", None)])
    assert no_tokens.features(at, covered_from_birth=True).early_reason == TOKENS_UNKNOWN
    empty = _ledger([_t(0.0, CREATOR, "buy", "5000")])
    assert empty.features(at, covered_from_birth=True).early_reason == NO_EARLY_WALLETS


def test_window_not_covered_until_thirty_seconds_of_feed() -> None:
    ledger = _ledger(_early_set())
    early = ledger.features(T0 + timedelta(seconds=29.9), covered_from_birth=True)
    assert early.new_wallets_30s is None and early.window_reason == WINDOW_NOT_COVERED
    exact = ledger.features(T0 + timedelta(seconds=30), covered_from_birth=True)
    assert exact.window_reason is None


def test_new_wallets_and_quick_flips_of_the_last_thirty_seconds() -> None:
    """At t = 100 s the window is (70, 100]. Inside it: N1..N5 first trades
    (new), S0 (early, old) sells 100 s after buying (not quick), N1 buys at
    75 and sells at 90 (quick: 15 s < 20 s), N2 buys at 76 and sells at 99
    (23 s: not quick), the creator sells (old wallet). Trades in the window:
    5 new buys + S0 sell + N1 sell + N2 sell + DEV sell = 9; quick = 1."""
    trades = _early_set() + [
        _t(75, "N1", "buy"),
        _t(76, "N2", "buy"),
        _t(77, "N3", "buy"),
        _t(78, "N4", "buy"),
        _t(79, "N5", "buy"),
        _t(90, "N1", "sell"),
        _t(95, "S0", "sell"),
        _t(98, CREATOR, "sell", "1000"),
        _t(99, "N2", "sell"),
    ]
    f = _ledger(trades).features(T0 + timedelta(seconds=100), covered_from_birth=True)
    assert f.new_wallets_30s == 5
    assert f.quick_flip_share_30s == Decimal("0.111111")
    assert f.window_reason is None


def test_a_flip_share_over_no_trade_is_unknown_and_zero_new_wallets_is_a_zero() -> None:
    f = _ledger(_early_set()).features(T0 + timedelta(seconds=60), covered_from_birth=True)
    assert f.new_wallets_30s == 0
    assert f.quick_flip_share_30s is None and f.window_reason == NO_TRADES_IN_WINDOW


def test_a_fill_received_after_as_of_never_counts() -> None:
    """S0's sell at 70 s reaches us at 70,5 s: judged at 70,4 s the retention
    is still 1; a millisecond after the receipt it is 0,9."""
    ledger = _ledger(_early_set() + [_t(70, "S0", "sell", "100")])
    before = ledger.features(T0 + timedelta(seconds=70.4), covered_from_birth=True)
    after = ledger.features(T0 + timedelta(seconds=70.501), covered_from_birth=True)
    assert before.early_retention_pct == Decimal("1.000000")
    assert after.early_retention_pct == Decimal("0.900000")
    # the window too: the late-received sell is not one of the window's trades
    assert before.quick_flip_share_30s is None and after.quick_flip_share_30s == Decimal("0")


def test_the_window_deque_is_bounded_by_time() -> None:
    ledger = _ledger([_t(i, f"W{i}", "buy") for i in range(0, 200, 2)])
    f = ledger.features(T0 + timedelta(seconds=198.5), covered_from_birth=True)
    assert f.new_wallets_30s == 15  # first trades in (168,5; 198,5]: 170, 172, …, 198
    assert len(ledger._recent) <= 16  # pyright: ignore[reportPrivateUsage]


# -- the gate ---------------------------------------------------------------


def _gate(**overrides: object) -> EntryGate:
    base: dict[str, object] = {
        "key": "crowd_test",
        "version": 1,
        "description": "t",
        "min_age_s": 0,
        "max_age_s": 600,
        "min_progress_pct": Decimal(0),
        "max_progress_pct": Decimal(100),
        "max_participation_pct": Decimal(100),
        "require_creator_not_net_seller": False,
        "require_progress": False,
        "exclude_mayhem": False,
    }
    base.update(overrides)
    return EntryGate(**base)  # type: ignore[arg-type]


def _features(**overrides: object) -> EntryFeatures:
    base: dict[str, object] = {
        "mint": "M",
        "age_s": 90,
        "progress_pct": Decimal(10),
        "creator_net_seller": False,
        "curve_volume_1m_sol": Decimal(10),
        "intended_size_sol": Decimal("0.05"),
    }
    base.update(overrides)
    return EntryFeatures(**base)  # type: ignore[arg-type]


def test_keys_off_leave_the_verdict_and_the_parameters_untouched() -> None:
    gate = _gate()
    assert crowd_refusals(_features(), gate) == []
    assert evaluate_entry(_features(), gate).allowed
    assert not any(
        k.startswith(("min_early", "min_new", "max_quick")) for k in gate.as_parameters()
    )
    # a row with the crowd measured is judged the same by a gate that does not ask
    measured = _features(
        early_retention_pct=Decimal("0.1"),
        early_age_s=Decimal(5),
        new_wallets_30s=0,
        quick_flip_share_30s=Decimal("0.9"),
    )
    assert evaluate_entry(measured, gate).allowed


ARM = {
    "min_early_retention_pct": Decimal("0.70"),
    "min_early_age_s": 60,
    "min_new_wallets_30s": 5,
    "max_quick_flip_share_30s": Decimal("0.20"),
}


def test_each_criterion_refuses_by_name_and_unknown_fails_closed() -> None:
    gate = _gate(**ARM)
    good = _features(
        early_retention_pct=Decimal("0.90"),
        early_age_s=Decimal(75),
        new_wallets_30s=7,
        quick_flip_share_30s=Decimal("0.10"),
    )
    assert evaluate_entry(good, gate).allowed
    assert crowd_refusals(replace(good, early_retention_pct=Decimal("0.40")), gate) == [
        "early_retention_below_min"
    ]
    assert crowd_refusals(replace(good, early_age_s=Decimal(59)), gate) == ["early_age_below_min"]
    assert crowd_refusals(replace(good, new_wallets_30s=4), gate) == ["new_wallets_below_min"]
    assert crowd_refusals(replace(good, quick_flip_share_30s=Decimal("0.21")), gate) == [
        "quick_flip_above_max"
    ]
    # the edges: equal passes (floor inclusive, ceiling inclusive)
    edge = replace(
        good,
        early_retention_pct=Decimal("0.70"),
        early_age_s=Decimal(60),
        new_wallets_30s=5,
        quick_flip_share_30s=Decimal("0.20"),
    )
    assert crowd_refusals(edge, gate) == []
    # the 15-second lane's row: every field None — three unknowns, by name
    assert crowd_refusals(_features(), gate) == [
        "early_retention_unknown",
        "new_wallets_unknown",
        "quick_flip_unknown",
    ]
    assert gate.as_parameters()["min_early_retention_pct"] == "0.70"
    assert gate.as_parameters()["max_quick_flip_share_30s"] == "0.20"
    assert gate.as_parameters()["min_early_age_s"] == "60"


def test_validation_rejects_a_zero_retention_floor_and_a_share_above_one() -> None:
    with pytest.raises(ValueError, match="min_early_retention_pct"):
        _gate(min_early_retention_pct=Decimal(0))
    with pytest.raises(ValueError, match="max_quick_flip_share_30s"):
        _gate(max_quick_flip_share_30s=Decimal("1.5"))
    with pytest.raises(ValueError, match="min_new_wallets_30s"):
        _gate(min_new_wallets_30s=-1)
    with pytest.raises(ValueError, match="min_early_age_s"):
        _gate(min_early_age_s=-1)
