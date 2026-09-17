"""A create frame whose identity carries a NUL byte becomes a row PostgreSQL accepts.

Production, 17/09/2026 00:11:48Z: pump.fun's trenches stream emitted a ``create``
named ``"spaceX链游\\x00"``; ``text`` refuses ``\\x00``
(``CharacterNotInRepertoireError``), the stream retried the same frame six
times in 53 s and the whole worker died — its 18th restart, 1 m 26 s blind.
``TokenRow`` now strips the byte at construction, for every text field and for
every one of its six producers (T4.47).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hunter_meme_worker.repo_rows import NUL, TokenRow, clean_text

pytestmark = pytest.mark.unit

_AT = datetime(2026, 9, 17, 0, 11, 48, tzinfo=UTC)


def _row(**identity: str | None) -> TokenRow:
    return TokenRow(
        mint="71CeThH29G5SuXy6BrRP2RAeTULJdV8VUshFit9vpump",
        first_seen_source="trenches_ws",
        first_seen_at=_AT,
        last_seen_at=_AT,
        **identity,
    )


def test_the_production_frame_loses_only_the_nul() -> None:
    row = _row(name="spaceX链游" + NUL, symbol="SpaceX-Wor")
    assert row.name == "spaceX链游"
    assert row.symbol == "SpaceX-Wor"
    assert not any(NUL in v for v in (row.name, row.symbol, row.mint, row.first_seen_source))


def test_a_nul_only_identity_is_not_observed() -> None:
    row = _row(description=NUL * 3, uri=NUL)
    assert row.description is None
    assert row.uri is None


def test_a_clean_row_is_untouched() -> None:
    row = _row(name="TAXCOIN", symbol="TAX", uri="https://ipfs.io/ipfs/x")
    assert (row.name, row.symbol, row.uri) == ("TAXCOIN", "TAX", "https://ipfs.io/ipfs/x")


def test_a_required_text_field_never_becomes_null() -> None:
    row = TokenRow(mint=NUL, first_seen_source="trenches_ws", first_seen_at=_AT, last_seen_at=_AT)
    assert row.mint == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("", ""), ("abc", "abc"), ("a" + NUL + "b", "ab"), (NUL, None)],
)
def test_clean_text(value: str | None, expected: str | None) -> None:
    assert clean_text(value) == expected
