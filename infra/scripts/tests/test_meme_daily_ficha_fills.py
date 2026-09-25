"""``meme_daily_ficha_fills.py`` — the raw fill/tape readers, pure.

No database. Run: ``uv run pytest infra/scripts/tests/test_meme_daily_ficha_fills.py -q``
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from meme_daily_ficha_fills import (  # noqa: E402
    fees_sol,
    fraction_to_pct,
    rent_refund_sol,
    round_trip_cost_sol,
    sol_from_lamports,
    tape_features,
)

pytestmark = pytest.mark.unit


def test_fees_sol_reads_the_pumpswap_shape_not_the_curve_keys() -> None:
    """Astra (T4.92 review, HIGH): a migrated position's exit fill is a
    PumpSwap fill (``venue: "pumpswap"``, ``lp_fee``/``protocol_fee``/
    ``coin_creator_fee``) -- reading the curve's ``fee``/``creator_fee`` off it
    used to silently sum to zero instead of admitting the fee is unknown."""
    curve_fill = {"fee": 875_000, "creator_fee": 350_000, "network_fee_lamports": 5_000}
    assert fees_sol(curve_fill) == Decimal(875_000 + 350_000 + 5_000) / Decimal(1_000_000_000)

    pumpswap_fill = {
        "venue": "pumpswap",
        "lp_fee": 100_000,
        "protocol_fee": 50_000,
        "coin_creator_fee": 20_000,
        "network_fee_lamports": 5_000,
    }
    assert fees_sol(pumpswap_fill) == Decimal(100_000 + 50_000 + 20_000 + 5_000) / Decimal(
        1_000_000_000
    )

    # curve keys read off a pumpswap fill (the old bug) must never happen: with no
    # decoded event the pumpswap fee legs are None, and the answer is "unknown".
    incomplete_pumpswap_fill = {
        "venue": "pumpswap",
        "lp_fee": None,
        "protocol_fee": None,
        "coin_creator_fee": None,
        "network_fee_lamports": 5_000,
    }
    assert fees_sol(incomplete_pumpswap_fill) is None
    assert fees_sol(None) is None


def test_fraction_to_pct_never_double_converts_a_missing_value() -> None:
    """Astra (T4.92 review, HIGH): curve_progress_pct/dev_share are fractions
    in [0, 1] despite the "_pct" name -- 0.515 must become 51.5, not stay 0.515."""
    assert fraction_to_pct(Decimal("0.515")) == Decimal("51.5")
    assert fraction_to_pct(Decimal("0.09")) == Decimal("9.0")
    assert fraction_to_pct(None) is None


def test_rent_refund_sol_is_none_when_the_fill_never_names_it() -> None:
    assert rent_refund_sol(None) is None
    assert rent_refund_sol({"fee": 1}) is None
    assert rent_refund_sol({"ata_rent_refund_lamports": 2_039_280}) == Decimal(2_039_280) / Decimal(
        1_000_000_000
    )


def test_round_trip_cost_requires_both_legs_known() -> None:
    assert round_trip_cost_sol(None, Decimal("0.001"), None) is None
    assert round_trip_cost_sol(Decimal("0.001"), None, None) is None
    assert round_trip_cost_sol(Decimal("0.001"), Decimal("0.002"), None) == Decimal("0.003")
    assert round_trip_cost_sol(Decimal("0.001"), Decimal("0.002"), Decimal("0.002")) == Decimal(
        "0.001"
    )


def test_sol_from_lamports() -> None:
    assert sol_from_lamports(None) is None
    assert sol_from_lamports(70_000_000) == Decimal("0.07")


def test_tape_features_is_none_throughout_without_a_tape_row() -> None:
    assert tape_features(None) == (None, None, None, None, None, None)


def test_tape_features_reads_the_60s_window_and_the_creation_bundle() -> None:
    derived = {
        "windows": {"60s": {"buys": 79, "sells": 8, "unique_buyers": 76, "net_sol": "29.5"}},
        "creation_bundle": {"sol": "3.1", "wallets": 4},
    }
    buys, sells, unique_buyers, net_flow, bundle_sol, bundle_wallets = tape_features(derived)
    assert (buys, sells, unique_buyers) == (79, 8, 76)
    assert net_flow == Decimal("29.5")
    assert bundle_sol == Decimal("3.1") and bundle_wallets == 4


def test_tape_features_an_uncovered_window_is_absent_not_zero() -> None:
    derived = {"windows": {"60s": {"reason": "window_not_covered"}}}
    buys, sells, unique_buyers, net_flow, _bundle_sol, _bundle_wallets = tape_features(derived)
    assert (buys, sells, unique_buyers, net_flow) == (None, None, None, None)
