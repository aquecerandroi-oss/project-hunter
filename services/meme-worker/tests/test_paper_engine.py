"""The paper engine of the Lab loop — pure, and every rule about **time**.

No database and no clock: the engine is a function of a rule set, a decision, a
wallet state and one snapshot. What is proved here is the state machine the
contract (``.claude/state/contrato-T4.6-T4.7-mesa-meme.md`` §Semântica) promises
the desk: a fill only on a snapshot strictly after the decision, ``unfilled`` by
name after the window, every ceiling a named refusal, and exits by target,
trailing, time stop, migration, ``sell_now`` and the loss floor — plus the
leakage test: the future is rewritten and the entry does not move.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from hunter_meme_worker.lab_models import (
    BetState,
    RuleSetSpec,
    Snapshot,
    SolUsd,
    WalletState,
    effective_params,
)
from hunter_meme_worker.paper_engine import (
    FILL_REFUSALS,
    close_bet,
    close_without_snapshot,
    decide_exit,
    evaluate_fill,
    mark_bet,
    pick_fill_snapshot,
)

from hunter_indicators.meme.curve import CurveReserves, quote_buy, quote_sell

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
MINT = "5bmYxJJnvAKn23VMxvjiTfeBckEmMok7C3SxztaA9c38"
RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000001"

PARAMS: dict[str, Any] = {
    "gate_key": "comprar_cedo_na_curva",
    "gate_version": 1,
    "exit_key": "alvo_2x_trailing_30_tempo_15m",
    "exit_version": 1,
    "min_age_s": 30,
    "max_age_s": 600,
    "min_progress_pct": "2",
    "max_progress_pct": "50",
    "max_participation_pct": "1",
    "require_creator_not_net_seller": True,
    "size_sol": "0.05",
    "target_x": "2",
    "trailing_pct": "30",
    "max_hold_s": 900,
    "max_loss_pct": "50",
    "wallet_max_sol": "2.0",
    "max_sol_per_bet": "0.05",
    "daily_loss_cap_sol": "0.20",
    "max_open_positions": 3,
    "max_exposure_per_mint_sol": "0.05",
    "fee_pct": "1.75",
    "priority_fee_sol": "0",
}


def _spec(**overrides: Any) -> RuleSetSpec:
    params = {**PARAMS, **overrides}
    return RuleSetSpec.from_params(
        id=RULE_SET_ID,
        name="meme_paper_v0",
        version="1",
        kind="research_only",
        exp_ref="EXP-M1",
        status="active",
        code_ref="hunter_indicators.meme.rules:evaluate_entry+evaluate_exit",
        params=params,
    )


def _snapshot(seconds: int, sol: str, tokens: str, *, complete: bool = False) -> Snapshot:
    return Snapshot(
        mint=MINT,
        observed_at=T0 + timedelta(seconds=seconds),
        source="pumpfun_rest",
        reserves=CurveReserves(
            virtual_sol_reserves=Decimal(sol),
            virtual_token_reserves=Decimal(tokens),
            real_token_reserves=Decimal(tokens) - Decimal("279900000"),
            initial_real_token_reserves=Decimal("793100000"),
            complete=complete,
        ),
        real_sol_reserves=Decimal(sol) - Decimal(30),
        total_supply=Decimal(1_000_000_000),
        complete=complete,
    )


WALLET = WalletState(
    balance_sol=Decimal("2.0"),
    open_positions=0,
    realized_today_sol=Decimal(0),
    exposure_by_mint={},
)
SOL_USD = SolUsd(
    price_usd=Decimal("101.4445"),
    source="pumpfun_rest:/sol-price",
    as_of=T0,
    observed_at=T0,
    stale=False,
)
DECIDED_AT = T0 + timedelta(seconds=90)
LATER = _snapshot(120, "32.4", "993000000")


def _fill(snapshot: Snapshot | None = LATER, *, now: datetime | None = None, **kw: Any) -> Any:
    spec = kw.pop("spec", _spec())
    wallet = kw.pop("wallet", WALLET)
    decision = kw.pop("decision", {"size_sol": "0.05"})
    return evaluate_fill(
        spec,
        decision,
        wallet,
        snapshot,
        decided_at=DECIDED_AT,
        now=now or DECIDED_AT + timedelta(seconds=30),
        migrated=kw.pop("migrated", False),
        fill_window_s=180,
        sol_usd=kw.pop("sol_usd", SOL_USD),
    )


# ---- fills ---------------------------------------------------------------------


def test_without_a_later_snapshot_the_fill_waits_and_then_refuses_by_name() -> None:
    waiting = _fill(None)
    assert waiting.kind == "wait" and waiting.refusal is None
    refused = _fill(None, now=DECIDED_AT + timedelta(seconds=181))
    assert refused.kind == "refused" and refused.refusal == "no_later_snapshot"


def test_a_snapshot_that_is_not_after_the_decision_can_never_fill() -> None:
    """The cheat is representable and it is refused, by name, at the engine."""
    verdict = _fill(_snapshot(90, "32.4", "993000000"))
    assert verdict.kind == "refused" and verdict.refusal == "fill_not_after_intent"


def test_the_fill_is_priced_at_the_later_snapshot_and_the_risk_is_everything_spent() -> None:
    verdict = _fill()
    assert verdict.kind == "filled" and verdict.entry is not None
    entry = verdict.entry
    quote = quote_buy(LATER.reserves, Decimal("0.05"), Decimal("1.75"))
    assert entry.tokens == quote.tokens
    assert entry.sol_spent == quote.total_sol == Decimal("0.05")
    assert entry.initial_risk_sol == entry.sol_spent  # RISK_ENGINE_MEME §5
    assert entry.entry_at == LATER.observed_at
    assert entry.entry["fill_delay_snapshots"] == 1
    assert entry.entry["decided_at"] == DECIDED_AT.isoformat()
    assert entry.entry["participation_pct"] is None
    assert entry.entry["participation_reason"] == "curve_volume_1m_unknown"
    assert entry.sol_usd_at_entry == Decimal("101.4445")
    assert entry.entry["sol_usd"]["source"] == "pumpfun_rest:/sol-price"
    # The first mark is what a full sell right after our own buy would net: below
    # what we paid, by the fee on both legs and our own impact.
    assert entry.high_water_x < 1
    assert entry.mark_sol == quote_sell(quote.reserves_after, quote.tokens, Decimal("1.75")).net_sol


def test_a_missing_sol_usd_quote_is_named_never_guessed() -> None:
    verdict = _fill(sol_usd=None)
    assert verdict.entry is not None
    assert verdict.entry.sol_usd_at_entry is None
    assert verdict.entry.entry["sol_usd"] is None
    assert verdict.entry.entry["sol_usd_reason"] == "quote_unavailable"


def test_pick_fill_snapshot_takes_the_first_after_the_decision_and_the_future_cannot_move_it() -> (
    None
):
    """The leakage test: the future is rewritten and the entry does not move."""
    before = (_snapshot(60, "31", "1000000000"), LATER, _snapshot(150, "33", "990000000"))
    rewritten = (
        before[0],
        LATER,
        _snapshot(150, "300", "300000000"),
        _snapshot(180, "300", "300000000"),
    )
    assert pick_fill_snapshot(before, DECIDED_AT) is LATER
    assert pick_fill_snapshot(rewritten, DECIDED_AT) is LATER
    assert pick_fill_snapshot((before[0],), DECIDED_AT) is None
    first, second = (
        _fill(pick_fill_snapshot(before, DECIDED_AT)),
        _fill(pick_fill_snapshot(rewritten, DECIDED_AT)),
    )
    assert first.entry is not None and second.entry is not None
    assert first.entry.tokens == second.entry.tokens
    assert first.entry.entry == second.entry.entry


@pytest.mark.parametrize(
    ("kw", "refusal"),
    [
        ({"migrated": True}, "migrated_before_fill"),
        ({"snapshot": _snapshot(120, "32.4", "993000000", complete=True)}, "curve_complete"),
        ({"decision": {"size_sol": "0.06"}}, "exceeds_max_sol_per_bet"),
        ({"decision": {"size_sol": "0"}}, "size_not_positive"),
        (
            {"wallet": WalletState(Decimal(2), 0, Decimal("-0.20"), {})},
            "daily_loss_cap",
        ),
        ({"wallet": WalletState(Decimal(2), 3, Decimal(0), {})}, "max_open_positions"),
        (
            {"wallet": WalletState(Decimal(2), 1, Decimal(0), {MINT: Decimal("0.05")})},
            "exposure_per_mint_cap",
        ),
        (
            {"wallet": WalletState(Decimal("0.04"), 0, Decimal(0), {})},
            "wallet_balance_insufficient",
        ),
    ],
)
def test_every_ceiling_is_a_named_refusal(kw: dict[str, Any], refusal: str) -> None:
    snapshot = kw.pop("snapshot", LATER)
    verdict = _fill(snapshot, **kw)
    assert verdict.kind == "refused" and verdict.refusal == refusal
    assert refusal in FILL_REFUSALS


def test_the_operator_may_change_the_four_numbers_inside_the_ceilings() -> None:
    spec = _spec()
    params = effective_params(
        spec, {"size_sol": "0.04", "target_x": "3", "trailing_pct": "20", "max_hold_s": 600}
    )
    assert not isinstance(params, str)
    assert (params.size_sol, params.target_x, params.trailing_pct, params.max_hold_s) == (
        Decimal("0.04"),
        Decimal(3),
        Decimal(20),
        600,
    )
    assert params.max_loss_pct == Decimal(50)  # the floor is the rule set's, not the operator's
    default = effective_params(spec, {})
    assert not isinstance(default, str) and default.size_sol == Decimal("0.05")  # suggested
    assert effective_params(spec, {"size_sol": "0.5"}) == "exceeds_max_sol_per_bet"


# ---- marks and exits -----------------------------------------------------------


def _bet(entry_snapshot: Snapshot = LATER, **kw: Any) -> BetState:
    verdict = _fill(entry_snapshot)
    assert verdict.entry is not None
    return BetState(
        id="bet-1",
        proposal_id="prop-1",
        rule_set_id=RULE_SET_ID,
        mint=MINT,
        entry_at=verdict.entry.entry_at,
        tokens=verdict.entry.tokens,
        sol_spent=verdict.entry.sol_spent,
        initial_risk_sol=verdict.entry.initial_risk_sol,
        params=kw.pop("params", effective_params(_spec(), {})),  # type: ignore[arg-type]
        high_water_x=kw.pop("high_water_x", verdict.entry.high_water_x),
        mark_sol=verdict.entry.mark_sol,
        mark_at=verdict.entry.entry_at,
        exit_intent=kw.pop("exit_intent", None),
        fee_pct=Decimal("1.75"),
        priority_fee_sol=Decimal(0),
    )


def _decide(bet: BetState, snapshot: Snapshot, **kw: Any) -> str | None:
    mark = mark_bet(bet, snapshot)
    return decide_exit(
        bet,
        snapshot,
        mark,
        migrated=kw.pop("migrated", False),
        creator_net_seller=kw.pop("creator_net_seller", None),
        sell_now=kw.pop("sell_now", False),
    )


def test_a_mark_is_what_a_full_sell_nets_and_the_high_water_only_rises() -> None:
    bet = _bet()
    up = mark_bet(bet, _snapshot(180, "60", "536000000"))
    assert (
        up.mark_sol
        == quote_sell(
            _snapshot(180, "60", "536000000").reserves, bet.tokens, Decimal("1.75")
        ).net_sol
    )
    assert up.high_water_x > bet.high_water_x
    down = mark_bet(bet, _snapshot(240, "31", "1000000000"))
    assert down.high_water_x == bet.high_water_x, "a lower mark must not lower the high water"


def test_the_target_closes_when_a_full_sell_would_double_what_was_paid() -> None:
    bet = _bet()
    assert _decide(bet, _snapshot(180, "40", "800000000")) is None
    assert _decide(bet, _snapshot(240, "70", "460000000")) == "target"


def test_the_trailing_closes_from_the_high_water_never_from_the_entry() -> None:
    bet = _bet()
    peak = _snapshot(180, "45", "715000000")
    high = mark_bet(bet, peak)
    bet_at_peak = replace(bet, high_water_x=high.high_water_x)
    assert _decide(bet_at_peak, _snapshot(240, "40", "804000000")) is None
    assert _decide(bet_at_peak, _snapshot(300, "31.5", "1020000000")) == "trailing"


def test_the_time_stop_closes_a_position_that_never_moved() -> None:
    bet = _bet()
    assert _decide(bet, _snapshot(120 + 899, "32.4", "993000000")) is None
    assert _decide(bet, _snapshot(120 + 900, "32.4", "993000000")) == "time_stop"


def test_migration_and_completion_end_the_curve_as_the_venue() -> None:
    bet = _bet()
    assert _decide(bet, _snapshot(180, "32.4", "993000000"), migrated=True) == "migrated"
    assert _decide(bet, _snapshot(180, "115", "280000000", complete=True)) == "migrated"


def test_the_loss_floor_and_the_creator_dump_are_named_and_the_operator_wins() -> None:
    bet = _bet()
    # A curve cannot fall below its launch price, so a 50 % loss needs a high entry.
    high_entry = _bet(_snapshot(120, "70", "460000000"))
    assert _decide(high_entry, _snapshot(180, "32", "1006000000")) == "max_loss"
    assert _decide(bet, _snapshot(180, "32.4", "993000000"), creator_net_seller=True) == (
        "creator_dump"
    )
    assert _decide(bet, _snapshot(180, "70", "460000000"), sell_now=True) == "sell_now"


def test_closing_prices_the_sale_and_r_is_pnl_over_everything_spent() -> None:
    bet = _bet()
    exit_snapshot = _snapshot(300, "70", "460000000")
    closed = close_bet(bet, exit_snapshot, "target", SOL_USD, intent_snapshot_at=T0)
    received = quote_sell(exit_snapshot.reserves, bet.tokens, Decimal("1.75")).net_sol
    assert closed.exit_at == exit_snapshot.observed_at
    assert closed.exit["sol_received"] == str(received)
    assert closed.pnl_sol == received - bet.sol_spent
    assert closed.r_multiple == closed.pnl_sol / bet.initial_risk_sol
    assert closed.exit["reason"] == "target"
    assert closed.sol_usd_at_exit == Decimal("101.4445")


def test_a_rug_without_a_snapshot_is_a_total_loss_never_a_fabricated_fill() -> None:
    bet = _bet()
    closed = close_without_snapshot(bet, now=T0 + timedelta(seconds=900), pending_reason="target")
    assert closed.exit["reason"] == "rug_no_snapshot"
    assert closed.exit["pending_reason"] == "target"
    assert closed.exit["sol_received"] == "0"
    assert closed.pnl_sol == -bet.sol_spent
    assert closed.r_multiple == Decimal(-1)
    assert closed.sol_usd_at_exit is None


def test_a_fill_never_touches_a_real_order_path() -> None:
    import hunter_meme_worker.paper_engine as engine

    source = open(engine.__file__, encoding="utf-8").read()
    for forbidden in (
        "hunter_risk",
        "hunter_core.execution",
        "ENABLE_MEME_LIVE_TRADING",
        "Keypair",
    ):
        assert forbidden not in source, forbidden
