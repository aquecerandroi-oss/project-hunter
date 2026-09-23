"""Regression test for the apostrophe bug in the §17.7 downgrade guards.

``infra/migrations/ddl/meme_refused_probe_arm.py``'s ``_GUARDED`` carries a
``why`` text with an apostrophe ("EXP-M23's inclusion probabilities"). Every
guard interpolates ``why`` straight into a single-quoted SQL string literal
(``MESSAGE = '... - {why}'``); an unescaped apostrophe there closes the
literal early and Postgres then misreads whatever follows — in production
this surfaced as ``trailing junk after numeric literal`` on the UUID that
came next in the statement, not as anything naming the actual mistake.

These assertions need no database: they call the guard functions with
``alembic.op.execute`` monkeypatched to a recorder, and check the SQL text
each one would have sent. A single-quote count that is odd is proof enough
that some literal was left open — exactly what an un-escaped apostrophe does
and what a correctly doubled one (``''``) does not; an even count alone is
not sufficient (two unescaped apostrophes would also come out even), which is
why the tests also assert the exact escaped message text, not just parity.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"


def _ddl(monkeypatch: pytest.MonkeyPatch, name: str) -> ModuleType:
    """Import ``infra/migrations/ddl/<name>.py`` by path, the same way
    ``test_market_events.py`` and ``tests/integration/conftest.py`` do —
    ``infra/migrations`` is not a uv workspace member. ``syspath_prepend``
    undoes itself when the test ends, so this file leaves no path behind for
    whatever test happens to run next (Astra's review, 23/09/2026)."""
    if str(MIGRATIONS_DIR) not in sys.path:
        monkeypatch.syspath_prepend(str(MIGRATIONS_DIR))
    return importlib.import_module(f"ddl.{name}")


def _recorded_statements(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> list[str]:
    statements: list[str] = []
    monkeypatch.setattr(module.op, "execute", statements.append)
    return statements


def _assert_even_apostrophe_count(statements: list[str]) -> None:
    """A necessary, not sufficient, check: an odd count proves a literal was
    left open (the unescaped-apostrophe bug), but an even count alone does not
    prove every literal closes in the right place — two unescaped apostrophes
    in the same ``why`` would also come out even. The tests below pair this
    with an explicit assertion on the escaped text for that reason."""
    assert statements, "the guard must have executed at least one statement"
    for sql in statements:
        assert sql.count("'") % 2 == 0, (
            "an odd number of apostrophes means a string literal was left open — "
            f"the exact failure mode of the unescaped-apostrophe bug:\n{sql}"
        )


class TestOperatorSixRefuseHelper:
    """``meme_operator_6._refuse`` is the shared helper three later arms copied
    verbatim (``meme_refused_probe_arm`` and ``meme_gate_absorb_arm`` inline
    the same shape); it is the most direct place to prove the escaping."""

    def test_a_why_with_an_apostrophe_still_balances_its_quotes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _ddl(monkeypatch, "meme_operator_6")
        statements = _recorded_statements(monkeypatch, module)
        module._refuse(
            "meme_proposals",
            "WHERE rule_set_id = '01994d00-6c1a-7000-8000-000000000019'",
            "proposals reference the seeded operator/6 set - they carry EXP-M23's "
            "inclusion probabilities and cannot be removed under them",
        )
        _assert_even_apostrophe_count(statements)
        assert "EXP-M23''s inclusion probabilities" in statements[0], (
            "the apostrophe must survive, doubled, inside the MESSAGE literal"
        )
        assert "EXP-M23's inclusion probabilities" not in statements[0], (
            "a single, unescaped apostrophe here is exactly what broke Postgres's parser"
        )

    def test_two_apostrophes_in_one_why_both_double_not_just_parity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Astra's review (23/09/2026): an even quote count alone would also
        pass if two apostrophes were left unescaped side by side. Assert the
        exact escaped message text, not just that the total is even."""
        module = _ddl(monkeypatch, "meme_operator_6")
        statements = _recorded_statements(monkeypatch, module)
        module._refuse(
            "meme_proposals",
            "WHERE rule_set_id = '01994d00-6c1a-7000-8000-000000000019'",
            "the desk's own operator's row can't be dropped",
        )
        _assert_even_apostrophe_count(statements)
        assert (
            "MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_proposals rows exist - "
            "the desk''s own operator''s row can''t be dropped', " in statements[0]
        )


class TestRefusedProbeArmGuard:
    """``meme_refused_probe_arm``'s own ``_GUARDED`` carries the real apostrophe
    text this bug report is about — exercised end to end, no synthetic input."""

    def test_the_guard_escapes_its_own_apostrophe_containing_why(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _ddl(monkeypatch, "meme_refused_probe_arm")
        statements = _recorded_statements(monkeypatch, module)
        module.refuse_a_downgrade_that_would_orphan_a_probe_row()
        _assert_even_apostrophe_count(statements)
        proposals_sql = next(sql for sql in statements if "meme_proposals" in sql)
        assert "EXP-M23''s inclusion probabilities" in proposals_sql
        assert "EXP-M23's inclusion probabilities" not in proposals_sql


class TestGateAbsorbArmGuard:
    """No ``why`` in ``meme_gate_absorb_arm`` carries an apostrophe today, but
    the same inline pattern must still escape one if it ever does — the guard
    is data-driven from ``_GUARDED`` and cannot special-case a future text."""

    def test_the_guard_would_still_balance_an_apostrophe_containing_why(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _ddl(monkeypatch, "meme_gate_absorb_arm")
        statements = _recorded_statements(monkeypatch, module)
        original_guarded = module._GUARDED
        monkeypatch.setattr(
            module,
            "_GUARDED",
            original_guarded
            + (("meme_paper_bets", "a synthetic why with an apostrophe, like EXP-M23's"),),
        )
        module.refuse_a_downgrade_that_would_orphan_an_absorb_row()
        _assert_even_apostrophe_count(statements)
        synthetic_sql = statements[-1]
        assert "EXP-M23''s" in synthetic_sql
        assert "EXP-M23's" not in synthetic_sql
