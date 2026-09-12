"""The wallet policy from the environment (§3): all five or nothing, by name."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_risk_meme import MEME_PAPER_V0, POLICY_ENV, MemePolicyMissing, limits_from_env

pytestmark = pytest.mark.unit

FULL = {
    "MEME_WALLET_MAX_SOL": "0.5",
    "MEME_MAX_SOL_PER_TRADE": "0.02",
    "MEME_DAILY_LOSS_CAP_SOL": "0.05",
    "MEME_MAX_OPEN_POSITIONS": "2",
    "MEME_COOLDOWN_S": "1800",
}


def test_a_full_policy_becomes_the_live_profile() -> None:
    live = limits_from_env(FULL)
    assert live.profile == "meme_live_v0"
    assert live.wallet_max_sol == Decimal("0.5")
    assert live.max_sol_per_trade == Decimal("0.02")
    assert live.max_exposure_per_mint_sol == Decimal("0.02"), "v0: no reinforcement"
    assert live.daily_loss_cap_sol == Decimal("0.05")
    assert live.max_open_positions == 2
    assert live.rug_cooldown_s == 1800
    assert live.token_age_max_s == MEME_PAPER_V0.token_age_max_s


@pytest.mark.parametrize("missing", POLICY_ENV)
def test_each_missing_variable_is_named_in_the_refusal(missing: str) -> None:
    env = {k: v for k, v in FULL.items() if k != missing}
    with pytest.raises(MemePolicyMissing) as info:
        limits_from_env(env)
    assert info.value.missing == (missing,)
    assert info.value.reason == "policy_missing"


def test_an_empty_value_counts_as_missing_and_a_malformed_one_as_invalid() -> None:
    env = {**FULL, "MEME_WALLET_MAX_SOL": "  ", "MEME_MAX_OPEN_POSITIONS": "two"}
    with pytest.raises(MemePolicyMissing) as info:
        limits_from_env(env)
    assert info.value.missing == ("MEME_WALLET_MAX_SOL",)
    assert info.value.invalid == ("MEME_MAX_OPEN_POSITIONS",)


def test_a_policy_that_contradicts_itself_is_refused() -> None:
    with pytest.raises(ValueError, match="max_sol_per_trade cannot exceed wallet_max_sol"):
        limits_from_env({**FULL, "MEME_MAX_SOL_PER_TRADE": "1"})
