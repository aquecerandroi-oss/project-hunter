"""T4.27 in the worker — pure: the paper mark of a Mayhem bet is capped at the
photo's real SOL, the close says so on the row, both feature series carry
``mcap_executable_sol``, the gate row reaches the gate as ``is_mayhem`` and the
minute clock's flag read fails closed.

KAT's numbers (15/09 17:37 BRT): ``virtual_sol_reserves`` 23,9 → 1 977 SOL in
60 s, ``real_token_reserves`` down 7 %, 5 holders — here the vault holds
0,9 SOL while the formula quotes a sale of about 3,3 SOL.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_indicators.meme.curve import CurveReserves, quote_sell
from hunter_indicators.meme.fast import FastPoint
from hunter_meme_worker.features import CurveObservation, MinuteInputs, build_row
from hunter_meme_worker.features_fast import FastInputs, build_fast_row
from hunter_meme_worker.lab_models import BetState, Snapshot, effective_params
from hunter_meme_worker.lab_repo_mayhem import with_mayhem_flags
from hunter_meme_worker.paper_engine import (
    MARK_BASIS_CURVE,
    MARK_BASIS_REAL_SOL,
    close_bet,
    decide_exit,
    mark_bet,
)
from hunter_meme_worker.proposals import GateRow, entry_features_of

from .test_paper_engine import (
    LATER,
    PARAMS,
    RULE_SET_ID,
    _fill,  # pyright: ignore[reportPrivateUsage]
    _spec,  # pyright: ignore[reportPrivateUsage]
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 15, 20, 37, tzinfo=UTC)
MINT = "KAT1111111111111111111111111111111111111pump"
FEE = Decimal("1.75")


def _snapshot(
    seconds: int,
    sol: str,
    tokens: str,
    *,
    real_sol: str,
    mayhem: bool | None = None,
    complete: bool = False,
) -> Snapshot:
    return Snapshot(
        mint=MINT,
        observed_at=T0 + timedelta(seconds=seconds),
        source="solana_rpc",
        reserves=CurveReserves(
            virtual_sol_reserves=Decimal(sol),
            virtual_token_reserves=Decimal(tokens),
            real_token_reserves=Decimal(tokens) - Decimal("279900000"),
            initial_real_token_reserves=Decimal("793100000"),
            complete=complete,
        ),
        real_sol_reserves=Decimal(real_sol),
        total_supply=Decimal(1_000_000_000),
        complete=complete,
        mayhem_enabled=mayhem,
    )


def _bet(is_mayhem: bool | None) -> BetState:
    verdict = _fill(LATER)
    assert verdict.entry is not None
    entry = verdict.entry
    params = effective_params(_spec(), {})
    assert not isinstance(params, str)
    return BetState(
        id="bet-kat",
        proposal_id="prop-kat",
        rule_set_id=RULE_SET_ID,
        mint=MINT,
        entry_at=entry.entry_at,
        tokens=entry.tokens,
        sol_spent=entry.sol_spent,
        initial_risk_sol=entry.initial_risk_sol,
        params=params,
        high_water_x=entry.high_water_x,
        mark_sol=entry.mark_sol,
        mark_at=entry.entry_at,
        exit_intent=None,
        fee_pct=FEE,
        priority_fee_sol=Decimal(0),
        is_mayhem=is_mayhem,
    )


PUSHED = _snapshot(180, "1977", "900000000", real_sol="0.9")
"""The agent's push: 1 977 SOL of virtual reserve over a vault of 0,9 SOL."""


def test_the_mark_of_a_mayhem_bet_is_capped_at_the_photos_real_sol() -> None:
    bet = _bet(True)
    formula = quote_sell(PUSHED.reserves, bet.tokens, FEE)
    assert formula.curve_proceeds_sol > Decimal(3), "the formula quotes what the vault cannot pay"
    mark = mark_bet(bet, PUSHED)
    assert mark.real_sol_cap_applied is True
    assert mark.mark_sol == Decimal("0.9") * (1 - FEE / 100) == Decimal("0.88425")
    assert mark.high_water_x == mark.mark_sol / bet.sol_spent
    assert decide_exit(
        bet, PUSHED, mark, migrated=False, creator_net_seller=False, sell_now=False
    ) == ("target"), "0,88 SOL for a 0,05 SOL stake is still the target — what the vault could pay"


def test_a_standard_bet_and_a_completed_curve_keep_the_formula() -> None:
    standard = mark_bet(_bet(False), PUSHED)
    assert standard.real_sol_cap_applied is False
    assert standard.mark_sol == quote_sell(PUSHED.reserves, _bet(False).tokens, FEE).net_sol
    completed = mark_bet(_bet(True), replace(PUSHED, complete=True))
    assert completed.real_sol_cap_applied is False, "the SOL left for the pool; no vault to cap by"


def test_the_photos_own_bit_wins_over_the_token_row_and_unknown_keeps_the_cap() -> None:
    chain_says_mayhem = replace(PUSHED, mayhem_enabled=True)
    assert mark_bet(_bet(False), chain_says_mayhem).real_sol_cap_applied is True
    chain_says_standard = replace(PUSHED, mayhem_enabled=False)
    assert mark_bet(_bet(True), chain_says_standard).real_sol_cap_applied is False
    assert mark_bet(_bet(None), PUSHED).real_sol_cap_applied is True, "unknown is not standard"


def test_the_close_prices_the_sale_by_the_vault_and_says_so_on_the_row() -> None:
    bet = _bet(True)
    closed = close_bet(bet, PUSHED, "target", None, intent_snapshot_at=None)
    assert closed.exit["real_sol_cap_applied"] is True
    assert closed.exit["mark_basis"] == MARK_BASIS_REAL_SOL
    assert closed.exit["curve_proceeds_sol"] == "0.9"
    assert closed.exit["sol_received"] == "0.88425"
    assert closed.exit["snapshot"]["mayhem_enabled"] is None
    assert closed.pnl_sol == Decimal("0.88425") - bet.sol_spent
    plain = close_bet(_bet(False), PUSHED, "target", None, intent_snapshot_at=None)
    assert plain.exit["real_sol_cap_applied"] is False
    assert plain.exit["mark_basis"] == MARK_BASIS_CURVE


# ---- the two feature series -------------------------------------------------------


def _minute(mayhem: bool | None, *, state: str | None = None, real_sol: str = "0.9") -> Any:
    return build_row(
        MinuteInputs(
            mint=MINT,
            end_time=T0,
            created_at=T0 - timedelta(minutes=3),
            initial_real_token_reserves=Decimal("793100000"),
            snapshot=CurveObservation(
                observed_at=T0 - timedelta(seconds=20),
                source="solana_rpc",
                real_token_reserves=Decimal("620100000"),
                mcap_sol=Decimal("1981"),
                complete=False,
                real_sol_reserves=Decimal(real_sol),
                mayhem_enabled=mayhem,
            ),
            mayhem_state=state,
        )
    )


def test_the_minute_row_caps_the_executable_cap_and_keeps_the_theoretical_one() -> None:
    mayhem = _minute(True)
    assert mayhem.mcap_sol == Decimal("1981.0000000000")
    assert mayhem.mcap_executable_sol == Decimal("0.9000000000")
    standard = _minute(False)
    assert standard.mcap_executable_sol == standard.mcap_sol == Decimal("1981.0000000000")
    witnessed = _minute(None, state="paused")
    assert witnessed.mcap_executable_sol == Decimal("0.9000000000"), "the agent state vouches"
    silent = _minute(None)
    assert silent.mcap_executable_sol == Decimal("1981.0000000000"), "no witness, no cap"
    absent = build_row(
        MinuteInputs(
            mint=MINT,
            end_time=T0,
            created_at=None,
            initial_real_token_reserves=None,
            snapshot=None,
        )
    )
    assert absent.mcap_sol is None and absent.mcap_executable_sol is None


def test_the_fast_row_carries_the_same_cap() -> None:
    at = T0 - timedelta(seconds=5)
    row = build_fast_row(
        FastInputs(
            mint=MINT,
            as_of=T0,
            created_at=T0 - timedelta(seconds=90),
            initial_real_token_reserves=Decimal("793100000"),
            points=[
                FastPoint(
                    observed_at=at,
                    received_at=at,
                    mcap_sol=Decimal("1981"),
                    real_token_reserves=Decimal("620100000"),
                    real_sol_reserves=Decimal("0.9"),
                    mayhem_enabled=True,
                )
            ],
            snapshot_source="solana_rpc",
        )
    )
    assert row.mcap_sol == Decimal("1981.0000000000")
    assert row.mcap_executable_sol == Decimal("0.9000000000")


# ---- the gate row and the minute clock's flag ------------------------------------


def _row(**overrides: Any) -> GateRow:
    base: dict[str, Any] = {
        "mint": MINT,
        "end_time": T0,
        "created_at": T0 - timedelta(seconds=120),
        "curve_progress_pct": Decimal("0.16"),
        "progress_reason": None,
        "mcap_sol": Decimal("35.94"),
        "creator_sold": False,
        "curve_volume_1m_sol": Decimal(20),
        "completed_at": None,
        "migrated_at": None,
        "snapshot": None,
    }
    base.update(overrides)
    return GateRow(**base)


def test_the_gate_row_hands_the_gate_its_is_mayhem_from_the_bit_or_the_state() -> None:
    spec = _spec()
    assert entry_features_of(_row(mayhem_enabled=True), spec).is_mayhem is True
    assert entry_features_of(_row(mayhem_enabled=False, mayhem_state="active"), spec).is_mayhem is (
        False
    )
    assert entry_features_of(_row(mayhem_state="active"), spec).is_mayhem is True
    assert entry_features_of(_row(), spec).is_mayhem is None
    assert PARAMS.get("exclude_mayhem") is None and spec.gate.exclude_mayhem is True, (
        "on by default: a frozen set with no key excludes Mayhem"
    )
    assert _spec(exclude_mayhem=False).gate.exclude_mayhem is False


def test_the_minute_clocks_flag_read_fails_closed() -> None:
    rows = [_row(), _row(mint="OTHER")]
    flagged = with_mayhem_flags(rows, {MINT: (True, "active")})
    assert flagged[0].mayhem_enabled is True and flagged[0].mayhem_state == "active"
    assert flagged[1].mayhem_enabled is None, "a mint the read did not answer for stays unknown"
    assert with_mayhem_flags(rows, {}) == rows, "a failed read changes nothing: refused by name"
