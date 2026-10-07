"""The paper sale cap counts the SOL our own hypothetical buy put in the curve.

Bug of 07/10 (R89, H-032; ``obsidian/07-BUGS``): a Mayhem bet's marks and
exit were capped at the photo's **observed** real SOL, and a later photo never
holds the SOL our hypothetical buy would have paid into the curve. A round
trip with no price move was cut to the vault of everyone else.

``REAL_PHOTO`` is a real ``solana_rpc`` photo, copied verbatim from
``meme_paper_bets`` id ``01a113bf-45eb-77c8-868c-cbabe08767e0`` (mint
``EjsrG2…``, Mayhem): entry 2026-10-07T00:24:18Z and exit 00:24:37Z read
the *same* reserves, real SOL 1 lamport; the row closed ``max_loss`` with
``curve_proceeds_sol = 0.000000001`` and ``pnl_sol = −0.0699999990`` on a
0,07 SOL stake (read-only query, 07/10). Photos marked SYNTHETIC are built
from it and say what they change.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal, localcontext

import pytest

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.curve import CurveReserves, quote_buy, quote_sell
from hunter_meme_worker.lab_models import BetState, EffectiveParams, Snapshot
from hunter_meme_worker.lab_values import SELL_CAP_MODEL, money_str
from hunter_meme_worker.paper_engine import close_bet, decide_exit, mark_bet

from .test_paper_engine import _fill  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.unit

MINT = "EjsrG2TcS1Sn6nqwYxijHHudsu8LsyJT37DdLVDLpump"
FEE = Decimal("1.75")
SIZE = Decimal("0.07")
ENTRY_AT = datetime(2026, 10, 7, 0, 24, 18, tzinfo=UTC)
EXIT_AT = datetime(2026, 10, 7, 0, 24, 37, tzinfo=UTC)
# the row's own entry numbers, verbatim
ROW_TOKENS = Decimal("479890.3842590632304570757415")
ROW_CURVE_COST = Decimal("0.0687960687960687960687960688")


def _photo(at: datetime, *, mayhem: bool | None = True) -> Snapshot:
    return Snapshot(
        mint=MINT,
        observed_at=at,
        source="solana_rpc",
        reserves=CurveReserves(
            virtual_sol_reserves=Decimal("152.672856608"),
            virtual_token_reserves=Decimal("1065456961.10503"),
            real_token_reserves=Decimal("785556961.10503"),
        ),
        real_sol_reserves=Decimal("0.000000001"),
        total_supply=Decimal(1_000_000_000),
        complete=False,
        mcap_sol=Decimal("143.2933118665"),
        mayhem_enabled=mayhem,
    )


REAL_ENTRY = _photo(ENTRY_AT)
REAL_PHOTO = _photo(EXIT_AT)


def _bet(*, is_mayhem: bool | None = True) -> BetState:
    return BetState(
        id="01a113bf-45eb-77c8-868c-cbabe08767e0",
        proposal_id="prop",
        rule_set_id="rs",
        mint=MINT,
        entry_at=ENTRY_AT,
        tokens=ROW_TOKENS,
        sol_spent=SIZE,
        initial_risk_sol=SIZE,
        params=EffectiveParams(
            size_sol=SIZE,
            target_x=Decimal("1.15"),
            trailing_pct=Decimal(10),
            max_hold_s=300,
            max_loss_pct=Decimal(50),
            exit_on_migration=True,
        ),
        high_water_x=Decimal("0.98"),
        mark_sol=None,
        mark_at=None,
        exit_intent=None,
        fee_pct=FEE,
        priority_fee_sol=Decimal(0),
        curve_cost_sol=ROW_CURVE_COST,
        is_mayhem=is_mayhem,
    )


def test_the_fixture_is_our_own_buy_arithmetic() -> None:
    quote = quote_buy(REAL_ENTRY.reserves, SIZE, FEE)
    assert quote.tokens == ROW_TOKENS
    assert quote.curve_cost_sol == ROW_CURVE_COST
    assert quote.total_sol == SIZE


def test_a_round_trip_on_the_identical_real_photo_is_not_cut_to_the_observed_vault() -> None:
    bet = _bet()
    formula = quote_sell(REAL_PHOTO.reserves, bet.tokens, FEE)
    closed = close_bet(bet, REAL_PHOTO, "max_loss", None, intent_snapshot_at=None)
    assert closed.exit["real_sol_cap_applied"] is False, "the vault holds our 0,0688 too"
    assert closed.exit["curve_proceeds_sol"] != "0.000000001", "the R89 row's number"
    assert closed.pnl_sol == formula.net_sol - SIZE
    # what is left is the fee and the impact paid twice — never the stake
    assert Decimal("-0.003") < closed.pnl_sol < 0
    mark = mark_bet(bet, REAL_PHOTO)
    assert mark.real_sol_cap_applied is False
    assert mark.mark_sol == formula.net_sol
    # the R89 row fired ``max_loss`` on this very photo; nothing fires now
    assert (
        decide_exit(bet, REAL_PHOTO, mark, migrated=False, creator_net_seller=False, sell_now=False)
        is None
    )


def test_the_cap_still_binds_at_observed_real_plus_our_own_curve_cost() -> None:
    # SYNTHETIC from REAL_PHOTO: the agent pushes the virtual SOL ×10 (KB-0098 §1
    # measured 23,9 → 1 977 in 60 s), the vault is unchanged at 1 lamport.
    pushed = replace(
        REAL_PHOTO,
        reserves=replace(REAL_PHOTO.reserves, virtual_sol_reserves=Decimal("1526.72856608")),
    )
    bet = _bet()
    cap = Decimal("0.000000001") + ROW_CURVE_COST
    closed = close_bet(bet, pushed, "target", None, intent_snapshot_at=None)
    assert closed.exit["real_sol_cap_applied"] is True
    assert closed.exit["curve_proceeds_sol"] == "0.0687960697960687960687960688" == str(cap)
    assert closed.exit["sell_cap_sol"] == "0.0687960697960687960687960688"
    assert closed.exit["own_curve_sol"] == "0.0687960687960687960687960688"
    assert closed.exit["sell_cap_model"] == SELL_CAP_MODEL
    assert mark_bet(bet, pushed).mark_sol == cap * (1 - FEE / 100)


def test_a_standard_coin_with_an_unknown_flag_and_an_almost_empty_vault_is_not_cut() -> None:
    # SYNTHETIC standard curve (virtual − real = 30, k = 30 × 1 073 000 000):
    # one lamport above the floor, flag unknown on the photo and on the token.
    k = Decimal(30) * Decimal(1_073_000_000)
    sol = Decimal("30.000000001")
    floor = replace(
        REAL_PHOTO,
        reserves=CurveReserves(virtual_sol_reserves=sol, virtual_token_reserves=k / sol),
        real_sol_reserves=sol - 30,
        mayhem_enabled=None,
    )
    entry = quote_buy(floor.reserves, SIZE, FEE)
    bet = replace(_bet(is_mayhem=None), tokens=entry.tokens, curve_cost_sol=entry.curve_cost_sol)
    closed = close_bet(bet, floor, "max_loss", None, intent_snapshot_at=None)
    assert closed.exit["real_sol_cap_applied"] is False
    with localcontext(CONTEXT):
        cap = Decimal("0.000000001") + entry.curve_cost_sol
    assert closed.exit["sell_cap_sol"] == money_str(cap)


def test_a_known_standard_coin_and_a_completed_curve_have_no_cap_at_all() -> None:
    standard = close_bet(
        _bet(is_mayhem=False),
        replace(REAL_PHOTO, mayhem_enabled=False),
        "max_loss",
        None,
        intent_snapshot_at=None,
    )
    assert standard.exit["sell_cap_sol"] is None
    assert standard.exit["sell_cap_model"] == SELL_CAP_MODEL
    completed = close_bet(
        _bet(), replace(REAL_PHOTO, complete=True), "migrated", None, intent_snapshot_at=None
    )
    assert (
        completed.exit["sell_cap_sol"] is None and completed.exit["real_sol_cap_applied"] is False
    )


def test_a_new_fill_names_the_cap_model_so_a_bet_across_the_deploy_is_visible() -> None:
    verdict = _fill()
    assert verdict.entry is not None
    assert verdict.entry.entry["sell_cap_model"] == SELL_CAP_MODEL


STANDARD_K = Decimal(30) * Decimal(1_073_000_000)


def _standard(real_sol: Decimal) -> Snapshot:
    """SYNTHETIC standard curve: ``virtual − real = 30`` and ``k`` constant."""
    sol = Decimal(30) + real_sol
    return replace(
        REAL_PHOTO,
        reserves=CurveReserves(virtual_sol_reserves=sol, virtual_token_reserves=STANDARD_K / sol),
        real_sol_reserves=real_sol,
        mayhem_enabled=None,
    )


@pytest.mark.parametrize("r0", ["0", "0.000000001", "0.5", "5", "40", "84"])
@pytest.mark.parametrize("budget", ["0.01", "0.07", "1", "5"])
@pytest.mark.parametrize("r1", ["0", "0.000000001", "0.01", "1", "30", "84.9"])
def test_on_a_standard_curve_the_sale_never_passes_observed_real_plus_own_buy(
    r0: str, budget: str, r1: str
) -> None:
    entry = quote_buy(_standard(Decimal(r0)).reserves, Decimal(budget), FEE)
    exit_photo = _standard(Decimal(r1))
    proceeds = quote_sell(exit_photo.reserves, entry.tokens, FEE).curve_proceeds_sol
    assert proceeds <= Decimal(r1) + entry.curve_cost_sol
    bet = replace(_bet(is_mayhem=None), tokens=entry.tokens, curve_cost_sol=entry.curve_cost_sol)
    assert mark_bet(bet, exit_photo).real_sol_cap_applied is False, "unknown flag, still uncut"


def test_the_old_cap_did_cut_a_standard_coin_with_an_unknown_flag() -> None:
    entry = quote_buy(_standard(Decimal("0.5")).reserves, SIZE, FEE)
    proceeds = quote_sell(_standard(Decimal(0)).reserves, entry.tokens, FEE).curve_proceeds_sol
    assert proceeds > 0, "observed real SOL alone (0) would have cut this sale to nothing"
