"""Unit tests for ``infra/scripts/pumpfun_rt_probe_sel.py`` — which per-mint and per-wallet NATS subjects the
latency probe opens, and when it lets them go (caps keep it to what a browsing visitor would hold).

Run:
    uv run --no-sync pytest infra/scripts/tests/test_pumpfun_rt_probe_sel.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:  # the layout every script in this folder uses
    sys.path.insert(0, str(SCRIPTS_DIR))

from pumpfun_rt_probe_sel import MintPlan, WalletPlan  # noqa: E402  (path surgery must come first)


def test_new_mint_opens_a_processed_subject_and_a_lite_one_while_lite_slots_last() -> None:
    plan = MintPlan(max_mints=3, hold_s=60, lite_max=1)
    assert plan.on_creation("M1", now=0.0) == [
        "unifiedTradeEvent.processed.M1",
        "unifiedTradeEvent.lite.M1",
    ]
    assert plan.on_creation("M2", now=1.0) == ["unifiedTradeEvent.processed.M2"]  # lite full


def test_a_full_plan_skips_and_counts_instead_of_growing() -> None:
    plan = MintPlan(max_mints=1, hold_s=60, lite_max=0)
    plan.on_creation("M1", now=0.0)
    assert plan.on_creation("M2", now=1.0) == []
    assert plan.skipped == 1


def test_the_same_mint_twice_opens_nothing_twice() -> None:
    plan = MintPlan(max_mints=5, hold_s=60, lite_max=5)
    plan.on_creation("M1", now=0.0)
    assert plan.on_creation("M1", now=0.5) == []
    assert plan.skipped == 0


def test_expiry_returns_the_subjects_to_drop_and_frees_the_slot_and_the_lite_slot() -> None:
    plan = MintPlan(max_mints=1, hold_s=60, lite_max=1)
    plan.on_creation("M1", now=0.0)
    assert plan.expire(now=59.9) == []
    assert sorted(plan.expire(now=60.1)) == [
        "unifiedTradeEvent.lite.M1",
        "unifiedTradeEvent.processed.M1",
    ]
    assert plan.on_creation("M2", now=61.0) == [
        "unifiedTradeEvent.processed.M2",
        "unifiedTradeEvent.lite.M2",
    ]


def test_is_active_tells_the_reader_which_mints_are_in_the_window() -> None:
    plan = MintPlan(max_mints=2, hold_s=10, lite_max=0)
    plan.on_creation("M1", now=0.0)
    assert plan.is_active("M1") and not plan.is_active("M9")
    plan.expire(now=11.0)
    assert not plan.is_active("M1")


def test_wallet_is_followed_from_its_second_trade_and_only_up_to_the_cap() -> None:
    plan = WalletPlan(max_wallets=2, min_trades=2)
    assert plan.on_trade("W1") is None  # first sighting
    assert plan.on_trade("W1") == "account_balance_change.W1.*"
    assert plan.on_trade("W1") is None  # already followed
    plan.on_trade("W2")
    assert plan.on_trade("W2") == "account_balance_change.W2.*"
    plan.on_trade("W3")
    assert plan.on_trade("W3") is None  # cap reached
    assert plan.followed == {"W1", "W2"}
