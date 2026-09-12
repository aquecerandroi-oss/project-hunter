"""§13: ``hunter_risk_meme`` never imports ``hunter_risk`` and ``hunter_risk`` never
imports ``hunter_risk_meme`` — proved on the source, not on a promise."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

RISK_CORE = Path(__file__).resolve().parents[3]
_IMPORT = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)


def _imports(package: str) -> set[str]:
    modules: set[str] = set()
    for path in (RISK_CORE / package).rglob("*.py"):
        modules.update(_IMPORT.findall(path.read_text(encoding="utf-8")))
    return modules


def test_the_meme_engine_does_not_import_the_spot_engine() -> None:
    offenders = {
        m
        for m in _imports("hunter_risk_meme")
        if m == "hunter_risk" or m.startswith("hunter_risk.")
    }
    assert offenders == set()


def test_the_spot_engine_does_not_import_the_meme_engine() -> None:
    offenders = {m for m in _imports("hunter_risk") if m.startswith("hunter_risk_meme")}
    assert offenders == set()


def test_the_meme_engine_has_no_network_database_or_clock() -> None:
    forbidden = ("httpx", "sqlalchemy", "redis", "asyncio", "time", "socket", "requests")
    offenders = {m for m in _imports("hunter_risk_meme") if m.split(".")[0] in forbidden}
    assert offenders == set()
