"""T4.8f (guardian F2) — byte parity of OUR pump ``buy``/``sell`` builders with real trades that
landed on the pump program **after** its 2026-10-02 redeploy (slot 452654932).

The pin patch says the pump builders were re-proven against post-upgrade trades; until this file
nothing in the repo executed that claim (the T4.8e fixtures were only decoded for their events).
Fixtures ``t48e_rpc_tx_*_raw.json``: real ``getTransaction`` results of slot 453609412..715
(2026-10-05, read-only). ``Global`` is the 2026-10-05 read (``t48f_rpc_global_account_raw.json``).

What the chain accepts is what we compare; what the **caller** chooses is named, not hidden:

- a user token account that is not the ATA (two sells): ``accounts[5]`` of ``sell``;
- a router's 26-byte ``buy`` (``track_volume`` tail) with ``global_volume_accumulator`` writable
  (``accounts[12]``) — the T4.8e guardian's two caller-side differences.

Everything else — account order, signer/writable flags, the 24 argument bytes, the
``["bonding-curve-v2", mint]`` PDA under the pump program, the buyback recipient from ``Global``,
the cashback sell's extra leading account — must be identical.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.global_state import GlobalAccount, decode_global_account
from hunter_exchanges.pumpfun.solana_codec import b58decode
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

# fixture -> (side, accounts that may differ because the CALLER chose them, writable-flag diffs)
CASES = {
    "t48e_rpc_tx_buy_2qnMHiEaNfxX_raw.json": ("buy", set[int](), set[int]()),
    "t48e_rpc_tx_buy_57oJq3tbU7aa_raw.json": ("buy", set[int](), set[int]()),
    "t48e_rpc_tx_sell_2DSRRspQNw13_raw.json": ("sell", set[int](), set[int]()),  # cashback sell
    "t48e_rpc_tx_37XpnUmxsTdv_raw.json": ("sell", {5}, set[int]()),  # token account not the ATA
    "t48e_rpc_tx_sell_61x6SRWNuLhg_raw.json": ("sell", {5}, set[int]()),
    "t48e_rpc_tx_buy_3JLToMLjc2mt_raw.json": ("buy", set[int](), {12}),  # 26 B, router
}


@pytest.fixture(scope="module")
def global_account() -> GlobalAccount:
    value = json.loads((FIXTURES / "t48f_rpc_global_account_raw.json").read_text())["result"][
        "value"
    ]
    return decode_global_account(value["data"][0], owner=value["owner"])


def _legacy_trade(tx: dict[str, Any]) -> tuple[list[str], list[bool], list[bool], bytes]:
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
    candidates = list(message["instructions"])
    for group in tx["meta"]["innerInstructions"]:
        candidates += group["instructions"]
    for ix in candidates:
        if keys[ix["programIdIndex"]] != PUMP_PROGRAM_ID:
            continue
        data = b58decode(ix["data"])
        if data[:8] in (BUY_DISCRIMINATOR, SELL_DISCRIMINATOR):  # by discriminator, never length
            idx = ix["accounts"]
            return [keys[i] for i in idx], [flags[i] for i in idx], [signers[i] for i in idx], data
    raise AssertionError("no legacy pump trade instruction in the fixture")


@pytest.mark.parametrize("name", list(CASES))
def test_our_builder_reproduces_a_real_post_upgrade_trade(
    name: str, global_account: GlobalAccount
) -> None:
    side, caller_accounts, caller_writable = CASES[name]
    tx = json.loads((FIXTURES / name).read_text())
    assert tx["slot"] >= 453_609_412 > 452_654_932, "landed after the 2026-10-02 redeploy"
    accounts, flags, signer_flags, data = _legacy_trade(tx)
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    assert event.is_buy == (side == "buy")
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
    assert len(data) in (24, 26), "26 = a router's optional ``track_volume`` tail"
    assert len(ours.accounts) == len(accounts)
    differing = {i for i, a in enumerate(ours.accounts) if a.pubkey != accounts[i]}
    assert differing == caller_accounts, f"accounts differing from the chain: {sorted(differing)}"
    writable = {i for i, a in enumerate(ours.accounts) if a.is_writable != flags[i]}
    assert writable == caller_writable, f"writable flags differing: {sorted(writable)}"
    # signer flags: the user signs the transaction on both sides; nothing else does
    assert [a.is_signer for a in ours.accounts] == signer_flags
    # the structural accounts the program checks are the program's, never the caller's
    v2_slot = len(accounts) - 2
    assert (
        ours.accounts[v2_slot].pubkey == accounts[v2_slot] == bonding_curve_v2_address(event.mint)
    )
    assert accounts[-1] in global_account.buyback_fee_recipients
    assert event.layout == "2026-10-02/trailing_u64"


def test_the_one_caller_side_difference_of_the_router_buy_is_the_data_tail_and_one_flag(
    global_account: GlobalAccount,
) -> None:
    """3JL: 26 bytes (the 24 plus the optional ``track_volume`` option) and
    ``global_volume_accumulator`` writable — the router's choices, which a ``buy`` we build
    never makes (``track_volume`` is ``None`` in our data)."""
    tx = json.loads((FIXTURES / "t48e_rpc_tx_buy_3JLToMLjc2mt_raw.json").read_text())
    accounts, flags, _signers, data = _legacy_trade(tx)
    assert len(data) == 26 and flags[12] and accounts[12] != accounts[0]
    assert data[24:] != b"", "the tail is the router's"
