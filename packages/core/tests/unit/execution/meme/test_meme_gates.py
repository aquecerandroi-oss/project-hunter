"""§12 gates and the boot refusal (``docs/RISK_ENGINE_MEME.md`` §3.4, §12)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from hunter_core.execution.meme.gates import (
    ENV_GATES_FILE,
    ENV_LIVE_FLAG,
    GATES_SCHEMA,
    MemeLiveTradingRefused,
    load_execution_mode,
    load_gates,
    parse_flag,
)

TODAY = date(2026, 10, 21)


def gates_doc(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema": GATES_SCHEMA,
        "gate_a_engineering": {
            "passed": True,
            "date": "2026-10-01",
            "evidence": ".claude/state/notes-T4.x.md",
        },
        "gate_b_evidence": {"passed": True, "date": "2026-10-20", "evidence": "EXP-M1 report"},
        "gate_c_owner": {"enabled": True, "date": "2026-10-21"},
        "signed_by": "everton",
        "signed_at": "2026-10-21",
        "valid_until": "2026-11-21",
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(doc.get(key), dict):
            doc[key] = {**doc[key], **value}
        else:
            doc[key] = value
    return doc


def write(tmp_path: Path, doc: Any) -> Path:
    path = tmp_path / "meme_gates.json"
    path.write_text(json.dumps(doc) if not isinstance(doc, str) else doc, encoding="utf-8")
    return path


def test_valid_gates_load(tmp_path: Path) -> None:
    gates = load_gates(write(tmp_path, gates_doc()), today=TODAY)
    assert gates.signed_by == "everton"
    assert gates.valid_until == date(2026, 11, 21)


@pytest.mark.parametrize(
    ("doc", "reason"),
    [
        (gates_doc(schema="other"), "gates_schema_mismatch"),
        (gates_doc(gate_a_engineering={"passed": False}), "gate_a_engineering_not_passed"),
        (gates_doc(gate_b_evidence={"passed": "yes"}), "gate_b_evidence_not_passed"),
        (gates_doc(gate_c_owner={"enabled": False}), "gate_c_owner_not_enabled"),
        (gates_doc(signed_by=""), "gates_unsigned"),
        (gates_doc(valid_until="2026-10-20"), "gates_expired"),
        (gates_doc(signed_at="2026-10-22"), "gates_date_in_future"),
        (gates_doc(gate_a_engineering={"evidence": ""}), "gates_without_evidence"),
        (gates_doc(gate_a_engineering={"date": "yesterday"}), "gates_file_invalid"),
        (gates_doc(gate_b_evidence="passed"), "gates_file_invalid"),
        ("{not json", "gates_file_invalid"),
        ("[1,2,3]", "gates_file_invalid"),
    ],
)
def test_every_red_gate_is_a_named_refusal(tmp_path: Path, doc: Any, reason: str) -> None:
    with pytest.raises(MemeLiveTradingRefused) as excinfo:
        load_gates(write(tmp_path, doc), today=TODAY)
    assert excinfo.value.reason == reason


def test_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(MemeLiveTradingRefused) as excinfo:
        load_gates(tmp_path / "nope.json", today=TODAY)
    assert excinfo.value.reason == "gates_file_missing"


def test_flag_off_never_needs_the_file() -> None:
    mode = load_execution_mode({}, today=TODAY)
    assert mode.live is False and mode.gates is None
    mode = load_execution_mode({ENV_LIVE_FLAG: "false", ENV_GATES_FILE: "/nowhere"}, today=TODAY)
    assert mode.live is False


def test_flag_on_without_file_path_is_refused() -> None:
    with pytest.raises(MemeLiveTradingRefused) as excinfo:
        load_execution_mode({ENV_LIVE_FLAG: "true"}, today=TODAY)
    assert excinfo.value.reason == "gates_file_not_configured"


def test_flag_on_with_valid_gates_is_live(tmp_path: Path) -> None:
    path = write(tmp_path, gates_doc())
    mode = load_execution_mode({ENV_LIVE_FLAG: "1", ENV_GATES_FILE: str(path)}, today=TODAY)
    assert mode.live is True and mode.gates is not None


def test_flag_on_with_red_gate_is_refused(tmp_path: Path) -> None:
    path = write(tmp_path, gates_doc(gate_b_evidence={"passed": False}))
    with pytest.raises(MemeLiveTradingRefused) as excinfo:
        load_execution_mode({ENV_LIVE_FLAG: "yes", ENV_GATES_FILE: str(path)}, today=TODAY)
    assert excinfo.value.reason == "gate_b_evidence_not_passed"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, False),
        ("", False),
        ("true", True),
        ("1", True),
        ("on", True),
        ("no", False),
        ("TRUE", True),
    ],
)
def test_parse_flag(raw: str | None, expected: bool) -> None:
    assert parse_flag(raw) is expected
