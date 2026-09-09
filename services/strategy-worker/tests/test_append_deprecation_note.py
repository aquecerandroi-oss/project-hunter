"""``append_deprecation_note`` — T3.47c (found by T3.47b, CONCERN 3).

``deprecate()`` and ``supersede()`` (retiring the row it replaces) used to set
``changelog = :verdict`` outright, which silently erased a derived variant's
lineage prefix (``derive_variant.py``'s ``derived_from=v<n> | overrides=...``,
the only column ``infra/scripts/obsidian_strategy_pages.py``'s
``parse_parent_version`` reads it from). Pure function, no database — the SQL
callers only ever pass its return value through, never build the string
themselves.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hunter_strategy_worker.activation_db import append_deprecation_note

pytestmark = pytest.mark.unit

_WHEN = datetime(2026, 9, 9, 3, 31, 58, tzinfo=UTC)


def test_it_appends_a_dated_line_after_an_existing_changelog() -> None:
    existing = (
        "variante de v6 | derived_from=v6 | overrides=stop_atr=2.25 "
        "| params_hash=5e456ae9eb5b | T3.26: piso de custo"
    )
    result = append_deprecation_note(existing, "K1: descartar", now=_WHEN)
    assert result == existing + "\n[deprecated 2026-09-09T03:31:58+00:00] K1: descartar"


def test_the_existing_changelog_survives_byte_for_byte() -> None:
    """The lineage prefix a variant is born with (T3.47b's exact case) is never
    truncated, reordered or reformatted — only appended to."""
    lineage = (
        "variante de v3 | derived_from=v3 | overrides=stop_atr=1.5,target_atr=2.25 "
        "| params_hash=1b868c55ebed | operator note with | a pipe in it"
    )
    result = append_deprecation_note(lineage, "verdict text", now=_WHEN)
    assert result.startswith(lineage)
    assert lineage in result


def test_a_missing_changelog_still_produces_a_dated_line() -> None:
    """A row with no prior ``changelog`` (``NULL``) is not a crash — the note
    stands on its own, still tagged and dated the same way."""
    result = append_deprecation_note(None, "first note ever", now=_WHEN)
    assert result == "\n[deprecated 2026-09-09T03:31:58+00:00] first note ever"


def test_an_empty_string_changelog_behaves_like_none() -> None:
    result = append_deprecation_note("", "note", now=_WHEN)
    assert result == append_deprecation_note(None, "note", now=_WHEN)


def test_the_new_note_text_is_never_mutated() -> None:
    """Whatever the operator wrote for this deprecation appears verbatim after
    the tag — no trimming, no escaping."""
    note = "  spaced note with trailing punctuation!  "
    result = append_deprecation_note("prior", note, now=_WHEN)
    assert result.endswith(note)


def test_it_defaults_to_the_real_current_time_when_now_is_not_given() -> None:
    """The production call sites never pass ``now=``; the default must be a
    timezone-aware UTC instant, not a naive one a careless caller could compare
    against a naive value without Python raising."""
    before = datetime.now(UTC)
    result = append_deprecation_note("prior", "note")
    after = datetime.now(UTC)
    tag_start = result.index("[deprecated ") + len("[deprecated ")
    tag_end = result.index("]", tag_start)
    stamped = datetime.fromisoformat(result[tag_start:tag_end])
    assert stamped.tzinfo is not None
    assert before <= stamped <= after
