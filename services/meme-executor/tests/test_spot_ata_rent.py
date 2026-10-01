"""KB-0171 bug (01/10/2026): the ``spot/1`` desk subtracted a constant
2 039 280 lamports of ATA rent from a buy's outflow, while the network charged
1 488 440 (``getMinimumBalanceForRentExemption(165)`` and the real
``createAccount`` of the 4 buys that opened an ATA). ``sol_spent`` was
understated and ``pnl_sol``/``r_multiple`` inflated by 550 840 lamports each.

Fixtures here are **labeled test data** shaped like a real ``getTransaction``
(``encoding: json``, v0 with ``loadedAddresses``) of a Jupiter SOL -> token buy:
the wallet's WSOL account is created and closed in the same transaction (rent
comes back, no token balance on either side), the token ATA is created and kept.
The rent is read from the new token account's own lamport delta in the meta —
never a constant; unreadable ⇒ ``None`` (the caller folds it into the spend
and says so, never an optimistic PnL).
"""

from __future__ import annotations

from typing import Any

import pytest

from hunter_exchanges.pumpfun.solana_codec import (
    SYSTEM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    associated_token_address,
)
from hunter_meme_executor import spot_send_rules
from hunter_meme_executor.spot_send_rules import entry_spend, fill_from_transaction

from .spot_tx_fixtures import WALLET, WIF, WSOL_ATA, create_account_ix

pytestmark = pytest.mark.unit

NEAR = WIF
"""Any classic SPL mint does; the fixture mint is reused so the ATA derives."""
NEAR_ATA = associated_token_address(WALLET, NEAR, token_program=TOKEN_PROGRAM_ID)
RENT_TODAY = 1_488_440
"""(165 + 128) × 5 080 — what the 4 real buys paid (KB-0171)."""
RENT_LEGACY = 2_039_280
"""(165 + 128) × 6 960 — the pre-reduction minimum the code had hard-coded."""
TICKET = 50_000_000
NETWORK_FEE = 5_000 + 38_316  # base + a real-sized priority (KB-0171 buy mean)


def jupiter_buy_meta(
    *,
    rent: int | None,
    token_index: int = 3,
    ata_pre_lamports: int = 0,
    token_pre: int | None = None,
    token_post: int = 3_123_456_789,
    mint: str = NEAR,
    funder: str | None = WALLET,
    other_account: bool = False,
) -> dict[str, Any]:
    """A v0 buy: static keys ``[wallet, wsol_ata, system, vaultA]`` plus two loaded
    addresses. ``token_index`` 3 = static, 5 = loaded. The wallet pays ticket +
    fee + the rent the token ATA keeps (``rent`` lamports added to the new account;
    ``None`` = no ATA created), through the ATA program's inner
    ``system::createAccount`` from ``funder`` (``None`` = no createAccount: a
    transfer to a pre-funded address). ``other_account``: the wallet already holds
    a second, empty token account of the same mint (index 4)."""
    everything = [WALLET, WSOL_ATA, SYSTEM_PROGRAM_ID, "VaultA", "VaultB", "VaultC"]
    everything[token_index] = NEAR_ATA
    static, loaded = everything[:4], {"writable": everything[4:], "readonly": []}
    n = len(everything)
    pre, post = [0] * n, [0] * n
    kept = 0 if rent is None or funder != WALLET else rent
    pre[0] = 1_000_000_000
    post[0] = pre[0] - TICKET - NETWORK_FEE - kept
    pre[1] = post[1] = 0  # WSOL: created and closed inside the transaction
    if rent is not None:
        pre[token_index], post[token_index] = ata_pre_lamports, ata_pre_lamports + rent
    else:
        pre[token_index] = post[token_index] = RENT_TODAY  # the ATA already existed

    def tb(amount: int, index: int = token_index) -> dict[str, Any]:
        return {
            "accountIndex": index,
            "mint": mint,
            "owner": WALLET,
            "programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
            "uiTokenAmount": {"amount": str(amount), "decimals": 6},
        }

    inner: list[dict[str, Any]] = []
    if rent is not None and funder is not None:
        ix = create_account_ix(everything, source=funder, new=NEAR_ATA, lamports=rent)
        inner = [{"index": 2, "instructions": [ix]}]
    extra = [tb(0, 4)] if other_account else []
    return {
        "slot": 371_000_000,
        "blockTime": 1_759_000_000,
        "version": 0,
        "transaction": {"message": {"accountKeys": static, "instructions": []}},
        "meta": {
            "err": None,
            "fee": NETWORK_FEE,
            "preBalances": pre,
            "postBalances": post,
            "loadedAddresses": loaded,
            "innerInstructions": inner,
            "preTokenBalances": extra + ([] if token_pre is None else [tb(token_pre)]),
            "postTokenBalances": [*extra, tb(token_post + (token_pre or 0))],
        },
    }


# ------------------------------------------------------------ the rent, read
@pytest.mark.parametrize("rent", [RENT_TODAY, RENT_LEGACY, 2_074_080])
def test_the_rent_is_the_new_token_account_s_own_lamports(rent: int) -> None:
    """Today's 1 488 440, the legacy 2 039 280 (an ATA created before the
    reduction) and a larger Token-2022 account are all read as paid."""
    fill = fill_from_transaction(jupiter_buy_meta(rent=rent), wallet=WALLET, mint=NEAR)
    assert fill is not None
    assert fill.ata_rent_lamports == rent
    assert fill.sol_delta_lamports == -(TICKET + NETWORK_FEE + rent)


def test_a_token_account_reached_through_a_lookup_table_is_read_too() -> None:
    """``accountIndex`` spans static keys + ``loadedAddresses``, like the balances."""
    meta = jupiter_buy_meta(rent=RENT_TODAY, token_index=5)
    fill = fill_from_transaction(meta, wallet=WALLET, mint=NEAR)
    assert fill is not None and fill.ata_rent_lamports == RENT_TODAY


def test_a_pre_funded_address_without_the_wallet_s_create_account_is_unknown() -> None:
    """The ATA program tops a pre-funded address up by transfer + allocate +
    assign, no ``createAccount``: who paid is not proven — unknown, folded."""
    meta = jupiter_buy_meta(rent=RENT_TODAY - 890_880, ata_pre_lamports=890_880, funder=None)
    fill = fill_from_transaction(meta, wallet=WALLET, mint=NEAR)
    assert fill is not None and fill.ata_rent_lamports is None


def test_a_deposit_funded_by_someone_else_is_never_subtracted() -> None:
    """Astra, diff review (reproduced): a third party funds the wallet's ATA in
    the same transaction — subtracting it would inflate the PnL by the whole rent."""
    meta = jupiter_buy_meta(rent=RENT_TODAY, funder="VaultC")
    fill = fill_from_transaction(meta, wallet=WALLET, mint=NEAR)
    assert fill is not None and fill.ata_rent_lamports is None
    assert fill.sol_delta_lamports == -(TICKET + NETWORK_FEE)
    assert entry_spend(fill.sol_delta_lamports, fill.ata_rent_lamports)[0] == TICKET + NETWORK_FEE


def test_a_create_account_that_disagrees_with_the_balance_is_unknown() -> None:
    meta = jupiter_buy_meta(rent=RENT_TODAY)
    meta["meta"]["postBalances"][3] += 1
    fill = fill_from_transaction(meta, wallet=WALLET, mint=NEAR)
    assert fill is not None and fill.ata_rent_lamports is None


def test_another_account_of_the_same_mint_does_not_hide_the_new_ata() -> None:
    """Astra, diff review (reproduced): an existing empty account of the mint
    made the old ``ata_created`` false and the rent silently 0."""
    meta = jupiter_buy_meta(rent=RENT_TODAY, other_account=True)
    fill = fill_from_transaction(meta, wallet=WALLET, mint=NEAR)
    assert fill is not None
    assert fill.ata_rent_lamports == RENT_TODAY


def test_garbage_indexes_and_fractional_balances_are_not_believed() -> None:
    bad_index = jupiter_buy_meta(rent=RENT_TODAY)
    bad_index["meta"]["preTokenBalances"] = [{"accountIndex": [], "mint": "x", "owner": "y"}]
    fill = fill_from_transaction(bad_index, wallet=WALLET, mint=NEAR)
    assert fill is not None and fill.ata_rent_lamports == RENT_TODAY, "an unrelated bad entry"
    fractional = jupiter_buy_meta(rent=RENT_TODAY)
    fractional["meta"]["postBalances"][3] = RENT_TODAY + 0.75
    fill = fill_from_transaction(fractional, wallet=WALLET, mint=NEAR)
    assert fill is not None and fill.ata_rent_lamports is None


def test_a_reused_ata_has_no_rent() -> None:
    meta = jupiter_buy_meta(rent=None, token_pre=0)
    fill = fill_from_transaction(meta, wallet=WALLET, mint=NEAR)
    assert fill is not None and fill.ata_rent_lamports == 0


def test_a_sell_has_no_rent() -> None:
    meta = jupiter_buy_meta(rent=None, token_pre=3_000_000, token_post=-3_000_000)
    fill = fill_from_transaction(meta, wallet=WALLET, mint=NEAR)
    assert fill is not None and fill.ata_rent_lamports == 0


@pytest.mark.parametrize(
    "breakage",
    ["index_out_of_range", "no_index", "zero_delta", "balance_not_int", "not_the_wallet_ata"],
)
def test_a_created_account_whose_rent_cannot_be_read_is_unknown(breakage: str) -> None:
    """Never a constant, never 0: ``None`` — the caller marks the position. A
    created account that is not the wallet's ATA of the mint proves nothing
    about who funded it (Astra, design review)."""
    meta = jupiter_buy_meta(rent=RENT_TODAY)
    entry = meta["meta"]["postTokenBalances"][0]
    if breakage == "not_the_wallet_ata":
        meta["transaction"]["message"]["accountKeys"][3] = WSOL_ATA
    elif breakage == "index_out_of_range":
        entry["accountIndex"] = 99
    elif breakage == "no_index":
        del entry["accountIndex"]
    elif breakage == "zero_delta":
        meta["meta"]["postBalances"][3] = meta["meta"]["preBalances"][3]
    else:
        meta["meta"]["postBalances"][3] = "lots"
    fill = fill_from_transaction(meta, wallet=WALLET, mint=NEAR)
    assert fill is not None
    assert fill.ata_rent_lamports is None


# ------------------------------------------------------------ the spend
def test_the_spend_is_the_outflow_minus_the_rent_actually_paid() -> None:
    for rent in (RENT_TODAY, RENT_LEGACY):
        delta = -(TICKET + NETWORK_FEE + rent)
        assert entry_spend(delta, rent) == (
            TICKET + NETWORK_FEE,
            rent,
            "signature_delta_minus_rent",
        )
    assert entry_spend(-(TICKET + NETWORK_FEE), 0) == (
        TICKET + NETWORK_FEE,
        0,
        "signature_delta_minus_rent",
    )


def test_the_old_constant_understated_the_spend_by_550_840() -> None:
    """The bug, in numbers: what the constant made of a 1 488 440 buy."""
    delta = -(TICKET + NETWORK_FEE + RENT_TODAY)
    right, _, _ = entry_spend(delta, RENT_TODAY)
    wrong = -delta - RENT_LEGACY
    assert right - wrong == 550_840


def test_an_unknown_rent_is_folded_into_the_spend_and_named() -> None:
    """Pessimistic, visible: the whole outflow is the cost and the source says why."""
    delta = -(TICKET + NETWORK_FEE + RENT_TODAY)
    assert entry_spend(delta, None) == (-delta, 0, "signature_delta_rent_unknown")


def test_a_rent_larger_than_the_outflow_is_folded_as_before() -> None:
    assert entry_spend(-1_000, 2_000) == (1_000, 0, "signature_delta_rent_folded")


def test_the_constant_is_only_an_upper_bound_now() -> None:
    """The old name is gone (nothing can account with it by accident); the
    simulation's allowance keeps the legacy value as a ceiling."""
    assert not hasattr(spot_send_rules, "ATA_RENT_LAMPORTS")
    assert spot_send_rules.ATA_RENT_MAX_LAMPORTS == RENT_LEGACY
