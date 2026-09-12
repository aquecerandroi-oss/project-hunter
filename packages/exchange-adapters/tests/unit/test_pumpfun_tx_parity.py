"""Byte-for-byte parity of our ``buy``/``sell`` with two confirmed mainnet transactions.

- ``rpc_tx_buy_raw.json`` — signature ``3R1GksCq…`` (slot 446373814): the site's
  own router (``6Vo3245…``) CPI-ing ``buy`` into the pump program. The inner
  instruction carries the exact accounts + data the program accepted.
- ``rpc_tx_probe_raw.json`` — signature ``5sLxc4wP…`` (same slot): an independent
  bot's direct ``sell`` (17 accounts).

Both fixtures were fetched read-only with ``getTransaction`` on the public RPC on
2026-09-12 ~07:34–07:42 UTC. The intent below is *reconstructed from the chain*
(user, mint, creator from the ``TradeEvent``, token program from the account
list, args from the data) and fed to our builder; the assertion is equality of
every account (pubkey, and writable flag where the outer message declares it)
and of the instruction data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.global_state import GlobalAccount, decode_global_account
from hunter_exchanges.pumpfun.solana_codec import b58decode
from hunter_exchanges.pumpfun.trade_event import trade_events_from_transaction
from hunter_exchanges.pumpfun.tx import (
    TradeIntent,
    build_buy_instruction,
    build_sell_instruction,
    decode_trade_instruction,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"


@pytest.fixture(scope="module")
def global_account() -> GlobalAccount:
    raw: dict[str, Any] = json.loads((FIXTURES / "rpc_global_account_raw.json").read_text())
    value = raw["result"]["value"]
    return decode_global_account(value["data"][0], owner=value["owner"])


def _keys_and_flags(tx: dict[str, Any]) -> tuple[list[str], list[bool | None]]:
    """Static keys with header-derived writability; loaded (ALT) keys by list."""
    message = tx["transaction"]["message"]
    keys: list[str] = list(message["accountKeys"])
    header = message["header"]
    n_signed = header["numRequiredSignatures"]
    n_ro_signed = header["numReadonlySignedAccounts"]
    n_ro_unsigned = header["numReadonlyUnsignedAccounts"]
    flags: list[bool | None] = []
    for i in range(len(keys)):
        if i < n_signed:
            flags.append(i < n_signed - n_ro_signed)
        else:
            flags.append(i < len(keys) - n_ro_unsigned)
    loaded: dict[str, list[str]] = tx["meta"].get("loadedAddresses") or {}
    for key in loaded.get("writable", []):
        keys.append(key)
        flags.append(True)
    for key in loaded.get("readonly", []):
        keys.append(key)
        flags.append(False)
    return keys, flags


def _pump_instruction(
    tx: dict[str, Any], *, inner: bool
) -> tuple[list[str], list[bool | None], bytes]:
    keys, flags = _keys_and_flags(tx)
    source = (
        [ix for group in tx["meta"]["innerInstructions"] for ix in group["instructions"]]
        if inner
        else list(tx["transaction"]["message"]["instructions"])
    )
    for ix in source:
        if keys[ix["programIdIndex"]] != PUMP_PROGRAM_ID:
            continue
        data = b58decode(ix["data"])
        if len(data) in (24, 25):
            return [keys[i] for i in ix["accounts"]], [flags[i] for i in ix["accounts"]], data
    raise AssertionError("no pump trade instruction in fixture")


def test_buy_matches_site_router_cpi_byte_for_byte(global_account: GlobalAccount) -> None:
    tx: dict[str, Any] = json.loads((FIXTURES / "rpc_tx_buy_raw.json").read_text())["result"]
    accounts, flags, data = _pump_instruction(tx, inner=True)
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    assert event.is_buy and event.ix_name == "buy"
    intent = TradeIntent(
        side="buy",
        mint=event.mint,
        user=event.user,
        creator=event.creator,
        token_program=accounts[8],
        token_amount=int.from_bytes(data[8:16], "little"),
        sol_limit=int.from_bytes(data[16:24], "little"),
        fee_recipient=event.fee_recipient,
        buyback_fee_recipient=accounts[17],
        is_mayhem_mode=event.mayhem_mode,
    )
    ours = build_buy_instruction(intent, global_account)
    assert ours.data == data, "instruction data differs"
    assert [a.pubkey for a in ours.accounts] == accounts, "account list differs"
    for index, (meta, flag) in enumerate(zip(ours.accounts, flags, strict=True)):
        if flag is not None:
            assert meta.is_writable == flag, f"writable flag differs at account {index}"
    assert ours.accounts[6].is_signer and ours.accounts[6].pubkey == event.user
    decoded = decode_trade_instruction(ours)
    assert decoded.token_amount == event.token_amount == 22628881309131
    assert decoded.sol_limit == 990000001 and decoded.track_volume is None
    # what the chain charged, from the event — fees are the event's, never a constant
    assert event.sol_amount == 977777777 and event.fee == 9288889 and event.cashback == 2933334
    assert event.buy_total_cost == 990000000 <= decoded.sol_limit


def test_sell_matches_independent_bot_byte_for_byte(global_account: GlobalAccount) -> None:
    tx: dict[str, Any] = json.loads((FIXTURES / "rpc_tx_probe_raw.json").read_text())["result"]
    accounts, flags, data = _pump_instruction(tx, inner=False)
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    assert not event.is_buy and event.ix_name == "sell"
    intent = TradeIntent(
        side="sell",
        mint=event.mint,
        user=event.user,
        creator=event.creator,
        token_program=accounts[9],
        token_amount=int.from_bytes(data[8:16], "little"),
        sol_limit=int.from_bytes(data[16:24], "little"),
        fee_recipient=event.fee_recipient,
        buyback_fee_recipient=accounts[16],
        is_mayhem_mode=event.mayhem_mode,
    )
    ours = build_sell_instruction(intent, global_account)
    assert ours.data == data
    assert [a.pubkey for a in ours.accounts] == accounts
    for index, (meta, flag) in enumerate(zip(ours.accounts, flags, strict=True)):
        assert meta.is_writable == flag, f"writable flag differs at account {index}"
    assert ours.accounts[6].is_signer
    # lamport-exact reconciliation of the trader's balance against the event
    keys = tx["transaction"]["message"]["accountKeys"]
    user_index = keys.index(event.user)
    delta = tx["meta"]["postBalances"][user_index] - tx["meta"]["preBalances"][user_index]
    tip = 60111  # the bot's own System transfer in the same transaction
    assert delta == event.sell_net_proceeds - tx["meta"]["fee"] - tip


def test_recipients_must_come_from_global(global_account: GlobalAccount) -> None:
    tx: dict[str, Any] = json.loads((FIXTURES / "rpc_tx_probe_raw.json").read_text())["result"]
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    base = dict(
        side="sell",
        mint=event.mint,
        user=event.user,
        creator=event.creator,
        token_program="TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        token_amount=1,
        sol_limit=0,
        is_mayhem_mode=False,
    )
    with pytest.raises(ValueError, match="fee_recipient"):
        build_sell_instruction(
            TradeIntent(
                **base,  # type: ignore[arg-type]
                fee_recipient=event.user,
                buyback_fee_recipient=global_account.buyback_fee_recipients[0],
            ),
            global_account,
        )
    with pytest.raises(ValueError, match="buyback"):
        build_sell_instruction(
            TradeIntent(
                **base,  # type: ignore[arg-type]
                fee_recipient=global_account.fee_recipient,
                buyback_fee_recipient=event.user,
            ),
            global_account,
        )
    # a Mayhem coin must pay a *reserved* recipient — the normal one is refused
    with pytest.raises(ValueError, match="reserved"):
        build_sell_instruction(
            TradeIntent(
                **{**base, "is_mayhem_mode": True},  # type: ignore[arg-type]
                fee_recipient=global_account.fee_recipient,
                buyback_fee_recipient=global_account.buyback_fee_recipients[0],
            ),
            global_account,
        )
    ok = build_sell_instruction(
        TradeIntent(
            **{**base, "is_mayhem_mode": True},  # type: ignore[arg-type]
            fee_recipient=global_account.reserved_fee_recipient,
            buyback_fee_recipient=global_account.buyback_fee_recipients[0],
        ),
        global_account,
    )
    assert ok.accounts[1].pubkey == global_account.reserved_fee_recipient
