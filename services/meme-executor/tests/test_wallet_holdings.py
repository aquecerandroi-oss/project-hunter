"""The wallet's token accounts, read and judged — pure pieces (no network, no DB).

``docs/RISK_ENGINE_MEME.md`` §3.2 promises that a token the engine did not open
refuses entries (``wallet_unrecognized_holdings``). Until this module the check
was fed ``()`` by all three builders (KB-0165, Astra 27/09/2026): an LST from
staking, an airdrop or the leftover of a failed sell was neither seen nor
counted. These tests pin the chain read's parsing (fail closed on anything
malformed) and the classification (recognized set, quote mints, dust per mint,
opaque balances)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

import pytest

from hunter_exchanges.jupiter import WRAPPED_SOL_MINT
from hunter_exchanges.pumpfun.solana_codec import TOKEN_2022_PROGRAM_ID, TOKEN_PROGRAM_ID
from hunter_meme_executor.chain import ChainReader, TokenHolding, parse_token_accounts
from hunter_meme_executor.treasury_rules import USDC_MINT
from hunter_meme_executor.wallet_holdings import QUOTE_MINTS, unrecognized_mints

pytestmark = pytest.mark.unit

OWNER = "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"
JITOSOL = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"
MEME = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
NEAR = "3ZLekZYq2qkZiSpnSvabjit34tUkjSwD1JFuW9as9wBG"


def _account(
    mint: str,
    amount: str,
    decimals: int,
    *,
    program: str = TOKEN_PROGRAM_ID,
    owner: str = OWNER,
    extensions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "isNative": mint == WRAPPED_SOL_MINT,
        "mint": mint,
        "owner": owner,
        "state": "initialized",
        "tokenAmount": {"amount": amount, "decimals": decimals, "uiAmountString": "ignored"},
    }
    if extensions is not None:
        info["extensions"] = extensions
    return {
        "pubkey": "AccountPubkey1111111111111111111111111111111",
        "account": {
            "data": {"program": "spl-token", "parsed": {"info": info, "type": "account"}},
            "executable": False,
            "lamports": 2_039_280,
            "owner": program,
        },
    }


def _result(*accounts: dict[str, Any], slot: int = 400_000_000) -> dict[str, Any]:
    return {"context": {"slot": slot}, "value": list(accounts)}


def _holding(mint: str, amount: int, decimals: int, *, opaque: bool = False) -> TokenHolding:
    return TokenHolding(mint, TOKEN_PROGRAM_ID, amount, decimals, opaque)


# ------------------------------------------------------------------ parsing
def test_a_well_formed_answer_becomes_holdings_with_the_slot() -> None:
    found, slot = parse_token_accounts(
        _result(_account(JITOSOL, "12345", 9), slot=7), owner=OWNER, program=TOKEN_PROGRAM_ID
    )
    assert slot == 7
    assert found == (TokenHolding(JITOSOL, TOKEN_PROGRAM_ID, 12345, 9, False, "initialized"),)


def test_an_empty_wallet_is_an_empty_tuple_not_a_failure() -> None:
    found, _ = parse_token_accounts(_result(), owner=OWNER, program=TOKEN_PROGRAM_ID)
    assert found == ()


@pytest.mark.parametrize(
    "broken",
    [
        None,
        {"value": []},  # no context/slot
        _result({"account": {}}),  # no data
        _result(_account(JITOSOL, "12.5", 9)),  # amount is not an integer string
        _result(_account(JITOSOL, "-1", 9)),
        _result(_account("", "1", 9)),  # empty mint
        _result(_account(JITOSOL, "1", 9, owner="SomeoneElse111111111111111111111111111111")),
        _result(_account(JITOSOL, "1", 9, program=TOKEN_2022_PROGRAM_ID)),  # wrong program
        {"context": {"slot": 100}, "value": {}},  # Astra: a dict is not "no accounts"
        {"context": {"slot": 100}, "value": ""},
        {"context": {"slot": "100"}, "value": []},  # no coercion
        {"context": {"slot": -1}, "value": []},
        {"context": {"slot": True}, "value": []},
    ],
)
def test_anything_malformed_fails_the_whole_read(broken: Any) -> None:
    """A read that cannot be trusted must never become "the wallet is clean"."""
    with pytest.raises(ValueError, match="token_accounts_malformed"):
        parse_token_accounts(broken, owner=OWNER, program=TOKEN_PROGRAM_ID)


def test_a_confidential_balance_extension_is_opaque() -> None:
    """Token-2022: a public ``amount`` of 0 proves nothing about a confidential one."""
    ext = [{"extension": "immutableOwner"}, {"extension": "confidentialTransferAccount"}]
    found, _ = parse_token_accounts(
        _result(_account(MEME, "0", 6, program=TOKEN_2022_PROGRAM_ID, extensions=ext)),
        owner=OWNER,
        program=TOKEN_2022_PROGRAM_ID,
    )
    assert found[0].opaque is True
    plain, _ = parse_token_accounts(
        _result(
            _account(
                MEME,
                "0",
                6,
                program=TOKEN_2022_PROGRAM_ID,
                extensions=[{"extension": "immutableOwner"}],
            )
        ),
        owner=OWNER,
        program=TOKEN_2022_PROGRAM_ID,
    )
    assert plain[0].opaque is False


class FakeRpc:
    def __init__(self, answers: dict[str, dict[str, Any]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, list[Any]]] = []

    def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, params))
        return self.answers[params[1]["programId"]]


def test_the_reader_asks_both_token_programs_and_keeps_each_slot() -> None:
    rpc = FakeRpc(
        {
            TOKEN_PROGRAM_ID: _result(_account(USDC_MINT, "5000000", 6), slot=110),
            TOKEN_2022_PROGRAM_ID: _result(
                _account(MEME, "900", 6, program=TOKEN_2022_PROGRAM_ID), slot=100
            ),
        }
    )
    before = datetime.now(UTC)
    read = ChainReader(rpc, commitment="confirmed").token_holdings(OWNER)  # type: ignore[arg-type]
    assert [c[0] for c in rpc.calls] == ["getTokenAccountsByOwner"] * 2
    assert {c[1][1]["programId"] for c in rpc.calls} == {TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID}
    assert all(c[1][0] == OWNER for c in rpc.calls)
    assert all(c[1][2] == {"encoding": "jsonParsed", "commitment": "confirmed"} for c in rpc.calls)
    assert read.slots == (110, 100)  # SPL Token, then Token-2022
    assert read.observed_at >= before
    assert {h.mint for h in read.holdings} == {USDC_MINT, MEME}


class RendezvousRpc(FakeRpc):
    """Each call waits for the other at a barrier: a sequential reader breaks it."""

    def __init__(self, answers: dict[str, dict[str, Any]]) -> None:
        super().__init__(answers)
        self.barrier = threading.Barrier(2, timeout=30)
        self.called_at: list[datetime] = []

    def call(self, method: str, params: list[Any]) -> Any:
        self.called_at.append(datetime.now(UTC))
        self.barrier.wait()  # BrokenBarrierError after 30 s if the other never comes
        return super().call(method, params)


def _both_programs() -> dict[str, dict[str, Any]]:
    return {
        TOKEN_PROGRAM_ID: _result(_account(USDC_MINT, "5000000", 6), slot=110),
        TOKEN_2022_PROGRAM_ID: _result(slot=100),
    }


def test_the_two_programs_are_read_concurrently() -> None:
    """Guardian F2: two sequential ~1-4.8 s calls do not fit one deadline; the
    wall time of the read is the slower call, not the sum."""
    rpc = RendezvousRpc(_both_programs())
    read = ChainReader(rpc, commitment="confirmed").token_holdings(OWNER)  # type: ignore[arg-type]
    assert read.slots == (110, 100)  # still SPL Token, then Token-2022
    assert len(rpc.calls) == 2


def test_one_program_failing_fails_the_whole_read() -> None:
    answers = _both_programs()
    answers[TOKEN_2022_PROGRAM_ID] = {"context": {"slot": 100}, "value": {}}
    with pytest.raises(ValueError, match="token_accounts_malformed"):
        ChainReader(FakeRpc(answers), commitment="confirmed").token_holdings(OWNER)  # type: ignore[arg-type]


def test_the_read_is_stamped_before_either_call() -> None:
    """The verdict's age runs from the oldest moment its data can be from, so
    30 s of validity is never 30 s plus the read's own duration."""
    rpc = RendezvousRpc(_both_programs())
    read = ChainReader(rpc, commitment="confirmed").token_holdings(OWNER)  # type: ignore[arg-type]
    assert read.observed_at <= min(rpc.called_at)


# ----------------------------------------------------------- classification
def test_quote_mints_are_wsol_and_the_treasury_usdc() -> None:
    assert QUOTE_MINTS == frozenset({WRAPPED_SOL_MINT, USDC_MINT})


def test_only_mints_outside_the_recognized_set_are_named() -> None:
    held = (
        _holding(NEAR, 1_130_289_673, 9),  # the open spot/1 position
        _holding(USDC_MINT, 5_000_000, 6),  # the treasury's
        _holding(WRAPPED_SOL_MINT, 10_000, 9),
        _holding(JITOSOL, 50_000_000, 9),  # staked SOL: not ours to hold
    )
    assert unrecognized_mints(held, frozenset({NEAR}) | QUOTE_MINTS) == (JITOSOL,)


def test_a_zero_balance_account_is_not_a_holding() -> None:
    assert unrecognized_mints((_holding(MEME, 0, 6),), QUOTE_MINTS) == ()


def test_dust_is_one_millionth_of_a_token_or_less_per_mint() -> None:
    assert unrecognized_mints((_holding(MEME, 1, 6),), QUOTE_MINTS) == ()
    assert unrecognized_mints((_holding(MEME, 2, 6),), QUOTE_MINTS) == (MEME,)
    assert unrecognized_mints((_holding(JITOSOL, 1_000, 9),), QUOTE_MINTS) == ()
    assert unrecognized_mints((_holding(JITOSOL, 1_001, 9),), QUOTE_MINTS) == (JITOSOL,)
    # zero decimals: one unit is a whole token, never dust
    assert unrecognized_mints((_holding("Nft", 1, 0),), QUOTE_MINTS) == ("Nft",)


def test_dust_is_judged_on_the_total_of_a_mint_not_per_account() -> None:
    """Astra: two accounts of 600 atoms each (9 decimals) are 1 200 together."""
    held = (_holding(JITOSOL, 600, 9), _holding(JITOSOL, 600, 9))
    assert unrecognized_mints(held, QUOTE_MINTS) == (JITOSOL,)


def test_an_opaque_balance_is_unrecognized_even_at_zero() -> None:
    assert unrecognized_mints((_holding(MEME, 0, 6, opaque=True),), QUOTE_MINTS) == (MEME,)
    assert unrecognized_mints((_holding(MEME, 0, 6, opaque=True),), frozenset({MEME})) == ()


def test_decimals_that_disagree_for_one_mint_refuse_rather_than_guess() -> None:
    held = (_holding(MEME, 1, 6), _holding(MEME, 1, 9))
    assert unrecognized_mints(held, QUOTE_MINTS) == (MEME,)


def test_the_answer_is_sorted_and_deduplicated() -> None:
    held = (_holding("Zed", 10, 0), _holding("Abe", 10, 0), _holding("Zed", 5, 0))
    assert unrecognized_mints(held, QUOTE_MINTS) == ("Abe", "Zed")
