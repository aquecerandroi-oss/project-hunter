"""``hunter_indicators.meme.event_match`` — the symbol/name/handle/avoid rule
(T4.26b), pure and unit-tested without a database."""

from __future__ import annotations

import pytest

from hunter_indicators.meme.event_match import (
    MATCH_AVOID,
    MATCH_BUY,
    event_hints,
    event_match_kind,
    is_match,
)

pytestmark = pytest.mark.unit


def test_symbol_matches_case_insensitively_and_strips_the_dollar_sign() -> None:
    hints = event_hints(symbol_hint="$arc", handle_hint=None, notes=None)
    assert is_match(hints, symbol="ARC", name=None, twitter=None)
    assert is_match(hints, symbol="$Arc", name=None, twitter=None)
    assert not is_match(hints, symbol="ARCH", name=None, twitter=None)


def test_notes_tickers_add_to_symbol_hint_not_replace_it() -> None:
    hints = event_hints(
        symbol_hint="ARC", handle_hint=None, notes={"tickers": ["ARCH", "$ARCC", "USDC"]}
    )
    assert hints.tickers == {"ARC", "ARCH", "ARCC", "USDC"}
    assert is_match(hints, symbol="usdc", name=None, twitter=None)


def test_name_matches_a_keyword_with_a_word_boundary() -> None:
    hints = event_hints(symbol_hint="ARC", handle_hint=None, notes={"keywords": ["circle"]})
    assert is_match(hints, symbol=None, name="Circle Mainnet Coin", twitter=None)
    assert not is_match(hints, symbol=None, name="Encircled Token", twitter=None)


def test_name_matches_a_ticker_with_a_word_boundary_never_a_substring() -> None:
    """The brief's own example: ``ARC`` must not match "march"."""
    hints = event_hints(symbol_hint="ARC", handle_hint=None, notes=None)
    assert not is_match(hints, symbol=None, name="March Madness Coin", twitter=None)
    assert is_match(hints, symbol=None, name="The ARC Protocol", twitter=None)


def test_twitter_handle_matches_the_announcer_not_a_lookalike() -> None:
    hints = event_hints(symbol_hint=None, handle_hint="@CoachPatNFT", notes=None)
    assert is_match(hints, symbol=None, name=None, twitter="x.com/CoachPatNFT/status/123")
    assert is_match(hints, symbol=None, name=None, twitter="x.com/coachpatnft")
    assert not is_match(hints, symbol=None, name=None, twitter="x.com/NotCoachPatNFT")


def test_no_hints_at_all_never_matches() -> None:
    hints = event_hints(symbol_hint=None, handle_hint=None, notes=None)
    assert not is_match(hints, symbol="ARC", name="Arc Coin", twitter="x.com/arc")


@pytest.mark.parametrize(
    ("notes", "expected"),
    [
        (None, MATCH_BUY),
        ({}, MATCH_BUY),
        ({"action": "buy"}, MATCH_BUY),
        ({"action": "avoid"}, MATCH_AVOID),
    ],
)
def test_event_match_kind_reads_the_notes_action(
    notes: dict[str, object] | None, expected: str
) -> None:
    assert event_match_kind(notes) == expected
