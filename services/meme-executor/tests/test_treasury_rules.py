"""T4.54 — sizing math, refusal reasons and the transaction-shape verifier.
Pure functions: no network, no database, no signer, no chain."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_exchanges.jupiter import JupiterQuote
from hunter_exchanges.jupiter.versioned_tx import (
    VersionedCompiledInstruction,
    VersionedMessage,
)
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID
from hunter_meme_executor.treasury_rules import (
    JUP_PROGRAM_ID,
    TreasurySwapRefused,
    classify_quote_refusal,
    should_attempt,
    size_first_pass,
    size_to_target,
    verify_swap_transaction,
)

pytestmark = pytest.mark.unit

WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
FOREIGN_PROGRAM = "11111111111111111111111111111111111111112"
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def _quote(**overrides: object) -> JupiterQuote:
    base: dict[str, object] = {
        "input_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "output_mint": "So11111111111111111111111111111111111111112",
        "in_amount": Decimal("5000000"),
        "out_amount": Decimal("34215678"),
        "other_amount_threshold": Decimal("34044000"),
        "price_impact_pct": Decimal("0.0012"),
        "slippage_bps": 50,
        "route_labels": ("Whirlpool",),
        "raw": {},
    }
    base.update(overrides)
    return JupiterQuote(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------- sizing
def test_size_first_pass_is_the_smallest_of_the_three_caps() -> None:
    assert (
        size_first_pass(
            wallet_usdc_atoms=100_000_000,
            remaining_daily_cap_atoms=20_000_000,
            max_per_swap_atoms=25_000_000,
        )
        == 20_000_000
    )
    assert (
        size_first_pass(
            wallet_usdc_atoms=5_000_000,
            remaining_daily_cap_atoms=20_000_000,
            max_per_swap_atoms=25_000_000,
        )
        == 5_000_000
    )


def test_size_first_pass_never_negative() -> None:
    assert (
        size_first_pass(
            wallet_usdc_atoms=5_000_000, remaining_daily_cap_atoms=-1, max_per_swap_atoms=25_000_000
        )
        == 0
    )


def test_size_to_target_shrinks_to_what_is_needed() -> None:
    # price: 1 USDC atom -> ~6.84 SOL-lamport-atoms in this fixture's ratio
    # (34215678 lamports / 5000000 usdc-atoms). Wallet at 0.55 SOL, target 0.60:
    # needs only 0.05 SOL = 50_000_000 lamports, well under the 25 USDC cap.
    resized = size_to_target(
        first_pass_usdc_atoms=25_000_000,
        quote_in_amount_atoms=5_000_000,
        quote_out_amount_atoms=34_215_678,
        wallet_lamports=550_000_000,
        target_lamports=600_000_000,
    )
    assert 0 < resized < 25_000_000, "the target needs less than the first-pass cap"


def test_size_to_target_returns_zero_once_the_target_is_already_met() -> None:
    resized = size_to_target(
        first_pass_usdc_atoms=25_000_000,
        quote_in_amount_atoms=5_000_000,
        quote_out_amount_atoms=34_215_678,
        wallet_lamports=600_000_000,
        target_lamports=600_000_000,
    )
    assert resized == 0


def test_size_to_target_never_exceeds_the_first_pass_cap() -> None:
    resized = size_to_target(
        first_pass_usdc_atoms=1_000,
        quote_in_amount_atoms=5_000_000,
        quote_out_amount_atoms=34_215_678,
        wallet_lamports=0,
        target_lamports=10_000_000_000,
    )
    assert resized == 1_000


def test_size_to_target_handles_a_zero_output_quote_without_dividing_by_zero() -> None:
    assert (
        size_to_target(
            first_pass_usdc_atoms=1_000,
            quote_in_amount_atoms=5_000_000,
            quote_out_amount_atoms=0,
            wallet_lamports=0,
            target_lamports=1,
        )
        == 0
    )


# ---------------------------------------------------------------- refusals
def test_route_empty_is_refused() -> None:
    assert classify_quote_refusal(_quote(route_labels=())) == "route_empty"
    assert classify_quote_refusal(_quote(out_amount=Decimal(0))) == "route_empty"


def test_price_impact_above_one_percent_is_refused() -> None:
    assert classify_quote_refusal(_quote(price_impact_pct=Decimal("0.011"))) == (
        "price_impact_above_cap"
    )


def test_a_good_quote_is_not_refused() -> None:
    assert classify_quote_refusal(_quote()) is None


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"enabled": False}, "disabled"),
        ({"live": False}, "live_disabled"),
        ({"has_signer": False}, "no_signer"),
        ({"kill_blocked": True}, "kill_switch_latched"),
        ({"wallet_sol": Decimal("0.5")}, "sol_above_floor"),
        (
            {"last_attempt_at": NOW - timedelta(seconds=10), "min_interval_s": 600.0},
            "min_interval_not_elapsed",
        ),
        ({"usdc_spent_today": Decimal("50")}, "daily_cap_reached"),
    ],
)
def test_should_attempt_refuses_each_gate_by_name(kwargs: dict[str, object], expected: str) -> None:
    base: dict[str, object] = {
        "enabled": True,
        "live": True,
        "has_signer": True,
        "kill_blocked": False,
        "wallet_sol": Decimal("0.1"),
        "floor": Decimal("0.30"),
        "last_attempt_at": None,
        "min_interval_s": 600.0,
        "now": NOW,
        "usdc_spent_today": Decimal("0"),
        "daily_cap": Decimal("50"),
    }
    base.update(kwargs)
    assert should_attempt(**base) == expected  # type: ignore[arg-type]


def test_should_attempt_allows_when_every_gate_passes() -> None:
    assert (
        should_attempt(
            enabled=True,
            live=True,
            has_signer=True,
            kill_blocked=False,
            wallet_sol=Decimal("0.1"),
            floor=Decimal("0.30"),
            last_attempt_at=NOW - timedelta(hours=1),
            min_interval_s=600.0,
            now=NOW,
            usdc_spent_today=Decimal("0"),
            daily_cap=Decimal("50"),
        )
        is None
    )


# ---------------------------------------------------------------------- verify
def _message(
    *,
    static_keys: list[str],
    num_required_signatures: int = 1,
    instructions: tuple[VersionedCompiledInstruction, ...],
    blockhash: str = "5" * 32,
) -> VersionedMessage:
    return VersionedMessage(
        version=0,
        num_required_signatures=num_required_signatures,
        num_readonly_signed=0,
        num_readonly_unsigned=0,
        static_account_keys=tuple(static_keys),
        recent_blockhash=blockhash,
        instructions=instructions,
        address_table_lookups=(),
    )


def test_a_clean_jupiter_route_verifies() -> None:
    message = _message(
        static_keys=[WALLET, JUP_PROGRAM_ID, TOKEN_PROGRAM_ID],
        instructions=(
            VersionedCompiledInstruction(1, (0,), b"\x01"),
            VersionedCompiledInstruction(2, (0,), b"\x02"),
        ),
    )
    verify_swap_transaction(message, wallet=WALLET)  # must not raise


def test_a_foreign_transfer_program_is_refused() -> None:
    message = _message(
        static_keys=[WALLET, JUP_PROGRAM_ID, FOREIGN_PROGRAM],
        instructions=(
            VersionedCompiledInstruction(1, (0,), b"\x01"),
            VersionedCompiledInstruction(2, (0,), b"\x02"),
        ),
    )
    with pytest.raises(TreasurySwapRefused) as excinfo:
        verify_swap_transaction(message, wallet=WALLET)
    assert excinfo.value.reason == f"program_not_allowed:{FOREIGN_PROGRAM}"


def test_a_program_behind_a_lookup_table_is_refused_not_trusted() -> None:
    message = _message(
        static_keys=[WALLET, JUP_PROGRAM_ID],
        instructions=(VersionedCompiledInstruction(9, (0,), b"\x01"),),
    )
    with pytest.raises(TreasurySwapRefused, match="program_via_lookup_table"):
        verify_swap_transaction(message, wallet=WALLET)


def test_a_fee_payer_that_is_not_the_wallet_is_refused() -> None:
    message = _message(
        static_keys=[FOREIGN_PROGRAM, JUP_PROGRAM_ID],
        instructions=(VersionedCompiledInstruction(1, (0,), b"\x01"),),
    )
    with pytest.raises(TreasurySwapRefused, match="fee_payer_not_wallet"):
        verify_swap_transaction(message, wallet=WALLET)


def test_more_than_one_signer_is_refused() -> None:
    message = _message(
        static_keys=[WALLET, FOREIGN_PROGRAM, JUP_PROGRAM_ID],
        num_required_signatures=2,
        instructions=(VersionedCompiledInstruction(2, (0, 1), b"\x01"),),
    )
    with pytest.raises(TreasurySwapRefused, match="more_than_one_signer"):
        verify_swap_transaction(message, wallet=WALLET)


def test_a_zero_blockhash_is_refused() -> None:
    message = _message(
        static_keys=[WALLET, JUP_PROGRAM_ID],
        instructions=(VersionedCompiledInstruction(1, (0,), b"\x01"),),
        blockhash="1" * 32,
    )
    with pytest.raises(TreasurySwapRefused, match="blockhash_missing"):
        verify_swap_transaction(message, wallet=WALLET)
