"""``repositories/meme_cursor.py`` — pure encode/decode, no DB (T4.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_api.repositories.meme_cursor import (
    InvalidMemeCursorError,
    decode_token_cursor,
    encode_token_cursor,
)

pytestmark = pytest.mark.unit


def test_roundtrip_decimal_sort_value() -> None:
    cursor = encode_token_cursor("mcap", Decimal("12.5"), "MintABC")
    value, mint = decode_token_cursor(cursor) or (None, "")
    assert value == Decimal("12.5")
    assert mint == "MintABC"


def test_roundtrip_datetime_sort_value() -> None:
    when = datetime(2026, 9, 12, 3, 0, tzinfo=UTC)
    cursor = encode_token_cursor("age", when, "MintXYZ")
    value, mint = decode_token_cursor(cursor) or (None, "")
    assert value == when
    assert mint == "MintXYZ"


def test_roundtrip_null_sort_value() -> None:
    """A mint with no curve snapshot yet sorts last — ``None`` must survive
    the round trip, distinct from ``Decimal(0)`` (T4-MEME-RADAR.md's
    null-never-zero rule applies to pagination state too)."""
    cursor = encode_token_cursor("progress", None, "MintNoSnap")
    value, mint = decode_token_cursor(cursor) or ("sentinel", "")
    assert value is None
    assert mint == "MintNoSnap"


def test_decode_none_is_none() -> None:
    assert decode_token_cursor(None) is None


def test_decode_rejects_unknown_sort_column() -> None:
    import base64

    bogus = base64.urlsafe_b64encode(b"not-a-real-sort|1|M").decode()
    with pytest.raises(InvalidMemeCursorError):
        decode_token_cursor(bogus)


def test_decode_rejects_garbage() -> None:
    with pytest.raises(InvalidMemeCursorError):
        decode_token_cursor("not-valid-base64!!!")


def test_decode_rejects_oversized_cursor() -> None:
    with pytest.raises(InvalidMemeCursorError):
        decode_token_cursor("a" * 200)


def test_decode_rejects_empty_mint() -> None:
    with pytest.raises(InvalidMemeCursorError):
        decode_token_cursor(encode_token_cursor("mcap", Decimal("1"), ""))
