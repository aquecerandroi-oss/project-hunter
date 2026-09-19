"""T4.67b — the prebuilt send: the blockhash cache is fresh for 5 s, refreshed
when older, unusable past 30 s (then fetched on the path and counted), and a
failed refresh keeps the previous value; the launch priority fee is
``min(max(p75, launch_floor), cap)`` with the winning bound named; the launch
submit policy carries the owner's simulation choice and a 0,5 s poll."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_meme_executor.config import ExecutorConfig
from hunter_meme_executor.launch_config import LaunchConfig
from hunter_meme_executor.launch_send import (
    BLOCKHASH_MAX_AGE_S,
    BlockhashCache,
    launch_priority_fee,
    launch_submit_policy,
)
from hunter_meme_executor.priority_fee import PriorityFeeChoice, cap_micro_lamports
from hunter_meme_executor.send_tuning import SendTuning
from hunter_risk_meme import MEME_PAPER_V0

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 19, 15, 0, tzinfo=UTC)


@dataclass
class FakeChain:
    fetches: int = 0
    fail: bool = False

    def blockhash(self) -> tuple[str, int]:
        self.fetches += 1
        if self.fail:
            raise RuntimeError("rpc down")
        return f"hash{self.fetches}", 100 + self.fetches


def test_the_cache_is_fresh_for_five_seconds_and_refreshed_after() -> None:
    chain, cache = FakeChain(), BlockhashCache()
    assert cache.is_fresh(T0) is False and cache.usable(T0) is None
    cache.refresh_if_stale(chain, now=T0)
    assert chain.fetches == 1 and cache.value is not None
    assert cache.value.blockhash == "hash1" and cache.value.last_valid_block_height == 101
    cache.refresh_if_stale(chain, now=T0 + timedelta(seconds=4.9))
    assert chain.fetches == 1, "younger than 5 s: no fetch"
    assert cache.is_fresh(T0 + timedelta(seconds=4.9))
    cache.refresh_if_stale(chain, now=T0 + timedelta(seconds=5))
    assert chain.fetches == 2 and cache.value.blockhash == "hash2"
    assert cache.refreshes == 2


def test_a_buy_signs_with_the_cache_and_fetches_only_when_it_is_unusable() -> None:
    chain, cache = FakeChain(), BlockhashCache()
    cache.refresh(chain, now=T0)
    signed = cache.for_signing(chain, now=T0 + timedelta(seconds=12))
    assert signed is not None and signed.blockhash == "hash1"
    assert chain.fetches == 1 and cache.fetched_on_path == 0, "12 s old: still usable, no fetch"
    edge = cache.for_signing(chain, now=T0 + timedelta(seconds=BLOCKHASH_MAX_AGE_S))
    assert edge is not None and edge.blockhash == "hash2"
    assert chain.fetches == 2 and cache.fetched_on_path == 1, "30 s old: fetched on the path"


def test_a_failed_refresh_keeps_the_previous_value_and_counts() -> None:
    chain, cache = FakeChain(), BlockhashCache()
    cache.refresh(chain, now=T0)
    chain.fail = True
    kept = cache.refresh(chain, now=T0 + timedelta(seconds=6))
    assert kept is not None and kept.blockhash == "hash1"
    assert cache.refresh_failures == 1 and cache.value is kept
    assert cache.describe(T0 + timedelta(seconds=6))["launch_blockhash_age_s"] == "6.0"
    none_yet = BlockhashCache()
    assert none_yet.for_signing(FakeChain(fail=True), now=T0) is None
    assert none_yet.refresh_failures == 1 and none_yet.fetched_on_path == 1


def _choice(micro: int, source: str = "p75", p75: int | None = None) -> PriorityFeeChoice:
    return PriorityFeeChoice(micro, source, p75, 100_000, 5_000_000, 50)


def test_the_launch_floor_lifts_a_quiet_curve_and_the_cap_holds_a_fought_one() -> None:
    cap = cap_micro_lamports(Decimal("0.002"), 400_000)
    assert cap == 5_000_000
    lifted = launch_priority_fee(
        _choice(100_000, "floor", 20_000),
        launch_floor=1_000_000,
        max_sol=Decimal("0.002"),
        compute_unit_limit=400_000,
    )
    assert lifted.micro_lamports == 1_000_000 and lifted.source == "launch_floor"
    assert lifted.floor_micro_lamports == 1_000_000 and lifted.p75_micro_lamports == 20_000
    kept = launch_priority_fee(
        _choice(2_500_000, "p75", 2_500_000),
        launch_floor=1_000_000,
        max_sol=Decimal("0.002"),
        compute_unit_limit=400_000,
    )
    assert kept.micro_lamports == 2_500_000 and kept.source == "p75"
    capped = launch_priority_fee(
        _choice(9_000_000, "p75", 9_000_000),
        launch_floor=1_000_000,
        max_sol=Decimal("0.002"),
        compute_unit_limit=400_000,
    )
    assert capped.micro_lamports == cap and capped.source == "cap"
    floor_above_cap = launch_priority_fee(
        _choice(100_000, "floor", None),
        launch_floor=50_000_000,
        max_sol=Decimal("0.002"),
        compute_unit_limit=400_000,
    )
    assert floor_above_cap.micro_lamports == cap and floor_above_cap.source == "cap"
    assert floor_above_cap.fee_sol(400_000) == Decimal("0.002")


def test_the_launch_submit_policy_carries_the_simulation_choice_and_a_half_second_poll() -> None:
    @dataclass
    class Rpc:
        allow_send: bool = True

    cfg = ExecutorConfig(
        live=True,
        cluster="devnet",
        rpc_url="https://fake",
        limits=MEME_PAPER_V0,
        system_kill_switch=KillSwitchState.ACTIVE,
        kill_file=None,
        send=SendTuning(resend_interval_s=1.5),
    )
    rpc: Any = Rpc()
    policy = launch_submit_policy(cfg, LaunchConfig(mode="on"), rpc)
    assert policy.skip_simulation is False and policy.poll_interval_s == 0.5
    assert policy.resend_interval_s == 1.5 and policy.allow_send is True
    skipping = launch_submit_policy(cfg, LaunchConfig(mode="on", skip_simulation=True), rpc)
    assert skipping.skip_simulation is True
    inert = launch_submit_policy(replace(cfg, live=False), LaunchConfig(mode="on"), rpc)
    assert inert.allow_send is False
