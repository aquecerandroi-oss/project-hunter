"""``activate_strategy_version.py``'s parser — MÉDIA-3 (T3.39b review, closing
the review of 4929b99): ``--successor``/``--force-paper`` outside the modes
that use them must be a loud ``parser.error`` (exit 2, a message on stderr),
never a flag the tool silently ignores. ``--force-paper`` widened to
``--supersede`` too when ALTA-2 gave that mode the same paper guard
``--deprecate`` already had.

No database: every case here is decided by :func:`argparse.ArgumentParser.parse_args`
before ``_run`` ever opens a connection; ``_run`` itself is stubbed out so a
case the parser *accepts* never touches ``DATABASE_URL_MIGRATIONS``.

Run: ``uv run pytest services/strategy-worker/tests/test_activate_strategy_version_cli.py -q``
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]


def _script() -> Any:
    path = REPO_ROOT / "infra" / "scripts" / "activate_strategy_version.py"
    spec = importlib.util.spec_from_file_location("activate_strategy_version_cli", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["activate_strategy_version_cli"] = module
    spec.loader.exec_module(module)
    return module


async def _noop_run(args: argparse.Namespace) -> int:
    """Stands in for ``_run``: proves the parser accepted the arguments without
    doing any of the work a real run would (no DB, no network)."""
    del args
    return 0


class TestForcePaperRequiresDeprecateOrSupersede:
    def test_without_either_mode_is_a_parser_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        module = _script()
        monkeypatch.setattr(
            sys,
            "argv",
            ["activate_strategy_version.py", "momentum", "v1", "--changelog", "x", "--force-paper"],
        )
        with pytest.raises(SystemExit) as excinfo:
            module.main()
        assert excinfo.value.code == 2
        assert "--force-paper requires --deprecate or --supersede" in capsys.readouterr().err

    def test_with_supersede_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _script()
        monkeypatch.setattr(module, "_run", _noop_run)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "activate_strategy_version.py",
                "momentum",
                "v1",
                "--changelog",
                "x",
                "--supersede",
                "--force-paper",
            ],
        )
        assert module.main() == 0

    def test_with_deprecate_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _script()
        monkeypatch.setattr(module, "_run", _noop_run)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "activate_strategy_version.py",
                "momentum",
                "v1",
                "--changelog",
                "x",
                "--deprecate",
                "--force-paper",
            ],
        )
        assert module.main() == 0


class TestSuccessorRequiresDeprecate:
    def test_without_deprecate_is_a_parser_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        module = _script()
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "activate_strategy_version.py",
                "momentum",
                "v1",
                "--changelog",
                "x",
                "--successor",
                "v2",
            ],
        )
        with pytest.raises(SystemExit) as excinfo:
            module.main()
        assert excinfo.value.code == 2
        assert "--successor requires --deprecate" in capsys.readouterr().err

    def test_with_deprecate_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _script()
        monkeypatch.setattr(module, "_run", _noop_run)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "activate_strategy_version.py",
                "breakout",
                "v1",
                "--changelog",
                "x",
                "--deprecate",
                "--successor",
                "v2",
            ],
        )
        assert module.main() == 0
