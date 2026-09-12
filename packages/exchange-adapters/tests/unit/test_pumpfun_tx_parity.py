"""Byte-for-byte parity of our ``buy``/``sell`` with the program deployed on 2026-09-12.

T4.8b fixtures (all read-only ``getTransaction``/``getAccountInfo`` on the public RPC,
2026-09-12 17:52–17:59 UTC, after the upgrade at slot 446462760 / 15:24:04 UTC):

- ``t48b_rpc_tx_sell_raw.json`` — signature ``5GfQvGkU…`` (slot 446490901): a bot's
  direct ``sell`` (CPI from ``FLASHX8…``), 16 accounts = the IDL's 14 + the two
  remaining accounts the upgraded program validates. Two more real sells of the
  same afternoon carried the same pair (``t48b_rpc_signatures_bcv2_raw.json``,
  ``.claude/state/notes-T4.8b.md``).
- ``t48b_simulation_proof_mainnet_raw.json`` — our ``buy`` as the cluster executed
  it in ``simulateTransaction`` (``sigVerify=false``, never sent): ``Instruction:
  Buy`` reached with the pair, ``InvalidBondingCurveV2`` (6074) with the morning's
  placeholder in that slot. No legacy ``buy`` landed in the windows sampled — the
  site's router and the bots buy through ``buy_exact_quote_in_v2`` now
  (``t48b_rpc_tx_buy_router_v2_raw.json``) — so the buy's parity target is what
  the program accepted from us, not a third party's bytes.
- ``rpc_tx_buy_raw.json`` / ``rpc_tx_probe_raw.json`` — T4.8's pre-upgrade trades on
  a cashback coin: still reproduced byte for byte, which is how the "undocumented"
  account turned out to be the derived PDA (see the third test).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.global_state import GlobalAccount, decode_global_account
from hunter_exchanges.pumpfun.solana_codec import b58decode
from hunter_exchanges.pumpfun.trade_event import (
    LAYOUT_HOLDER_REWARDS,
    trade_events_from_transaction,
)
from hunter_exchanges.pumpfun.tx import (
    BUY_ACCOUNT_NAMES,
    SELL_ACCOUNT_NAMES,
    SELL_CASHBACK_ACCOUNT_NAMES,
    TradeIntent,
    bonding_curve_v2_address,
    build_buy_instruction,
    build_sell_instruction,
    decode_trade_instruction,
    user_volume_accumulator_address,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
OLD_PLACEHOLDER = "4CLQeN5wrddJ9adY3GJGSTyu1AEKD4Ta14RffSy5aHud"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def global_account() -> GlobalAccount:
    value = _fixture("t48b_rpc_global_account_raw.json")["result"]["value"]
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


def test_sell_matches_a_real_sell_of_2026_09_12_byte_for_byte(
    global_account: GlobalAccount,
) -> None:
    tx = _fixture("t48b_rpc_tx_sell_raw.json")["result"]
    assert tx["slot"] == 446490901 and tx["blockTime"] == 1789235562  # 17:52:42 UTC
    accounts, flags, data = _pump_instruction(tx, inner=True)
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    assert not event.is_buy and event.ix_name == "sell" and event.mayhem_mode
    assert event.layout == LAYOUT_HOLDER_REWARDS
    intent = TradeIntent(
        side="sell",
        mint=event.mint,
        user=event.user,
        creator=event.creator,
        token_program=accounts[9],
        token_amount=int.from_bytes(data[8:16], "little"),
        sol_limit=int.from_bytes(data[16:24], "little"),
        fee_recipient=event.fee_recipient,
        buyback_fee_recipient=accounts[15],
        is_mayhem_mode=event.mayhem_mode,
        is_cashback_coin=event.cashback_fee_basis_points > 0,
    )
    assert not intent.is_cashback_coin
    ours = build_sell_instruction(intent, global_account)
    assert ours.data == data, "instruction data differs"
    assert [a.pubkey for a in ours.accounts] == accounts, "account list differs"
    for index, (meta, flag) in enumerate(zip(ours.accounts, flags, strict=True)):
        assert meta.is_writable == flag, f"writable flag differs at account {index}"
    assert len(ours.accounts) == len(SELL_ACCOUNT_NAMES) == 16
    assert ours.accounts[6].is_signer and ours.accounts[6].pubkey == event.user
    # the two remaining accounts: the derived PDA (read-only) and a buyback recipient
    assert ours.accounts[14].pubkey == bonding_curve_v2_address(event.mint)
    assert not ours.accounts[14].is_writable
    assert ours.accounts[15].pubkey in global_account.buyback_fee_recipients
    assert ours.accounts[15].is_writable
    assert user_volume_accumulator_address(event.user) not in accounts
    assert OLD_PLACEHOLDER not in accounts
    # a Mayhem coin pays a reserved recipient — the builder and the chain agree
    assert event.fee_recipient in global_account.mayhem_fee_recipients
    decoded = decode_trade_instruction(ours)
    assert decoded.token_amount == event.token_amount == 6147682252894
    assert decoded.sol_limit == 0 and decoded.track_volume is None
    # what the chain charged, from the event — fees are the event's, never a constant
    assert event.sol_amount == 1237388211 and event.fee == 11755189
    assert event.creator_fee == 3712165 and event.cashback == 0 and event.holder_rewards == 0
    assert event.sell_net_proceeds == 1221920857
    # lamport-exact reconciliation of the seller's balance against the event:
    # the bot's own 1 % of the net (12 219 208) and its tip transfer (1 723 238)
    keys = tx["transaction"]["message"]["accountKeys"]
    user_index = keys.index(event.user)
    delta = tx["meta"]["postBalances"][user_index] - tx["meta"]["preBalances"][user_index]
    bot_cut = 12_219_208 + 1_723_238
    assert delta == event.sell_net_proceeds - tx["meta"]["fee"] - bot_cut == 1_207_696_649


def test_buy_matches_the_accounts_the_cluster_executed_in_simulation(
    global_account: GlobalAccount,
) -> None:
    proof = _fixture("t48b_simulation_proof_mainnet_raw.json")
    assert proof["sent"] is False and proof["sig_verify"] is False
    buy = proof["buy"]
    i = buy["intent"]
    intent = TradeIntent(
        side="buy",
        mint=proof["mint"],
        user=i["user"],
        creator=i["creator"],
        token_program=i["token_program"],
        token_amount=i["token_amount"],
        sol_limit=i["sol_limit"],
        fee_recipient=i["fee_recipient"],
        buyback_fee_recipient=i["buyback_fee_recipient"],
        is_mayhem_mode=i["is_mayhem_mode"],
    )
    ours = build_buy_instruction(intent, global_account)
    assert ours.data.hex() == buy["data_hex"]
    assert [[a.pubkey, a.is_signer, a.is_writable] for a in ours.accounts] == buy["accounts"]
    assert len(ours.accounts) == len(BUY_ACCOUNT_NAMES) == 18
    assert ours.accounts[16].pubkey == bonding_curve_v2_address(proof["mint"])
    assert not ours.accounts[16].is_writable and ours.accounts[17].is_writable
    sims = proof["simulations"]
    assert sims["buy_full"]["ok"] is True and sims["buy_full"]["err"] is None
    assert any("Instruction: Buy" in line for line in sims["buy_full"]["logs"])
    assert sims["buy_full"]["units_consumed"] > 0
    # the same bytes with another coin's PDA in that slot (T4.8's constant): 6074
    assert sims["buy_with_another_coins_pda"]["ok"] is False
    assert {"Custom": 6074} in _customs(sims["buy_with_another_coins_pda"]["err"])
    assert proof["buy_with_another_coins_pda"]["accounts"][16][0] == OLD_PLACEHOLDER
    # without the pair, or with the buyback recipient alone: BuybackFeeRecipientMissing
    assert {"Custom": 6062} in _customs(sims["buy_without_remaining_accounts"]["err"])
    assert {"Custom": 6062} in _customs(sims["buy_buyback_only"]["err"])
    # the empty in-memory wallet as payer: the cluster refuses (the simulation is real)
    assert sims["buy_empty_throwaway_wallet"]["err"] == "AccountNotFound"
    assert proof["submitter"]["signatures"] == [], "verify → simulate → refused before signing"
    # the sell: an unsigned current holder of the coin, 16 accounts, ``Instruction: Sell``
    assert sims["sell_full"]["ok"] is True
    assert any("Instruction: Sell" in line for line in sims["sell_full"]["logs"])
    s = proof["sell"]["intent"]  # a fresh SOL-quoted coin: the recorded holders had sold out
    sell_intent = TradeIntent(
        side="sell",
        mint=proof["sell"]["mint"],
        user=s["user"],
        creator=s["creator"],
        token_program=s["token_program"],
        token_amount=s["token_amount"],
        sol_limit=s["sol_limit"],
        fee_recipient=s["fee_recipient"],
        buyback_fee_recipient=s["buyback_fee_recipient"],
        is_mayhem_mode=s["is_mayhem_mode"],
        is_cashback_coin=s["is_cashback_coin"],
    )
    ours_sell = build_sell_instruction(sell_intent, global_account)
    assert [[a.pubkey, a.is_signer, a.is_writable] for a in ours_sell.accounts] == proof["sell"][
        "accounts"
    ]
    assert ours_sell.data.hex() == proof["sell"]["data_hex"]
    # the morning's cashback coin, same afternoon program: its "4CLQ…" is its own PDA
    cashback = proof["cashback_coin"]
    assert cashback["is_cashback_coin"] is True
    assert cashback["buy"]["accounts"][16][0] == OLD_PLACEHOLDER
    assert sims["cashback_buy_full"]["ok"] is True
    if "cashback_sell_full" in sims:
        assert sims["cashback_sell_full"]["ok"] is True
        assert len(cashback["sell"]["accounts"]) == 17
        assert cashback["sell"]["accounts"][14][0] == user_volume_accumulator_address(
            cashback["sell"]["intent"]["user"]
        )
        assert sims["cashback_sell_without_accumulator"]["ok"] is False


def _customs(err: Any) -> list[dict[str, int]]:
    if not isinstance(err, dict):
        return []
    inner = cast(list[Any], cast(dict[str, Any], err).get("InstructionError") or [])
    return [
        cast(dict[str, int], item) for item in inner if isinstance(item, dict) and "Custom" in item
    ]


def test_t48s_undocumented_account_was_the_bonding_curve_v2_pda_of_its_coin() -> None:
    """The finding that rewrites T4.8's §6b: ``4CLQ…`` — kept as a constant because
    "not derivable" — is ``["bonding-curve-v2", mint]`` of the fixture coin ``5ejA…``.
    The constant was right for that one coin and wrong for every other (T4.14's 6074
    on ``4VuV…``). With the derivation the builder reproduces the **morning's** router
    buy and bot sell byte for byte too — the sell of that *cashback* coin carrying the
    user's volume accumulator before the pair (17 accounts)."""
    assert (
        bonding_curve_v2_address("5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump") == OLD_PLACEHOLDER
    )
    value = _fixture("rpc_global_account_raw.json")["result"]["value"]
    old_global = decode_global_account(value["data"][0], owner=value["owner"])
    buy_tx = _fixture("rpc_tx_buy_raw.json")["result"]
    old_accounts, old_flags, data = _pump_instruction(buy_tx, inner=True)
    (event,) = trade_events_from_transaction(buy_tx, program_id=PUMP_PROGRAM_ID)
    assert event.cashback_fee_basis_points == 30, "a cashback coin"
    intent = TradeIntent(
        side="buy",
        mint=event.mint,
        user=event.user,
        creator=event.creator,
        token_program=old_accounts[8],
        token_amount=event.token_amount,
        sol_limit=int.from_bytes(data[16:24], "little"),
        fee_recipient=event.fee_recipient,
        buyback_fee_recipient=old_accounts[17],
        is_mayhem_mode=event.mayhem_mode,
        is_cashback_coin=True,
    )
    ours = build_buy_instruction(intent, old_global)
    assert [a.pubkey for a in ours.accounts] == old_accounts and ours.data == data
    assert [a.is_writable for a in ours.accounts] == old_flags
    assert ours.accounts[16].pubkey == bonding_curve_v2_address(event.mint) == OLD_PLACEHOLDER

    sell_tx = _fixture("rpc_tx_probe_raw.json")["result"]
    old_accounts, old_flags, data = _pump_instruction(sell_tx, inner=False)
    (event,) = trade_events_from_transaction(sell_tx, program_id=PUMP_PROGRAM_ID)
    intent = TradeIntent(
        side="sell",
        mint=event.mint,
        user=event.user,
        creator=event.creator,
        token_program=old_accounts[9],
        token_amount=event.token_amount,
        sol_limit=int.from_bytes(data[16:24], "little"),
        fee_recipient=event.fee_recipient,
        buyback_fee_recipient=old_accounts[16],
        is_mayhem_mode=event.mayhem_mode,
        is_cashback_coin=True,
    )
    ours = build_sell_instruction(intent, old_global)
    assert len(ours.accounts) == len(SELL_CASHBACK_ACCOUNT_NAMES) == 17
    assert [a.pubkey for a in ours.accounts] == old_accounts and ours.data == data
    assert [a.is_writable for a in ours.accounts] == old_flags
    assert [a.pubkey for a in ours.accounts[14:]] == [
        user_volume_accumulator_address(event.user),
        bonding_curve_v2_address(event.mint),
        old_accounts[16],
    ]
    # the same intent without the cashback flag is the 16-account shape of today's sells
    plain = build_sell_instruction(replace(intent, is_cashback_coin=False), old_global)
    assert [a.pubkey for a in plain.accounts] == old_accounts[:14] + old_accounts[15:]


def test_recipients_must_come_from_global(global_account: GlobalAccount) -> None:
    tx = _fixture("t48b_rpc_tx_sell_raw.json")["result"]
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
