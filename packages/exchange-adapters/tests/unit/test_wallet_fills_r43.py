"""R43 — the 2 860 040 lamports the first real buy spent outside the trade, and
T4.46's answer: name the rent instead of losing it.

The operator's first mainnet fill (16/09/2026 21:31 BRT, TAXCOIN) left the wallet
52 659 524 lamports lighter, while the pump ``TradeEvent`` plus every fee it names
plus the network fee account for only 49 799 484. The gap is two ``createAccount``s
the wallet funded:

* 1 513 840 — rent of the Token-2022 ATA created by ``createIdempotent`` (170 bytes
  with ``immutableOwner``; 5 080 lamports/byte at the current rent rate, not the
  2 039 280 of a 165-byte SPL account). **Per coin bought**, refundable only by a
  ``CloseAccount`` the sell of 16/09/2026 never sent (T4.46 makes the executor send
  one on a full sell from here on).
* 1 346 200 — rent of the ``user_volume_accumulator`` PDA (137 bytes), seeded by the
  wallet alone (``tx.user_volume_accumulator_address``): **one-time per wallet**.

``hunter_exchanges.pumpfun.wallet_fills.rent_funded_by`` is T4.46's fix, in
production, not a pure copy in a test: a reading of the wallet's own inner
``system::createAccount`` instructions, ``jsonParsed`` **or** the raw
``encoding: json`` the RPC clients in this repo actually request (the System
Program's instruction data itself: ``u32 index=0, u64 lamports, u64 space, pubkey
owner`` — decoded byte-for-byte against this fixture below). ``ata_close_refund_lamports``
does the same for the sell side's ``CloseAccount``. Three captured ``getTransaction``
results, two encodings (``json`` is what the decoders demand; ``jsonParsed`` is what
the R43 investigation used to name the rent first) plus one small synthetic sell
(no real close was ever captured before T4.46 shipped the builder side).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.tx import user_volume_accumulator_address
from hunter_exchanges.pumpfun.wallet_fills import (
    ata_close_refund_lamports,
    rent_funded_by,
    rent_labels,
    wallet_fills_from_transaction,
)

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


def _parsed_types(tx: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for group in cast(list[Any], cast(dict[str, Any], tx["meta"])["innerInstructions"]):
        for ix in cast(list[Any], cast(dict[str, Any], group)["instructions"]):
            parsed_raw = cast(dict[str, Any], ix).get("parsed")
            if isinstance(parsed_raw, dict):
                out.add(str(cast(dict[str, Any], parsed_raw).get("type")))
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
    """Two ``createAccount``s, and the sum closes the transaction to the lamport —
    ``rent_funded_by`` in production (T4.46), not a pure copy in this test."""
    parsed = _tx(BUY_PARSED)
    rent = rent_funded_by(parsed, WALLET)
    assert rent == {TOKEN_ATA: ATA_RENT, ACCUMULATOR: ACCUMULATOR_RENT}
    assert sum(rent.values()) == GAP
    assert EVENT_SPENT + sum(rent.values()) == -BUY_PAYER_DELTA == -_payer_delta(parsed)


def test_rent_names_the_same_gap_from_the_raw_encoding_json_result_too() -> None:
    """T4.46: the RPC clients in this repo request ``encoding: json`` (never
    ``jsonParsed``) for a real ``getTransaction`` — so the fix must read the raw
    ``data`` field of the System Program's own ``createAccount``, not only the
    ``parsed`` convenience the R43 investigation used to find the rent first."""
    raw = _tx(BUY_JSON)
    rent = rent_funded_by(raw, WALLET)
    assert rent == {TOKEN_ATA: ATA_RENT, ACCUMULATOR: ACCUMULATOR_RENT}
    assert rent_labels(raw, WALLET) == (ATA_RENT, ACCUMULATOR_RENT)


def test_accumulator_rent_is_per_wallet_and_ata_rent_is_per_coin() -> None:
    """The PDA is seeded by the wallet alone: a second coin pays the ATA rent again,
    never this one."""
    assert user_volume_accumulator_address(WALLET) == ACCUMULATOR
    rent = rent_funded_by(_tx(BUY_PARSED), WALLET)
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


def test_the_watcher_now_names_the_same_rent_the_executor_does() -> None:
    """T4.46 closes R43's §3 gap: ``wallet_fills`` (the watcher) and ``FillRecord``
    (the executor, ``build.py``) read the wallet's own ``createAccount``s the same
    way, so ``meme_wallet_trades`` and ``meme_live_positions`` stop disagreeing by
    the rent on every buy."""
    (fill,) = wallet_fills_from_transaction(_tx(BUY_JSON), wallet=WALLET, signature=BUY_SIG)
    assert fill.raw["ata_rent_lamports"] == ATA_RENT
    assert fill.raw["account_rent_lamports"] == ACCUMULATOR_RENT


def test_sell_reconciles_and_leaves_the_ata_rent_on_chain() -> None:
    """The sell is lamport-exact — and 1 513 840 stays parked in the emptied ATA
    (16/09/2026: before T4.46 taught the builder to close it on a full sell)."""
    tx = _tx(SELL_PARSED)
    assert _payer_delta(tx) == SELL_PAYER_DELTA
    assert rent_funded_by(tx, WALLET) == {}, "no new account: the accumulator exists"
    assert "closeAccount" not in _parsed_types(tx), "no CloseAccount: the rent is not refunded"
    assert ata_close_refund_lamports(tx, WALLET) is None
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


def test_json_parsed_payload_now_names_the_program_not_the_wallet() -> None:
    """T4.46 fixes the one-line bug R43 §5 found (``_account_keys`` stringified a
    ``jsonParsed`` key object): the pump program is found in the account list, and
    the balance-delta fallback says so by a truer name (``no_trade_event_for_wallet``,
    not ``no_known_venue``). It still cannot decode a ``buy``/``sell`` from this
    payload — that decode goes through ``trade_event._event_payloads``, a different
    module, out of this task's scope, and its own ``programIdIndex`` comparison has
    the identical ``jsonParsed`` bug, left named here rather than silently patched."""
    (fill,) = wallet_fills_from_transaction(_tx(BUY_PARSED), wallet=WALLET, signature=BUY_SIG)
    assert fill.side == "unknown"
    assert fill.raw.get("reason") == "no_trade_event_for_wallet", "the pump program IS seen now"
    assert fill.sol_lamports is None


def _synthetic_sell_with_close() -> dict[str, Any]:
    """A minimal, hand-built ``getTransaction`` result: a curve ``sell`` (opaque
    ``data``, this reader never needs to decode it) followed by an SPL Token
    ``CloseAccount`` of the wallet's own ATA — the shape T4.46's builder now sends
    on a full sell. Account order: ``[wallet, mint's ATA, token program]``."""
    wallet, ata, token_program = "W" * 44, "A" * 44, "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    return {
        "slot": 1,
        "blockTime": 1_700_000_000,
        "transaction": {
            "signatures": ["sig"],
            "message": {
                "accountKeys": [wallet, ata, token_program],
                "instructions": [
                    {
                        "programIdIndex": 2,
                        "accounts": [1, 0, 0],
                        "data": "A",  # base58 of a single 0x09 byte
                    }
                ],
            },
        },
        "meta": {
            "err": None,
            "fee": 5_000,
            "preBalances": [1_000_000_000, 2_039_280, 0],
            "postBalances": [1_002_039_280, 0, 0],
            "innerInstructions": [],
            "preTokenBalances": [],
            "postTokenBalances": [],
        },
    }


def test_a_synthetic_close_labels_the_refund_and_feeds_it_into_sol_received() -> None:
    """No real sell has closed the ATA yet (T4.46 ships the day it is written) —
    this is the shape it will have, read the same way the real fixtures are."""
    tx = _synthetic_sell_with_close()
    wallet = tx["transaction"]["message"]["accountKeys"][0]
    refund = ata_close_refund_lamports(tx, wallet)
    assert refund == 2_039_280, "the closed ATA's own preBalance — rent-only, the instant before"


def test_wallet_fill_sol_received_folds_in_the_close_refund() -> None:
    """Wired at the ``WalletFill`` level: a sell whose ``raw`` already carries the
    refund (as ``_from_event`` would set it from a real trade) reports it as cash
    in, not a silent gap."""
    from datetime import UTC, datetime
    from decimal import Decimal as D

    from hunter_exchanges.pumpfun.wallet_fills import WalletFill

    fill = WalletFill(
        wallet=WALLET,
        signature="s",
        event_index=0,
        slot=1,
        block_time=datetime(2026, 9, 16, tzinfo=UTC),
        mint=MINT,
        side="sell",
        venue="curve",
        sol_lamports=100_000,
        fee_lamports=1_000,
        token_amount=D(0),
        decode="trade_event",
        raw={"ata_rent_refund_lamports": 2_039_280},
    )
    assert fill.sol_received_lamports == 100_000 - 1_000 + 2_039_280
