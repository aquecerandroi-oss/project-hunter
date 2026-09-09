"""The digest a slice of a replay is keyed on — ``hunter_core.domain.digests``.

Everything here is arithmetic over strings. The database half (the frozen SQL
expression, the backfill and the trigger that refuses a digest which does not
name its own markets) is proved against a real Postgres in
``packages/core/tests/integration/test_migrations.py``; what this file fixes is
the two properties the key *depends* on and that no CHECK can express:

1. **order-independence** — the digest is over the sorted list, so the order the
   markets happened to be dispatched in cannot fabricate a second receipt for
   work that already has one;
2. **no number ever reaches it** — the input is market keys, so no ``float`` and
   no ``Decimal`` can decide whether two slices are the same slice.

The failure this closes is measured, not hypothetical: ``.claude/state/notes-T3.62.md``
concern 1 — 32 replay runs, 8 receipts, because four market slices of one window
collided on a key that only named the window.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_core.domain.digests import (
    MARKETS_DIGEST_PATTERN,
    MARKETS_DIGEST_SEPARATOR,
    markets_digest,
)

pytestmark = pytest.mark.unit

FOUR = ("binance:ETHUSDT", "binance:SOLUSDT", "binance:XRPUSDT", "binance:DOGEUSDT")


def test_the_digest_is_a_lowercase_hex_sha256() -> None:
    """The shape the CHECK enforces, so ``'legacy'`` and ``''`` are not digests."""
    import re

    digest = markets_digest(FOUR)
    assert len(digest) == 64
    assert re.match(MARKETS_DIGEST_PATTERN, digest)


def test_the_order_the_markets_were_dispatched_in_does_not_change_it() -> None:
    """The property the slice key rests on.

    ``run.py`` builds ``markets`` in dispatch order, so a UNIQUE over the array
    itself would have made "the same four markets, dispatched the other way
    round" a second slice — a duplicate receipt for work already recorded.
    """
    assert markets_digest(reversed(FOUR)) == markets_digest(FOUR)
    assert markets_digest(sorted(FOUR)) == markets_digest(FOUR)
    assert markets_digest(list(FOUR[2:]) + list(FOUR[:2])) == markets_digest(FOUR)


def test_the_four_market_slices_of_one_window_are_four_digests() -> None:
    """The T3.62 case, in one assertion: four disjoint market sets, four keys."""
    slices = [
        ("binance:ETHUSDT", "binance:SOLUSDT", "binance:XRPUSDT", "binance:DOGEUSDT"),
        ("binance:BTCUSDT", "binance:BNBUSDT", "binance:ZECUSDT", "binance:SUIUSDT"),
        ("binance:NEARUSDT", "binance:UNIUSDT", "binance:ARBUSDT", "binance:TAOUSDT"),
        ("binance:LINKUSDT", "binance:DASHUSDT", "binance:PROMUSDT", "binance:SAHARAUSDT"),
    ]
    assert len({markets_digest(one) for one in slices}) == 4


def test_a_market_that_is_only_missing_changes_the_digest() -> None:
    """Three markets of a four-market slice is a different slice, not the same
    one measured worse — the distinction the old key could not make."""
    assert markets_digest(FOUR[:3]) != markets_digest(FOUR)


def test_the_separator_keeps_two_different_sets_apart() -> None:
    """Concatenation would make ``("a","bc")`` and ``("ab","c")`` one key."""
    assert markets_digest(["a", "bc"]) != markets_digest(["ab", "c"])
    assert MARKETS_DIGEST_SEPARATOR == "\n"


def test_the_same_market_twice_is_not_the_same_as_once() -> None:
    """No de-duplication, deliberately: the SQL side sorts the array as stored
    and would keep both members too, so the two halves of the digest agree on a
    list the writer should never produce instead of disagreeing about it."""
    assert markets_digest(["a", "a"]) != markets_digest(["a"])


def test_a_case_difference_is_a_different_market() -> None:
    """Byte order, never a locale's collation: the SQL side sorts ``COLLATE
    "C"`` for the same reason — a digest that depended on ``lc_collate`` would
    hash the same list differently on two clusters."""
    assert markets_digest(["binance:BTCUSDT"]) != markets_digest(["binance:btcusdt"])
    assert markets_digest(["A", "a", "B"]) == markets_digest(["a", "B", "A"])


def test_a_slice_that_visited_no_market_has_no_receipt_to_key() -> None:
    """The Python half of ``ck_replay_runs_a_slice_visited_a_market`` (§25.2):
    ``run.py`` already refuses the run before this (``no market matched the
    selection``), so this refuses the impossible rather than inventing a digest
    of the empty string."""
    with pytest.raises(ValueError, match="at least one market"):
        markets_digest([])


@pytest.mark.parametrize("value", [Decimal("1"), 1, 1.0, None, b"binance:BTCUSDT"])
def test_no_number_and_no_bytes_ever_reach_the_hash(value: object) -> None:
    """Decimal-free by refusal, not by convention.

    A UNIQUE key that depended on the ``repr`` of a ``Decimal`` — or on a
    ``float``, which the project bans from every money path — would be a key
    nobody could reproduce from the row. The digest takes market keys, which are
    ``<exchange>:<symbol>`` strings, and nothing else.
    """
    with pytest.raises(TypeError, match="market keys as str"):
        markets_digest([value])  # type: ignore[list-item]


def test_a_key_carrying_the_separator_is_refused_rather_than_made_ambiguous() -> None:
    """``<exchange>:<symbol>`` cannot contain a newline; if one ever did, the
    join would make two different sets share a digest. Declared limit: the SQL
    half cannot express this (a CHECK may not carry a subquery), so it would
    compute a digest for a value the only writer cannot produce."""
    with pytest.raises(ValueError, match="may not contain a newline"):
        markets_digest(["binance:BTCUSDT", "bad\nkey"])
