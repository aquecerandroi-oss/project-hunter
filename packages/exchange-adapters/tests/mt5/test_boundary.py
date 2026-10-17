"""I-$-1: `float` is built only inside the boundary modules (convert, builders, parse)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import hunter_exchanges.mt5 as mt5_pkg

pytestmark = pytest.mark.unit

PKG_DIR = Path(mt5_pkg.__file__).parent
BOUNDARY = {"convert.py", "builders.py", "parse.py"}


def test_float_conversions_live_only_in_the_boundary_modules() -> None:
    offenders: list[tuple[str, int]] = []
    for path in sorted(PKG_DIR.glob("*.py")):
        if path.name in BOUNDARY:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "float"
            ):
                offenders.append((path.name, node.lineno))
    assert offenders == []
