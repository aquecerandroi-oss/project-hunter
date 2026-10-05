"""T4.8f (Astra, round 3): the first cashback PumpSwap sell of a wallet that never traded there
creates its ``user_volume_accumulator`` (and, if absent, the accumulator's WSOL ATA) at the
payer's expense — measured by simulating our own sell on a migrated cashback pool: the
accumulator went 0 -> 1 346 200 lamports and the payer's delta fell by exactly that. The
ledger's truth stays the payer's real delta (``sell_net_lamports``); what changes is that the
cost is **named** (``cashback_init_lamports``, read from the transaction's own pre/post balances,
never a constant) so ``unexplained_lamports`` keeps meaning "something we cannot explain".
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID, associated_token_address
from hunter_exchanges.pumpswap.decode import WSOL_MINT
from hunter_exchanges.pumpswap.pdas import user_volume_accumulator_address
from hunter_meme_executor.pumpswap_build import decode_pumpswap_fills

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpswap"
)
ACCUMULATOR_RENT = 1_346_200  # what the simulation showed; here only a test number
ATA_RENT = 2_039_280


def _clean() -> dict[str, Any]:
    return json.loads((FIXTURES / "t48e_rpc_amm_tx_5mrYZLam93Kd_raw.json").read_text())


def _with_cashback_accounts(
    tx: dict[str, Any], *, acc: tuple[int, int], ata: tuple[int, int], payer_pays: int
) -> dict[str, Any]:
    """SYNTHETIC: the same sale with the two cashback accounts among the transaction's accounts
    (appended after every real one, so no instruction index moves) and balances ``(pre, post)``."""
    out = copy.deepcopy(tx)
    payer = out["transaction"]["message"]["accountKeys"][0]
    accumulator = user_volume_accumulator_address(payer)
    accumulator_ata = associated_token_address(
        accumulator, WSOL_MINT, token_program=TOKEN_PROGRAM_ID
    )
    meta = out["meta"]
    loaded = cast(
        dict[str, list[str]], meta.setdefault("loadedAddresses", {"writable": [], "readonly": []})
    )
    loaded["readonly"] = [*loaded.get("readonly", []), accumulator, accumulator_ata]
    meta["preBalances"] = [*meta["preBalances"], acc[0], ata[0]]
    meta["postBalances"] = [*meta["postBalances"], acc[1], ata[1]]
    meta["postBalances"][0] -= payer_pays  # the payer funded the creation
    return out


def test_a_first_cashback_sell_names_the_accumulator_it_funded_and_unexplained_stays_zero() -> None:
    clean = decode_pumpswap_fills(_clean())[0]
    tx = _with_cashback_accounts(
        _clean(), acc=(0, ACCUMULATOR_RENT), ata=(ATA_RENT, ATA_RENT), payer_pays=ACCUMULATOR_RENT
    )
    (fill,) = decode_pumpswap_fills(tx)
    assert fill.cashback_init_lamports == ACCUMULATOR_RENT
    assert fill.payer_delta_lamports == (clean.payer_delta_lamports or 0) - ACCUMULATOR_RENT
    assert fill.sell_net_lamports == fill.payer_delta_lamports, "the wallet's real delta is the PnL"
    assert fill.unexplained_lamports == 0, "the cost is named, not hidden in the residual"
    assert fill.as_json()["cashback_init_lamports"] == ACCUMULATOR_RENT


def test_both_accounts_created_in_the_sale_are_summed() -> None:
    tx = _with_cashback_accounts(
        _clean(),
        acc=(0, ACCUMULATOR_RENT),
        ata=(0, ATA_RENT),
        payer_pays=ACCUMULATOR_RENT + ATA_RENT,
    )
    (fill,) = decode_pumpswap_fills(tx)
    assert fill.cashback_init_lamports == ACCUMULATOR_RENT + ATA_RENT
    assert fill.unexplained_lamports == 0


def test_accounts_that_already_existed_name_nothing() -> None:
    tx = _with_cashback_accounts(
        _clean(), acc=(ACCUMULATOR_RENT, ACCUMULATOR_RENT), ata=(ATA_RENT, 2_045_000), payer_pays=0
    )
    (fill,) = decode_pumpswap_fills(tx)
    assert fill.cashback_init_lamports is None and fill.unexplained_lamports == 0


def test_a_residual_that_is_not_the_creation_is_still_unexplained() -> None:
    """The payer lost more than the accounts it created: the rest stays visible."""
    tx = _with_cashback_accounts(
        _clean(),
        acc=(0, ACCUMULATOR_RENT),
        ata=(ATA_RENT, ATA_RENT),
        payer_pays=ACCUMULATOR_RENT + 777,
    )
    (fill,) = decode_pumpswap_fills(tx)
    assert fill.unexplained_lamports == -777


def test_a_sell_without_the_cashback_accounts_has_nothing_to_name() -> None:
    (fill,) = decode_pumpswap_fills(_clean())
    assert fill.cashback_init_lamports is None and fill.unexplained_lamports == 0
