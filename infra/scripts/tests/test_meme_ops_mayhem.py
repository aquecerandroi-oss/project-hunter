"""T4.27's two audited acts against a fake connection — ``meme_rule_set.py
--set-param`` and ``meme_reclassify_mayhem.py``: dry-run writes nothing,
``--apply`` needs a reason, every refusal is named, the UPDATE carries exactly
the guards the docstrings promise, and the audit row is written on apply.

No database. Run: ``uv run pytest infra/scripts/tests/test_meme_ops_mayhem.py -q``
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
        f"hunter_infra_{name}_t427", SCRIPTS_DIR / f"{name}.py"
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
    """Answers the SELECT with ``rows``; records every statement."""

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
            return _Result([{"id": i} for i in cast("list[Any]", params["ids"])])
        return _Result([])

    def writes(self) -> list[str]:
        return [s for s, _ in self.statements if not s.lstrip().startswith("SELECT")]

    def update(self) -> tuple[str, dict[str, Any]]:
        return next((s, p) for s, p in self.statements if s.lstrip().startswith("UPDATE"))

    def audit(self) -> dict[str, Any]:
        return next(p for s, p in self.statements if "system_events" in s)


# ---- meme_rule_set --set-param ----------------------------------------------------


def _set(name: str, version: str, *, kind: str = "research_only", **params: Any) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{name}/{version}")),
        "name": name,
        "version": version,
        "kind": kind,
        "exp_ref": None if kind == "operator" else "EXP-M5",
        "status": params.pop("status", "active"),
        "open_bets": 0,
        "pending_proposals": 0,
        "params": {"size_sol": "0.05", **params},
    }


ROWS = [
    _set("flow_v2", "1"),
    _set("flow_v2", "5", exclude_mayhem=True),
    _set("operator", "5", kind="operator"),
    _set("operator", "4", kind="operator", status="retired"),
]
REASON = "T4.27: os picos de mcap sao SOL virtual do agente Mayhem, nao demanda"


async def test_set_param_dry_run_plans_every_active_set_and_writes_nothing() -> None:
    script = _load("meme_rule_set")
    conn = FakeConn(ROWS)
    code, report = await script.run(
        conn,
        deprecate=None,
        apply=False,
        reason=REASON,
        set_param="exclude_mayhem=true",
        all_active=True,
    )
    assert code == 0 and "dry-run" in report and conn.writes() == []
    assert "flow_v2/1" in report and "<unset> -> true (change)" in report
    assert "flow_v2/5" in report and "true -> true (unchanged)" in report
    assert "operator/4" not in report, "a retired set is not a live one"


async def test_set_param_apply_updates_only_the_sets_that_differ_and_leaves_an_audit_row() -> None:
    script = _load("meme_rule_set")
    conn = FakeConn(ROWS)
    code, report = await script.run(
        conn,
        deprecate=None,
        apply=True,
        reason=REASON,
        set_param="exclude_mayhem=true",
        all_active=True,
    )
    assert code == 0 and "applied: 2 row(s) updated" in report
    update, params = conn.update()
    assert (
        "params = params || jsonb_build_object(CAST(:key AS text), CAST(:value AS jsonb))" in update
    )
    assert "AND status = 'active'" in update
    assert params == {
        "key": "exclude_mayhem",
        "value": "true",
        "ids": [ROWS[0]["id"], ROWS[2]["id"]],
    }, "flow_v2/5 already said true and is left alone"
    audit = conn.audit()
    assert audit["component"] == "meme_rule_set" and audit["event"] == "param_set"
    assert "flow_v2/1 (<unset>)" in audit["message"] and REASON in audit["message"]


async def test_set_param_refusals_are_named_and_nothing_to_change_is_a_plain_exit() -> None:
    script = _load("meme_rule_set")
    cases: list[tuple[dict[str, Any], str]] = [
        (
            {"set_param": "exclude_mayhem=true", "all_active": True, "reason": "short"},
            "reason_required",
        ),
        ({"set_param": "exclude_mayhem", "all_active": True}, "param_invalid"),
        ({"set_param": "=true", "all_active": True}, "param_invalid"),
        ({"set_param": "exclude_mayhem=true"}, "no_target"),
        ({"set_param": "exclude_mayhem=true", "rule_sets": ["nope/1"]}, "rule_set_missing"),
        ({"set_param": "exclude_mayhem=true", "rule_sets": ["operator/4"]}, "rule_set_retired"),
    ]
    for kwargs, refusal in cases:
        conn = FakeConn(ROWS)
        kwargs.setdefault("reason", REASON)
        with pytest.raises(script.Refused, match=refusal):
            await script.run(conn, deprecate=None, apply=True, **kwargs)
        assert conn.writes() == [], refusal
    conn = FakeConn(ROWS)
    code, report = await script.run(
        conn,
        deprecate=None,
        apply=True,
        reason=REASON,
        set_param="exclude_mayhem=true",
        rule_sets=["flow_v2/5"],
    )
    assert code == 0 and "nothing to do" in report and conn.writes() == []


def test_parse_param_reads_json_and_keeps_a_bare_word_as_text() -> None:
    script = _load("meme_rule_set")
    assert script.parse_param("exclude_mayhem=true") == ("exclude_mayhem", True)
    assert script.parse_param("max_hold_s=900") == ("max_hold_s", 900)
    assert script.parse_param('size_sol="0.05"') == ("size_sol", "0.05")
    assert script.parse_param("clock=15s") == ("clock", "15s")


# ---- meme_reclassify_mayhem -------------------------------------------------------

BET_A = uuid.UUID("01924f6e-0000-7000-8000-00000000042a")
BET_B = uuid.UUID("01924f6e-0000-7000-8000-00000000042b")
ENTRY = datetime(2026, 9, 15, 20, 37, tzinfo=UTC)


def _candidate(bet: uuid.UUID) -> dict[str, Any]:
    return {
        "id": bet,
        "mint": "KAT1111111111111111111111111111111111111pump",
        "rule_set": "flow_v2/5",
        "entry_at": ENTRY,
        "exit_at": ENTRY.replace(minute=45),
        "pnl_sol": Decimal("0.0421"),
        "exit_reason": "target",
        "mayhem_state": "active",
    }


async def test_mayhem_dry_run_lists_the_candidates_and_writes_nothing() -> None:
    script = _load("meme_reclassify_mayhem")
    conn = FakeConn([_candidate(BET_A), _candidate(BET_B)])
    code, report = await script.run(conn, day=None, ids=None, apply=False, reason=None)
    assert code == 0 and "2 candidate(s)" in report and "dry-run" in report
    assert conn.writes() == []
    select, params = conn.statements[0]
    assert "t.mayhem_enabled = true" in select and "outcome_quality = 'measured'" in select
    assert "JOIN meme_tokens t ON t.mint = b.mint" in select
    assert params == {"day": None, "ids": None}


async def test_mayhem_apply_needs_a_reason_and_refuses_a_non_candidate_by_name() -> None:
    script = _load("meme_reclassify_mayhem")
    conn = FakeConn([_candidate(BET_A)])
    with pytest.raises(script.Refused, match="reason_required"):
        await script.run(conn, day=None, ids=None, apply=True, reason="short")
    assert conn.statements == [], "refused before touching the database"
    with pytest.raises(script.Refused, match="not_a_candidate") as refused:
        await script.run(conn, day=None, ids=[BET_A, BET_B], apply=True, reason="x" * 20)
    assert str(BET_B) in str(refused.value) and conn.writes() == []


async def test_mayhem_apply_writes_the_machine_reason_and_leaves_an_audit_row() -> None:
    script = _load("meme_reclassify_mayhem")
    conn = FakeConn([_candidate(BET_A), _candidate(BET_B)])
    reason = "T4.27: a marca era SOL virtual do agente Mayhem, nao o que a curva pagaria"
    code, report = await script.run(conn, day=None, ids=None, apply=True, reason=reason)
    assert code == 0 and "applied: 2 row(s)" in report
    update, params = conn.update()
    assert "outcome_quality = 'indeterminate'" in update
    assert "outcome_quality_reason = :outcome_reason" in update
    assert "outcome_quality_at = now()" in update and "pnl_sol" not in update
    assert "t.mayhem_enabled = true AND b.outcome_quality = 'measured'" in update
    assert params == {"ids": [BET_A, BET_B], "outcome_reason": "mayhem_virtual_sol"}
    audit = conn.audit()
    assert audit["component"] == "meme_reclassify_mayhem" and audit["event"] == "reclassified"
    assert "mayhem_virtual_sol" in audit["message"] and reason in audit["message"]
    assert str(BET_A) in audit["message"]


async def test_mayhem_with_nothing_to_do_exits_zero_and_writes_nothing() -> None:
    script = _load("meme_reclassify_mayhem")
    conn = FakeConn([])
    code, report = await script.run(conn, day=None, ids=None, apply=True, reason="x" * 20)
    assert code == 0 and "nothing to do" in report and conn.writes() == []


def test_set_param_statement_types_the_key_for_asyncpg() -> None:
    """16/09/2026 15:0x BRT, VPS: ``--set-param max_progress_pct=50 --rule-set operator/5
    --apply`` failed with asyncpg ``IndeterminateDatatypeError: could not determine data
    type of parameter $1`` — ``jsonb_build_object(:key, …)`` leaves the key untyped for a
    prepared statement. The unit tests above run on fakes and never executed the SQL, so
    this pins the cast in the statement text itself."""
    from meme_rule_set import _SET_PARAM

    assert "jsonb_build_object(CAST(:key AS text), CAST(:value AS jsonb))" in str(_SET_PARAM)
