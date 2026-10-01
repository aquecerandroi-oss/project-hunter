"""KB-0171 — the two openers of a ``spot/1`` position (the entries loop's
``open_position`` and the reconcile's ``open_from_order``) take the rent from
the transaction, through the one rule ``entry_spend``; a stored fill written
before the fix (no ``ata_rent_source``) is never believed when it says it
locked rent (Astra, design review: a crash orphan repaired after the deploy
would otherwise bring the old constant back). Fakes only."""

from __future__ import annotations

from typing import Any, cast

import pytest

from hunter_meme_executor import spot_entries, spot_reconcile
from hunter_meme_executor.spot_send_rules import ATA_RENT_SOURCE, stored_fill_rent

from .spot_entries_rig import UNI_OUT, Store, candidate, entries_rig
from .spot_exits_rig import TICKET, exits_rig, order_row
from .spot_fakes import tx_meta
from .spot_tx_fixtures import ATA_RENT, WIF

pytestmark = pytest.mark.unit

LEGACY_RENT = 2_039_280
FEES = 5_050


@pytest.mark.parametrize(
    "fill,expected",
    [
        ({"ata_rent_lamports": ATA_RENT, "ata_rent_source": ATA_RENT_SOURCE}, ATA_RENT),
        ({"ata_rent_lamports": 0, "ata_rent_source": ATA_RENT_SOURCE}, 0),
        ({"ata_rent_lamports": None, "ata_rent_source": ATA_RENT_SOURCE}, None),
        ({"ata_rent_lamports": LEGACY_RENT}, None),  # the old constant: unknown
        ({"ata_rent_lamports": 0}, 0),  # legacy, reused ATA
        ({}, 0),
    ],
)
def test_a_stored_fill_s_rent_is_trusted_only_with_its_provenance(
    fill: dict[str, Any], expected: int | None
) -> None:
    assert stored_fill_rent(fill) == expected


async def _orphan_opened(monkeypatch: pytest.MonkeyPatch, fill: dict[str, Any]) -> dict[str, Any]:
    rig = exits_rig(monkeypatch)
    rig.store.orphan_buys = [order_row(status="confirmed", fill=fill)]
    await spot_reconcile.spot_reconcile_once(rig.ctx)
    (opened,) = rig.store.opened
    return opened


async def test_a_legacy_orphan_fill_folds_its_rent_and_says_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fill = {
        "filled_atoms": UNI_OUT,
        "ata_rent_lamports": LEGACY_RENT,
        "sol_delta_lamports": -(TICKET + ATA_RENT + FEES),
    }
    opened = await _orphan_opened(monkeypatch, fill)
    assert opened["sol_spent_lamports"] == TICKET + ATA_RENT + FEES, "pessimistic, never +550 840"
    assert opened["ata_rent_lamports"] == 0
    assert opened["entry"]["sol_spent_source"] == "signature_delta_rent_unknown"


async def test_a_new_orphan_fill_keeps_its_read_rent_out_of_the_spend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fill = {
        "filled_atoms": UNI_OUT,
        "ata_rent_lamports": ATA_RENT,
        "ata_rent_source": ATA_RENT_SOURCE,
        "sol_delta_lamports": -(TICKET + ATA_RENT + FEES),
    }
    opened = await _orphan_opened(monkeypatch, fill)
    assert opened["sol_spent_lamports"] == TICKET + FEES
    assert opened["ata_rent_lamports"] == ATA_RENT
    assert opened["entry"]["sol_spent_source"] == "signature_delta_minus_rent"


async def test_an_unknown_rent_on_a_new_orphan_fill_is_folded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fill = {
        "filled_atoms": UNI_OUT,
        "ata_rent_lamports": None,
        "ata_rent_source": ATA_RENT_SOURCE,
        "sol_delta_lamports": -(TICKET + ATA_RENT + FEES),
    }
    opened = await _orphan_opened(monkeypatch, fill)
    assert opened["sol_spent_lamports"] == TICKET + ATA_RENT + FEES
    assert opened["entry"]["sol_spent_source"] == "signature_delta_rent_unknown"


async def test_the_live_buy_whose_ata_deposit_is_unreadable_opens_pessimistic_and_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(candidates=[candidate()])
    rig = entries_rig(monkeypatch, store)
    rig.ctx.chain.rpc.transaction = tx_meta(
        wallet_pre=500_000_000,
        wallet_post=500_000_000 - TICKET - ATA_RENT - FEES,
        token_pre=None,
        token_post=UNI_OUT,
        mint=WIF,
        ata_rent=None,
    )
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    (pos,) = store.positions
    assert pos["sol_spent_lamports"] == TICKET + ATA_RENT + FEES
    assert pos["ata_rent_lamports"] == 0
    assert pos["entry"]["sol_spent_source"] == "signature_delta_rent_unknown"
    fill = cast(dict[str, Any], next(kw["fill"] for s, kw in rig.db.rows if s == "confirmed"))
    assert fill["ata_rent_lamports"] is None and fill["ata_rent_source"] == ATA_RENT_SOURCE


async def test_the_live_buy_records_the_rent_the_chain_charged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(candidates=[candidate()])
    rig = entries_rig(monkeypatch, store)
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    (pos,) = store.positions
    assert (pos["sol_spent_lamports"], pos["ata_rent_lamports"]) == (TICKET + FEES, ATA_RENT)
    assert pos["params"]["ata_rent_lamports"] == ATA_RENT
    fill = cast(dict[str, Any], next(kw["fill"] for s, kw in rig.db.rows if s == "confirmed"))
    assert fill["ata_rent_lamports"] == ATA_RENT and fill["ata_rent_source"] == ATA_RENT_SOURCE
