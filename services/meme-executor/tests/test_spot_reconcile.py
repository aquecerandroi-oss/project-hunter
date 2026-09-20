"""T4.74-5 — ``spot_reconcile.spot_reconcile_once`` with fakes only, part 1:
a buy that confirms late **opens** the position from the order's own
admission (the T4.74-4 concern) and its reservation goes with the status; an
expired row (block height past ``last_valid_block_height``, signature still
absent on a second look) is ``failed:blockhash_expired_never_landed``; a
not-yet-expired row waits; a confirmed sell closes the position with the
lamports; an errored sell clears the marker and backs off. Never signs, never
sends."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_meme_executor import spot_reconcile
from hunter_meme_executor.spot_send_rules import ATA_RENT_LAMPORTS

from .spot_exits_rig import (
    FEES,
    NOW,
    ORDER_ID,
    POSITION_ID,
    SPENT,
    TICKET,
    TOKENS,
    UNI_OUT,
    WALLET_BEFORE,
    buy_landed,
    confirmed_status,
    exits_rig,
    order_row,
    position,
    sell_row,
)
from .spot_fakes import tx_meta
from .spot_tx_fixtures import SIGNATURE

pytestmark = pytest.mark.unit


# ------------------------------------------------------------ late buys
async def test_a_buy_that_confirms_late_opens_the_position_from_the_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [order_row()]
    buy_landed(rig)
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.log == ["get_transaction"], "read by signature; never sent, never signed"
    confirmed = rig.store.confirmed[0]
    assert confirmed["order_id"] == ORDER_ID and confirmed["filled_atoms"] == UNI_OUT
    assert confirmed["sol_delta_lamports"] == -(TICKET + ATA_RENT_LAMPORTS + 5_050)
    assert confirmed["ata_rent_lamports"] == ATA_RENT_LAMPORTS, "the tx created the ATA"
    assert confirmed["settled_by"] == "reconcile"
    opened = rig.store.opened[0]
    assert opened["entry_order_id"] == ORDER_ID and opened["tokens"] == UNI_OUT
    assert opened["sol_spent_lamports"] == TICKET + 5_050, "the outflow minus the rent it locked"
    assert opened["initial_risk_sol"] == Decimal("0.05") * Decimal("0.015"), "ticket × stop_frac"
    assert opened["params"]["stop_frac"] == "0.015"
    assert opened["params"]["target_frac"] == "0.0225"
    assert opened["params"]["horizon_s"] == 14400
    assert opened["params"]["sol_usd_at_entry"] == "200"
    assert opened["params"]["opened_by"] == "reconcile"
    assert opened["entry"]["quoted_out_atoms"] == 133333333
    assert rig.stats.reconciled_buys == 1 and rig.stats.buys_confirmed == 1
    assert rig.stats.last_signature == SIGNATURE
    assert rig.ctx.state.entries_confirmed == 1


async def test_a_landed_buy_whose_meta_is_not_served_yet_waits_and_is_never_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [order_row()]
    rig.ctx.chain.rpc.statuses = [confirmed_status()]
    rig.ctx.chain.rpc.transaction = None
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.confirmed == [] and rig.store.opened == [] and rig.store.failed == []


async def test_a_landed_buy_without_geometry_is_confirmed_but_not_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [order_row(admission={})]
    buy_landed(rig)
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert len(rig.store.confirmed) == 1, "the chain's truth is recorded"
    assert rig.store.opened == [], "never a position with an invented R"
    assert rig.stats.reconciled_buys == 0


# ----------------------------------------------------------- expired rows
async def test_an_expired_buy_is_failed_and_its_reservation_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [order_row(last_valid_block_height=100)]
    rig.ctx.chain.rpc.statuses = [None]
    rig.ctx.chain.rpc.block_height = 101
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.log == ["get_block_height"]
    assert rig.ctx.chain.rpc.status_calls == 2, "absence is proven by a second look"
    assert rig.store.failed == [(ORDER_ID, "blockhash_expired_never_landed")]
    assert rig.store.opened == [] and rig.store.confirmed == []
    assert rig.stats.reconciled_expired == 1
    # The reservation is the row's status: ``pending_spot_markets`` reads only
    # admitted/simulated/submitted_unconfirmed — a failed row holds nothing.


async def test_a_not_yet_expired_row_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [order_row(last_valid_block_height=100)]
    rig.ctx.chain.rpc.statuses = [None]
    rig.ctx.chain.rpc.block_height = 100
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.failed == [] and rig.store.confirmed == []


async def test_without_a_block_height_the_row_expires_by_age(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.ctx.chain.rpc.statuses = [None]
    rig.store.unconfirmed = [
        order_row(last_valid_block_height=None, submitted_at=NOW - timedelta(seconds=181))
    ]
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.failed == [(ORDER_ID, "blockhash_expired_never_landed")]
    assert "get_block_height" not in rig.log


async def test_an_unreadable_height_leaves_the_row_for_the_next_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [order_row(last_valid_block_height=100)]
    rig.ctx.chain.rpc.statuses = [None]

    def boom(*, commitment: str = "confirmed") -> int:
        raise ConnectionError("rpc")

    monkeypatch.setattr(rig.ctx.chain.rpc, "get_block_height", boom)
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.failed == [] and rig.ctx.state.rpc_errors == 1


# ------------------------------------------------------------- late sells
async def test_a_sell_that_confirms_late_closes_the_position_with_the_lamports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.positions = [
        position(exit_intent={"status": "submitted_unconfirmed", "order_id": ORDER_ID})
    ]
    rig.store.unconfirmed = [sell_row()]
    sol_out = 51_200_000
    after = WALLET_BEFORE + sol_out - FEES
    rig.ctx.chain.rpc.statuses = [confirmed_status()]
    rig.ctx.chain.rpc.transaction = tx_meta(
        wallet_pre=WALLET_BEFORE, wallet_post=after, token_pre=TOKENS, token_post=0
    )
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.confirmed[0]["filled_atoms"] == sol_out - FEES
    close = rig.store.closes[0]
    assert close["position_id"] == POSITION_ID and close["exit_order_id"] == ORDER_ID
    assert close["sol_received_lamports"] == sol_out - FEES
    assert close["sol_spent_lamports"] == SPENT
    assert close["exit_payload"]["reason"] == "target"
    assert close["exit_payload"]["settled_by"] == "reconcile"
    assert rig.stats.exits_by_reason == {"target": 1}
    assert rig.stats.lane is not None, "the refutation is recomputed at the close"


async def test_an_errored_sell_clears_the_pending_marker_and_backs_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [sell_row()]
    rig.ctx.chain.rpc.statuses = [{"confirmationStatus": "confirmed", "err": {"x": 1}}]
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.failed == [(ORDER_ID, "onchain_error:{'x': 1}")]
    cleared = rig.store.pending_cleared[0]
    assert cleared["position_id"] == POSITION_ID and cleared["order_id"] == ORDER_ID
    assert cleared["outcome"] == "failed:onchain_error:{'x': 1}"
    assert rig.stats.exit_backoff_until[POSITION_ID] == NOW + timedelta(seconds=4), "attempt 2"
    assert rig.store.closes == []


async def test_an_expired_sell_clears_the_marker_so_the_loop_may_try_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [sell_row(last_valid_block_height=5)]
    rig.ctx.chain.rpc.statuses = [None]
    rig.ctx.chain.rpc.block_height = 6
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.failed == [(ORDER_ID, "blockhash_expired_never_landed")]
    assert rig.store.pending_cleared[0]["outcome"] == "failed:blockhash_expired_never_landed"
