"""There is no deposit and there is no reset — asserted against the source.

Directive §1: "Não fazer aportes nem resetar a carteira para apagar prejuízos."
The schema already refuses the crude versions (the anchor is immutable, an
anchored wallet's ``initial_capital`` is frozen, a principal paper wallet is one
per workspace for ever). What the schema cannot refuse is a *second code path*
that credits a wallet — an admin route, a fixture helper promoted to production,
a "recapitalise" service — because from Postgres' point of view that is just the
first opening happening again in another organization.

So this file reads the AST of **every Python module the repository ships** —
``packages/``, ``apps/`` and ``services/``, not just ``hunter_core`` — and
asserts four things:

1. the anchor and the wallet row are only ever created by
   :func:`hunter_core.portfolio.opening.open_paper_wallet`, whether the call is
   written as an attribute (``repo.create_anchor(...)``) or through a bare name
   an alias bound earlier;
2. ``initial_capital`` is only ever named where the opening computes it and
   where the wallet's own insert writes it — never a third place, and never as
   an assignment to an existing object;
3. nothing in the package's public surface is named like a deposit or a reset;
4. the package exports exactly one way to open a wallet.

It is a **verification, not the guarantee** — the guarantee is the single write
path plus the schema (M3 joint decision, item 4, "a varredura de código é
verificação auxiliar"). Astra's review of this diff listed what a scan like this
still misses (SQL written as text, a helper in a module nobody imports); the
answer to those is the database's own triggers and the behavioural tests in
``tests/integration/test_portfolio_opening.py``, not a cleverer parser.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import hunter_core

pytestmark = pytest.mark.unit

PACKAGE_ROOT = Path(hunter_core.__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[2]
SCANNED_ROOTS = ("packages", "apps", "services")
SKIP_PARTS = frozenset({".venv", "node_modules", "__pycache__", "tests", "migrations"})

CREDITING_CALLS = frozenset({"create_anchor", "create_wallet"})
"""The two writes that bring a funded wallet into existence."""

OPENING_MODULE = "packages/core/hunter_core/portfolio/opening.py"
DEFINING_MODULE = "packages/core/hunter_core/db/repositories/portfolio.py"

FORBIDDEN_NAMES = ("deposit", "top_up", "topup", "fund_wallet", "recapitalis", "reset_wallet")


def _modules() -> list[tuple[str, ast.Module]]:
    found: list[tuple[str, ast.Module]] = []
    for root in SCANNED_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            if SKIP_PARTS.intersection(path.parts):
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            found.append((relative, ast.parse(path.read_text(encoding="utf-8"))))
    return found


def _called_names(node: ast.AST) -> str | None:
    """The name a call uses, whether it is ``a.b()``, ``b()`` or an alias of ``b``."""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        if isinstance(node.func, ast.Name):
            return node.func.id
    return None


def test_the_scan_really_reaches_the_whole_repository() -> None:
    """A scan that silently found nothing would pass every assertion below."""
    scanned = {relative for relative, _ in _modules()}
    assert OPENING_MODULE in scanned
    assert DEFINING_MODULE in scanned
    assert any(relative.startswith("apps/api/") for relative in scanned)
    assert any(relative.startswith("services/") for relative in scanned)


def test_only_the_opening_calls_the_two_crediting_writes() -> None:
    callers: dict[str, set[str]] = {}
    for relative, tree in _modules():
        if relative == DEFINING_MODULE:
            continue  # where they are defined, not where they are used
        for node in ast.walk(tree):
            name = _called_names(node)
            if name in CREDITING_CALLS:
                callers.setdefault(name, set()).add(relative)
    assert callers == {name: {OPENING_MODULE} for name in CREDITING_CALLS}, (
        f"a wallet may only be created and anchored by {OPENING_MODULE}; found {callers}"
    )


def test_no_module_binds_a_crediting_write_to_another_name() -> None:
    """``writer = repo.create_wallet`` would defeat the call scan above."""
    aliases = {
        relative
        for relative, tree in _modules()
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in CREDITING_CALLS
        # an attribute that is *not* the callee of a call is a reference to the
        # bound method, i.e. an alias
        and not any(
            isinstance(parent, ast.Call) and parent.func is node for parent in ast.walk(tree)
        )
    }
    assert aliases == set(), f"a crediting write was aliased in {sorted(aliases)}"


def test_initial_capital_is_only_ever_written_where_the_wallet_is_created() -> None:
    writers = {
        relative
        for relative, tree in _modules()
        for node in ast.walk(tree)
        if (isinstance(node, ast.keyword) and node.arg == "initial_capital")
        or (isinstance(node, ast.Attribute) and node.attr == "initial_capital")
    }
    assert writers == {DEFINING_MODULE, OPENING_MODULE}, (
        "the opening capital is named exactly twice: where the opening computes it and "
        f"where the wallet's insert writes it; found {sorted(writers)}"
    )


def test_no_public_name_in_the_package_offers_a_deposit_or_a_reset() -> None:
    import hunter_core.portfolio as portfolio

    offenders = [
        name
        for name in dir(portfolio)
        if not name.startswith("_") and any(bad in name.lower() for bad in FORBIDDEN_NAMES)
    ]
    assert offenders == [], f"there is no aporte and no reset; found {offenders}"


def test_no_module_anywhere_defines_a_deposit_or_a_reset() -> None:
    """``dir()`` only sees what the package re-exports; this sees definitions."""
    offenders = {
        f"{relative}:{node.name}"
        for relative, tree in _modules()
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(bad in node.name.lower() for bad in FORBIDDEN_NAMES)
    }
    assert offenders == set(), f"there is no aporte and no reset; found {sorted(offenders)}"


def test_the_package_exports_exactly_one_way_to_open_a_wallet() -> None:
    import hunter_core.portfolio as portfolio

    assert "open_paper_wallet" in portfolio.__all__
    assert sum(1 for name in portfolio.__all__ if name.startswith("open_")) == 1
