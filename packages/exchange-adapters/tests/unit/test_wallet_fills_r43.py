"""R43 — the 2 860 040 lamports the first real buy spent outside the trade.

The operator's first mainnet fill (16/09/2026 21:31 BRT, TAXCOIN) left the wallet
52 659 524 lamports lighter, while the pump ``TradeEvent`` plus every fee it names
plus the network fee account for only 49 799 484. The executor's ``FillRecord``
calls the difference ``unexplained_lamports``; ``meme_live_positions`` swallows it
inside ``sol_spent_lamports`` (the payer delta), and ``wallet_fills`` — the watcher's
reading of the same transaction — simply loses it. Both halves are pinned here:

* 1 513 840 — rent of the Token-2022 ATA created by ``createIdempotent`` (170 bytes
  with ``immutableOwner``; 5 080 lamports/byte at the current rent rate, not the
  2 039 280 of a 165-byte SPL account). **Per coin bought**, refundable only by a
  ``CloseAccount`` the sell never sends.
* 1 346 200 — rent of the ``user_volume_accumulator`` PDA (137 bytes), seeded by the
  wallet alone (``tx.user_volume_accumulator_address``): **one-time per wallet**.

``_rent_funded_by`` is the whole of the proposed fix: a pure reading of the inner
``system::createAccount`` instructions the wallet funded, which would let a fill carry
``ata_rent_lamports`` instead of an unnamed residue. Nothing here touches the executor,
a socket or a clock — three captured ``getTransaction`` results, two encodings
(``json`` is what the decoders demand; ``jsonParsed`` is what names the rent).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.tx import user_volume_accumulator_address
from hunter_exchanges.pumpfun.wallet_fills import wallet_fills_from_transaction

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
BUY_JSON = "rpc_tx_r43_real_buy_json_raw.json"
BUY_PARSED = "rpc_tx_r43_real_buy_raw.json"
SELL_PARSED = "rpc_tx_r43_real_sell_raw.json"

WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
MINT = "7s4dKmpvQxNy5CwDpsy9SKw3JVoFGRYNd6F8mr4GAxi8"
BUY_SIG = "SwjKQmywDbwgXZnuhZzCiYYduVTTzdrA146vfS8uXebotkAesRDUU32i6obist86xSh5Pd926baRS8qWhcjEyK7"
TOKEN_ATA = "oP37bN43zQGNp4Lx6ADrfvFfDtmkBYWs6AQGsS6fxTA"
ACCUMULATOR = "BY3qA3VVv76yCKHCSLcNJAGxtjpdywUznPgUo7xoMben"

ATA_RENT = 1_513_840
ACCUMULATOR_RENT = 1_346_200
GAP = 2_860_040
BUY_PAYER_DELTA = -52_659_524
SELL_PAYER_DELTA = 42_895_712
EVENT_SPENT = 49_799_484
"""``sol_amount`` 49 175 786 + fee 467 170 + creator fee 147 528 + network fee 9 000."""


def _tx(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def _payer_delta(tx: dict[str, Any]) -> int:
    meta = cast(dict[str, Any], tx["meta"])
    return int(meta["postBalances"][0]) - int(meta["preBalances"][0])


def _rent_funded_by(tx: dict[str, Any], wallet: str) -> dict[str, int]:
    """``new account -> lamports`` for every ``createAccount`` the wallet paid for.

    The proposed labelling, as a pure function of a ``jsonParsed`` payload: no program
    list, no PDA guessing, just the System Program's own words.
    """
    meta = cast(dict[str, Any], tx.get("meta") or {})
    rent: dict[str, int] = {}
    for group in cast(list[Any], meta.get("innerInstructions") or []):
        for ix in cast(list[Any], cast(dict[str, Any], group).get("instructions") or []):
            parsed = cast(dict[str, Any], ix).get("parsed")
            if not isinstance(parsed, dict) or parsed.get("type") != "createAccount":
                continue
            info = cast(dict[str, Any], parsed.get("info") or {})
            if info.get("source") != wallet:
                continue
            key = str(info["newAccount"])
            rent[key] = rent.get(key, 0) + int(info["lamports"])
    return rent


def _parsed_types(tx: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for group in cast(list[Any], cast(dict[str, Any], tx["meta"])["innerInstructions"]):
        for ix in cast(list[Any], cast(dict[str, Any], group)["instructions"]):
            parsed = cast(dict[str, Any], ix).get("parsed")
            if isinstance(parsed, dict):
                out.add(str(parsed.get("type")))
    return out


def test_buy_fill_is_short_of_the_wallet_by_the_rent() -> None:
    """The fill's arithmetic is exact — and is not what the wallet lost."""
    tx = _tx(BUY_JSON)
    (fill,) = wallet_fills_from_transaction(tx, wallet=WALLET, signature=BUY_SIG)
    assert (fill.side, fill.mint, fill.decode) == ("buy", MINT, "trade_event")
    assert fill.sol_lamports == 49_175_786
    assert fill.fee_lamports == 467_170 + 147_528 + 9_000
    assert fill.sol_spent_lamports == EVENT_SPENT
    assert _payer_delta(tx) == BUY_PAYER_DELTA
    assert -BUY_PAYER_DELTA - EVENT_SPENT == GAP, "the executor's unexplained_lamports"


def test_rent_names_every_lamport_of_the_gap() -> None:
    """Two ``createAccount``s, and the sum closes the transaction to the lamport."""
    parsed = _tx(BUY_PARSED)
    rent = _rent_funded_by(parsed, WALLET)
    assert rent == {TOKEN_ATA: ATA_RENT, ACCUMULATOR: ACCUMULATOR_RENT}
    assert sum(rent.values()) == GAP
    assert EVENT_SPENT + sum(rent.values()) == -BUY_PAYER_DELTA == -_payer_delta(parsed)


def test_accumulator_rent_is_per_wallet_and_ata_rent_is_per_coin() -> None:
    """The PDA is seeded by the wallet alone: a second coin pays the ATA rent again,
    never this one."""
    assert user_volume_accumulator_address(WALLET) == ACCUMULATOR
    rent = _rent_funded_by(_tx(BUY_PARSED), WALLET)
    assert rent[ACCUMULATOR] == ACCUMULATOR_RENT
    assert rent[TOKEN_ATA] == ATA_RENT
    top = cast(
        list[Any],
        cast(dict[str, Any], cast(dict[str, Any], _tx(BUY_PARSED)["transaction"])["message"])[
            "instructions"
        ],
    )
    creates = [
        ix
        for ix in top
        if isinstance(cast(dict[str, Any], ix).get("parsed"), dict)
        and cast(dict[str, Any], cast(dict[str, Any], ix)["parsed"]).get("type")
        == "createIdempotent"
    ]
    assert len(creates) == 1, "one ATA per mint, created by the buy itself"


def test_priority_fee_is_inside_the_network_fee_not_the_gap() -> None:
    """5 000 base + 4 000 priority = ``meta.fee``; the residue is no compute-budget cost."""
    tx = _tx(BUY_JSON)
    assert int(cast(dict[str, Any], tx["meta"])["fee"]) == 9_000
    (fill,) = wallet_fills_from_transaction(tx, wallet=WALLET, signature=BUY_SIG)
    fees = cast(dict[str, Any], fill.raw["fees"])
    assert fees["network"] == 9_000
    assert fees["protocol"] + fees["creator"] == 467_170 + 147_528
    assert fees["network"] + fees["protocol"] + fees["creator"] + fill.sol_lamports == EVENT_SPENT


def test_sell_reconciles_and_leaves_the_ata_rent_on_chain() -> None:
    """The sell is lamport-exact — and 1 513 840 stays parked in the emptied ATA."""
    tx = _tx(SELL_PARSED)
    assert _payer_delta(tx) == SELL_PAYER_DELTA
    assert _rent_funded_by(tx, WALLET) == {}, "no new account: the accumulator exists"
    assert "closeAccount" not in _parsed_types(tx), "no CloseAccount: the rent is not refunded"
    top = cast(
        list[Any],
        cast(dict[str, Any], cast(dict[str, Any], tx["transaction"])["message"])["instructions"],
    )
    assert len(top) == 3, "2 compute budget + Sell; nothing closes the ATA"
    balances = [
        entry
        for entry in cast(list[Any], cast(dict[str, Any], tx["meta"])["postTokenBalances"])
        if cast(dict[str, Any], entry).get("owner") == WALLET
    ]
    amount = cast(dict[str, Any], cast(dict[str, Any], balances[0])["uiTokenAmount"])["amount"]
    assert Decimal(str(amount)) == 0, "token balance 0 — the ATA is closable, and left open"


def test_ledger_pnl_equals_the_wallet_delta() -> None:
    """The gap *is* charged to the position: ``pnl = received − payer-delta spend``.

    ``meme_live_positions`` on the VPS: ``sol_spent_lamports = 52 659 524``,
    ``sol_received_lamports = 42 895 712``, ``pnl_sol = −0.0097638120`` — the wallet's
    own 717 439 933 → 707 676 121. Nothing is lost to the ledger; it is only unnamed.
    """
    buy, sell = _tx(BUY_PARSED), _tx(SELL_PARSED)
    spent, received = -_payer_delta(buy), _payer_delta(sell)
    assert (spent, received) == (52_659_524, 42_895_712)
    assert Decimal(received - spent) / Decimal(1_000_000_000) == Decimal("-0.009763812")
    # Of that loss, the ATA rent is recoverable and the accumulator rent is not.
    assert spent - received - ATA_RENT == 8_249_972


def test_json_parsed_payload_decodes_as_unknown() -> None:
    """The trap next door: ``wallet_fills`` wants ``encoding: json`` and does not check.

    Handed the ``jsonParsed`` result of the very same transaction it stringifies the
    account-key objects, never finds the wallet, and returns ``unknown`` — no error.
    """
    (fill,) = wallet_fills_from_transaction(_tx(BUY_PARSED), wallet=WALLET, signature=BUY_SIG)
    assert fill.side == "unknown"
    assert fill.raw.get("reason") == "no_known_venue", "not even the pump program is seen"
    assert fill.sol_lamports is None
