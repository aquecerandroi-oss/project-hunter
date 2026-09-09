"""A fifth connection that forgets ``SET LOCAL ROLE`` fails CI here.

Since ``0015_runtime_login_role`` (T3.15f, ``docs/DATABASE.md`` §27) the runtime
login is ``hunter_runtime``: ``NOINHERIT``, member of ``hunter_app`` and
``hunter_worker`` and holder of **no privilege of its own**. A transaction that
skips ``SET LOCAL ROLE`` therefore reaches no table at all — it fails with
*permission denied* instead of quietly running with the union of both roles
(§27.1, item 1). That is the property the revision bought, and it turns every
raw ``engine.begin()`` / ``engine.connect()`` in a runtime process into an
outage waiting for step (d) of the runbook.

**Why a lint test and not a behavioural one** (security review of T3.15f,
MEDIUM 4): every conftest in this repository still connects as the schema
*owner*, so a new code path that forgets the role passes the whole suite and
fails in production after the credential swap. ``test_runtime_login_role.py``
proves the *role*; it cannot prove the *call sites*. The four scanner
connections that the T3.15f sweep found were found by a human running ``grep``,
once — and a sweep that happened once is not a guarantee.

The sanctioned way to open a transaction in a runtime process is
:func:`hunter_core.db.session.role_session` (or its wrappers ``tenant_session``,
``user_session``, ``bootstrap_session``), which issues ``SET LOCAL ROLE`` and
the ``statement_timeout`` before any query of the application (§1.2a). Anything
else is listed below, by file, with a reason and a count — and the count is
exact in both directions, so this test fails when a *fifth* raw connection
appears **and** when an allowlisted one is fixed and the entry is left to rot.

Scope, declared: this reads source text, so it sees a raw connection written in
Python and nothing else. SQL executed through a helper this file does not know
about, or a connection handed in from outside, is not visible here — the answer
to those is the database itself (the ``permission denied`` that §27.1 buys),
not a cleverer parser. Same limit and same reason as
``tests/unit/portfolio/test_no_funding_route.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import hunter_core

pytestmark = pytest.mark.unit

REPO_ROOT = Path(hunter_core.__file__).resolve().parents[3]
SKIP_PARTS = frozenset({".venv", "node_modules", "__pycache__", "tests"})

RAW_CONNECTION = re.compile(r"(?:^|[^\w.])([\w.]*[eE]ngine)\.(begin|connect)\s*\(")
"""``engine.begin(``, ``runtime.engine.connect(``, ``self._engine.begin(`` …

The receiver has to *end* in ``engine`` so that ``connection.begin()`` (a nested
transaction on a connection whose role is already set) is not swept up with it.
"""

SCANNER = "services/scanner-worker/hunter_scanner_worker"

ALLOWED: dict[str, tuple[int, str]] = {
    f"{SCANNER}/main.py": (
        1,
        "TODO(T3.15g, owner of services/**): `_warm` opens a bare transaction and "
        "reads `feature_baselines` through `cache.refresh`. Under `hunter_runtime` "
        "this is *permission denied for table feature_baselines*. The fix is one "
        "line — `SET LOCAL ROLE hunter_worker` as the transaction's first "
        "statement — and it is a **prerequisite of step (d)** of the runbook "
        "(docs/DATABASE.md §27.5, docs/DEPLOYMENT.md §3.5).",
    ),
    f"{SCANNER}/refresh.py": (
        3,
        "TODO(T3.15g, owner of services/**): three bare transactions read "
        "`feature_snapshots` and **write** `feature_baselines` "
        "(`SqlBaselineStore.append`). Same one-line fix, same prerequisite "
        "(docs/DATABASE.md §27.5).",
    ),
    "services/strategy-worker/hunter_strategy_worker/activation_db.py": (
        1,
        "Not a runtime connection: this engine is built from "
        "`DATABASE_URL_MIGRATIONS` (`migration_url()`), i.e. the owner DSN that "
        "only `migrate` and the `ops` service carry (docs/DATABASE.md §23.5). It "
        "is an ops script path — activation is written by the owner on purpose "
        "(§23.2) — and it is out of reach of `hunter_runtime` by construction.",
    ),
}
"""Every raw connection a runtime package is allowed to open, and why.

Four of the five are the scanner's, and they are debt with a name on it, not a
pattern to copy. The fifth is the owner DSN, which is a different credential
entirely.
"""


def _scanned_files() -> list[Path]:
    roots = [REPO_ROOT / "apps" / "api" / "hunter_api"]
    roots += sorted(
        package
        for service in (REPO_ROOT / "services").iterdir()
        if service.is_dir()
        for package in service.iterdir()
        if package.is_dir() and package.name.startswith("hunter_")
    )
    return sorted(
        path
        for root in roots
        if root.is_dir()
        for path in root.rglob("*.py")
        if not SKIP_PARTS.intersection(path.parts)
    )


def _raw_connections() -> dict[str, list[int]]:
    """``{relative path: [line numbers]}`` for every raw connection found."""
    found: dict[str, list[int]] = {}
    for path in _scanned_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if RAW_CONNECTION.search(line):
                found.setdefault(relative, []).append(number)
    return found


def test_the_scan_really_reaches_the_runtime_packages() -> None:
    """A scan that silently found nothing would pass every assertion below."""
    scanned = {path.relative_to(REPO_ROOT).as_posix() for path in _scanned_files()}
    assert any(relative.startswith("apps/api/hunter_api/") for relative in scanned)
    assert any(relative.startswith("services/scanner-worker/") for relative in scanned)
    assert any(relative.startswith("services/execution-worker/") for relative in scanned)
    assert f"{SCANNER}/refresh.py" in scanned


def test_the_regex_recognises_a_raw_connection_and_leaves_the_rest_alone() -> None:
    """The guard is a regex; a regex that matched nothing would also be green."""
    assert RAW_CONNECTION.search("    async with engine.begin() as connection:")
    assert RAW_CONNECTION.search("    async with runtime.engine.begin() as connection:")
    assert RAW_CONNECTION.search("async with engine.connect() as conn, conn.begin():")
    assert RAW_CONNECTION.search("self._engine.connect()")
    # a transaction on a connection whose role the helper already set
    assert not RAW_CONNECTION.search("    async with connection.begin():")
    assert not RAW_CONNECTION.search("    async with session.begin():")


def test_no_runtime_package_opens_a_connection_the_session_helpers_do_not_own() -> None:
    """The whole point: a *fifth* raw connection is a CI failure, not a grep.

    A new one is almost never wanted. If it genuinely is — an ops path on the
    owner DSN, say — it comes here with a file, a count and a sentence saying
    which role its first statement sets, in the same review that adds it.
    """
    found = _raw_connections()
    unexpected = {relative: lines for relative, lines in found.items() if relative not in ALLOWED}
    assert unexpected == {}, (
        "a runtime process opened a transaction outside hunter_core.db.session's "
        "helpers; under `hunter_runtime` (NOINHERIT) it reaches no table without a "
        f"`SET LOCAL ROLE` first statement (docs/DATABASE.md §27.1): {unexpected}"
    )


@pytest.mark.parametrize("relative", sorted(ALLOWED))
def test_each_allowlisted_file_still_has_exactly_the_raw_connections_it_declares(
    relative: str,
) -> None:
    """Exact, in both directions — an entry that outlived its debt is a lie.

    When the scanner's four sites are fixed (whether by adding ``SET LOCAL ROLE``
    through the helper or by dropping the raw transaction), this fails with the
    count it found, and removing the entry is the last step of that fix.
    """
    expected, reason = ALLOWED[relative]
    lines = _raw_connections().get(relative, [])
    assert len(lines) == expected, (
        f"{relative} declares {expected} sanctioned raw connection(s) and has "
        f"{len(lines)} (lines {lines}). If they were fixed, drop or lower the "
        f"allowlist entry; if one was added, it needs its own reason. Entry: {reason}"
    )
