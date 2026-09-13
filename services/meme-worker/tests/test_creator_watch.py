# pyright: reportPrivateUsage=false
"""T4.2h — the creator watch, without a database: the ATAs derived per token
program, the parsed balances, the sum per mint, and the one rule — a decrease
between two readings is a sale; a first reading, a missing account or a rise
is not."""

from __future__ import annotations

from decimal import Decimal

from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    associated_token_address,
)
from hunter_meme_worker.creator_watch import (
    Drop,
    ata_targets,
    balances_by_mint,
    detect_drops,
    parse_token_amounts,
)

MINT = "25xPUKHqporrJqzKgdShSuckPPPmTMdyVp5Ue256pump"
OTHER = "J2RPV929Cv3CHDFpUtQ4FNG8YcxJWVDgZ9HHa1PRpump"
CREATOR = "6nAh8drzAYfFZuTFFRgwRdV8tNndFiX1E8NGRAGzSk5F"


def _account(amount: str) -> dict[str, object]:
    return {"data": {"parsed": {"info": {"tokenAmount": {"amount": amount}}}}}


def test_the_targets_are_the_creator_s_classic_and_2022_atas_in_order() -> None:
    targets = ata_targets([(MINT, CREATOR)])
    assert [mint for mint, _ in targets] == [MINT, MINT]
    assert targets[0][1] == associated_token_address(CREATOR, MINT, token_program=TOKEN_PROGRAM_ID)
    assert targets[1][1] == associated_token_address(
        CREATOR, MINT, token_program=TOKEN_2022_PROGRAM_ID
    )
    assert targets[0][1] != targets[1][1], "the token program is part of the seed"


def test_amounts_parse_and_a_missing_or_foreign_account_is_none() -> None:
    assert parse_token_amounts([_account("1000"), None, {"data": "AAAA"}, {"data": {}}]) == [
        1000,
        None,
        None,
        None,
    ]


def test_balances_sum_the_creator_s_accounts_and_none_means_no_account() -> None:
    targets = ata_targets([(MINT, CREATOR), (OTHER, CREATOR)])
    assert balances_by_mint(targets, [700, 300, None, None]) == {MINT: 1000, OTHER: None}
    assert balances_by_mint(targets, [None, 5, None, None]) == {MINT: 5, OTHER: None}


def test_only_a_decrease_between_two_readings_is_a_sale() -> None:
    assert detect_drops({}, {MINT: 1000}) == [], "a first reading is not a sale"
    assert detect_drops({MINT: 1000}, {MINT: 1000}) == []
    assert detect_drops({MINT: 1000}, {MINT: 1200}) == [], "a rise is not a sale"
    assert detect_drops({MINT: 1000}, {MINT: None}) == [], "a vanished account is unmeasured"
    drops = detect_drops({MINT: 1000, OTHER: 10}, {MINT: 400, OTHER: 10})
    assert drops == [Drop(mint=MINT, before=1000, after=400)]
    assert drops[0].fraction == Decimal("0.600000")


def test_the_fraction_of_a_full_exit_is_one() -> None:
    assert Drop(mint=MINT, before=10, after=0).fraction == Decimal("1.000000")
