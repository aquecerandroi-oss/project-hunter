"""``meme_event.py`` — the audited script that registers a "may pump" event
(T4.26): dry-run by default, ``--apply`` needs a valid kind/confidence/source
and a ``--recorded-by``, and the audit row lands on apply.

No database: the connection records the statements it receives and answers a
canned id for the ``RETURNING``. Run: ``uv run pytest infra/scripts/tests/test_meme_event.py -q``
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
EVENT_ID = "00000000-0000-4000-8000-0000000e7e17"


def _load(name: str) -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}_ut", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return self._values


class FakeConn:
    def __init__(self) -> None:
        self.statements: list[tuple[str, Any]] = []

    async def execute(self, statement: Any, parameters: Any = None, /) -> _Result:
        sql = str(statement)
        self.statements.append((sql, parameters))
        if sql.lstrip().startswith("INSERT INTO meme_events"):
            return _Result([EVENT_ID])
        return _Result([])

    def writes(self) -> list[str]:
        return [s for s, _ in self.statements]


BASE = {
    "kind": "public_figure_launch",
    "title": "Figure X anuncia moeda",
    "url": "https://x.com/handle/status/123",
    "mint": None,
    "handle": "@handle",
    "symbol": None,
    "confidence": "confirmed",
    "source": "manual",
    "observed_at": datetime(2026, 9, 16, 1, 0, tzinfo=UTC),
    "notes": None,
    "recorded_by": "sexta-feira",
}


async def test_dry_run_writes_nothing_and_names_the_plan() -> None:
    script = _load("meme_event")
    conn = FakeConn()
    code, report = await script.run(conn, apply=False, **BASE)
    assert code == 0 and "dry-run" in report
    assert conn.writes() == []
    assert "handle=handle" in report, "the @ is stripped in the plan too"


async def test_apply_inserts_and_leaves_an_audit_row() -> None:
    script = _load("meme_event")
    conn = FakeConn()
    code, report = await script.run(conn, apply=True, **BASE)
    assert code == 0 and f"meme_events {EVENT_ID}" in report
    insert_sql, insert_params = conn.statements[0]
    assert "INSERT INTO meme_events" in insert_sql
    assert insert_params["handle_hint"] == "handle", "stripped of its leading @"
    assert insert_params["kind"] == "public_figure_launch"
    _, audit_params = next(s for s in conn.statements if "system_events" in s[0])
    assert audit_params["component"] == "meme_event" and audit_params["event"] == "added"
    assert EVENT_ID in audit_params["message"] and "sexta-feira" in audit_params["message"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("kind", "rumor_only", "kind_unknown"),
        ("confidence", "sure", "confidence_unknown"),
        ("source", "twitter_dm", "source_unknown"),
        ("recorded_by", None, "recorded_by_required"),
        ("recorded_by", "  ", "recorded_by_required"),
    ],
)
async def test_refuses_by_name_before_writing_anything(
    field: str, value: str | None, reason: str
) -> None:
    script = _load("meme_event")
    conn = FakeConn()
    overrides = {**BASE, field: value}
    with pytest.raises(script.Refused, match=reason):
        await script.run(conn, apply=True, **overrides)
    assert conn.statements == [], "refused before touching the database"


async def test_a_handle_with_no_leading_at_is_kept_as_is() -> None:
    script = _load("meme_event")
    conn = FakeConn()
    overrides = {**BASE, "handle": "plainhandle"}
    await script.run(conn, apply=True, **overrides)
    _, params = conn.statements[0]
    assert params["handle_hint"] == "plainhandle"


async def test_no_handle_writes_no_handle_hint() -> None:
    script = _load("meme_event")
    conn = FakeConn()
    overrides = {**BASE, "handle": None, "symbol": "BUM"}
    await script.run(conn, apply=True, **overrides)
    _, params = conn.statements[0]
    assert params["handle_hint"] is None and params["symbol_hint"] == "BUM"
