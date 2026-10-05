"""T4.8f (guardian, 05/10): PumpSwap sells had no ``unexplained`` check.

The sell message always ends with a ``CloseAccount`` of the wallet's WSOL ATA, which pays
back **everything the ATA holds** — the rent and whatever WSOL was already there — on top of
this sale's proceeds. With an ATA created in the same transaction that is a round trip (the
payer funded the rent); with a **pre-existing** ATA (spot/1 trades through WSOL) the payer
delta inflates the position's PnL by the rent plus the leftover — the family of the ATA-rent
bug of KB-0171. The fix reads what the ATA held *before* the transaction from its own
``preBalances``, keeps it out of ``sell_net_lamports`` and reports ``unexplained_lamports``.

Fixtures: real third-party PumpSwap sells of 2026-10-05 (``t48e_rpc_amm_tx_*``); the
pre-existing-ATA shape is one of them with the ATA's balances edited, labelled below.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID, associated_token_address
from hunter_exchanges.pumpswap.decode import WSOL_MINT
from hunter_meme_executor.pumpswap_build import decode_pumpswap_fills
from hunter_meme_executor.stored_fill import PUMPSWAP, parse_stored_sell_fill

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpswap"
)
ATA_RENT = 2_039_280
LEFTOVER_WSOL = 500_000


def _tx(sig12: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"t48e_rpc_amm_tx_{sig12}_raw.json").read_text(encoding="utf-8"))


def _with_preexisting_wsol_ata(tx: dict[str, Any], held: int) -> dict[str, Any]:
    """SYNTHETIC: the same sale, but the wallet's WSOL ATA already held ``held`` lamports
    (rent + leftover WSOL), so the closing ``CloseAccount`` pays them back to the payer."""
    out = copy.deepcopy(tx)
    loaded = cast(dict[str, list[str]], out["meta"].get("loadedAddresses") or {})
    keys = [
        *cast(list[str], out["transaction"]["message"]["accountKeys"]),
        *loaded.get("writable", []),
        *loaded.get("readonly", []),
    ]
    ata = associated_token_address(keys[0], WSOL_MINT, token_program=TOKEN_PROGRAM_ID)
    out["meta"]["preBalances"][keys.index(ata)] += held
    out["meta"]["postBalances"][0] += held
    return out


def test_a_sale_through_an_ata_created_in_the_transaction_has_nothing_unexplained() -> None:
    (fill,) = decode_pumpswap_fills(_tx("5mrYZLam93Kd"))
    assert fill.wsol_ata_pre_lamports == 0
    assert fill.event is not None and fill.payer_delta_lamports is not None
    assert fill.sell_net_lamports == fill.payer_delta_lamports
    assert fill.sell_net_lamports == fill.event.user_quote_amount_out - fill.network_fee_lamports
    assert fill.unexplained_lamports == 0
    payload = fill.as_json()
    assert payload["unexplained_lamports"] == 0 and payload["wsol_ata_pre_lamports"] == 0


def test_a_preexisting_wsol_ata_does_not_inflate_the_sale() -> None:
    clean = decode_pumpswap_fills(_tx("5mrYZLam93Kd"))[0]
    held = ATA_RENT + LEFTOVER_WSOL
    (fill,) = decode_pumpswap_fills(_with_preexisting_wsol_ata(_tx("5mrYZLam93Kd"), held))
    assert fill.wsol_ata_pre_lamports == held
    # the wallet really received more (rent + leftover come back) ...
    assert clean.payer_delta_lamports is not None
    assert fill.payer_delta_lamports == clean.payer_delta_lamports + held
    # ... but that is not this position's sale: the ledger number is unchanged
    assert fill.sell_net_lamports == clean.sell_net_lamports
    assert fill.unexplained_lamports == 0
    assert fill.as_json()["wsol_ata_pre_lamports"] == held
    assert fill.as_json()["sell_net_lamports"] == clean.sell_net_lamports


def test_a_cost_the_event_does_not_explain_is_reported_not_hidden() -> None:
    """A real third-party sale whose wallet paid 108 019 lamports beyond the event and the
    network fee (another program's cut): ``unexplained`` carries it, ``sell_net`` stays the
    wallet's real delta."""
    (fill,) = decode_pumpswap_fills(_tx("V99doZZTds6x"))
    assert fill.event is not None
    assert fill.unexplained_lamports == -108_019
    assert fill.sell_net_lamports == fill.payer_delta_lamports == 205_841_594


def test_the_preexisting_ata_stays_out_of_the_sale_even_without_an_event() -> None:
    """The payer-delta fallback (event undecodable) must not book the leftover either."""
    tx = _with_preexisting_wsol_ata(_tx("5mrYZLam93Kd"), ATA_RENT + LEFTOVER_WSOL)
    tx["meta"]["innerInstructions"] = []  # no SellEvent to read: the payer-delta fallback
    (fill,) = decode_pumpswap_fills(tx)
    assert fill.event is None and fill.unexplained_lamports is None
    assert fill.sell_net_lamports == 11_713_877  # delta − (rent + leftover): the clean sale
    assert fill.wsol_ata_pre_lamports == ATA_RENT + LEFTOVER_WSOL


def test_the_stored_json_replays_with_the_adjusted_number() -> None:
    held = ATA_RENT + LEFTOVER_WSOL
    (fill,) = decode_pumpswap_fills(_with_preexisting_wsol_ata(_tx("5mrYZLam93Kd"), held))
    stored = parse_stored_sell_fill(json.loads(json.dumps(fill.as_json())), venue=PUMPSWAP)
    assert stored is not None and stored.sell_net_lamports == 11_713_877


def test_a_transaction_without_the_ata_among_its_accounts_keeps_the_plain_delta() -> None:
    """Not our shape (no unwrap): nothing to subtract, nothing invented."""
    tx = _tx("5mrYZLam93Kd")
    tx["meta"]["postBalances"] = tx["meta"]["postBalances"][:1]
    tx["meta"]["preBalances"] = tx["meta"]["preBalances"][:1]
    tx["transaction"]["message"]["accountKeys"] = tx["transaction"]["message"]["accountKeys"][:1]
    tx["meta"]["innerInstructions"] = []
    (fill,) = decode_pumpswap_fills(tx)
    assert fill.wsol_ata_pre_lamports is None
    assert fill.sell_net_lamports == fill.payer_delta_lamports
