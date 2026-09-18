"""The wallet policy from the environment (§3): all five or nothing, by name."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_risk_meme import MEME_PAPER_V0, POLICY_ENV, MemePolicyMissing, limits_from_env
from hunter_risk_meme.limits import ENV_CURVE_PROGRESS_MAX, ENV_CURVE_PROGRESS_MIN

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


# ------------------------------------------------- T4.58: the curve window from the env


def test_the_curve_window_is_the_bases_when_the_two_variables_are_absent() -> None:
    live = limits_from_env(FULL)
    assert live.curve_progress_min_pct == MEME_PAPER_V0.curve_progress_min_pct == Decimal("0.02")
    assert live.curve_progress_max_pct == MEME_PAPER_V0.curve_progress_max_pct == Decimal("0.50")


def test_the_paper_preset_keeps_its_window_untouched() -> None:
    assert (MEME_PAPER_V0.curve_progress_min_pct, MEME_PAPER_V0.curve_progress_max_pct) == (
        Decimal("0.02"),
        Decimal("0.50"),
    )


def test_a_valid_window_from_the_env_replaces_the_bases() -> None:
    live = limits_from_env(
        {**FULL, ENV_CURVE_PROGRESS_MIN: " 0.05 ", ENV_CURVE_PROGRESS_MAX: "1.0"}
    )
    assert live.curve_progress_min_pct == Decimal("0.05")
    assert live.curve_progress_max_pct == Decimal("1.0")


def test_only_the_max_given_keeps_the_bases_min() -> None:
    live = limits_from_env({**FULL, ENV_CURVE_PROGRESS_MAX: "1.0"})
    assert live.curve_progress_min_pct == Decimal("0.02")
    assert live.curve_progress_max_pct == Decimal("1.0")


@pytest.mark.parametrize("raw", ["half", "NaN", "Infinity", "-0.1", "1.5", "50%"])
def test_a_malformed_or_out_of_range_max_is_refused_by_name(raw: str) -> None:
    with pytest.raises(MemePolicyMissing) as info:
        limits_from_env({**FULL, ENV_CURVE_PROGRESS_MAX: raw})
    assert info.value.missing == ()
    assert info.value.invalid == (ENV_CURVE_PROGRESS_MAX,)
    assert ENV_CURVE_PROGRESS_MAX in str(info.value)


def test_a_malformed_min_is_refused_by_name() -> None:
    with pytest.raises(MemePolicyMissing) as info:
        limits_from_env({**FULL, ENV_CURVE_PROGRESS_MIN: "two"})
    assert info.value.invalid == (ENV_CURVE_PROGRESS_MIN,)


@pytest.mark.parametrize(
    "env",
    [
        {ENV_CURVE_PROGRESS_MIN: "0.6", ENV_CURVE_PROGRESS_MAX: "0.5"},
        {ENV_CURVE_PROGRESS_MIN: "0.5", ENV_CURVE_PROGRESS_MAX: "0.5"},
        {ENV_CURVE_PROGRESS_MAX: "0.01"},  # below the base's min of 0.02
        {ENV_CURVE_PROGRESS_MIN: "0.50"},  # equal to the base's max of 0.50
    ],
)
def test_an_inverted_or_empty_window_is_refused_with_the_window_in_the_message(
    env: dict[str, str],
) -> None:
    with pytest.raises(MemePolicyMissing) as info:
        limits_from_env({**FULL, **env})
    assert info.value.missing == ()
    assert set(info.value.invalid) == set(env)
    assert "curve_progress window is empty" in str(info.value)


def test_a_bad_window_is_named_alongside_the_five() -> None:
    env = {**FULL, "MEME_COOLDOWN_S": "soon", ENV_CURVE_PROGRESS_MAX: "x"}
    with pytest.raises(MemePolicyMissing) as info:
        limits_from_env(env)
    assert info.value.invalid == ("MEME_COOLDOWN_S", ENV_CURVE_PROGRESS_MAX)
