"""R1 (T4.14 precedent): ``hunter_risk``, ``hunter_risk_meme`` and ``hunter_risk_b3`` never
import one another, and the B3 engine has no network, database, clock or file IO —
proved on the source, not on a promise."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

RISK_CORE = Path(__file__).resolve().parents[3]
_IMPORT = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)
ENGINES = ("hunter_risk", "hunter_risk_meme", "hunter_risk_b3")


def _imports(package: str) -> set[str]:
    modules: set[str] = set()
    for path in (RISK_CORE / package).rglob("*.py"):
        modules.update(_IMPORT.findall(path.read_text(encoding="utf-8")))
    return modules


def _top(module: str) -> str:
    return module.split(".")[0]


def test_the_b3_package_exists_and_has_modules() -> None:
    assert any((RISK_CORE / "hunter_risk_b3").rglob("*.py"))


@pytest.mark.parametrize("engine", ENGINES)
def test_no_engine_imports_a_sibling_engine(engine: str) -> None:
    siblings = set(ENGINES) - {engine}
    offenders = {m for m in _imports(engine) if _top(m) in siblings}
    assert offenders == set()


def test_the_b3_engine_has_no_network_database_clock_or_io() -> None:
    forbidden = {
        "httpx", "sqlalchemy", "redis", "asyncio", "time", "socket", "requests",
        "os", "pathlib", "io", "subprocess", "random", "MetaTrader5", "hunter_exchanges",
        "hunter_b3_robot", "hunter_indicators",
    }  # fmt: skip
    offenders = {m for m in _imports("hunter_risk_b3") if _top(m) in forbidden}
    assert offenders == set()


def test_the_b3_engine_never_reads_the_wall_clock() -> None:
    source = "\n".join(
        p.read_text(encoding="utf-8") for p in (RISK_CORE / "hunter_risk_b3").rglob("*.py")
    )
    for call in ("datetime.now(", "datetime.utcnow(", "date.today(", "time.time("):
        assert call not in source, call
