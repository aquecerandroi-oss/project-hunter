"""T4.96 — the small-test scope against the **whole** wallet debit, pure.

Measured on 161 confirmed buys (diary 2026-09-26, ``obsidian/09-OPERATIONS/Diario/2026-09-26.md``):
the counter charges ``fill.buy_total_lamports`` (curve + curve fees + network +
priority + ATA rent), but the clamp only bounded ``sol_final`` (curve + curve
fees) — debit − ``sol_final`` median +0,00156, max +0,00327 SOL, so the last
buy could pass ``max_total_sol``. Proved here, in lamports: the clamp leaves
room for the reserve (network + priority rounded **up** + ATA rent) and for the
instruction's own tolerance (``max_sol_cost = ceil(total × (1 + bps))``), so
``max_sol_cost + reserve <= remaining`` for every admissible buy; and the
"restante abaixo do mínimo do perfil" state (``small_test_below_min``) is
per profile, distinct from ``exhausted``.
"""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from hunter_core.execution.meme.gates import SmallTestAuthorization
from hunter_meme_executor.config import ExecutorConfig
from hunter_meme_executor.launch_config import LaunchConfig
from hunter_meme_executor.priority_fee import PriorityFeeChoice
from hunter_meme_executor.scope import (
    SMALL_TEST_BELOW_MIN,
    SMALL_TEST_SCOPE_EXHAUSTED,
    ScopeUse,
    below_min_profiles,
    buy_reserve_sol,
    legacy_extra_sol,
    scope_refusal,
    scope_use,
)
from hunter_meme_executor.send_tuning import SendTuning
from hunter_risk_meme import limits_from_env

pytestmark = pytest.mark.unit

LAMPORTS = Decimal(1_000_000_000)
POLICY = {
    "MEME_WALLET_MAX_SOL": "0.5",
    "MEME_MAX_SOL_PER_TRADE": "0.07",
    "MEME_DAILY_LOSS_CAP_SOL": "0.1",
    "MEME_MAX_OPEN_POSITIONS": "3",
    "MEME_COOLDOWN_S": "3600",
}
LIMITS = limits_from_env(POLICY)  # live floor 0,02; ATA rent 0,00203928; network 0,000005
SMALL = SmallTestAuthorization(
    authorized_by="everton",
    max_sol_per_trade=Decimal("0.07"),
    max_total_sol=Decimal("10"),
    max_trades=1000,
    expires_at=date(2026, 12, 31),
    decision_note="obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md",
)


def _use(used: str, requested: str = "0.07", trades: int = 161) -> ScopeUse:
    return scope_use(
        SMALL, trades_done=trades, used_sol=Decimal(used), requested_sol=Decimal(requested)
    )


def _config(*, launch: str = "off") -> ExecutorConfig:
    from hunter_core.domain.enums import KillSwitchState

    return ExecutorConfig(
        live=True,
        cluster="devnet",
        rpc_url="https://fake",
        limits=LIMITS,
        system_kill_switch=KillSwitchState.ACTIVE,
        kill_file=None,
        send=SendTuning(),
        launch=LaunchConfig(mode=launch),  # type: ignore[arg-type]
    )


# ---- the reserve -----------------------------------------------------------------------


def test_the_reserve_is_network_plus_priority_rounded_up_plus_the_ata_rent() -> None:
    # 400 000 CU x 100 001 micro-lamports = 40 000,4 lamports: Solana charges 40 001.
    fee = PriorityFeeChoice.static(100_001)
    with_ata = buy_reserve_sol(_config(), fee, creates_ata=True)
    assert with_ata == Decimal("0.000005") + Decimal("0.000040001") + Decimal("0.00203928")
    without = buy_reserve_sol(_config(), fee, creates_ata=False)
    assert without == Decimal("0.000005") + Decimal("0.000040001")


def test_the_legacy_extra_is_network_rent_and_the_priority_cap() -> None:
    cfg = _config()
    assert legacy_extra_sol(cfg) == (
        LIMITS.network_fee_sol + LIMITS.ata_rent_sol + cfg.send.priority_fee_max_sol
    )


# ---- the clamp covers the whole debit ------------------------------------------------------


def test_without_a_reserve_the_clamp_is_what_it_was() -> None:
    use = _use("9.95")
    assert use.usable_sol == Decimal("0.05") and use.requested_cap_sol == Decimal("0.05")


def test_the_clamp_leaves_room_for_the_reserve_and_the_tolerance() -> None:
    reserve = Decimal("0.00208428")
    use = _use("9.95").for_buy(reserve, 100)  # 1 % tolerance on the curve leg
    room = 50_000_000 - 2_084_280
    assert use.usable_sol == Decimal(room * 10_000 // 10_100) / LAMPORTS
    assert use.requested_cap_sol == use.usable_sol and use.requested_clamped
    budget = int(use.usable_sol * LAMPORTS)
    worst_curve = -(-budget * 10_100 // 10_000)
    assert worst_curve + 2_084_280 <= 50_000_000


def test_a_request_inside_the_room_passes_whole() -> None:
    use = _use("9.5").for_buy(Decimal("0.0025"), 100)
    assert use.requested_cap_sol == Decimal("0.07") and not use.requested_clamped


def test_a_fractional_remaining_is_floored_to_lamports_first() -> None:
    """Astra's arithmetic case: 21 000 001,1 lamports of room at 500 bps — a
    budget computed on the fraction would allow a 21 000 002 worst case."""
    small = replace(SMALL, max_total_sol=Decimal("0.0210000011"))
    use = scope_use(small, trades_done=0, used_sol=Decimal(0), requested_sol=Decimal("0.05"))
    use = use.for_buy(Decimal(0), 500)
    budget = int(use.usable_sol * LAMPORTS)
    assert -(-budget * 10_500 // 10_000) <= 21_000_001


def test_the_worst_case_debit_never_passes_what_is_left_property() -> None:
    rng = random.Random(496)
    for _ in range(5_000):
        remaining_l = rng.randint(0, 80_000_000)
        remaining = Decimal(remaining_l) / LAMPORTS + Decimal(rng.randint(0, 9)) / (LAMPORTS * 10)
        micro = rng.randint(0, 3_000_000)
        cu = rng.choice([100_000, 200_000, 400_000])
        creates_ata = rng.random() < 0.8
        bps = rng.randint(0, 2_000)
        cfg = replace(_config(), compute_unit_limit=cu)
        reserve = buy_reserve_sol(cfg, PriorityFeeChoice.static(micro), creates_ata=creates_ata)
        small = replace(SMALL, max_total_sol=Decimal("10"))
        use = scope_use(
            small,
            trades_done=0,
            used_sol=Decimal("10") - remaining,
            requested_sol=Decimal("0.07"),
        ).for_buy(reserve, bps)
        budget = int(use.requested_cap_sol * LAMPORTS)
        curve = -(-budget * (10_000 + bps) // 10_000)
        priority = -(-cu * micro // 1_000_000)
        rent = 2_039_280 if creates_ata else 0
        debit = curve + 5_000 + priority + rent
        assert budget == 0 or Decimal(debit) / LAMPORTS <= remaining, (remaining, reserve, bps)


# ---- the named states ------------------------------------------------------------------------


def test_the_measured_remainder_is_below_the_live_floor_not_exhausted() -> None:
    """26/09: 9,987575929 used of 10 → 0,012424071 left, floor 0,02."""
    use = _use("9.987575929")
    assert use.exhausted is None
    assert scope_refusal(use, LIMITS.min_trade_sol) == (SMALL_TEST_BELOW_MIN, use.as_json())


def test_exhausted_wins_over_below_min_and_none_is_no_scope() -> None:
    assert scope_refusal(_use("10"), Decimal("0.02"))[0] == SMALL_TEST_SCOPE_EXHAUSTED  # type: ignore[index]
    full = _use("1", trades=1000)
    assert scope_refusal(full, Decimal("0.02"))[0] == SMALL_TEST_SCOPE_EXHAUSTED  # type: ignore[index]
    assert scope_refusal(None, Decimal("0.02")) is None


def test_the_floor_is_per_profile_the_launch_floor_is_lower() -> None:
    use = _use("9.985")  # 0,015 left
    assert scope_refusal(use, Decimal("0.02")) is not None
    assert scope_refusal(use, Decimal("0.01")) is None


def test_below_min_counts_the_reserve_it_is_given() -> None:
    use = _use("9.978")  # 0,022 left: above the 0,02 floor on the curve alone
    assert scope_refusal(use, Decimal("0.02")) is None
    tight = use.for_buy(Decimal("0.00208428"), 100)
    assert scope_refusal(tight, Decimal("0.02")) == (SMALL_TEST_BELOW_MIN, tight.as_json())


def test_the_json_names_the_reserve_the_tolerance_and_the_usable_budget() -> None:
    payload = _use("9.95").for_buy(Decimal("0.002"), 100).as_json()
    assert payload["debit_reserve_sol"] == "0.002" and payload["buy_slippage_bps"] == 100
    assert Decimal(payload["usable_sol"]) < Decimal("0.048")


# ---- the heartbeat's per-profile state -------------------------------------------------------


def test_below_min_profiles_names_the_full_profile_on_the_measured_remainder() -> None:
    assert below_min_profiles(_use("9.987575929"), _config()) == ["full"]


def test_below_min_profiles_is_per_profile_and_launch_only_when_on() -> None:
    # 0,015 left: under the live floor (0,02), over the launch floor (0,01 + rent).
    assert below_min_profiles(_use("9.985"), _config(launch="on")) == ["full"]
    # 0,005 left: under both.
    assert below_min_profiles(_use("9.995"), _config(launch="on")) == ["full", "launch"]
    assert below_min_profiles(_use("9.995"), _config()) == ["full"]


def test_below_min_profiles_is_empty_when_exhausted_or_healthy() -> None:
    assert below_min_profiles(_use("10"), _config(launch="on")) == []
    assert below_min_profiles(_use("5"), _config(launch="on")) == []
