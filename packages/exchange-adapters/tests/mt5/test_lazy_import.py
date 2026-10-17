"""The package imports cleanly without MetaTrader5 and never imports it at module level."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import hunter_exchanges.mt5 as mt5_pkg
from hunter_exchanges.mt5.errors import Mt5NotAvailable
from hunter_exchanges.mt5.raw import load_metatrader5

pytestmark = pytest.mark.unit

PKG_DIR = Path(mt5_pkg.__file__).parent


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=False
    )


def test_importing_every_module_never_pulls_in_the_vendor_package() -> None:
    result = _run(
        "import pkgutil, importlib, sys\n"
        "import hunter_exchanges.mt5 as pkg\n"
        "for m in pkgutil.iter_modules(pkg.__path__):\n"
        "    importlib.import_module('hunter_exchanges.mt5.' + m.name)\n"
        "assert 'MetaTrader5' not in sys.modules, 'vendor package imported at module level'\n"
    )
    assert result.returncode == 0, result.stderr


def test_imports_cleanly_when_the_vendor_package_is_absent() -> None:
    """Linux CI: the wheel does not exist. Simulate absence with a blocked entry."""
    result = _run(
        "import sys\n"
        "sys.modules['MetaTrader5'] = None\n"  # `import MetaTrader5` now raises ImportError
        "import hunter_exchanges.mt5.adapter\n"
        "from hunter_exchanges.mt5.errors import Mt5NotAvailable\n"
        "from hunter_exchanges.mt5.raw import load_metatrader5\n"
        "try:\n"
        "    load_metatrader5(platform='win32')\n"
        "except Mt5NotAvailable as exc:\n"
        "    print('not-available:', exc)\n"
        "else:\n"
        "    raise SystemExit('expected Mt5NotAvailable')\n"
    )
    assert result.returncode == 0, result.stderr
    assert "not-available" in result.stdout


def test_off_windows_the_loader_refuses_without_even_trying_to_import() -> None:
    sys.modules.pop("MetaTrader5", None)
    with pytest.raises(Mt5NotAvailable, match="Windows"):
        load_metatrader5(platform="linux")
    assert "MetaTrader5" not in sys.modules


def test_no_module_imports_the_vendor_package_at_top_level() -> None:
    for path in PKG_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # module level only; functions are allowed to import lazily
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            assert not any(n.split(".")[0] == "MetaTrader5" for n in names), path.name
