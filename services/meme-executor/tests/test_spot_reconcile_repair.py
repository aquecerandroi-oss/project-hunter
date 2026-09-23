"""T4.74-5 — ``spot_reconcile.spot_reconcile_once`` with fakes only, part 2:
the crash orphans repaired from the row's fill (a confirmed buy with no
position, a confirmed sell whose position still names it, a marker left on a
refused sell), abandoned rows never signed, and the guards (no signer, short
or unreadable RPC answers, a meta that contradicts its side, a transaction
that lands between the status and the height, entry_at from the block time)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from hunter_meme_executor import spot_reconcile
from hunter_meme_executor.spot_send_rules import ATA_RENT_LAMPORTS

from .spot_exits_rig import (
    NOW,
    ORDER_ID,
    POSITION_ID,
    TICKET,
    UNI_OUT,
    buy_landed,
    confirmed_status,
    exits_rig,
    order_row,
    position,
    sell_row,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------- orphans
async def test_a_confirmed_buy_without_a_position_is_opened_from_its_own_fill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    fill = {
        "filled_atoms": UNI_OUT,
        "ata_rent_lamports": ATA_RENT_LAMPORTS,
        "sol_delta_lamports": -(TICKET + ATA_RENT_LAMPORTS + 5_050),
        "quoted_out_atoms": UNI_OUT,
    }
    rig.store.orphan_buys = [order_row(status="confirmed", fill=fill)]
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.log == [], "no chain read: the row's fill is the truth already recorded"
    assert rig.store.opened[0]["sol_spent_lamports"] == TICKET + 5_050
    assert rig.store.opened[0]["tokens"] == UNI_OUT


async def test_a_confirmed_sell_still_pending_on_its_position_closes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.positions = [
        position(exit_intent={"status": "submitted_unconfirmed", "order_id": ORDER_ID})
    ]
    fill = {"filled_atoms": 51_000_000, "sol_delta_lamports": 51_000_000}
    rig.store.orphan_sells = [sell_row(status="confirmed", fill=fill)]
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.closes[0]["sol_received_lamports"] == 51_000_000
    assert rig.store.closes[0]["exit_payload"]["reason"] == "target"


async def test_an_orphan_without_a_fill_is_never_guessed(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.orphan_buys = [order_row(status="confirmed", fill=None)]
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.opened == []


# -------------------------------------------------------- abandoned rows
async def test_an_admitted_row_never_signed_is_failed_after_the_grace_and_frees_its_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    old = NOW - timedelta(seconds=spot_reconcile.ABANDONED_AFTER_S + 1)
    fresh = NOW - timedelta(seconds=10)
    rig.store.abandoned = [
        order_row(id="buy-old", status="admitted", signature="", submitted_at=old),
        sell_row(id="sell-old", status="simulated", signature="", submitted_at=old),
        order_row(id="buy-fresh", status="admitted", signature="", submitted_at=fresh),
    ]
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.abandoned_failed == ["buy-old", "sell-old"], "a live leg is left alone"
    assert rig.store.pending_cleared == [
        {
            "position_id": POSITION_ID,
            "order_id": "sell-old",
            "outcome": "abandoned_before_signing",
            "now": NOW,
        }
    ]


# ------------------------------------------------------------------ guards
async def test_without_a_signer_nothing_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = exits_rig(monkeypatch)
    rig.ctx.signer = None
    rig.store.unconfirmed = [order_row()]
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.queries == [] and rig.log == []


async def test_an_unreadable_status_read_leaves_every_row_and_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [order_row()]

    def boom(signatures: list[str]) -> list[Any]:
        raise ConnectionError("rpc")

    monkeypatch.setattr(rig.ctx.chain.rpc, "get_signature_statuses", boom)
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.failed == [] and rig.store.confirmed == []
    assert rig.ctx.state.rpc_errors == 1


async def test_a_landed_buy_whose_meta_contradicts_its_side_is_left_for_a_human(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [order_row()]
    buy_landed(rig, token_pre=UNI_OUT, token_post=UNI_OUT)  # no tokens landed
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.confirmed == [] and rig.store.opened == []


async def test_a_transaction_that_lands_between_the_status_and_the_height_is_not_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [order_row(last_valid_block_height=100)]
    rig.ctx.chain.rpc.statuses = [None, confirmed_status()]  # 1st look: nothing; 2nd: it landed
    rig.ctx.chain.rpc.block_height = 101
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.failed == [], "never failed on a stale absence"
    assert rig.stats.reconciled_expired == 0


async def test_a_short_answer_on_the_second_look_is_not_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4.90b: the height is past ``last_valid``, the first read said ``None``
    and the second look came back ``[]``. That proves nothing — before the fix
    the landed buy became ``failed:blockhash_expired_never_landed``, its
    reservation was released and the tokens sat in the wallet with no position."""
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [order_row(last_valid_block_height=100)]
    answers: list[list[Any]] = [[None], []]

    def first_none_then_short(signatures: list[str]) -> list[Any]:
        return answers.pop(0)

    monkeypatch.setattr(rig.ctx.chain.rpc, "get_signature_statuses", first_none_then_short)
    rig.ctx.chain.rpc.block_height = 101
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert answers == [], "both looks were taken"
    assert rig.store.failed == [], "a short answer never becomes failed"
    assert rig.stats.reconciled_expired == 0 and rig.ctx.state.rpc_errors == 1


async def test_a_short_status_answer_settles_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [order_row(last_valid_block_height=1), order_row(id="o2")]

    def short(signatures: list[str]) -> list[Any]:
        return [None]

    monkeypatch.setattr(rig.ctx.chain.rpc, "get_signature_statuses", short)
    rig.ctx.chain.rpc.block_height = 10
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.failed == [] and rig.ctx.state.rpc_errors == 1


async def test_a_sell_the_leg_confirmed_meanwhile_keeps_its_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [sell_row()]
    rig.ctx.chain.rpc.statuses = [{"confirmationStatus": "confirmed", "err": {"x": 1}}]
    rig.store.failed_ok = False  # the row is ``confirmed`` already: ``mark_failed`` loses
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    assert rig.store.pending_cleared == [], "exit_order_id stays for the orphan repair"
    assert POSITION_ID not in rig.stats.exit_backoff_until


async def test_a_marker_left_on_a_refused_sell_by_a_crash_is_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.stuck = [sell_row(status="refused", intent={"reason": "stop", "attempt": 1})]
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    (cleared,) = rig.store.pending_cleared
    assert cleared["position_id"] == POSITION_ID and cleared["order_id"] == ORDER_ID
    assert cleared["outcome"] == "refused:stop"


async def test_a_late_buy_enters_at_its_block_time_never_at_the_repair_instant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    rig.store.unconfirmed = [order_row(submitted_at=NOW - timedelta(hours=5))]
    buy_landed(rig)
    landed = NOW - timedelta(hours=5, seconds=-2)
    rig.ctx.chain.rpc.transaction["blockTime"] = int(landed.timestamp())
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    opened = rig.store.opened[0]
    assert opened["entry_at"] == landed and opened["params"]["entry_at_source"] == "block_time"
    assert rig.store.confirmed[0]["landed_at"] == landed.isoformat()


async def test_an_orphan_buy_without_a_block_time_enters_at_its_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = exits_rig(monkeypatch)
    submitted = NOW - timedelta(hours=3)
    fill = {"filled_atoms": UNI_OUT, "ata_rent_lamports": 0, "sol_delta_lamports": -TICKET}
    rig.store.orphan_buys = [order_row(status="confirmed", fill=fill, submitted_at=submitted)]
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    opened = rig.store.opened[0]
    assert opened["entry_at"] == submitted
    assert opened["params"]["entry_at_source"] == "submitted_at"
