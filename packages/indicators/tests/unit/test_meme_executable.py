"""T4.27 — the Mayhem agent's virtual SOL is not price: the mark and the
market cap never claim more SOL than the curve holds, and the gate refuses a
Mayhem coin by name.

The exact fixture is ``test_meme_curve.py``'s tiny curve (``30 SOL`` against
``300`` tokens, ``k = 9000``) pushed the way the agent pushes it: the virtual
SOL reserve multiplied by ten (``300``) with **5 SOL** of real SOL in the
vault. Selling 100 tokens then quotes ``300 * 100 / 400 = 75`` SOL — fifteen
times what the vault could pay — and the ceiling cuts it to 5, fee on what
leaves (``5 * 1,25 % = 0,0625``, net ``4,9375``). On a standard curve the
ceiling is a no-op by construction (the vault *is* what every buyer paid in),
which Hypothesis checks over every buy-then-sell path of the tiny curve.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hunter_indicators.meme.curve import (
    CurveReserves,
    quote_sell,
    reserves_after_buy,
    sell_all_value_sol,
    sell_proceeds,
)
from hunter_indicators.meme.executable import (
    EXECUTABLE_DEFINITIONS,
    executable_market_cap_sol,
    is_mayhem_curve,
    sell_cap_sol,
)
from hunter_indicators.meme.fast import FastPoint, compute_fast
from hunter_indicators.meme.rules import EntryFeatures, EntryGate, evaluate_entry

pytestmark = pytest.mark.unit

FEE = Decimal("1.25")
TINY = CurveReserves(
    virtual_sol_reserves=Decimal(30),
    virtual_token_reserves=Decimal(300),
    real_token_reserves=Decimal(200),
    initial_real_token_reserves=Decimal(240),
)
PUSHED = replace(TINY, virtual_sol_reserves=Decimal(300))
"""The agent's push: ten times the virtual SOL, the vault untouched (5 SOL)."""
VAULT = Decimal(5)
T0 = datetime(2026, 9, 15, 20, 37, tzinfo=UTC)


# ---- the ceiling on the sale -----------------------------------------------------


def test_the_formula_quotes_what_the_vault_cannot_pay_and_the_ceiling_cuts_it() -> None:
    formula = quote_sell(PUSHED, Decimal(100), FEE)
    assert formula.curve_proceeds_sol == Decimal(75)
    assert formula.real_sol_cap_applied is False
    capped = quote_sell(PUSHED, Decimal(100), FEE, real_sol_reserves=VAULT)
    assert capped.real_sol_cap_applied is True
    assert capped.curve_proceeds_sol == VAULT
    assert capped.fee_sol == Decimal("0.0625")
    assert capped.net_sol == Decimal("4.9375")
    assert sell_all_value_sol(PUSHED, Decimal(100), FEE, real_sol_reserves=VAULT) == Decimal(
        "4.9375"
    )
    # The paper curve after the sale gives back only what left the vault.
    assert capped.reserves_after.virtual_sol_reserves == Decimal(295)
    assert capped.reserves_after.virtual_token_reserves == Decimal(400)


def test_a_vault_that_covers_the_sale_leaves_the_quote_untouched() -> None:
    plain = quote_sell(TINY, Decimal(100), FEE)
    with_ceiling = quote_sell(TINY, Decimal(100), FEE, real_sol_reserves=Decimal(1000))
    assert with_ceiling == replace(plain, real_sol_cap_applied=False)
    assert with_ceiling.real_sol_cap_applied is False


def test_an_empty_vault_is_a_sale_worth_nothing_and_a_negative_one_is_refused() -> None:
    empty = quote_sell(PUSHED, Decimal(100), FEE, real_sol_reserves=Decimal(0))
    assert empty.net_sol == 0 and empty.real_sol_cap_applied is True
    with pytest.raises(ValueError, match="real_sol_reserves"):
        quote_sell(PUSHED, Decimal(100), FEE, real_sol_reserves=Decimal(-1))


@settings(max_examples=200, deadline=None)
@given(
    bought=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("199"), places=2),
    fraction=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1"), places=2),
)
def test_on_a_standard_curve_the_ceiling_never_binds(bought: Decimal, fraction: Decimal) -> None:
    """Buyers put ``real_sol`` into the vault buying ``bought`` tokens; a
    holder of any fraction of them sells for no more than that vault. The one
    holder who owns the *whole* buy sells it back for exactly the vault, where
    28-digit arithmetic may land a hair (< 1e-20 SOL) on either side — the
    ceiling then "binds" by that hair and changes nothing a ledger can see."""
    after = reserves_after_buy(TINY, bought)
    real_sol = after.virtual_sol_reserves - TINY.virtual_sol_reserves
    held = (bought * fraction).quantize(Decimal("0.0001")) or Decimal("0.0001")
    assert sell_proceeds(after, held) <= real_sol + Decimal("1e-20")
    plain = quote_sell(after, held, FEE)
    quote = quote_sell(after, held, FEE, real_sol_reserves=real_sol)
    assert abs(quote.net_sol - plain.net_sol) < Decimal("1e-20")
    if held < bought:
        assert quote.real_sol_cap_applied is False and quote.net_sol == plain.net_sol


# ---- the executable market cap and the two witnesses ------------------------------


def test_the_executable_market_cap_is_the_theoretical_one_capped_at_the_vault() -> None:
    kat = Decimal("1981")  # 15/09 17:37 BRT: 1 981 SOL "of market cap", 5 holders
    assert executable_market_cap_sol(kat, Decimal(2), mayhem=True) == Decimal(2)
    assert executable_market_cap_sol(kat, Decimal(2), mayhem=False) == kat
    assert executable_market_cap_sol(kat, Decimal(2), mayhem=None) == kat
    assert executable_market_cap_sol(Decimal(3), Decimal(50), mayhem=True) == Decimal(3)
    assert executable_market_cap_sol(None, Decimal(2), mayhem=True) is None
    assert executable_market_cap_sol(kat, None, mayhem=True) is None, "a cap nobody observed"


def test_the_chain_bit_wins_and_only_an_agent_state_vouches_for_mayhem() -> None:
    assert is_mayhem_curve(True, None) is True
    assert is_mayhem_curve(False, "active") is False
    assert is_mayhem_curve(None, "active") is True
    assert is_mayhem_curve(None, "paused") is True
    assert is_mayhem_curve(None, "completed") is True
    assert is_mayhem_curve(None, "unknown") is None
    assert is_mayhem_curve(None, None) is None


def test_the_sell_cap_applies_unless_the_coin_is_known_standard_or_the_curve_is_complete() -> None:
    assert sell_cap_sol(VAULT, mayhem=True, complete=False) == VAULT
    assert sell_cap_sol(VAULT, mayhem=None, complete=False) == VAULT
    assert sell_cap_sol(VAULT, mayhem=False, complete=False) is None
    assert sell_cap_sol(VAULT, mayhem=True, complete=True) is None
    assert sell_cap_sol(None, mayhem=True, complete=False) is None


def test_the_feature_is_registered_with_its_inputs_and_its_cap() -> None:
    (definition,) = EXECUTABLE_DEFINITIONS
    assert definition.key == "mcap_executable_sol" and definition.version == 1
    assert "meme_curve_snapshots.real_sol_reserves" in definition.inputs
    assert definition.params["cap"] == "real_sol_reserves"


# ---- the gate ---------------------------------------------------------------------

GATE = EntryGate(
    key="teste_porta",
    version=1,
    description="T4.27 fixture: the frozen EXP-M1 shape, exclude_mayhem on by default.",
    min_age_s=60,
    max_age_s=900,
    min_progress_pct=Decimal(1),
    max_progress_pct=Decimal(20),
    max_participation_pct=Decimal(5),
)
STANDARD = EntryFeatures(
    mint="5bmYxJJnvAKn23VMxvjiTfeBckEmMok7C3SxztaA9c38",
    age_s=300,
    progress_pct=Decimal(8),
    creator_net_seller=False,
    curve_volume_1m_sol=Decimal(10),
    intended_size_sol=Decimal("0.4"),
    is_mayhem=False,
)


def test_a_mayhem_coin_is_refused_by_name_and_an_unknown_flag_too() -> None:
    assert evaluate_entry(STANDARD, GATE).allowed
    mayhem = evaluate_entry(replace(STANDARD, is_mayhem=True), GATE)
    assert not mayhem.allowed and mayhem.refusals == ("mayhem_curve",)
    unknown = evaluate_entry(replace(STANDARD, is_mayhem=None), GATE)
    assert not unknown.allowed and unknown.refusals == ("mayhem_unknown",)


def test_an_arm_that_wants_mayhem_says_so_and_the_registration_shows_it() -> None:
    wants = replace(GATE, exclude_mayhem=False)
    assert evaluate_entry(replace(STANDARD, is_mayhem=True), wants).allowed
    assert evaluate_entry(replace(STANDARD, is_mayhem=None), wants).allowed
    assert "exclude_mayhem" not in GATE.as_parameters(), "the default reads as it was frozen"
    assert wants.as_parameters()["exclude_mayhem"] == "False"


# ---- the 15-second series ---------------------------------------------------------


def _point(seconds: int, mcap: str, real_sol: str, mayhem: bool | None) -> FastPoint:
    at = T0 + timedelta(seconds=seconds)
    return FastPoint(
        observed_at=at,
        received_at=at,
        mcap_sol=Decimal(mcap),
        real_token_reserves=Decimal("700000000"),
        real_sol_reserves=Decimal(real_sol),
        mayhem_enabled=mayhem,
    )


def test_the_fast_row_caps_the_newest_photo_and_keeps_the_delta_theoretical() -> None:
    points = [_point(0, "27.96", "0", True), _point(60, "1981", "2", True)]
    fast = compute_fast(points, as_of=T0 + timedelta(seconds=61), initial_real_token_reserves=None)
    assert fast.mcap_sol == Decimal("1981.0000000000")
    assert fast.mcap_executable_sol == Decimal("2.0000000000")
    assert fast.mcap_delta_60s == Decimal("1953.0400000000"), "the theoretical series, labelled"
    standard = compute_fast(
        [_point(0, "27.96", "0", False), _point(60, "60", "30", False)],
        as_of=T0 + timedelta(seconds=61),
        initial_real_token_reserves=None,
    )
    assert standard.mcap_executable_sol == standard.mcap_sol == Decimal("60.0000000000")
    witnessed = compute_fast(
        [_point(60, "1981", "2", None)],
        as_of=T0 + timedelta(seconds=61),
        initial_real_token_reserves=None,
        mayhem_state="active",
    )
    assert witnessed.mcap_executable_sol == Decimal("2.0000000000")
    silent = compute_fast(
        [_point(60, "1981", "2", None)],
        as_of=T0 + timedelta(seconds=61),
        initial_real_token_reserves=None,
    )
    assert silent.mcap_executable_sol == Decimal("1981.0000000000"), "no witness, no cap"
