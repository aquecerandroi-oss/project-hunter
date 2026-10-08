"""T4.8g — byte parity of OUR pump ``buy``/``sell`` builders with real trades that landed on the
pump program **after** its 2026-10-08 redeploy (slot 454596459, 16:20:17Z), the fifth in a month.

Same method as ``test_pumpfun_tx_parity_t48f.py`` for the previous deploy. Fixtures
``t48g_rpc_tx_{buy,sell}_*_raw.json``: real ``getTransaction`` results of slots 454630531..454631564
(2026-10-08, read-only; provenance in ``t48g_provenance.json``). ``Global`` is the 2026-10-08 read.

What the chain accepts is what we compare; what the **caller** chose is named, not hidden:

- a user token account that is not the ATA (``sell`` ``accounts[5]``) and a mint the router passes
  writable (``accounts[2]``) — a bot router;
- a router's 26-byte ``buy`` with ``global_volume_accumulator`` writable (``accounts[12]``) and the
  two trailing accounts writable;
- the **Mayhem agent's own** CPI (T4.8d §3): ``bonding-curve-v2`` derived under the Mayhem program.
  Not our path: Mayhem entries are refused at admission.

Everything else — account order, signer/writable flags, the 24 argument bytes, the
``["bonding-curve-v2", mint]`` PDA under the pump program, the buyback recipient from ``Global`` —
must be identical. Counting precisely (45 legacy ``buy``/``sell`` instructions read): 19 are identical
in EVERY byte, accounts and flags; 4 more are identical except that their data carries one extra
trailing byte (25 B — the optional ``track_volume``; our 24 bytes are their exact prefix), so 23 match
on accounts, flags, signers and the 24 argument bytes (the comparison below, ``data[:24]``); 22 differ
only where the caller chose or are the Mayhem agent's CPI.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.fee_config import decode_fee_config
from hunter_exchanges.pumpfun.global_state import GlobalAccount, decode_global_account
from hunter_exchanges.pumpfun.solana_codec import b58decode, find_program_address, pubkey_bytes
from hunter_exchanges.pumpfun.trade_event import trade_events_from_transaction
from hunter_exchanges.pumpfun.tx import (
    BUY_DISCRIMINATOR,
    SELL_DISCRIMINATOR,
    TradeIntent,
    bonding_curve_v2_address,
    build_buy_instruction,
    build_sell_instruction,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
DEPLOY_SLOT = 454_596_459
MAYHEM_PROGRAM = "MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e"

# fixture -> (side, accounts the CALLER chose, writable-flag diffs the CALLER chose)
CASES = {
    "t48g_rpc_tx_buy_Kz7Nk1YiVWWj_raw.json": ("buy", set[int](), set[int]()),  # 24 B, HR coin
    "t48g_rpc_tx_buy_3p8KxySa18L6_raw.json": ("buy", set[int](), set[int]()),  # 24 B
    "t48g_rpc_tx_buy_4yATaRdQNe2N_raw.json": ("buy", set[int](), set[int]()),  # 25 B
    "t48g_rpc_tx_buy_iJjSTjH8AoKT_raw.json": ("buy", set[int](), set[int]()),  # 25 B
    "t48g_rpc_tx_sell_2zmu5NQsqrJ3_raw.json": ("sell", set[int](), set[int]()),
    "t48g_rpc_tx_sell_3SefGhSLx9f9_raw.json": ("sell", set[int](), set[int]()),  # HR coin
    "t48g_rpc_tx_sell_49Lfa4aoEdTw_raw.json": ("sell", set[int](), set[int]()),  # HR coin
    "t48g_rpc_tx_sell_4Cuu6mMnzpvB_raw.json": ("sell", set[int](), set[int]()),  # HR coin
    # bot router: token account not the ATA, mint writable
    "t48g_rpc_tx_sell_25uxGAn5kiFj_raw.json": ("sell", {5}, {2}),
    # router: 26 B data, global_volume_accumulator + the two bonding-curve-v2/buyback slots writable
    "t48g_rpc_tx_buy_5rtmX79KnNHo_raw.json": ("buy", set[int](), {12, 15, 16}),
}
# the Mayhem agent's own CPI: the bonding-curve-v2 slot holds a PDA derived under the Mayhem program
MAYHEM_AGENT_CASES = {
    "t48g_rpc_tx_buy_3xkAuEWcRGsQ_raw.json": ("buy", {16}, {12}),
    "t48g_rpc_tx_sell_64waqn42fyBs_raw.json": ("sell", {14}, set[int]()),
}


def _fixture(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text()))


@pytest.fixture(scope="module")
def global_account() -> GlobalAccount:
    value = _fixture("t48g_rpc_global_account_raw.json")["result"]["value"]
    return decode_global_account(value["data"][0], owner=value["owner"])


def _legacy_trade(
    tx: dict[str, Any],
) -> tuple[list[str], list[bool], list[bool], bytes, list[str]]:
    message = tx["transaction"]["message"]
    keys: list[str] = list(message["accountKeys"])
    header = message["header"]
    n = len(keys)
    signed, ro_signed, ro_unsigned = (
        header["numRequiredSignatures"],
        header["numReadonlySignedAccounts"],
        header["numReadonlyUnsignedAccounts"],
    )
    flags = [(i < signed - ro_signed) if i < signed else (i < n - ro_unsigned) for i in range(n)]
    signers = [i < signed for i in range(n)]
    loaded = cast(dict[str, list[str]], tx["meta"].get("loadedAddresses") or {})
    keys += loaded.get("writable", []) + loaded.get("readonly", [])
    flags += [True] * len(loaded.get("writable", [])) + [False] * len(loaded.get("readonly", []))
    signers += [False] * (len(keys) - len(signers))
    top_level: list[str] = [keys[ix["programIdIndex"]] for ix in message["instructions"]]
    candidates = list(message["instructions"])
    for group in tx["meta"]["innerInstructions"]:
        candidates += group["instructions"]
    for ix in candidates:
        if keys[ix["programIdIndex"]] != PUMP_PROGRAM_ID:
            continue
        data = b58decode(ix["data"])
        if data[:8] in (BUY_DISCRIMINATOR, SELL_DISCRIMINATOR):  # by discriminator, never length
            idx = ix["accounts"]
            return (
                [keys[i] for i in idx],
                [flags[i] for i in idx],
                [signers[i] for i in idx],
                data,
                top_level,
            )
    raise AssertionError("no legacy pump trade instruction in the fixture")


def _compare(
    name: str, side: str, global_account: GlobalAccount
) -> tuple[set[int], set[int], set[int], bool]:
    tx = _fixture(name)
    assert tx["slot"] > DEPLOY_SLOT, "landed after the 2026-10-08 redeploy"
    accounts, flags, signer_flags, data, top_level = _legacy_trade(tx)
    event = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)[0]
    assert event.is_buy == (side == "buy")
    assert event.layout == "2026-10-02/trailing_u64", "the event layout did not move"
    intent = TradeIntent(
        side=side,  # type: ignore[arg-type]
        mint=event.mint,
        user=event.user,
        creator=event.creator,
        token_program=accounts[8] if side == "buy" else accounts[9],
        token_amount=int.from_bytes(data[8:16], "little"),
        sol_limit=int.from_bytes(data[16:24], "little"),
        fee_recipient=event.fee_recipient,
        buyback_fee_recipient=accounts[-1],
        is_mayhem_mode=event.mayhem_mode,
        is_cashback_coin=event.cashback_fee_basis_points > 0,
    )
    ours = (build_buy_instruction if side == "buy" else build_sell_instruction)(
        intent, global_account
    )
    assert ours.data == data[:24], "the 24 argument bytes (discriminator + two u64)"
    assert len(data) in (24, 25, 26), "25/26 = a caller's optional ``track_volume`` tail"
    assert len(ours.accounts) == len(accounts)
    differing = {i for i, a in enumerate(ours.accounts) if a.pubkey != accounts[i]}
    writable = {i for i, a in enumerate(ours.accounts) if a.is_writable != flags[i]}
    signers = {i for i, a in enumerate(ours.accounts) if a.is_signer != signer_flags[i]}
    return differing, writable, signers, MAYHEM_PROGRAM in top_level


@pytest.mark.parametrize("name", list(CASES))
def test_our_builder_reproduces_a_real_post_redeploy_trade(
    name: str, global_account: GlobalAccount
) -> None:
    side, caller_accounts, caller_writable = CASES[name]
    differing, writable, signers, via_mayhem = _compare(name, side, global_account)
    assert not via_mayhem and not signers, "the user signs the transaction on both sides"
    assert differing == caller_accounts, f"accounts differing from the chain: {sorted(differing)}"
    assert writable == caller_writable, f"writable flags differing: {sorted(writable)}"
    tx = _fixture(name)
    accounts, *_rest = _legacy_trade(tx)
    event = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)[0]
    # the structural accounts the program checks are the program's, never the caller's
    v2_slot = len(accounts) - 2
    assert accounts[v2_slot] == bonding_curve_v2_address(event.mint)
    assert (
        accounts[v2_slot]
        == find_program_address([b"bonding-curve-v2", pubkey_bytes(event.mint)], PUMP_PROGRAM_ID)[0]
    )
    assert accounts[-1] in global_account.buyback_fee_recipients


@pytest.mark.parametrize("name", list(MAYHEM_AGENT_CASES))
def test_the_mayhem_agents_own_cpi_differs_only_where_t48d_said_it_would(
    name: str, global_account: GlobalAccount
) -> None:
    """The T4.8d §3 trap again, on the new program: the agent (a CPI from the Mayhem program)
    derives ``bonding-curve-v2`` under *its own* program id. Not our path — and not new."""
    side, caller_accounts, caller_writable = MAYHEM_AGENT_CASES[name]
    differing, writable, signers, via_mayhem = _compare(name, side, global_account)
    assert via_mayhem, "a top-level instruction of the Mayhem program"
    assert signers == {6}, "the agent's ``user`` is a PDA that signs by CPI, not a tx signer"
    assert differing == caller_accounts and writable == caller_writable
    tx = _fixture(name)
    accounts, *_rest = _legacy_trade(tx)
    event = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)[0]
    slot = next(iter(caller_accounts))
    assert event.mayhem_mode is True
    assert (
        accounts[slot]
        == find_program_address([b"bonding-curve-v2", pubkey_bytes(event.mint)], MAYHEM_PROGRAM)[0]
    )


def test_the_router_buy_tail_is_the_callers_not_ours(global_account: GlobalAccount) -> None:
    """26 bytes = the 24 plus the optional ``track_volume`` option; ours never sends it."""
    tx = _fixture("t48g_rpc_tx_buy_5rtmX79KnNHo_raw.json")
    _accounts, _flags, _signers, data, _top = _legacy_trade(tx)
    assert len(data) == 26 and data[24:] != b""


# -- the accounts the builders read: Global grew one byte, FeeConfig did not move --------------


def test_global_gained_one_unnamed_trailing_byte_and_every_known_field_is_the_same(
    global_account: GlobalAccount,
) -> None:
    """2026-10-08 read (slot 454636168): 1088 bytes, the T4.8f read (05/10) had 1087. The first
    1087 are byte-identical; the new last byte is ``01`` (no IDL names it — the on-chain IDL was
    not republished). The decoder reads the named prefix and does not trust the tail."""
    old = _fixture("t48f_rpc_global_account_raw.json")["result"]["value"]
    new = _fixture("t48g_rpc_global_account_raw.json")["result"]["value"]
    raw_old, raw_new = base64.b64decode(old["data"][0]), base64.b64decode(new["data"][0])
    assert (len(raw_old), len(raw_new)) == (1087, 1088)
    assert raw_new[:1087] == raw_old and raw_new[1087:] == b"\x01"
    assert global_account == decode_global_account(old["data"][0], owner=old["owner"])
    assert global_account.fee_basis_points == 95 and global_account.creator_fee_basis_points == 5
    assert len(global_account.buyback_fee_recipients) == 8


def test_fee_config_is_byte_identical_to_the_one_the_quote_code_was_proven_against() -> None:
    new = _fixture("t48g_rpc_fee_config_raw.json")["result"]["value"]
    old = _fixture("rpc_fee_config_raw.json")
    old_value = old.get("result", old)["value"]
    assert new["data"][0] == old_value["data"][0]
    fees = decode_fee_config(new["data"][0], owner=new["owner"]).flat_fees
    assert (fees.lp_fee_bps, fees.protocol_fee_bps, fees.creator_fee_bps) == (0, 95, 30)
