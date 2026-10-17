"""Workspace skeleton smoke test: the package imports without the MT5 wheel."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.unit


def test_package_imports_without_metatrader5() -> None:
    import hunter_b3_robot

    assert hunter_b3_robot.__doc__
    assert "MetaTrader5" not in sys.modules
