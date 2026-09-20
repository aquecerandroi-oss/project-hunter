"""``meme_close_atas_verify.verify_close_atas_message`` (T4.77): the pure
verifier that runs on the compiled message **before** the signer touches it.
Every bad transaction here is hand-built the way an attacker (or a bug in the
builder) would build it: a System ``Transfer``, a ``CloseAccount`` whose
refund goes to a foreign destination, a foreign program, a Token
``Transfer`` disguised inside the allowed program, a close of an account the
plan never listed, a Token-2022 close of an account the plan judged on the
classic program, more than one signer, a priority fee above the cap. The
good transaction is the builder's own output. The Token-2022 positive and
negative cases of T4.77b live in ``test_meme_close_atas_token_2022.py``.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in ("services/meme-executor", "packages/exchange-adapters", "packages/risk-core"):
    candidate = str(REPO_ROOT / extra)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from meme_close_atas_plan import build_batch_message  # noqa: E402
from meme_close_atas_verify import (  # noqa: E402
    MAX_CLOSES_PER_BATCH,
    MAX_PRIORITY_FEE_LAMPORTS,
    CloseAtasRefused,
    verify_close_atas_message,
)

from hunter_exchanges.pumpfun.solana_codec import (  # noqa: E402
    COMPUTE_BUDGET_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    AccountMeta,
    Instruction,
    b58encode,
    compile_message,
    set_compute_unit_limit,
    set_compute_unit_price,
)

WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
OTHER = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
JUP6 = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
BLOCKHASH = b58encode(bytes([7]) * 32)
ATAS = tuple(b58encode(bytes([i + 1]) * 32) for i in range(10))
CLOSE = bytes([9])


def _close(account: str, *, destination: str = WALLET, authority: str = WALLET) -> Instruction:
    return Instruction(
        TOKEN_PROGRAM_ID,
        (
            AccountMeta(account, False, True),
            AccountMeta(destination, False, True),
            AccountMeta(authority, True, False),
        ),
        CLOSE,
    )


def _budget() -> list[Instruction]:
    return [set_compute_unit_limit(50_000), set_compute_unit_price(200_000)]


def _plan(allowed: tuple[str, ...]) -> dict[str, str]:
    """What the plan records: account -> the token program it was judged on."""
    return {account: TOKEN_PROGRAM_ID for account in allowed}


def _verify(instructions: list[Instruction], *, allowed: tuple[str, ...] = ATAS[:8]) -> None:
    message = compile_message(WALLET, instructions, BLOCKHASH)
    verify_close_atas_message(message, wallet=WALLET, allowed_accounts=_plan(allowed))


def test_the_builders_own_batch_verifies() -> None:
    message = build_batch_message(
        wallet=WALLET,
        accounts=ATAS[:8],
        blockhash=BLOCKHASH,
        priority_fee_lamports=10_000,
        token_program=TOKEN_PROGRAM_ID,
    )
    closed = verify_close_atas_message(message, wallet=WALLET, allowed_accounts=_plan(ATAS[:8]))
    assert closed == ATAS[:8]


def test_a_system_transfer_is_refused() -> None:
    transfer = Instruction(
        SYSTEM_PROGRAM_ID,
        (AccountMeta(WALLET, True, True), AccountMeta(OTHER, False, True)),
        struct.pack("<I", 2) + struct.pack("<Q", 1_000_000),
    )
    with pytest.raises(CloseAtasRefused, match="program_not_allowed:1111"):
        _verify([*_budget(), _close(ATAS[0]), transfer])


def test_a_close_whose_refund_goes_to_a_foreign_destination_is_refused() -> None:
    with pytest.raises(CloseAtasRefused, match="close_destination_not_wallet"):
        _verify([*_budget(), _close(ATAS[0], destination=OTHER)])


def test_a_close_whose_authority_is_not_the_wallet_is_refused() -> None:
    # The authority is a non-signer here so the message still carries exactly
    # one signature; a signing foreign authority is a second signer, caught below.
    foreign = Instruction(
        TOKEN_PROGRAM_ID,
        (
            AccountMeta(ATAS[0], False, True),
            AccountMeta(WALLET, False, True),
            AccountMeta(OTHER, False, False),
        ),
        CLOSE,
    )
    with pytest.raises(CloseAtasRefused, match="close_authority_not_wallet"):
        _verify([*_budget(), foreign])


def test_a_foreign_program_is_refused_by_name() -> None:
    route = Instruction(
        JUP6, (AccountMeta(WALLET, True, True),), b"\xe5\x17\xcb\x97\x7a\xe3\xad\x2a"
    )
    with pytest.raises(CloseAtasRefused, match="program_not_allowed:JUP6"):
        _verify([*_budget(), _close(ATAS[0]), route])


def test_a_token_2022_close_of_an_account_the_plan_judged_as_classic_is_refused() -> None:
    """T4.77b: the program is allowed, but only on the accounts the plan
    recorded under it — a classic verdict is not a Token-2022 verdict."""
    close_2022 = Instruction(TOKEN_2022_PROGRAM_ID, _close(ATAS[0]).accounts, CLOSE)
    with pytest.raises(CloseAtasRefused, match="close_account_program_mismatch"):
        _verify([*_budget(), close_2022])


def test_a_token_transfer_disguised_inside_the_token_program_is_refused() -> None:
    transfer = Instruction(
        TOKEN_PROGRAM_ID,
        (
            AccountMeta(ATAS[0], False, True),
            AccountMeta(OTHER, False, True),
            AccountMeta(WALLET, True, False),
        ),
        bytes([3]) + struct.pack("<Q", 1),
    )
    with pytest.raises(CloseAtasRefused, match="token_instruction_not_close_account"):
        _verify([*_budget(), transfer])


def test_a_close_account_with_trailing_bytes_is_not_a_close_account() -> None:
    padded = Instruction(TOKEN_PROGRAM_ID, _close(ATAS[0]).accounts, CLOSE + b"\x00")
    with pytest.raises(CloseAtasRefused, match="token_instruction_not_close_account"):
        _verify([*_budget(), padded])


def test_a_close_of_an_account_the_plan_never_listed_is_refused() -> None:
    with pytest.raises(CloseAtasRefused, match="close_account_not_in_plan"):
        _verify([*_budget(), _close(ATAS[9])], allowed=ATAS[:8])


def test_the_same_account_closed_twice_is_refused() -> None:
    with pytest.raises(CloseAtasRefused, match="close_account_duplicated"):
        _verify([*_budget(), _close(ATAS[0]), _close(ATAS[0])])


def test_more_than_the_batch_size_is_refused() -> None:
    closes = [_close(a) for a in ATAS[: MAX_CLOSES_PER_BATCH + 1]]
    with pytest.raises(CloseAtasRefused, match="too_many_close_instructions"):
        _verify([*_budget(), *closes], allowed=ATAS)


def test_a_message_with_no_close_at_all_is_refused() -> None:
    with pytest.raises(CloseAtasRefused, match="no_close_account_instruction"):
        _verify(_budget())


def test_a_second_signer_is_refused() -> None:
    extra = Instruction(
        TOKEN_PROGRAM_ID,
        (
            AccountMeta(ATAS[0], False, True),
            AccountMeta(WALLET, False, True),
            AccountMeta(OTHER, True, False),  # a second required signature
        ),
        CLOSE,
    )
    with pytest.raises(CloseAtasRefused, match="signers_not_exactly_wallet"):
        _verify([*_budget(), _close(ATAS[1]), extra])


def test_a_priority_fee_above_the_cap_is_refused() -> None:
    limit = 50_000
    price = (MAX_PRIORITY_FEE_LAMPORTS + 1) * 1_000_000 // limit + 1
    with pytest.raises(CloseAtasRefused, match="priority_fee_above_cap"):
        _verify([set_compute_unit_limit(limit), set_compute_unit_price(price), _close(ATAS[0])])


def test_a_compute_budget_instruction_that_is_not_limit_or_price_is_refused() -> None:
    heap = Instruction(COMPUTE_BUDGET_PROGRAM_ID, (), bytes([1]) + struct.pack("<I", 65_536))
    with pytest.raises(CloseAtasRefused, match="compute_budget_instruction_unknown"):
        _verify([*_budget(), heap, _close(ATAS[0])])


def test_a_close_whose_account_is_not_writable_is_refused() -> None:
    readonly = Instruction(
        TOKEN_PROGRAM_ID,
        (
            AccountMeta(ATAS[0], False, False),
            AccountMeta(WALLET, False, True),
            AccountMeta(WALLET, True, False),
        ),
        CLOSE,
    )
    with pytest.raises(CloseAtasRefused, match="close_account_not_writable"):
        _verify([*_budget(), readonly])
