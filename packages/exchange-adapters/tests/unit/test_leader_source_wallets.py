"""Copy-trade pilot (H-037): the wallet set handed to any leader source is validated, fail closed.

A wallet is interpolated into a NATS ``SUB`` line (``account_balance_change.<wallet>.*``), so anything
that is not a base58 public key — a ``*`` or ``>`` wildcard, a space, CRLF — must never reach it.
"""

from __future__ import annotations

import pytest

from hunter_exchanges.pumpfun.leader_source_wallets import MAX_WALLETS, validate_wallets
from hunter_exchanges.pumpfun.solana_codec import b58encode

pytestmark = pytest.mark.unit


def key(n: int) -> str:
    return b58encode(bytes([n]) * 32)


def test_valid_keys_pass_as_a_frozenset() -> None:
    assert validate_wallets([key(1), key(2), key(1)]) == frozenset({key(1), key(2)})


@pytest.mark.parametrize(
    "bad",
    [
        "*",
        ">",
        "WalletA",  # 'l' is not in the base58 alphabet
        key(1) + ".*",
        key(1) + "\r\nPUB x 1\r\n",
        key(1) + " 1\r\nSUB >",
        key(1)[:-1],  # 31 bytes
        key(1) + "11",  # 33 bytes
        "",
        "é" * 32,
        "1" * 5000,
    ],
)
def test_anything_that_is_not_exactly_a_32_byte_base58_key_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="wallet"):
        validate_wallets([key(1), bad])


def test_at_most_24_wallets_and_the_error_says_so() -> None:
    assert len(validate_wallets([key(n) for n in range(1, MAX_WALLETS + 1)])) == 24
    with pytest.raises(ValueError, match="at most 24"):
        validate_wallets([key(n) for n in range(1, MAX_WALLETS + 2)])


def test_an_empty_set_is_refused() -> None:
    with pytest.raises(ValueError, match="wallet"):
        validate_wallets([])


def test_the_error_never_echoes_the_offending_text() -> None:
    with pytest.raises(ValueError) as err:
        validate_wallets(["SECRET\r\nCRLF"])
    assert "SECRET" not in str(err.value)
