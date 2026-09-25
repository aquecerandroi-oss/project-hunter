"""T4.64: ``meme_rule_set.py --set-param`` must never write a ``meme_rule_sets
.params`` document ``hunter_meme_worker.lab_models.RuleSetSpec.from_params``
(the gate, the exit rules) cannot load — the two incidents of 18/09/2026,
reproduced against a fake connection: a bare JSON number for a key the live
document already carries as a string (``max_sol_per_bet=0.28``, 14:19 BRT) and
a bare JSON number for a decimal key with no string precedent yet
(``trailing_arm_x=1.0`` typed without quotes — the same slip; the *quoted*
``"1.0"`` T4.65 later made the reader tolerant of is exercised here too, as a
passing case). ``--validate NAME/VERSION`` is the read-only check on a row
already in the table.

No database. Run: ``uv run pytest infra/scripts/tests/test_meme_rule_set_validate.py -q``
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
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
        f"hunter_infra_{name}_t464", SCRIPTS_DIR / f"{name}.py"
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
            return _Result([{"id": i} for i in cast("list[Any]", params["ids"])])
        return _Result([])

    def writes(self) -> list[str]:
        return [s for s, _ in self.statements if not s.lstrip().startswith("SELECT")]


# T4.64: a full, valid document — the same shape as a real seeded set
# (``meme_gate_v2_seed.py``) — so validation loads it exactly as the worker
# would, not tripping on a merely-incomplete fixture.
BASE_PARAMS: dict[str, Any] = {
    "gate_key": "fluxo_e_holders",
    "gate_version": 1,
    "min_age_s": 30,
    "max_age_s": 300,
    "min_progress_pct": "5",
    "max_progress_pct": "100",
    "max_participation_pct": "1",
    "size_sol": "0.05",
    "target_x": "3",
    "trailing_pct": "35",
    "max_hold_s": 1800,
    "max_loss_pct": "50",
    "wallet_max_sol": "2.0",
    "max_sol_per_bet": "0.05",
    "daily_loss_cap_sol": "0.20",
}


def _set(name: str, version: str, **params: Any) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{name}/{version}")),
        "name": name,
        "version": version,
        "kind": "research_only",
        "exp_ref": "EXP-M13",
        "status": params.pop("status", "active"),
        "open_bets": 0,
        "pending_proposals": 0,
        "params": {**BASE_PARAMS, **params},
    }


REASON = "T4.64: regressao dos dois incidentes de 18/09/2026 (KB-0140)"


def _obsidian_note(tmp_path: Path, *mentions: str) -> str:
    """T4.93: a fixture note under ``obsidian/`` mentioning every target."""
    note_dir = tmp_path / "obsidian" / "11-KNOWLEDGE"
    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / "fixture.md"
    note_path.write_text("# fixture de teste\n\n" + "\n".join(mentions), encoding="utf-8")
    return "obsidian/11-KNOWLEDGE/fixture.md"


async def test_incident_1_bare_float_over_a_string_key_is_refused_with_the_fix() -> None:
    """14:19 BRT: ``max_sol_per_bet=0.28`` — a bare JSON number over a key the
    live document already carries as a string. Refused before the merge even
    reaches ``RuleSetSpec.from_params``; nothing written, dry-run included."""
    script = _load("meme_rule_set")
    conn = FakeConn([_set("operator", "5", kind="operator")])
    with pytest.raises(script.WouldNotLoad, match=r'decimals are strings.*max_sol_per_bet="0\.28"'):
        await script.run(
            conn,
            deprecate=None,
            apply=False,
            reason=REASON,
            set_param="max_sol_per_bet=0.28",
            rule_sets=["operator/5"],
        )
    assert conn.writes() == [], "dry-run: refused before any write, none happened anyway"

    conn = FakeConn([_set("operator", "5", kind="operator")])
    with pytest.raises(script.WouldNotLoad, match="decimals are strings"):
        await script.run(
            conn,
            deprecate=None,
            apply=True,
            reason=REASON,
            set_param="max_sol_per_bet=0.28",
            rule_sets=["operator/5"],
        )
    assert conn.writes() == [], "--apply: still nothing written"


async def test_incident_2_bare_float_with_no_string_precedent_is_refused() -> None:
    """19:47 BRT's slip typed without quotes: ``trailing_arm_x=1.0`` (a bare
    JSON number, key absent from the live document) reaches
    ``RuleSetSpec.from_params`` and dies the exact way the worker would have —
    ``decimal_of``'s ``a float is not an exact number`` — refused, not stored."""
    script = _load("meme_rule_set")
    conn = FakeConn([_set("flow_v2", "6")])
    with pytest.raises(script.WouldNotLoad, match="float is not an exact number"):
        await script.run(
            conn,
            deprecate=None,
            apply=True,
            reason=REASON,
            set_param="trailing_arm_x=1.0",
            rule_sets=["flow_v2/6"],
        )
    assert conn.writes() == []


async def test_valid_string_decimal_passes(tmp_path: Path) -> None:
    script = _load("meme_rule_set")
    conn = FakeConn([_set("flow_v2", "6")])
    note = _obsidian_note(tmp_path, "flow_v2/6")
    code, report = await script.run(
        conn,
        deprecate=None,
        apply=True,
        reason=REASON,
        set_param='trailing_pct="40"',
        rule_sets=["flow_v2/6"],
        note=note,
        repo_root=tmp_path,
    )
    assert code == 0 and "applied: 1 row(s) updated" in report


async def test_trailing_arm_x_null_passes(tmp_path: Path) -> None:
    """A set disarming its trailing rule back to "from the entry" — ``null``
    over a previously-set value — loads fine (``arm_multiple_or_none(None)``)."""
    script = _load("meme_rule_set")
    conn = FakeConn([_set("flow_v2", "6", trailing_arm_x="2.0")])
    note = _obsidian_note(tmp_path, "flow_v2/6")
    code, report = await script.run(
        conn,
        deprecate=None,
        apply=True,
        reason=REASON,
        set_param="trailing_arm_x=null",
        rule_sets=["flow_v2/6"],
        note=note,
        repo_root=tmp_path,
    )
    assert code == 0 and "applied: 1 row(s) updated" in report


async def test_t480_max_buys_1m_accepts_an_int_and_refuses_a_decimal_or_a_negative(
    tmp_path: Path,
) -> None:
    """T4.80: the buy-count ceiling is a **count** — ``25`` is written,
    ``25.5`` is refused by type (never truncated to 25 by ``int()``) and
    ``-1`` by the gate's own validation. Nothing written in either refusal."""
    script = _load("meme_rule_set")
    good = FakeConn([_set("operator", "5", kind="operator")])
    note = _obsidian_note(tmp_path, "operator/5")
    code, report = await script.run(
        good,
        deprecate=None,
        apply=True,
        reason="T4.80: R65 (KB-0147) — teto de compras no minuto, em sombra",
        set_param="max_buys_1m=25",
        rule_sets=["operator/5"],
        note=note,
        repo_root=tmp_path,
    )
    assert code == 0 and "applied: 1 row(s) updated" in report

    for bad_value, message in (("25.5", "is a count"), ("-1", "cannot be negative")):
        conn = FakeConn([_set("operator", "5", kind="operator")])
        with pytest.raises(script.WouldNotLoad, match=message):
            await script.run(
                conn,
                deprecate=None,
                apply=True,
                reason=REASON,
                set_param=f"max_buys_1m={bad_value}",
                rule_sets=["operator/5"],
            )
        assert conn.writes() == [], f"max_buys_1m={bad_value} must write nothing"


async def test_t480_a_row_without_the_key_still_validates() -> None:
    """Absent = today's behaviour: the seeded document loads untouched."""
    script = _load("meme_rule_set")
    conn = FakeConn([_set("flow_v2", "6")])
    code, report = await script.run(
        conn, deprecate=None, apply=False, reason=None, validate="flow_v2/6"
    )
    assert code == 0 and "OK: flow_v2/6" in report


async def test_validate_reports_ok_for_a_good_row_and_error_for_a_bad_one() -> None:
    script = _load("meme_rule_set")
    good = FakeConn([_set("flow_v2", "6")])
    code, report = await script.run(
        good, deprecate=None, apply=False, reason=None, validate="flow_v2/6"
    )
    assert code == 0 and "OK: flow_v2/6" in report

    bad = FakeConn([_set("flow_v2", "7", max_sol_per_bet=0.28)])
    with pytest.raises(script.WouldNotLoad, match="float is not an exact number"):
        await script.run(bad, deprecate=None, apply=False, reason=None, validate="flow_v2/7")
