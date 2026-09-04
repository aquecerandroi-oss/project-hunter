"""Slug derivation, cursor encoding and invitation-token handling.

Small pure functions, but each one guards something real: a slug is a public
identifier, a cursor is client-supplied input, and an invitation token is a
bearer credential that must never be stored in a form it could be replayed
from.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

import pytest

from hunter_api.repositories.base import decode_cursor, encode_cursor
from hunter_api.services.invitations import hash_token, mint_token
from hunter_api.services.slugs import SLUG_PATTERN, derive_slug, suffixed_slug

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Acme Capital", "acme-capital"),
        ("  Acme   Capital  ", "acme-capital"),
        ("ACME", "acme"),
        ("Acme & Co.", "acme-co"),
        ("Ação Trading", "acao-trading"),
        ("hedge---fund", "hedge-fund"),
        ("-leading-and-trailing-", "leading-and-trailing"),
        ("123 Fund", "123-fund"),
    ],
)
def test_derive_slug_produces_the_documented_shape(name: str, expected: str) -> None:
    assert derive_slug(name) == expected
    assert re.match(SLUG_PATTERN, derive_slug(name))


@pytest.mark.parametrize("name", ["", "  ", "!!!", "ab", "é", "-", "🙂"])
def test_a_name_that_cannot_make_a_valid_slug_falls_back(name: str) -> None:
    # the column is UNIQUE NOT NULL and the pattern demands 3-40 chars; a
    # two-letter or emoji-only organization name still has to produce one
    slug = derive_slug(name)
    assert re.match(SLUG_PATTERN, slug)
    assert slug.startswith("org-")


def test_a_long_name_is_truncated_to_the_pattern_budget() -> None:
    slug = derive_slug("A" * 200)
    assert len(slug) == 40
    assert re.match(SLUG_PATTERN, slug)


def test_suffixed_slug_stays_within_the_pattern() -> None:
    base = derive_slug("A" * 200)
    for _ in range(5):
        candidate = suffixed_slug(base)
        assert re.match(SLUG_PATTERN, candidate), candidate
        assert candidate != base


def test_cursor_round_trips() -> None:
    moment = datetime(2026, 9, 4, 12, 30, 45, 123456, tzinfo=UTC)
    row_id = uuid.uuid4()

    decoded = decode_cursor(encode_cursor(moment, row_id))

    assert decoded == (moment, row_id)


@pytest.mark.parametrize(
    "cursor",
    ["", "not-base64!!", "YWJj", "MjAyNi0wOS0wNHxub3QtYS11dWlk", "|" * 10, "x" * 500],
)
def test_a_malformed_cursor_is_rejected_not_ignored(cursor: str) -> None:
    # silently ignoring a bad cursor would restart the page at the top and
    # look like data loss to the client; a 422 says what happened
    from hunter_api.repositories.base import InvalidCursorError

    with pytest.raises(InvalidCursorError):
        decode_cursor(cursor)


def test_decode_cursor_passes_none_through() -> None:
    assert decode_cursor(None) is None


def test_mint_token_is_unguessable_and_never_stored_in_the_clear() -> None:
    token, token_hash = mint_token()

    assert len(token) >= 40
    assert token != token_hash
    assert hash_token(token) == token_hash
    assert len(token_hash) == 64
    assert token not in token_hash


def test_two_mints_never_collide() -> None:
    tokens = {mint_token()[0] for _ in range(50)}
    assert len(tokens) == 50


def test_hash_token_is_stable_and_case_sensitive() -> None:
    token, _ = mint_token()
    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != hash_token(token.upper() + "x")
