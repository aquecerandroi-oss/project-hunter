"""``derive_variant.py`` — the pure half: overrides, canonical form and lineage.

No database. What is checked here is the part of T3.26 that has to hold before
any row is written: an override is parsed, canonicalised and validated against
the parent's *frozen* schema, and the ``changelog`` it produces is the exact
string the two readers downstream expect —
``hunter_strategy_worker.activate_derived.LINEAGE_RE`` (which keeps the lineage
alive across activation) and ``obsidian_strategy_pages.parse_parent_version``
(which turns it into a link in the catalogue).

Run: ``uv run pytest infra/scripts/tests/test_derive_variant_lineage.py -q``
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from obsidian_strategy_pages import parse_parent_version  # noqa: E402

from hunter_core.strategies.canonical import params_hash  # noqa: E402
from hunter_core.strategies.momentum_v1 import MOMENTUM_V1  # noqa: E402
from hunter_strategy_worker.activate_derived import LINEAGE_RE, keep_lineage  # noqa: E402


def _script() -> Any:
    """The ops script, loaded by path (it is not an importable module)."""
    path = SCRIPTS_DIR / "derive_variant.py"
    spec = importlib.util.spec_from_file_location("derive_variant_unit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["derive_variant_unit"] = module
    spec.loader.exec_module(module)
    return module


DV = _script()

FROZEN_SCHEMA: dict[str, Any] = dict(MOMENTUM_V1.parameters_schema)
FROZEN_PARAMS: dict[str, Any] = {
    name: str(value) for name, value in MOMENTUM_V1.default_parameters.items()
}
"""``momentum_v1``'s own contract, in the wire shape a JSONB round trip gives:
``params_format = 1`` normalises every number to a string (``canonical.py``)."""


class TestParsingOverrides:
    def test_it_splits_on_the_first_equals_only(self) -> None:
        assert DV.parse_overrides(["atr_pct_min=0.0089"]) == {"atr_pct_min": "0.0089"}

    def test_it_refuses_a_pair_without_an_equals(self) -> None:
        with pytest.raises(DV.Refused, match="parametro=valor"):
            DV.parse_overrides(["atr_pct_min"])

    def test_it_refuses_the_same_parameter_twice(self) -> None:
        with pytest.raises(DV.Refused, match="aparece duas vezes"):
            DV.parse_overrides(["atr_pct_min=0.0089", "atr_pct_min=0.01"])

    def test_it_refuses_a_pipe_because_the_changelog_uses_it_as_a_separator(self) -> None:
        with pytest.raises(DV.Refused, match="não pode conter"):
            DV.parse_overrides(["atr_pct_min=0.0089 | derived_from=v9"])


class TestBuildingTheVariantParameters:
    def test_the_override_moves_and_nothing_else_does(self) -> None:
        params, changes = DV.build_parameters(
            FROZEN_SCHEMA, FROZEN_PARAMS, {"atr_pct_min": "0.0089"}
        )
        assert changes == [("atr_pct_min", "0.003", "0.0089")]
        assert params["atr_pct_min"] == "0.0089"
        assert {k: v for k, v in params.items() if k != "atr_pct_min"} == {
            k: v for k, v in FROZEN_PARAMS.items() if k != "atr_pct_min"
        }
        assert params_hash(params) != params_hash(FROZEN_PARAMS)

    def test_a_differently_spelled_same_number_is_not_a_variant(self) -> None:
        """``0.00300`` is ``0.003``: canonical form first, comparison after —
        otherwise two spellings of one experiment would get two params_hash."""
        with pytest.raises(DV.Refused, match="nenhum parâmetro se moveu"):
            DV.build_parameters(FROZEN_SCHEMA, FROZEN_PARAMS, {"atr_pct_min": "0.00300"})

    def test_the_value_is_canonicalised_not_copied(self) -> None:
        params, changes = DV.build_parameters(
            FROZEN_SCHEMA, FROZEN_PARAMS, {"atr_pct_min": "0.00890"}
        )
        assert params["atr_pct_min"] == "0.0089"
        assert changes == [("atr_pct_min", "0.003", "0.0089")]

    def test_it_refuses_a_parameter_the_frozen_schema_does_not_declare(self) -> None:
        with pytest.raises(DV.Refused, match="não declara esse parâmetro"):
            DV.build_parameters(FROZEN_SCHEMA, FROZEN_PARAMS, {"invalidation_closes": "2"})

    def test_it_refuses_a_value_that_does_not_validate(self) -> None:
        with pytest.raises(DV.Refused, match="não validam contra o schema"):
            DV.build_parameters(FROZEN_SCHEMA, FROZEN_PARAMS, {"atr_timeframe": "30m"})

    def test_it_refuses_a_fraction_where_the_schema_wants_a_whole_number(self) -> None:
        with pytest.raises(DV.Refused, match="não validam contra o schema"):
            DV.build_parameters(FROZEN_SCHEMA, FROZEN_PARAMS, {"lookback_closes": "20.5"})

    def test_it_refuses_deriving_nothing(self) -> None:
        with pytest.raises(DV.Refused, match="sem --set"):
            DV.build_parameters(FROZEN_SCHEMA, FROZEN_PARAMS, {})

    def test_two_overrides_at_once_are_both_recorded(self) -> None:
        params, changes = DV.build_parameters(
            FROZEN_SCHEMA, FROZEN_PARAMS, {"atr_pct_min": "0.0089", "rvol_min": "2"}
        )
        assert changes == [("atr_pct_min", "0.003", "0.0089"), ("rvol_min", "1.5", "2")]
        assert params["rvol_min"] == "2"


class TestTheLineageContract:
    """The one string three tools have to agree on."""

    def _changelog(self) -> str:
        params, changes = DV.build_parameters(
            FROZEN_SCHEMA, FROZEN_PARAMS, {"atr_pct_min": "0.0089"}
        )
        return DV.variant_changelog("v2", changes, params_hash(params), "KB-0008: piso de custo")

    def test_it_reads_like_a_sentence_and_names_the_override(self) -> None:
        assert self._changelog().startswith(
            "variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.0089 | params_hash="
        )
        assert self._changelog().endswith(" | KB-0008: piso de custo")

    def test_the_activation_keeps_the_lineage_in_front_of_the_new_note(self) -> None:
        frozen = self._changelog()
        kept = keep_lineage(frozen, "ativada para a coorte prospectiva")
        assert kept.startswith("variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.0089")
        assert kept.endswith(" | ativada para a coorte prospectiva")
        assert parse_parent_version(kept) == "v2"

    def test_a_paper_line_changelog_is_left_exactly_as_it_was(self) -> None:
        assert keep_lineage("paper line of v1 (D10, T3.15): x", "D10 met") == "D10 met"

    def test_both_spellings_of_the_frozen_prefix_agree(self) -> None:
        """``derive_variant.LINEAGE_RE`` and ``activate_derived.LINEAGE_RE`` are
        written out separately (a package cannot import ``infra/scripts``); this
        is the test that keeps the two copies honest."""
        assert DV.LINEAGE_RE.pattern == LINEAGE_RE.pattern
        changelog = self._changelog()
        match = LINEAGE_RE.match(changelog)
        assert match is not None
        assert DV.lineage_of(changelog) == match.group(0)

    def test_the_catalogue_exporter_links_the_variant_to_its_parent(self) -> None:
        assert parse_parent_version(self._changelog()) == "v2"

    def test_the_three_older_spellings_still_win_where_they_apply(self) -> None:
        assert parse_parent_version("succeeds v1: code moved") == "v1"
        assert parse_parent_version("paper line of v2 (D10, T3.15): x") == "v2"
        assert parse_parent_version("uma frase escrita à mão") is None
