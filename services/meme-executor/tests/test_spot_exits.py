"""T4.74-5 — ``spot_exits.spot_exits_once`` with fakes only (``spot_exits_rig``):
the mark by the quote of the whole lot, the exit order ``emergency`` >
``sell_requested`` > ``stop`` > ``target`` > ``time``, a confirmed sell
closed with the chain's lamports and ``exit.reason`` set, a failed quote
keeping the old mark, six failed sells blocking the position (still marked),
the panic tolerance per attempt/reason, a pending sell pinning the position
until the reconcile, the attempt counter seeded from the rows, and a disabled
lane that makes no query and no quote."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_meme_executor import spot_exits
from hunter_meme_executor.spot_config import SpotConfig
from hunter_meme_executor.spot_send_rules import LegResult

from .spot_exits_rig import (
    FEES,
    NOW,
    POSITION_ID,
    SPENT,
    TOKENS,
    FailingJupiter,
    exits_rig,
    position,
)
from .spot_tx_fixtures import SIGNATURE, WIF, WSOL, as_swap, quote, sell_message

pytestmark = pytest.mark.unit

STOP_OUT = 49_000_000
"""A mark of 0,049 SOL over 0,05 spent with r_unit 0,00075 is −1,33 R: a stop."""
FLAT_OUT = 50_500_000
"""0,0505 SOL: +0,67 R — no reason to sell."""


def _stub_leg(
    monkeypatch: pytest.MonkeyPatch, status: str, reason: str | None
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def leg(ctx: Any, **kw: Any) -> LegResult:
        calls.append(kw)
        sig = SIGNATURE if status != "refused" else None
        return LegResult(status, reason, sig, 0, 0, None)

    monkeypatch.setattr(spot_exits, "spot_leg", leg)
    return calls


# ------------------------------------------------------------------- the mark
async def test_the_mark_is_the_quote_of_the_whole_lot_and_is_written_every_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=FLAT_OUT)
    rig.store.positions = [position()]
    await spot_exits.spot_exits_once(rig.ctx)
    assert rig.store.marks == [(POSITION_ID, Decimal("0.0505"), None)]
    assert rig.ctx.treasury_client.quote_calls == 1
    assert rig.store.orders == [], "no reason: nothing sold"
    assert rig.stats.mark_ok_at[POSITION_ID] == NOW
    assert rig.stats.last_exits_tick_at == NOW
    assert rig.ctx.kill.refreshes == 1, "the switch is re-read on every tick"


async def test_a_failed_quote_keeps_the_old_mark_names_the_reason_and_three_make_it_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, jupiter=FailingJupiter(cast(Any, None), cast(Any, None)))
    # The old mark on the row (0,049) is at the stop; a failed quote must not sell on it.
    rig.store.positions = [position(mark_sol=Decimal("0.049"))]
    for _ in range(3):
        await spot_exits.spot_exits_once(rig.ctx)
    assert rig.store.marks == [(POSITION_ID, None, "quote_failed:RuntimeError")] * 3
    assert rig.store.orders == [], "the rules saw no mark: a stop is never decided on a stale one"
    assert rig.stats.mark_failures[POSITION_ID] == 3
    assert rig.stats.mark_ok_at[POSITION_ID] == NOW, "the first failure pins the floor"
    assert rig.stats.blocked_exits == {}, "a failed quote is not a failed exit"


async def test_a_time_exit_needs_no_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = exits_rig(monkeypatch, jupiter=FailingJupiter(cast(Any, None), cast(Any, None)))
    rig.store.positions = [position(mark_sol=None, entry_at=NOW - timedelta(seconds=14_400))]
    calls = _stub_leg(monkeypatch, "refused", "quote_failed:RuntimeError")
    await spot_exits.spot_exits_once(rig.ctx)
    assert [o["intent"]["reason"] for o in rig.store.orders] == ["time"]
    assert len(calls) == 1


# --------------------------------------------------------------- the exit order
@pytest.mark.parametrize(
    "sol_out,kill,auto_close,sell_requested,age_s,expected",
    [
        (STOP_OUT, KillSwitchState.EMERGENCY, True, True, 20_000, "emergency"),
        (STOP_OUT, KillSwitchState.EMERGENCY, False, True, 20_000, "sell_requested"),
        (STOP_OUT, KillSwitchState.TRADING_DISABLED, False, False, 20_000, "stop"),
        (51_200_000, KillSwitchState.ACTIVE, False, False, 20_000, "target"),
        (FLAT_OUT, KillSwitchState.ACTIVE, False, False, 20_000, "time"),
        (FLAT_OUT, KillSwitchState.ACTIVE, False, False, 300, None),
        (STOP_OUT, KillSwitchState.EMERGENCY, False, False, 300, "stop"),
    ],
)
async def test_the_exit_order_is_emergency_sell_requested_stop_target_time(
    monkeypatch: pytest.MonkeyPatch,
    sol_out: int,
    kill: KillSwitchState,
    auto_close: bool,
    sell_requested: bool,
    age_s: int,
    expected: str | None,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=sol_out, kill=kill, auto_close=auto_close)
    rig.store.positions = [
        position(
            entry_at=NOW - timedelta(seconds=age_s),
            sell_requested_at=NOW - timedelta(seconds=5) if sell_requested else None,
            sell_requested_by="everton" if sell_requested else None,
        )
    ]
    _stub_leg(monkeypatch, "refused", "quote_failed:X")
    await spot_exits.spot_exits_once(rig.ctx)
    reasons = [o["intent"]["reason"] for o in rig.store.orders]
    assert reasons == ([] if expected is None else [expected])


# ---------------------------------------------------------- a confirmed sell
async def test_a_stop_sells_the_lot_and_closes_with_the_chain_lamports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.store.positions = [position()]
    await spot_exits.spot_exits_once(rig.ctx)
    assert rig.log.count("sign") == 1, "one signature, in spot_leg"
    order = rig.store.orders[0]
    assert order["side"] == "sell" and order["position_id"] == POSITION_ID
    assert order["client_order_id"] == f"spot:sell:{POSITION_ID}:1"
    assert order["intent"]["amount_atoms"] == TOKENS, "the whole lot, never partial"
    assert order["intent"]["slippage_bps"] == 300, "a stop uses the panic tolerance at once"
    assert order["quote"] is None, "the leg re-quotes; the row's quote is the one that built the tx"
    # The position named its sell before the leg, then closed with the landed lamports.
    assert rig.store.pending_set[0]["order_id"] == "order-1"
    close = rig.store.closes[0]
    assert (
        close["sol_received_lamports"]
        == STOP_OUT - FEES
        == close["exit_payload"]["sol_delta_lamports"]
    )
    assert close["sol_spent_lamports"] == SPENT and close["exit_order_id"] == "order-1"
    assert close["exit_payload"]["reason"] == "stop"
    assert close["exit_payload"]["signature"] == SIGNATURE
    assert rig.stats.exits_by_reason == {"stop": 1} and rig.stats.sells_confirmed == 1
    assert rig.stats.last_signature == SIGNATURE
    assert "closed_stats" in rig.store.queries, "the refutation is recomputed at the close"
    assert rig.stats.lane is not None and rig.stats.lane.state == "on"
    assert POSITION_ID not in rig.stats.exit_attempts, "a closed position leaves the memory"


async def test_a_sell_proceeds_under_trading_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT, kill=KillSwitchState.TRADING_DISABLED)
    rig.store.positions = [position()]
    await spot_exits.spot_exits_once(rig.ctx)
    assert len(rig.store.closes) == 1, "an exit is never blocked by a switch"


# ------------------------------------------------------------- failed sells
async def test_six_failed_sells_block_the_position_which_stays_marked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.store.positions = [position()]
    calls = _stub_leg(monkeypatch, "refused", "simulation_failed:x")
    backoffs = [2, 4, 8, 16, 32, 60]
    clock = NOW
    for n in range(6):
        monkeypatch.setattr(spot_exits, "utcnow", lambda clock=clock: clock)
        await spot_exits.spot_exits_once(rig.ctx)
        assert len(calls) == n + 1, f"attempt {n + 1} sent"
        assert rig.stats.exit_backoff_until[POSITION_ID] == clock + timedelta(seconds=backoffs[n])
        # Inside the backoff nothing is tried, the mark still goes.
        await spot_exits.spot_exits_once(rig.ctx)
        assert len(calls) == n + 1
        clock = clock + timedelta(seconds=backoffs[n])
    assert [o["attempt"] for o in rig.store.orders] == [1, 2, 3, 4, 5, 6]
    assert [o["client_order_id"] for o in rig.store.orders] == [
        f"spot:sell:{POSITION_ID}:{n}" for n in range(1, 7)
    ]
    assert rig.stats.blocked_exits == {POSITION_ID: "stop"}
    assert [p["outcome"] for p in rig.store.pending_cleared][:1] == ["refused:simulation_failed:x"]
    monkeypatch.setattr(spot_exits, "utcnow", lambda: NOW + timedelta(hours=1))
    marks_before = len(rig.store.marks)
    await spot_exits.spot_exits_once(rig.ctx)
    assert len(calls) == 6, "blocked: never re-sold by the loop"
    assert len(rig.store.marks) == marks_before + 1, "but still marked"


@pytest.mark.parametrize(
    "sol_out,reason,attempts,expected",
    [
        (51_200_000, "target", 3, [50, 50, 300]),
        (STOP_OUT, "stop", 2, [300, 300]),
    ],
)
async def test_the_panic_tolerance_from_the_third_attempt_or_from_the_first_on_a_stop(
    monkeypatch: pytest.MonkeyPatch, sol_out: int, reason: str, attempts: int, expected: list[int]
) -> None:
    rig = exits_rig(monkeypatch, sol_out=sol_out)
    rig.store.positions = [position()]
    calls = _stub_leg(monkeypatch, "failed", "on_chain_error")
    for n in range(attempts):
        monkeypatch.setattr(spot_exits, "utcnow", lambda n=n: NOW + timedelta(minutes=n))
        await spot_exits.spot_exits_once(rig.ctx)
    assert [c["slippage_bps"] for c in calls] == expected
    assert [o["intent"]["reason"] for o in rig.store.orders] == [reason] * attempts
    assert rig.stats.blocked_exits == {}


async def test_the_attempt_counter_is_seeded_from_the_rows_after_a_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.store.positions = [position()]
    rig.store.sell_attempts = 7  # seven sell rows exist, six failed for a hard reason
    rig.store.hard_failures = 6
    calls = _stub_leg(monkeypatch, "refused", "x")
    await spot_exits.spot_exits_once(rig.ctx)
    assert calls == [] and rig.store.orders == []
    assert rig.stats.blocked_exits == {POSITION_ID: "stop"}, "the block survives a restart"


async def test_a_duplicate_attempt_key_is_skipped_and_the_next_tick_uses_the_next_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.store.positions = [position()]
    rig.store.sell_attempts = 1
    rig.store.duplicate_order_keys = {f"spot:sell:{POSITION_ID}:2"}
    calls = _stub_leg(monkeypatch, "refused", "x")
    await spot_exits.spot_exits_once(rig.ctx)
    assert calls == [] and rig.store.pending_set == [], "no row, no leg"
    await spot_exits.spot_exits_once(rig.ctx)
    assert rig.store.orders[0]["attempt"] == 3 and len(calls) == 1


# ------------------------------------------------------------ pending sells
async def test_a_pending_sell_pins_the_position_until_the_reconcile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.store.positions = [position()]
    calls = _stub_leg(monkeypatch, "submitted_unconfirmed", "confirm_pending_reconcile")
    await spot_exits.spot_exits_once(rig.ctx)
    assert len(calls) == 1 and rig.store.closes == []
    assert rig.store.pending_set[0]["reason"] == "stop" and rig.store.pending_cleared == []
    assert rig.stats.last_signature == SIGNATURE
    # The row now says a sell is in flight: the next tick marks and sells nothing.
    rig.store.positions = [
        position(exit_intent={"status": "submitted_unconfirmed", "order_id": "order-1"})
    ]
    monkeypatch.setattr(spot_exits, "utcnow", lambda: NOW + timedelta(minutes=5))
    await spot_exits.spot_exits_once(rig.ctx)
    assert len(calls) == 1 and len(rig.store.marks) == 2


# ---------------------------------------------------------------- inert lane
@pytest.mark.parametrize(
    "spot",
    [
        SpotConfig(),
        SpotConfig(requested=True, live=False, signer_present=True),
        SpotConfig(requested=True, live=True, signer_present=False),
    ],
)
async def test_a_disabled_lane_makes_no_query_and_no_quote(
    monkeypatch: pytest.MonkeyPatch, spot: SpotConfig
) -> None:
    rig = exits_rig(monkeypatch, jupiter=FailingJupiter(cast(Any, None), cast(Any, None)))
    rig.ctx.config.spot = spot
    rig.store.positions = [position()]

    def no_session(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("no query while inert")

    monkeypatch.setattr(spot_exits, "role_session", no_session)
    await spot_exits.spot_exits_once(rig.ctx)
    assert rig.ctx.treasury_client.quote_calls == 0 and rig.store.marks == []
    assert rig.stats.last_exits_tick_at is None


async def test_a_tick_that_raises_is_counted_never_propagated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)

    async def boom(_s: Any) -> list[Any]:
        raise RuntimeError("db_down")

    monkeypatch.setattr(spot_exits, "open_spot_positions", boom)
    await spot_exits.spot_exits_once(rig.ctx)
    assert rig.stats.tick_failures == 1 and rig.ctx.state.rpc_errors == 1


async def test_the_sell_quote_the_leg_uses_is_for_this_pair_and_lot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.ctx.treasury_client.quote_reply = quote(
        input_mint=WIF, output_mint=WSOL, amount=TOKENS - 1, out=STOP_OUT
    )
    rig.ctx.treasury_client.swap_reply = as_swap(sell_message(in_amount=TOKENS - 1, out=STOP_OUT))
    rig.store.positions = [position()]
    await spot_exits.spot_exits_once(rig.ctx)
    assert "sign" not in rig.log, "a quote for another amount never reaches the signature"
    assert rig.db.statuses() == ["refused"]
    assert rig.store.pending_cleared[0]["outcome"] == "refused:quote_mismatch:in_amount"


async def test_transient_refusals_back_off_but_never_spend_the_block_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.store.positions = [position()]
    calls = _stub_leg(monkeypatch, "refused", "quote_failed:ReadTimeout")
    clock = NOW
    for _ in range(8):  # a Jupiter outage longer than the whole backoff ladder
        monkeypatch.setattr(spot_exits, "utcnow", lambda clock=clock: clock)
        await spot_exits.spot_exits_once(rig.ctx)
        clock = clock + timedelta(seconds=61)
    assert len(calls) == 8, "every tick past the backoff tries again"
    assert rig.stats.blocked_exits == {}, "an outage is not a reason to park a stop"
    assert rig.stats.exit_hard_failures[POSITION_ID] == 0
    assert [o["attempt"] for o in rig.store.orders] == list(range(1, 9)), "still one row per try"
