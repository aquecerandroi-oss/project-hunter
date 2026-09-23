"""T4.8d — byte-for-byte parity with the program deployed on 2026-09-23.

The third upgrade this package has had to be re-proven against (deploy slot
449734335, 14:45:19 UTC). Unlike T4.8c's, this deploy did **not** republish the
on-chain IDL account (``test_pumpfun_program_identity.py``), so the IDL says
nothing about it: the only evidence that ``buy``/``sell``/``TradeEvent`` still
have the layout our builders assume is third-party trades that landed on the new
program, plus a mainnet simulation of our own bytes.

Fixtures (all read-only ``getTransaction`` on the public RPC, 2026-09-23
17:38 UTC — 2 h 53 after the deploy):

- ``t48d_rpc_tx_buy_nonmayhem_raw.json`` — a real legacy ``buy`` (``66063d12…``)
  on a **Mayhem** coin, 18 accounts, paying a *reserved* fee recipient;
- ``t48d_rpc_tx_sell_nonmayhem_raw.json`` — a real legacy ``sell`` (``33e685a4…``)
  on a plain coin, 16 accounts;
- ``t48d_rpc_tx_buy_legacy_raw.json`` / ``t48d_rpc_tx_sell_raw.json`` — trades the
  **Mayhem program** (``MAyhSmzXz…``) CPI'd for its own agent. These are the trap
  of this task: they pay *no* fee, mark ``global_volume_accumulator`` writable and
  carry, in the ``bonding_curve_v2`` slot, the same seeds derived under the *Mayhem*
  program instead of the pump program. They are the caller's own choices on a path
  this package never builds — the last test here pins that down so the next
  re-record does not mistake them for a layout change;
- ``t48d_simulation_proof_mainnet_raw.json`` — our own ``buy``/``sell``, built by the
  executor's path and executed by the cluster in ``simulateTransaction``
  (``sigVerify=false``, never signed, never sent).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.global_state import GlobalAccount, decode_global_account
from hunter_exchanges.pumpfun.solana_codec import b58decode, find_program_address, pubkey_bytes
from hunter_exchanges.pumpfun.trade_event import (
    LAYOUT_HOLDER_REWARDS,
    TRADE_EVENT_DISCRIMINATOR,
    trade_events_from_transaction,
)
from hunter_exchanges.pumpfun.tx import (
    BUY_ACCOUNT_NAMES,
    BUY_DISCRIMINATOR,
    SELL_ACCOUNT_NAMES,
    SELL_DISCRIMINATOR,
    TradeIntent,
    bonding_curve_v2_address,
    build_buy_instruction,
    build_sell_instruction,
    decode_trade_instruction,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
DEPLOY_SLOT = 449734335
MAYHEM_PROGRAM_ID = "MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e"
MAYHEM_AGENT_EVENT_DISCRIMINATOR = bytes.fromhex("31487b2d6e40b085")


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def global_account() -> GlobalAccount:
    value = _fixture("t48d_rpc_global_account_raw.json")["result"]["value"]
    return decode_global_account(value["data"][0], owner=value["owner"])


def _keys_and_flags(tx: dict[str, Any]) -> tuple[list[str], list[bool]]:
    message = tx["transaction"]["message"]
    keys: list[str] = list(message["accountKeys"])
    header = message["header"]
    n_signed = header["numRequiredSignatures"]
    n_ro_signed = header["numReadonlySignedAccounts"]
    n_ro_unsigned = header["numReadonlyUnsignedAccounts"]
    flags = [
        (i < n_signed - n_ro_signed) if i < n_signed else (i < len(keys) - n_ro_unsigned)
        for i in range(len(keys))
    ]
    loaded: dict[str, list[str]] = tx["meta"].get("loadedAddresses") or {}
    keys += list(loaded.get("writable", [])) + list(loaded.get("readonly", []))
    flags += [True] * len(loaded.get("writable", [])) + [False] * len(loaded.get("readonly", []))
    return keys, flags


def _instructions(tx: dict[str, Any], *, inner_only: bool = False) -> list[dict[str, Any]]:
    """Outer instructions then every inner group's, flat and typed."""
    out: list[dict[str, Any]] = []
    if not inner_only:
        out += [cast(dict[str, Any], ix) for ix in tx["transaction"]["message"]["instructions"]]
    for group in cast(list[Any], tx["meta"].get("innerInstructions") or []):
        out += [cast(dict[str, Any], ix) for ix in cast(dict[str, Any], group)["instructions"]]
    return out


def _legacy_trade(tx: dict[str, Any]) -> tuple[list[str], list[bool], bytes]:
    """The one ``buy``/``sell`` instruction, matched by **discriminator** — never by
    data length alone: ``sell_v2`` also carries 24 bytes (T4.8c) and would be
    mistaken for a legacy sell."""
    keys, flags = _keys_and_flags(tx)
    for ix in _instructions(tx):
        if keys[ix["programIdIndex"]] != PUMP_PROGRAM_ID:
            continue
        data = b58decode(ix["data"])
        if data[:8] in (BUY_DISCRIMINATOR, SELL_DISCRIMINATOR):
            return [keys[i] for i in ix["accounts"]], [flags[i] for i in ix["accounts"]], data
    raise AssertionError("no legacy pump trade instruction in fixture")


def test_buy_matches_a_real_legacy_buy_on_the_new_program_byte_for_byte(
    global_account: GlobalAccount,
) -> None:
    """A Mayhem coin, bought by a third party through its own bot, 2 h 53 after the
    deploy: 18 accounts, the same order, the same writability, the same 24 bytes —
    including ``creator_vault`` / ``fee_config`` / ``fee_program`` (T4.29/T4.48) and
    the ``["bonding-curve-v2", mint]`` PDA derived under the *pump* program."""
    tx = _fixture("t48d_rpc_tx_buy_nonmayhem_raw.json")["result"]
    assert tx["slot"] == 449773177 > DEPLOY_SLOT and tx["blockTime"] == 1790185083
    assert tx["version"] == 1, "versioned transactions are normal now (RPC needs v>=1)"
    accounts, flags, data = _legacy_trade(tx)
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    assert event.is_buy and event.layout == LAYOUT_HOLDER_REWARDS
    assert event.mayhem_mode and event.cashback_fee_basis_points == 0
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
        is_cashback_coin=False,
    )
    ours = build_buy_instruction(intent, global_account)
    assert ours.data == data, "instruction data differs"
    assert [a.pubkey for a in ours.accounts] == accounts, "account list differs"
    for index, (meta, flag) in enumerate(zip(ours.accounts, flags, strict=True)):
        assert meta.is_writable == flag, f"writable flag differs at account {index}"
    assert len(ours.accounts) == len(BUY_ACCOUNT_NAMES) == 18
    assert ours.accounts[6].is_signer and ours.accounts[6].pubkey == event.user
    assert ours.accounts[16].pubkey == bonding_curve_v2_address(event.mint)
    assert not ours.accounts[16].is_writable and ours.accounts[17].is_writable
    assert ours.accounts[17].pubkey in global_account.buyback_fee_recipients
    # a Mayhem coin pays a *reserved* recipient — builder and chain agree
    assert event.fee_recipient in global_account.mayhem_fee_recipients
    decoded = decode_trade_instruction(ours)
    assert decoded.token_amount == event.token_amount == 91796810131
    assert decoded.sol_limit == 2475001 and decoded.track_volume is None
    # fees from the event, same tier as T4.8b/T4.8c (95 / 30 bps)
    assert event.sol_amount == 2444444 and event.fee == 23223 and event.fee_basis_points == 95
    assert event.creator_fee == 7334 and event.creator_fee_basis_points == 30
    assert event.holder_rewards == 0 and event.holder_rewards_basis_points == 0
    assert event.buy_total_cost == 2475001 == decoded.sol_limit


def test_sell_matches_a_real_legacy_sell_on_the_new_program_byte_for_byte(
    global_account: GlobalAccount,
) -> None:
    """The exit path: a plain (non-Mayhem, non-cashback) coin sold by a third party
    on the new program — 16 accounts, the same pair of remaining accounts, the same
    24 bytes of data."""
    tx = _fixture("t48d_rpc_tx_sell_nonmayhem_raw.json")["result"]
    assert tx["slot"] == 449773176 > DEPLOY_SLOT and tx["blockTime"] == 1790185083
    accounts, flags, data = _legacy_trade(tx)
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    assert not event.is_buy and event.layout == LAYOUT_HOLDER_REWARDS
    assert not event.mayhem_mode and event.cashback_fee_basis_points == 0
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
    ours = build_sell_instruction(intent, global_account)
    assert ours.data == data
    assert [a.pubkey for a in ours.accounts] == accounts
    for index, (meta, flag) in enumerate(zip(ours.accounts, flags, strict=True)):
        assert meta.is_writable == flag, f"writable flag differs at account {index}"
    assert len(ours.accounts) == len(SELL_ACCOUNT_NAMES) == 16
    assert ours.accounts[14].pubkey == bonding_curve_v2_address(event.mint)
    assert not ours.accounts[14].is_writable
    assert ours.accounts[15].pubkey in global_account.buyback_fee_recipients
    assert event.fee_recipient in global_account.normal_fee_recipients
    decoded = decode_trade_instruction(ours)
    assert decoded.token_amount == event.token_amount == 380420193127
    assert decoded.sol_limit == 0 and decoded.track_volume is None
    assert event.sol_amount == 25909045 and event.fee == 246136 and event.fee_basis_points == 95
    assert event.creator_fee == 77728 and event.creator_fee_basis_points == 30
    assert event.buyback_fee == 123068 and event.holder_rewards == 0
    assert event.sell_net_proceeds == 25585181


def test_global_and_the_fee_tier_did_not_move_with_the_deploy(
    global_account: GlobalAccount,
) -> None:
    """``Global`` decodes identically to T4.8c's capture and the fee program still
    answers 95 / 30 bps — so ``fee_bps``'s proven floor is still the right one."""
    old_value = _fixture("t48c_rpc_global_account_raw.json")["result"]["value"]
    old = decode_global_account(old_value["data"][0], owner=old_value["owner"])
    assert global_account == old
    assert global_account.fee_basis_points == 95
    for name in ("t48d_rpc_tx_buy_nonmayhem_raw.json", "t48d_rpc_tx_sell_nonmayhem_raw.json"):
        logs = _fixture(name)["result"]["meta"]["logMessages"]
        assert any("Instruction: GetFeesWithQuoteMint" in line for line in logs)
        # lp 0 / protocol 95 (0x5f) / creator 30 (0x1e), little-endian u64 triple
        assert any(
            line.endswith("AAAAAAAAAABfAAAAAAAAAB4AAAAAAAAA")
            for line in logs
            if line.startswith("Program return: pfee")
        )


def test_the_mayhem_agents_own_trades_are_not_our_path(global_account: GlobalAccount) -> None:
    """The trap of this re-record. The Mayhem program CPIs ``buy``/``sell`` for its
    own agent wallet and, on that path only: charges **no** fee, marks
    ``global_volume_accumulator`` writable, and passes ``["bonding-curve-v2", mint]``
    derived under the **Mayhem** program in the remaining slot. Three deltas that
    look exactly like a layout change and are not — our builder never takes it, and
    an ordinary trade on the *same* Mayhem coin (the buy above) carries the
    pump-derived PDA. Its own ``31487b2d…`` event is ignored by our extractor."""
    for name, side, declared in (
        ("t48d_rpc_tx_buy_legacy_raw.json", "buy", 16),
        ("t48d_rpc_tx_sell_raw.json", "sell", 14),
    ):
        tx = _fixture(name)["result"]
        assert tx["slot"] > DEPLOY_SLOT
        keys, _ = _keys_and_flags(tx)
        outer: list[str] = [
            keys[cast(dict[str, Any], ix)["programIdIndex"]]
            for ix in tx["transaction"]["message"]["instructions"]
        ]
        assert MAYHEM_PROGRAM_ID in outer, "this fixture is the agent path, by construction"
        accounts, _, data = _legacy_trade(tx)
        (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
        assert event.mayhem_mode and event.layout == LAYOUT_HOLDER_REWARDS
        # no fee at all on this path — the event says so, and so does the ledger
        assert event.fee == 0 and event.fee_basis_points == 0
        assert event.creator_fee == 0 and event.buyback_fee == 0
        # the remaining account is the *Mayhem* program's PDA, not ours
        pump_pda = bonding_curve_v2_address(event.mint)
        mayhem_pda = find_program_address(
            [b"bonding-curve-v2", pubkey_bytes(event.mint)], MAYHEM_PROGRAM_ID
        )[0]
        assert accounts[declared] == mayhem_pda != pump_pda
        if side == "buy":
            assert len(data) == 25, "the agent passes the optional track_volume byte"
            assert data[24] == 0
        # ...and our builder, given the same trade, would pass the pump PDA
        assert pump_pda not in accounts
    # the Mayhem program emits an event of its own; ours is filtered by program id
    tx = _fixture("t48d_rpc_tx_buy_legacy_raw.json")["result"]
    keys, _ = _keys_and_flags(tx)
    emitters: dict[str, bytes] = {
        keys[ix["programIdIndex"]]: b58decode(ix["data"])[8:16]
        for ix in _instructions(tx, inner_only=True)
        if len(b58decode(ix["data"])) > 16
    }
    assert emitters[MAYHEM_PROGRAM_ID] == MAYHEM_AGENT_EVENT_DISCRIMINATOR
    assert emitters[PUMP_PROGRAM_ID] == TRADE_EVENT_DISCRIMINATOR
    assert len(trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)) == 1


def test_the_cluster_executed_our_own_bytes_on_the_new_program() -> None:
    """``simulateTransaction`` (``sigVerify=false``, nothing signed, nothing sent):
    the executor's own ``build_buy``/``build_sell`` output, reaching ``Instruction:
    Buy`` / ``Instruction: Sell`` on the program deployed at slot 449734335."""
    proof = _fixture("t48d_simulation_proof_mainnet_raw.json")
    assert proof["sent"] is False and proof["sig_verify"] is False
    assert proof["program_deploy_slot"] == DEPLOY_SLOT
    assert "sendTransaction" not in proof["calls"]
    results = proof["results"]
    for key, instruction in (
        ("buy_classic", "Buy"),
        ("buy_mayhem", "Buy"),
        ("sell_classic", "Sell"),
    ):
        outcome = results[key]
        assert outcome["ok"] is True and outcome["err"] is None, key
        assert outcome["units_consumed"] > 0
        assert any(f"Instruction: {instruction}" in line for line in outcome["logs"])
        assert any("GetFeesWithQuoteMint" in line for line in outcome["logs"])
    assert results["buy_mayhem"]["is_mayhem_mode"] is True
    assert results["buy_classic"]["is_mayhem_mode"] is False
    # The Mayhem *sell* could not be proven: the only holder left was the agent's
    # own wallet, on a curve drained to 1 lamport of real SOL. `Overflow` (6024) is
    # that state, not the accounts — the same error comes back with the Mayhem PDA
    # in the remaining slot and at three different sizes (notes-T4.8d.md §4).
    for size in (755493416085, 100000000000, 10000000000):
        ours = results[f"sell_ours_pump_pda_{size}"]
        theirs = results[f"sell_mayhem_pda_{size}"]
        assert ours["err"] == theirs["err"] == {"InstructionError": [2, {"Custom": 6024}]}
