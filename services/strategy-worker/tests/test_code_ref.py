"""The per-version code digest — MUST-FIX 1 of the risk-engine-guardian review.

The tree-wide digest made every activated version hostage to every other file
under ``hunter_core/strategies``: adding ``momentum_v2.py``, or a comment in a
module the version never imports, changed the digest, ``load_active_versions``
skipped every frozen version and the Lab died silently behind a green
``/ready``.

What a version's ``code_ref`` must cover is exactly the code that produced its
decisions: its own module plus the transitive closure of the sibling modules it
actually imports, derived from the imports themselves and never from a
hand-written list that could drift.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hunter_core.strategies.registry import DEFAULT_REGISTRY
from hunter_strategy_worker.code_ref import (
    CODE_REF_RE,
    STRATEGIES_DIR,
    UnsupportedImport,
    code_ref_module,
    module_closure,
    strategy_module,
    version_code_ref,
)

pytestmark = pytest.mark.unit


def _tree(tmp_path: Path) -> None:
    """A miniature ``hunter_core.strategies`` with two independent versions."""
    (tmp_path / "numeric.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "base.py").write_text(
        "from hunter_core.strategies.numeric import X\n", encoding="utf-8"
    )
    (tmp_path / "alpha_v1.py").write_text(
        "from hunter_core.strategies.base import X\n", encoding="utf-8"
    )
    (tmp_path / "beta_v1.py").write_text(
        "from hunter_core.strategies.numeric import X\n", encoding="utf-8"
    )


class TestClosure:
    def test_it_is_the_modules_the_version_really_imports(self) -> None:
        """momentum_v1 imports base/aggregate/indicators/envelope/numeric/schema,
        and base pulls canonical in. Nothing else is part of its code."""
        assert module_closure("momentum_v1", STRATEGIES_DIR) == (
            "aggregate",
            "base",
            "canonical",
            "envelope",
            "indicators",
            "momentum_v1",
            "numeric",
            "schema",
        )

    def test_a_sibling_strategy_and_the_registry_are_not_in_it(self) -> None:
        closure = module_closure("momentum_v1", STRATEGIES_DIR)
        assert "volume_anomaly_v1" not in closure
        assert "registry" not in closure
        assert "__init__" not in closure

    def test_an_unknown_module_is_refused_instead_of_hashing_nothing(self) -> None:
        with pytest.raises(FileNotFoundError):
            module_closure("no_such_module", STRATEGIES_DIR)


class TestDigest:
    def test_the_format_names_the_module_and_the_digest(self) -> None:
        ref = version_code_ref("momentum_v1")
        assert CODE_REF_RE.fullmatch(ref), ref
        assert ref.startswith("hunter_core.strategies.momentum_v1@sha256:")
        assert code_ref_module(ref) == "momentum_v1"

    def test_it_is_stable_for_unchanged_code(self) -> None:
        assert version_code_ref("momentum_v1") == version_code_ref("momentum_v1")

    def test_two_versions_of_the_same_tree_have_different_digests(self) -> None:
        assert version_code_ref("momentum_v1") != version_code_ref("volume_anomaly_v1")

    def test_a_new_module_does_not_change_an_existing_version(self, tmp_path: Path) -> None:
        """The reproduced regression: dropping ``momentum_v2.py`` into the tree
        must not invalidate the frozen digest of a version that never imports it."""
        _tree(tmp_path)
        before = version_code_ref("alpha_v1", tmp_path)
        (tmp_path / "gamma_v2.py").write_text(
            "from hunter_core.strategies.base import X\n", encoding="utf-8"
        )
        assert version_code_ref("alpha_v1", tmp_path) == before

    def test_a_comment_in_an_unimported_module_does_not_change_it(self, tmp_path: Path) -> None:
        _tree(tmp_path)
        before = version_code_ref("alpha_v1", tmp_path)
        (tmp_path / "beta_v1.py").write_text(
            "# a comment alpha_v1 never reads\nfrom hunter_core.strategies.numeric import X\n",
            encoding="utf-8",
        )
        assert version_code_ref("alpha_v1", tmp_path) == before

    def test_a_comment_in_an_imported_module_does_change_it(self, tmp_path: Path) -> None:
        """The other half: the digest is worthless if it misses a real edit."""
        _tree(tmp_path)
        before = version_code_ref("alpha_v1", tmp_path)
        (tmp_path / "numeric.py").write_text("# edited\nX = 1\n", encoding="utf-8")
        assert version_code_ref("alpha_v1", tmp_path) != before

    def test_moving_a_module_changes_it(self, tmp_path: Path) -> None:
        _tree(tmp_path)
        before = version_code_ref("alpha_v1", tmp_path)
        (tmp_path / "alpha_v1.py").write_text(
            "from hunter_core.strategies.renamed import X\n", encoding="utf-8"
        )
        (tmp_path / "base.py").rename(tmp_path / "renamed.py")
        assert version_code_ref("alpha_v1", tmp_path) != before


def _force_lf(path: Path) -> None:
    """Rewrite ``path`` with literal ``\\n`` bytes on disk.

    ``Path.write_text`` translates ``\\n`` to the platform's newline on write
    (that is how ``_tree`` above already wrote CRLF on a Windows test box) —
    so a test that reads back the raw bytes needs a known, platform-independent
    baseline before it rewrites them to CRLF/CR itself.
    """
    path.write_bytes(path.read_text(encoding="utf-8").encode("utf-8"))


class TestLineEndingNormalization:
    """A Windows checkout writes ``\\r\\n``; the VPS (Linux) writes ``\\n``. The
    tree-wide digest hashed raw bytes, so the same commit froze two different
    ``code_ref`` values depending on which OS activated it, and the side that
    did not activate refused the version as ``shadow_version_code_ref_mismatch``
    (Sexta-feira, VPS bug report). The digest now normalizes line endings
    before hashing so both checkouts agree; it still changes for any real
    difference in the code, trailing whitespace included.
    """

    def test_crlf_and_lf_produce_the_same_digest(self, tmp_path: Path) -> None:
        _tree(tmp_path)
        for name in ("numeric.py", "base.py", "alpha_v1.py"):
            _force_lf(tmp_path / name)
        lf_digest = version_code_ref("alpha_v1", tmp_path)
        for name in ("numeric.py", "base.py", "alpha_v1.py"):
            path = tmp_path / name
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        assert version_code_ref("alpha_v1", tmp_path) == lf_digest

    def test_lone_cr_is_also_normalized(self, tmp_path: Path) -> None:
        """Old Mac-style line endings are rarer but the rule is "any newline
        spelling", not "CRLF specifically"."""
        _tree(tmp_path)
        for name in ("numeric.py", "base.py", "alpha_v1.py"):
            _force_lf(tmp_path / name)
        lf_digest = version_code_ref("alpha_v1", tmp_path)
        for name in ("numeric.py", "base.py", "alpha_v1.py"):
            path = tmp_path / name
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r"))
        assert version_code_ref("alpha_v1", tmp_path) == lf_digest

    def test_a_utf8_bom_is_stripped_before_hashing(self, tmp_path: Path) -> None:
        _tree(tmp_path)
        _force_lf(tmp_path / "numeric.py")
        lf_digest = version_code_ref("alpha_v1", tmp_path)
        path = tmp_path / "numeric.py"
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        assert version_code_ref("alpha_v1", tmp_path) == lf_digest

    def test_a_real_code_change_still_changes_the_digest_under_crlf(self, tmp_path: Path) -> None:
        """Normalization must not become a loophole: a genuine edit still
        moves the digest, whichever line ending the file was saved with."""
        _tree(tmp_path)
        for name in ("numeric.py", "base.py", "alpha_v1.py"):
            path = tmp_path / name
            _force_lf(path)
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        before = version_code_ref("alpha_v1", tmp_path)
        (tmp_path / "numeric.py").write_bytes(b"X = 2\r\n")
        assert version_code_ref("alpha_v1", tmp_path) != before

    def test_trailing_whitespace_still_changes_the_digest(self, tmp_path: Path) -> None:
        """Normalization touches newline spelling and the BOM only: trailing
        spaces and the rest of the text stay significant."""
        _tree(tmp_path)
        before = version_code_ref("alpha_v1", tmp_path)
        (tmp_path / "numeric.py").write_text("X = 1   \n", encoding="utf-8")
        assert version_code_ref("alpha_v1", tmp_path) != before

    def test_momentum_v1_digest_agrees_between_crlf_and_lf_checkouts(self, tmp_path: Path) -> None:
        """The reported bug, reproduced on the real closure: a CRLF copy of
        every module momentum_v1 pulls in must freeze the same code_ref as
        the LF checkout it was cloned from."""
        lf_digest = version_code_ref("momentum_v1")
        for name in module_closure("momentum_v1"):
            src = STRATEGIES_DIR / f"{name}.py"
            dst = tmp_path / f"{name}.py"
            dst.write_bytes(src.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        assert version_code_ref("momentum_v1", tmp_path) == lf_digest


class TestImportsItCannotResolve:
    """Astra, S2 fixes diff review (HIGH a): silently dropping an import the
    closure cannot follow is the one direction that must never happen — the
    version would keep its digest while the code it runs changed."""

    def test_a_subpackage_import_is_refused_not_dropped(self, tmp_path: Path) -> None:
        _tree(tmp_path)
        (tmp_path / "calc").mkdir()
        (tmp_path / "calc" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "calc" / "impl.py").write_text("X = 1\n", encoding="utf-8")
        (tmp_path / "alpha_v1.py").write_text(
            "from hunter_core.strategies.calc.impl import X\n", encoding="utf-8"
        )
        with pytest.raises(UnsupportedImport, match="calc.impl"):
            version_code_ref("alpha_v1", tmp_path)

    def test_a_reexport_through_the_package_is_refused(self, tmp_path: Path) -> None:
        """``from hunter_core.strategies import CONTEXT`` runs ``__init__``,
        which the digest deliberately does not cover."""
        _tree(tmp_path)
        (tmp_path / "alpha_v1.py").write_text(
            "from hunter_core.strategies import CONTEXT\n", encoding="utf-8"
        )
        with pytest.raises(UnsupportedImport, match="CONTEXT"):
            version_code_ref("alpha_v1", tmp_path)

    def test_importing_the_package_itself_is_refused(self, tmp_path: Path) -> None:
        _tree(tmp_path)
        (tmp_path / "alpha_v1.py").write_text("import hunter_core.strategies\n", encoding="utf-8")
        with pytest.raises(UnsupportedImport):
            version_code_ref("alpha_v1", tmp_path)

    def test_a_dynamic_import_is_refused(self, tmp_path: Path) -> None:
        """``importlib.import_module`` hides the dependency from the AST, so a
        strategy that used one would freeze a digest that proves nothing."""
        _tree(tmp_path)
        (tmp_path / "alpha_v1.py").write_text(
            "import importlib\n"
            "from hunter_core.strategies.base import X\n"
            "mod = importlib.import_module('hunter_core.strategies.numeric')\n",
            encoding="utf-8",
        )
        with pytest.raises(UnsupportedImport, match="import_module"):
            version_code_ref("alpha_v1", tmp_path)

    def test_the_real_strategies_use_nothing_it_cannot_resolve(self) -> None:
        for strategy in DEFAULT_REGISTRY.all():
            module_closure(strategy_module(strategy), STRATEGIES_DIR)


class TestSharedResolution:
    def test_the_ops_script_and_the_worker_use_one_function_and_one_path(self) -> None:
        """MUST-FIX 1(a), nice-to-have 3: a second path constant is a second
        answer waiting to disagree with the first."""
        import importlib.util
        import sys

        repo_root = Path(__file__).resolve().parents[3]
        path = repo_root / "infra" / "scripts" / "activate_strategy_version.py"
        spec = importlib.util.spec_from_file_location("activate_strategy_version", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["activate_strategy_version"] = module
        spec.loader.exec_module(module)
        assert module.version_code_ref is version_code_ref
        source = path.read_text(encoding="utf-8")
        assert "STRATEGIES_DIR = " not in source, "the only path resolution lives in code_ref.py"
        assert re.search(r"^STRATEGIES_DIR", source, re.MULTILINE) is None

    def test_every_registered_strategy_names_a_module_that_digests(self) -> None:
        for strategy in DEFAULT_REGISTRY.all():
            module = strategy_module(strategy)
            assert (STRATEGIES_DIR / f"{module}.py").is_file(), module
            assert CODE_REF_RE.fullmatch(version_code_ref(module))
