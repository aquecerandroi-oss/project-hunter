"""The two audited operator scripts of T4.16 — ``meme_reclassify_indeterminate.py``
and ``meme_rule_set.py`` — against a fake connection: dry-run writes nothing,
``--apply`` needs a reason, every refusal is named, the UPDATE carries exactly
the guards the docstrings promise, and the audit row is written on apply.

No database: the connection records the statements it receives and answers
canned rows. Run: ``uv run pytest infra/scripts/tests/test_meme_ops_scripts.py -q``
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


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
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return [next(iter(r.values())) for r in self._rows]


class FakeConn:
    """Answers the first SELECT with ``rows``; records every statement."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.statements: list[tuple[str, Any]] = []

    async def execute(self, statement: Any, parameters: Any = None, /) -> _Result:
        sql = str(statement)
        self.statements.append((sql, parameters))
        if sql.lstrip().startswith("SELECT"):
            return _Result(self.rows)
        if sql.lstrip().startswith("UPDATE"):
            params = cast("dict[str, Any]", parameters)
            ids = cast("list[uuid.UUID] | None", params.get("ids"))
            if ids is not None:
                return _Result([{"id": i} for i in ids])
            return _Result([{"id": params["id"]}])
        return _Result([])

    def writes(self) -> list[str]:
        return [s for s, _ in self.statements if not s.lstrip().startswith("SELECT")]


BET_A = uuid.UUID("01924f6e-0000-7000-8000-00000000000a")
BET_B = uuid.UUID("01924f6e-0000-7000-8000-00000000000b")
ENTRY = datetime(2026, 9, 12, 14, 0, tzinfo=UTC)


def _candidate(bet: uuid.UUID) -> dict[str, Any]:
    return {
        "id": bet,
        "mint": "DOJO111111111111111111111111111111111111111",
        "rule_set": "meme_paper_v0/1",
        "entry_at": ENTRY,
        "exit_at": ENTRY.replace(minute=5),
        "pnl_sol": Decimal("-0.05"),
        "pending_reason": "target",
    }


# ---- meme_reclassify_indeterminate ------------------------------------------------


async def test_reclassify_dry_run_lists_the_candidates_and_writes_nothing() -> None:
    script = _load("meme_reclassify_indeterminate")
    conn = FakeConn([_candidate(BET_A), _candidate(BET_B)])
    code, report = await script.run(conn, day=None, ids=None, apply=False, reason=None)
    assert code == 0 and "2 candidate(s)" in report and "dry-run" in report
    assert conn.writes() == []
    select, params = conn.statements[0]
    assert "exit ->> 'reason' = 'rug_no_snapshot'" in select
    assert "outcome_quality = 'measured'" in select and params == {"day": None, "ids": None}


async def test_reclassify_apply_needs_a_reason_and_refuses_a_non_candidate_by_name() -> None:
    script = _load("meme_reclassify_indeterminate")
    conn = FakeConn([_candidate(BET_A)])
    with pytest.raises(script.Refused, match="reason_required"):
        await script.run(conn, day=None, ids=None, apply=True, reason="short")
    assert conn.statements == [], "refused before touching the database"
    with pytest.raises(script.Refused, match="not_a_candidate") as refused:
        await script.run(conn, day=None, ids=[BET_A, BET_B], apply=True, reason="x" * 20)
    assert str(BET_B) in str(refused.value) and conn.writes() == []


async def test_reclassify_apply_updates_only_the_candidates_and_leaves_an_audit_row() -> None:
    script = _load("meme_reclassify_indeterminate")
    conn = FakeConn([_candidate(BET_A), _candidate(BET_B)])
    reason = "artefato do simulador antes de 12:14 BRT: sem fotografia por 3 min"
    code, report = await script.run(conn, day=None, ids=None, apply=True, reason=reason)
    assert code == 0 and "applied: 2 row(s)" in report
    update, params = next((s, p) for s, p in conn.statements if s.lstrip().startswith("UPDATE"))
    assert "outcome_quality = 'indeterminate'" in update
    assert "outcome_quality_at = now()" in update and "pnl_sol" not in update
    assert "exit ->> 'reason' = 'rug_no_snapshot' AND outcome_quality = 'measured'" in update
    assert params == {"ids": [BET_A, BET_B], "reason": reason}
    _, audit_params = next((s, p) for s, p in conn.statements if "system_events" in s)
    assert audit_params["component"] == "meme_reclassify_indeterminate"
    assert audit_params["event"] == "reclassified" and reason in audit_params["message"]
    assert str(BET_A) in audit_params["message"]


async def test_reclassify_with_nothing_to_do_exits_zero_and_writes_nothing() -> None:
    script = _load("meme_reclassify_indeterminate")
    conn = FakeConn([])
    code, report = await script.run(conn, day=None, ids=None, apply=True, reason="x" * 20)
    assert code == 0 and "nothing to do" in report and conn.writes() == []


# ---- meme_rule_set ------------------------------------------------------------------


def _set(
    name: str, version: str, kind: str = "research_only", status: str = "active"
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{name}/{version}")),
        "name": name,
        "version": version,
        "kind": kind,
        "exp_ref": None if kind == "operator" else "EXP-M1",
        "status": status,
        "open_bets": 1,
        "pending_proposals": 2,
    }


ROWS = [
    _set("meme_paper_v0", "1"),
    _set("hype_probe_v0", "1"),
    _set("operator", "2", kind="operator"),
    _set("operator", "1", kind="operator", status="retired"),
]


async def test_deprecate_dry_run_plans_and_refusals_are_named() -> None:
    script = _load("meme_rule_set")
    code, report = await script.run(FakeConn(ROWS), deprecate=None, apply=False, reason=None)
    assert code == 0 and "meme_paper_v0/1" in report and "retired" in report
    conn = FakeConn(ROWS)
    code, report = await script.run(
        conn, deprecate="meme_paper_v0/1", apply=False, reason="EXP-M1: descartar (9/9)"
    )
    assert code == 0 and "1 open bet(s)" in report and "dry-run" in report
    assert conn.writes() == []
    for label, refusal, reason in (
        ("meme_paper_v0/1", "reason_required", None),
        ("nope/1", "rule_set_missing", "x" * 20),
        ("operator/1", "already_retired", "x" * 20),
        ("operator/2", "last_operator_set", "x" * 20),
    ):
        conn = FakeConn(ROWS)
        with pytest.raises(script.Refused, match=refusal):
            await script.run(conn, deprecate=label, apply=True, reason=reason)
        assert conn.writes() == [], label


async def test_deprecate_apply_retires_the_active_row_and_leaves_an_audit_row() -> None:
    script = _load("meme_rule_set")
    conn = FakeConn(ROWS)
    reason = "EXP-M3: descartar; sucessora hype_probe_v0/2 (EXP-M5)"
    code, report = await script.run(conn, deprecate="hype_probe_v0/1", apply=True, reason=reason)
    assert code == 0 and "applied: retired" in report
    update, params = next((s, p) for s, p in conn.statements if s.lstrip().startswith("UPDATE"))
    assert "status = 'retired', retired_at = now()" in update and "AND status = 'active'" in update
    assert params == {"id": ROWS[1]["id"]}
    _, audit = next((s, p) for s, p in conn.statements if "system_events" in s)
    assert audit["component"] == "meme_rule_set" and audit["event"] == "deprecated"
    assert "hype_probe_v0/1" in audit["message"] and reason in audit["message"]
