"""Wave 1b of H-030, part 2: which two tokens does a PumpSwap pool trade, per event?

A PumpSwap event names the pool, not its mints. The swap instruction that emitted it (top level or
reached through a router) lists them: accounts 3 and 4 are ``base_mint`` and ``quote_mint`` in the
program's own IDL. ``read_transaction_logs`` attaches them to every pool record, so ``quote_is_sol``
is decided by the QUOTE mint and a pool whose base is WSOL is marked, not read as SOL.

The independent witness is the chain, not the decoder: the ``mint`` field of the token-balance rows of
the pool's own vaults (instruction accounts 7 and 8) and of the user's accounts. Real fixtures
only; anything built from them is labelled SYNTHETIC.
"""

from __future__ import annotations

import copy
import json
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.program_logs import read_program_logs, read_transaction_logs
from hunter_exchanges.pumpfun.swap_record import SwapRecord
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID, WSOL_MINT

from .t1a_chain import FIXTURES, account_keys, all_instructions, load
from .t1a_logs import (
    AMM_BUY,
    AMM_SELL,
    AMM_SELL_CASHBACK_X2,
    AMM_SELL_NEXT,
    RECEIVED,
    V1_AMM_BUY_ROUTED,
    V1_AMM_SELL,
    amm,
    logs_of,
    sig_of,
)

_WSOL_BASE = (
    "t1a_rpc_amm_buy_nocreator_4jyiFoCoVoWt_raw.json",
    AMM_SELL,
    AMM_SELL_NEXT,
)
_ROUTED = ("t1a_rpc_amm_buy_routed_2HzxLVTqSFWq_raw.json", V1_AMM_BUY_ROUTED, V1_AMM_SELL)
_PUMP_QUOTED = "t48e_rpc_amm_tx_5A1byFyLnuFA_raw.json"  # a pool quoted in the PUMP token
_SWAP_IX = {
    "66063d1201daebea",  # buy
    "c62e1552b4d9e870",  # buy_exact_quote_in
    "33e685a4017f83ad",  # sell
}
_ALL = sorted(
    p.name
    for pattern in (
        "t1a_rpc_*amm*_raw.json",
        "t48e_rpc_amm_tx_*_raw.json",
        "t48f_rpc_amm_tx_*_raw.json",
    )
    for p in (FIXTURES / "pumpswap").glob(pattern)
)


def _read(tx: dict[str, Any]) -> Any:
    return read_transaction_logs(tx, received_at=RECEIVED)


def _swap_instructions(tx: dict[str, Any]) -> list[list[str]]:
    """Account lists of every PumpSwap swap instruction, in execution order."""
    from hunter_exchanges.pumpfun.solana_codec import b58decode

    keys = account_keys(tx)
    return [
        [keys[i] for i in cast(list[int], ix["accounts"])]
        for _, ix in all_instructions(tx)
        if keys[ix["programIdIndex"]] == PUMPSWAP_PROGRAM_ID
        and b58decode(str(ix["data"]))[:8].hex() in _SWAP_IX
    ]


def _mint_of_account(tx: dict[str, Any], address: str) -> str | None:
    """The chain's own label of a token account: the ``mint`` of its balance row (pre or post)."""
    index = account_keys(tx).index(address)
    for side in ("preTokenBalances", "postTokenBalances"):
        for row in tx["meta"][side]:
            if row["accountIndex"] == index:
                return str(row["mint"])
    return None


def _witness(tx: dict[str, Any], pool: str) -> tuple[str, str]:
    """(base, quote) of a pool from its two vault accounts (instruction accounts 7 and 8)."""
    accounts = next(a for a in _swap_instructions(tx) if a[0] == pool)
    base, quote = _mint_of_account(tx, accounts[7]), _mint_of_account(tx, accounts[8])
    assert base and quote
    return base, quote


def _pool_swaps(tx: dict[str, Any]) -> tuple[SwapRecord, ...]:
    return tuple(s for s in _read(tx).swaps if s.venue == "pool")


# -- the IDL premise ------------------------------------------------------------------------------


def test_the_amm_idl_puts_the_mints_at_accounts_3_and_4_and_the_vaults_at_7_and_8() -> None:
    idl = load("pumpswap/t429a_idl_pump_amm_onchain.json")
    for ix in idl["instructions"]:
        if ix["name"] in ("buy", "buy_exact_quote_in", "sell"):
            names = [a["name"] for a in ix["accounts"]]
            assert names[:9] == [
                "pool",
                "user",
                "global_config",
                "base_mint",
                "quote_mint",
                "user_base_token_account",
                "user_quote_token_account",
                "pool_base_token_account",
                "pool_quote_token_account",
            ]


# -- every real pool swap, against the chain's own evidence ---------------------------------------


@pytest.mark.parametrize("name", _ALL)
def test_every_real_pool_swap_gets_the_mints_the_pools_own_vaults_hold(name: str) -> None:
    tx = amm(name)
    swaps = _pool_swaps(tx)
    assert swaps, name
    for swap in swaps:
        base, quote = _witness(tx, cast(str, swap.pool))
        assert (swap.base_mint, swap.quote_mint) == (base, quote)
        assert swap.quote_is_sol is (quote == WSOL_MINT)
        assert swap.wsol_is_base is (base == WSOL_MINT)
    read = _read(tx)
    assert read.counters.pool_mints_unresolved == 0 and read.counters.pool_mints_conflict == 0
    assert not read.gap


def test_the_wsol_base_pools_are_marked_and_their_quote_leg_is_not_sol() -> None:
    for name in _WSOL_BASE:
        (swap,) = _pool_swaps(amm(name))
        assert swap.base_mint == WSOL_MINT and swap.wsol_is_base is True
        assert swap.quote_mint != WSOL_MINT and swap.quote_is_sol is False


def test_the_usual_pool_has_wsol_in_the_quote() -> None:
    (swap,) = _pool_swaps(amm(AMM_BUY))
    assert swap.quote_mint == WSOL_MINT and swap.quote_is_sol is True
    assert swap.base_mint != WSOL_MINT and swap.wsol_is_base is False


def test_a_pool_quoted_in_another_token_is_neither_sol_nor_wsol_base() -> None:
    swaps = _pool_swaps(amm(_PUMP_QUOTED))
    quoted = [s for s in swaps if s.quote_mint != WSOL_MINT]
    assert quoted and all(s.quote_is_sol is False and s.wsol_is_base is False for s in quoted)
    assert all(s.quote_mint.startswith("pumpCm") for s in quoted if s.quote_mint)


def test_a_swap_reached_through_a_router_is_attributed_to_the_inner_instruction() -> None:
    for name in _ROUTED:
        tx = amm(name)
        keys = account_keys(tx)
        top_programs: set[str] = {
            keys[ix["programIdIndex"]] for kind, ix in all_instructions(tx) if kind == "top"
        }
        assert PUMPSWAP_PROGRAM_ID not in top_programs  # the pool is only reached by CPI
        (swap,) = _pool_swaps(tx)
        assert (swap.base_mint, swap.quote_mint) == _witness(tx, cast(str, swap.pool))
        assert swap.quote_is_sol is True


def test_two_events_of_one_transaction_each_get_their_pool_mints() -> None:
    tx = amm(AMM_SELL_CASHBACK_X2)
    swaps = _pool_swaps(tx)
    assert len(swaps) == 2
    assert {(s.base_mint, s.quote_mint) for s in swaps} == {_witness(tx, cast(str, swaps[0].pool))}


# -- what the logs alone cannot say ---------------------------------------------------------------


def test_the_logs_only_reader_leaves_the_mints_unknown_it_cannot_see_instructions() -> None:
    tx = amm(AMM_BUY)
    r = read_program_logs(
        signature=sig_of(tx), slot=int(tx["slot"]), logs=logs_of(tx), received_at=RECEIVED
    )
    (swap,) = r.swaps
    assert (swap.base_mint, swap.quote_mint, swap.quote_is_sol) == (None, None, None)
    assert swap.wsol_is_base is None
    assert r.counters.pool_mints_unresolved == 0  # not looked up, not "failed to resolve"


def test_the_record_keeps_the_users_token_accounts_the_match_is_made_on() -> None:
    (swap,) = _pool_swaps(amm(AMM_BUY))
    accounts = _swap_instructions(amm(AMM_BUY))[0]
    assert (swap.user_base_token_account, swap.user_quote_token_account) == (
        accounts[5],
        accounts[6],
    )


# -- never guess ----------------------------------------------------------------------------------


def _copy(tx: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(tx)))


def _blank_swap_instructions(tx: dict[str, Any]) -> None:
    """SYNTHETIC: overwrite the data of every PumpSwap instruction that is not an event CPI so its
    discriminator is no known swap (what an instruction this reader does not know looks like)."""
    from hunter_exchanges.pumpfun.solana_codec import b58decode

    keys = account_keys(tx)
    for ix in [i for _, i in all_instructions(tx)]:
        if keys[ix["programIdIndex"]] == PUMPSWAP_PROGRAM_ID:
            if b58decode(str(ix["data"]))[:8].hex() in _SWAP_IX:
                ix["data"] = "1" * 20


def test_an_event_whose_instruction_cannot_be_found_is_counted_and_left_unknown() -> None:
    tx = _copy(amm(AMM_BUY))
    _blank_swap_instructions(tx)
    r = _read(tx)
    (swap,) = r.swaps
    assert (swap.base_mint, swap.quote_mint, swap.quote_is_sol) == (None, None, None)
    assert r.counters.pool_mints_unresolved == 1
    assert (
        r.counters.swaps == 1 and not r.gap
    )  # the swap itself is intact; only its legs are unknown


def test_a_vault_that_disagrees_with_the_instruction_makes_the_legs_a_conflict() -> None:
    """SYNTHETIC: the pool's quote vault balance row relabelled with another mint."""
    tx = _copy(amm(AMM_BUY))
    vault = _swap_instructions(tx)[0][8]
    index = account_keys(tx).index(vault)
    for side in ("preTokenBalances", "postTokenBalances"):
        for row in tx["meta"][side]:
            if row["accountIndex"] == index:
                row["mint"] = "7" * 43
    r = _read(tx)
    (swap,) = r.swaps
    assert (swap.base_mint, swap.quote_mint, swap.quote_is_sol) == (None, None, None)
    assert r.counters.pool_mints_conflict == 1 and r.counters.pool_mints_unresolved == 0


def test_two_matching_instructions_that_name_different_mints_are_a_conflict() -> None:
    """SYNTHETIC: a second swap instruction for the same pool/user/accounts that names the base mint
    as the quote (an account index the transaction already has)."""
    tx = _copy(amm(AMM_BUY))
    keys = account_keys(tx)
    top = tx["transaction"]["message"]["instructions"]
    original = next(
        ix
        for ix in top
        if keys[ix["programIdIndex"]] == PUMPSWAP_PROGRAM_ID and len(ix["accounts"]) > 8
    )
    twin = copy.deepcopy(original)
    twin["accounts"][4] = original["accounts"][3]
    top.append(twin)
    r = _read(tx)
    (swap,) = r.swaps
    assert (swap.base_mint, swap.quote_mint) == (None, None)
    assert r.counters.pool_mints_conflict == 1


def test_resolving_does_not_mutate_the_callers_transaction() -> None:
    tx = amm(AMM_BUY)
    before = json.dumps(tx, sort_keys=True)
    _read(tx)
    assert json.dumps(tx, sort_keys=True) == before


def test_the_vaults_of_every_matching_instruction_are_checked_not_only_the_first() -> None:
    """SYNTHETIC (Astra, wallets-1b-record): a twin of the real swap instruction (same pool, user,
    accounts and mints) whose pool quote vault is the BASE vault. Both name the same mints, but the
    twin's vault contradicts the chain's labels, so the legs are a conflict."""
    tx = _copy(amm(AMM_BUY))
    keys = account_keys(tx)
    top = tx["transaction"]["message"]["instructions"]
    original = next(
        ix
        for ix in top
        if keys[ix["programIdIndex"]] == PUMPSWAP_PROGRAM_ID and len(ix["accounts"]) > 8
    )
    twin = copy.deepcopy(original)
    twin["accounts"][8] = original["accounts"][7]
    top.append(twin)
    r = _read(tx)
    (swap,) = r.swaps
    assert (swap.base_mint, swap.quote_mint) == (None, None)
    assert r.counters.pool_mints_conflict == 1


def _retag_second_swap_as_unknown_v2(tx: dict[str, Any]) -> None:
    """SYNTHETIC: the discriminator of the transaction's second swap instruction replaced by the
    one of ``SellV2`` (``5df6823ce7e940b2``, seen on chain, layout not known to this reader)."""
    from hunter_exchanges.pumpfun.solana_codec import b58decode, b58encode

    keys = account_keys(tx)
    swaps = [
        ix
        for ix in tx["transaction"]["message"]["instructions"]
        if keys[ix["programIdIndex"]] == PUMPSWAP_PROGRAM_ID
        and b58decode(str(ix["data"]))[:8].hex() in _SWAP_IX
    ]
    assert len(swaps) == 2
    swaps[1]["data"] = b58encode(
        bytes.fromhex("5df6823ce7e940b2") + b58decode(swaps[1]["data"])[8:]
    )


def test_an_event_that_may_come_from_an_unknown_instruction_is_counted_as_via_sibling() -> None:
    """SYNTHETIC (Astra + code-reviewer, round 2): two sells of one pool and user, the second
    instruction retagged as an unknown ``SellV2``. The mints are right by construction (one pair
    per pool) but the unknown invocation is only borrowing the known one's evidence: both events
    of that pool/user are counted in ``pool_mints_via_sibling`` instead of passing as proven."""
    tx = _copy(amm(AMM_SELL_CASHBACK_X2))
    _retag_second_swap_as_unknown_v2(tx)
    r = _read(tx)
    assert len(r.swaps) == 2 and all(s.base_mint is not None for s in r.swaps)
    assert r.counters.pool_mints_via_sibling == 2
    assert r.counters.pool_mints_unresolved == 0 and not r.gap


def test_real_swaps_with_only_known_instructions_are_never_via_sibling() -> None:
    for name in _ALL:
        assert _read(amm(name)).counters.pool_mints_via_sibling == 0, name


def test_an_unknown_instruction_of_another_user_does_not_make_the_event_via_sibling() -> None:
    """SYNTHETIC: as above, but the unknown instruction's user account (account 1) is another account,
    so it does not involve this event's user: nothing is borrowed."""
    tx = _copy(amm(AMM_SELL_CASHBACK_X2))
    _retag_second_swap_as_unknown_v2(tx)
    keys = account_keys(tx)
    unknown = [
        ix
        for ix in tx["transaction"]["message"]["instructions"]
        if keys[ix["programIdIndex"]] == PUMPSWAP_PROGRAM_ID
    ][1]
    unknown["accounts"][1] = unknown["accounts"][3]  # the base mint stands in for another "user"
    r = _read(tx)
    assert r.counters.pool_mints_via_sibling == 0
