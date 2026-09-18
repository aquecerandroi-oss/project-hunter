"""T4.54 — ``MEME_TREASURY_*`` parsing: defaults, valid overrides, and every
unreadable/out-of-range value falling back to the safe default rather than
refusing the boot (these are sizing knobs, not the five policy variables)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_meme_executor.config import boot

pytestmark = pytest.mark.unit

TODAY = date(2026, 9, 17)


def _boot(env: dict[str, str]):
    return boot(env, today=TODAY, system_kill_switch=KillSwitchState.ACTIVE)


def test_defaults_with_nothing_set() -> None:
    config, _, _ = _boot({})
    assert config.treasury_enabled is False
    assert config.treasury_sol_floor == Decimal("0.30")
    assert config.treasury_sol_target == Decimal("0.60")
    assert config.treasury_max_usdc_per_swap == Decimal("25")
    assert config.treasury_max_usdc_per_day == Decimal("50")
    assert config.treasury_max_slippage_bps == 50
    assert config.treasury_min_interval_s == 600.0


def test_every_flag_can_be_overridden() -> None:
    env = {
        "MEME_TREASURY_ENABLED": "true",
        "MEME_TREASURY_SOL_FLOOR": "0.25",
        "MEME_TREASURY_SOL_TARGET": "0.75",
        "MEME_TREASURY_MAX_USDC_PER_SWAP": "10",
        "MEME_TREASURY_MAX_USDC_PER_DAY": "20",
        "MEME_TREASURY_MAX_SLIPPAGE_BPS": "75",
        "MEME_TREASURY_MIN_INTERVAL_S": "300",
    }
    config, _, _ = _boot(env)
    assert config.treasury_enabled is True
    assert config.treasury_sol_floor == Decimal("0.25")
    assert config.treasury_sol_target == Decimal("0.75")
    assert config.treasury_max_usdc_per_swap == Decimal("10")
    assert config.treasury_max_usdc_per_day == Decimal("20")
    assert config.treasury_max_slippage_bps == 75
    assert config.treasury_min_interval_s == 300.0


@pytest.mark.parametrize(
    "name,bad",
    [
        ("MEME_TREASURY_SOL_FLOOR", "not-a-number"),
        ("MEME_TREASURY_SOL_FLOOR", "-1"),
        ("MEME_TREASURY_SOL_FLOOR", "0"),
        ("MEME_TREASURY_MAX_USDC_PER_SWAP", "abc"),
        ("MEME_TREASURY_MAX_USDC_PER_DAY", "-5"),
    ],
)
def test_unreadable_or_non_positive_decimals_fall_back_to_the_default(name: str, bad: str) -> None:
    config, _, _ = _boot({name: bad})
    defaults = {
        "MEME_TREASURY_SOL_FLOOR": Decimal("0.30"),
        "MEME_TREASURY_MAX_USDC_PER_SWAP": Decimal("25"),
        "MEME_TREASURY_MAX_USDC_PER_DAY": Decimal("50"),
    }
    field = {
        "MEME_TREASURY_SOL_FLOOR": "treasury_sol_floor",
        "MEME_TREASURY_MAX_USDC_PER_SWAP": "treasury_max_usdc_per_swap",
        "MEME_TREASURY_MAX_USDC_PER_DAY": "treasury_max_usdc_per_day",
    }[name]
    assert getattr(config, field) == defaults[name]


@pytest.mark.parametrize("bad", ["0", "-1", "10001", "not-a-number"])
def test_slippage_bps_out_of_range_falls_back_to_the_default(bad: str) -> None:
    config, _, _ = _boot({"MEME_TREASURY_MAX_SLIPPAGE_BPS": bad})
    assert config.treasury_max_slippage_bps == 50


def test_the_flag_off_is_the_only_default_that_matters_at_boot() -> None:
    """Everton's flag: nothing else in this module is read unless it is on."""
    config, _, _ = _boot({"MEME_TREASURY_SOL_FLOOR": "0.99"})
    assert config.treasury_enabled is False
    assert config.treasury_sol_floor == Decimal("0.99"), "still parsed, just inert while off"
