"""Renderer unit tests — brief T3.20 item 5: a version with 14 parameters, a
paper line, and a sibling with a cohort. No database: every input here is a
hand-built fixture, the same shape :mod:`obsidian_strategy_queries` returns.

Run: ``uv run pytest infra/scripts/tests/test_obsidian_strategy_pages.py -q``
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from obsidian_family_pages import build_family_body, extract_latest_result  # noqa: E402
from obsidian_strategy_pages import (  # noqa: E402
    ParamInfo,
    build_parameters,
    build_version_body,
    build_version_frontmatter,
    exp_links_for,
    parse_parent_version,
    parse_replication_sibling,
    sibling_slug_for,
    slug_for,
)
from obsidian_strategy_queries import ActivationEvent, CohortCount  # noqa: E402

# -- fixture: volume_anomaly v2's real shape, 14 parameters -------------------

_VOLUME_ANOMALY_V2_SCHEMA: dict[str, Any] = {
    "properties": {
        "fee_bps": {
            "type": ["string", "number"],
            "pattern": r"^-?[0-9]+(\.[0-9]+)?$",
            "description": "assumed fee per side, bps",
        },
        "atr_bars": {
            "type": ["string", "integer"],
            "pattern": r"^-?[0-9]+$",
            "description": "bars the ATR is recomputed from",
        },
        "horizon_s": {
            "type": ["string", "integer"],
            "pattern": r"^-?[0-9]+$",
            "description": "expected holding, seconds",
        },
        "atr_period": {
            "type": ["string", "integer"],
            "pattern": r"^-?[0-9]+$",
            "description": "Wilder ATR period",
        },
        "return_min": {
            "type": ["string", "number"],
            "pattern": r"^-?[0-9]+(\.[0-9]+)?$",
            "description": "return floor",
        },
        "target_atr": {
            "type": ["string", "number"],
            "pattern": r"^-?[0-9]+(\.[0-9]+)?$",
            "description": "target distance, in ATR",
        },
        "volume_mult": {
            "type": ["string", "number"],
            "pattern": r"^-?[0-9]+(\.[0-9]+)?$",
            "description": "spike multiplier",
        },
        "slippage_bps": {
            "type": ["string", "number"],
            "pattern": r"^-?[0-9]+(\.[0-9]+)?$",
            "description": "assumed slippage per side, bps",
        },
        "atr_timeframe": {
            "type": "string",
            "enum": ["1m", "5m", "15m", "1h"],
            "description": "timeframe the ATR is computed on",
        },
        "volume_window": {
            "type": ["string", "integer"],
            "pattern": r"^-?[0-9]+$",
            "description": "bars in the volume baseline",
        },
        "return_max_atr": {
            "type": ["string", "number"],
            "pattern": r"^-?[0-9]+(\.[0-9]+)?$",
            "description": "return ceiling, in ATR",
        },
        "base_confidence": {
            "type": ["string", "number"],
            "pattern": r"^-?[0-9]+(\.[0-9]+)?$",
            "description": "uncalibrated constant confidence",
        },
        "max_entry_delay_s": {
            "type": ["string", "integer"],
            "pattern": r"^-?[0-9]+$",
            "description": "max seconds to entry open",
        },
        "assumed_spread_bps": {
            "type": ["string", "number"],
            "pattern": r"^-?[0-9]+(\.[0-9]+)?$",
            "description": "assumed total spread, bps",
        },
    },
    "required": [],
    "additionalProperties": False,
}

_VOLUME_ANOMALY_V2_DEFAULTS = {
    "fee_bps": "4",
    "atr_bars": "97",
    "horizon_s": "7200",
    "atr_period": "14",
    "return_min": "0",
    "target_atr": "1.5",
    "volume_mult": "4",
    "slippage_bps": "5",
    "atr_timeframe": "15m",
    "volume_window": "288",
    "return_max_atr": "2",
    "base_confidence": "0.5",
    "max_entry_delay_s": "120",
    "assumed_spread_bps": "2",
}


def test_build_parameters_returns_every_diameter_of_a_14_parameter_version() -> None:
    params = build_parameters(_VOLUME_ANOMALY_V2_SCHEMA, _VOLUME_ANOMALY_V2_DEFAULTS)

    assert len(params) == 14
    assert params == sorted(params, key=lambda p: p.name)  # deterministic order

    by_name = {p.name: p for p in params}
    atr_timeframe = by_name["atr_timeframe"]
    assert atr_timeframe.value == "15m"
    assert atr_timeframe.type == "string"
    assert atr_timeframe.bounds == "um de: 1m, 5m, 15m, 1h"
    assert atr_timeframe.description == "timeframe the ATR is computed on"

    volume_mult = by_name["volume_mult"]
    assert volume_mult.value == "4"
    assert volume_mult.type == "string | number"
    assert volume_mult.bounds == r"regex `^-?[0-9]+(\.[0-9]+)?$`"
    assert volume_mult.description == "spike multiplier"


def test_build_parameters_marks_a_default_missing_from_the_schema() -> None:
    schema = {"properties": {"a": {"type": "string", "description": "known"}}}
    defaults = {"a": "1", "b": "2"}  # "b" has no schema entry — shouldn't happen, shown anyway

    params = build_parameters(schema, defaults)

    by_name = {p.name: p for p in params}
    assert by_name["a"].type == "string"
    assert by_name["b"].type == "(fora do schema)"
    assert by_name["b"].value == "2"


def test_build_parameters_empty_schema_and_defaults_is_an_empty_list() -> None:
    assert build_parameters({}, {}) == []


def test_version_body_renders_the_14_parameter_table_with_every_row() -> None:
    params = build_parameters(_VOLUME_ANOMALY_V2_SCHEMA, _VOLUME_ANOMALY_V2_DEFAULTS)

    body = build_version_body(
        strategy_key="volume_anomaly",
        version="v2",
        purpose="research_only",
        changelog="succeeds v1: code moved",
        params=params,
        events=[],
        cohorts=[CohortCount(cohort="prospective", count=18)],
        exp_links=exp_links_for("volume_anomaly", "research_only"),
        replication_status=None,
        derived_from_slug=slug_for("volume_anomaly", "v1", "research_only"),
    )

    params_section = body.split("## Origem")[0]
    param_rows = [line for line in params_section.splitlines() if line.startswith("| `")]
    assert len(param_rows) == 14
    assert "volume_anomaly-v1" in body
    assert "EXP-0002-volume-anomaly-v1" in body
    assert "prospective" in body and "18" in body
    assert "não iniciada" in body
    assert "Risk Engine" not in body  # research_only, not paper

    # a "string | number" type must not add extra Markdown table columns: a
    # data row has exactly 6 *unescaped* pipes ("| a | b | c | d | e |") —
    # the type text's own "|" must come back escaped as "\|", never as a
    # column separator (assumed_spread_bps' type is "string | number").
    import re as _re

    for row in param_rows:
        unescaped = _re.findall(r"(?<!\\)\|", row)
        assert len(unescaped) == 6, row


# -- fixture: a paper line -----------------------------------------------------


def test_slug_for_a_paper_line_gets_the_paper_suffix() -> None:
    assert slug_for("momentum", "v3", "paper") == "momentum-v3-paper"
    assert slug_for("momentum", "v2", "research_only") == "momentum-v2"


def test_parse_parent_version_recognises_paper_line_and_supersede() -> None:
    assert parse_parent_version("paper line of v2 (D10, T3.15): the paper coorte") == "v2"
    assert parse_parent_version("succeeds v1: code moved") == "v1"
    assert parse_parent_version("first activation, no parent") is None
    assert parse_parent_version(None) is None


# -- fixture: a real T3.19 replication sibling (docs/plans/REPLICATION.md §4) --

_SIBLING_CHANGELOG = (
    "replication:3e655c2a-4ef1-492b-ae80-46ec6f26321c:3 | irmã 3 de v2 "
    "(T3.19, docs/plans/REPLICATION.md) | promising_at=2026-09-08T12:00:00+00:00 "
    "| seed=20260908 | pct=0.15 | jitter round"
)


def test_parse_replication_sibling_reads_the_real_arm_label() -> None:
    assert parse_replication_sibling(_SIBLING_CHANGELOG) == ("v2", 3)
    assert parse_replication_sibling("succeeds v1: code moved") is None
    assert parse_replication_sibling(None) is None


def test_parse_parent_version_also_recognises_a_sibling_changelog() -> None:
    assert parse_parent_version(_SIBLING_CHANGELOG) == "v2"


def test_sibling_slug_for_matches_the_briefs_own_example() -> None:
    assert sibling_slug_for("momentum", "v2", 3) == "momentum-v2-irma-03"


def test_paper_line_body_links_the_risk_engine_and_has_no_signals_yet() -> None:
    body = build_version_body(
        strategy_key="momentum",
        version="v3",
        purpose="paper",
        changelog="paper line of v2 (D10, T3.15): D10_coorte_paper",
        params=build_parameters({"properties": {}}, {}),
        events=[
            ActivationEvent(
                created_at=datetime(2026, 9, 8, 4, 34, 18, tzinfo=UTC),
                level="info",
                event="strategy_version_paper_line_derived",
                message="momentum v3 derived from v2 with purpose=paper",
            )
        ],
        cohorts=[],
        exp_links=exp_links_for("momentum", "paper"),
        replication_status=None,
        derived_from_slug=slug_for("momentum", "v2", "research_only"),
    )

    assert "Risk Engine" in body
    assert "Nenhum sinal emitido ainda." in body
    assert "EXP-0005-momentum-paper" in body
    assert "momentum-v2" in body
    assert "strategy_version_paper_line_derived" in body


def test_frontmatter_quotes_a_code_ref_with_a_colon_and_an_at_sign() -> None:
    frontmatter = build_version_frontmatter(
        strategy_key="momentum",
        version="v3",
        purpose="paper",
        status="draft",
        code_ref="hunter_core.strategies.momentum_v1@sha256:ab2e0398",
        params_hash="deadbeef",
        activated_at=None,
        deprecated_at=None,
        derived_from_slug="momentum-v2",
        cohorts=[],
        exp_links=exp_links_for("momentum", "paper"),
        updated=date(2026, 9, 8),
    )

    assert 'code_ref: "hunter_core.strategies.momentum_v1@sha256:ab2e0398"' in frontmatter
    assert 'derived_from: "[[momentum-v2]]"' in frontmatter
    assert 'exp: ["[[EXP-0005-momentum-paper]]"]' in frontmatter
    assert 'activated_at: ""' in frontmatter
    assert "updated: 2026-09-08" in frontmatter


# -- fixture: a replication sibling with a cohort ------------------------------


def test_version_body_lists_a_replication_sibling_and_its_cohort() -> None:
    body = build_version_body(
        strategy_key="momentum",
        version="v2",
        purpose="research_only",
        changelog="succeeds v1: digest moved",
        params=[
            ParamInfo(
                name="rvol_min",
                value="1.5",
                type="string | number",
                bounds="regex `x`",
                description="d",
            )
        ],
        events=[],
        cohorts=[CohortCount(cohort="replay:irma-03", count=42)],
        exp_links=(),
        replication_status="em andamento — braço INV-B, ver docs/plans/REPLICATION.md",
        derived_from_slug="momentum-v1",
        sibling_slugs=("momentum-v2-irma-03",),
    )

    assert "replay:irma-03" in body and "42" in body
    assert "momentum-v2-irma-03" in body
    assert "em andamento" in body


def test_extract_latest_result_takes_the_last_dated_evaluation() -> None:
    text = (
        "### Avaliacao de 2026-09-06\n- **Result:** **inconclusivo** — ...\n"
        "### Avaliacao de 2026-09-07\n- **Result:** **promissor** — ...\n"
    )
    assert extract_latest_result(text) == "promissor"
    assert extract_latest_result("no result section here") is None


def test_build_family_body_links_every_version_page() -> None:
    from obsidian_family_pages import FamilyEntry

    body = build_family_body(
        "momentum",
        [
            FamilyEntry(
                version="v1",
                purpose="research_only",
                status="deprecated",
                slug="momentum-v1",
                verdict="inconclusivo",
            ),
            FamilyEntry(version="v2", purpose="research_only", status="active", slug="momentum-v2"),
            FamilyEntry(version="v3", purpose="paper", status="draft", slug="momentum-v3-paper"),
        ],
    )

    assert "[[momentum-v1]]" in body
    assert "[[momentum-v2]]" in body
    assert "[[momentum-v3-paper]]" in body
    assert "inconclusivo" in body
