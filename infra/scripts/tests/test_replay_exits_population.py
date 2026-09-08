"""``replay_exits.py`` — the population selectors added by T3.32.

No database and no replay: what is checked here is the only thing the two new
flags may do — *narrow* the set of frozen entries a run folds — and the only
thing they must never do: change a run that did not ask for them.

A paired contrast is only meaningful inside one population. ``--versions`` names
a strategy *key*, so a plain ``--versions momentum`` folds four activated
versions and five coortes into one comparison, and the two replay coortes of
``momentum v2`` hold the same 224 entries twice under different ``signal_id``s.
Counting every pair twice would halve the standard error of a contrast without
adding one observation, which is the specific way this script could lie.

Run: ``uv run pytest infra/scripts/tests/test_replay_exits_population.py -q``
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _script() -> Any:
    """The ops script, loaded by path (it is not an importable module)."""
    path = SCRIPTS_DIR / "replay_exits.py"
    spec = importlib.util.spec_from_file_location("replay_exits_unit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["replay_exits_unit"] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class _Version:
    """Enough of ``VersionRow`` for the manifest filter: the label."""

    label: str


@dataclass(frozen=True)
class _Case:
    """Enough of ``ReplayCase`` for the coorte filter: the signal id."""

    signal_id: uuid.UUID


class _Rows:
    def __init__(self, rows: list[tuple[uuid.UUID, str]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[uuid.UUID, str]]:
        return self._rows


class _Session:
    """A session that answers the one SELECT ``keep_cohorts`` makes."""

    def __init__(self, labels: dict[uuid.UUID, str]) -> None:
        self._labels = labels
        self.executed = 0

    async def execute(self, _statement: object) -> _Rows:
        self.executed += 1
        return _Rows(list(self._labels.items()))


PROSPECTIVE = "prospective"
REPLAY_A = "replay:f8d8279c-1fba-42ae-95ef-202042f96c60"
REPLAY_B = "replay:7598d6c4-c8b6-430e-974e-3a5118d3a288"


def test_no_selector_is_the_r1_run() -> None:
    """Absent flags must leave both the manifest and the cases untouched."""
    module = _script()
    versions = [_Version("momentum_v1"), _Version("momentum_v2")]
    cases = [_Case(uuid.uuid4()) for _ in range(3)]
    session = _Session({})

    assert module.keep_versions(versions, labels=None) == versions
    assert asyncio.run(module.keep_cohorts(session, cases, cohorts=None)) == cases
    assert session.executed == 0, "no selector must not cost a query"


@pytest.mark.parametrize("raw", ["", "  ", " , "])
def test_an_empty_selector_is_no_selector(raw: str) -> None:
    """A flag that would filter everything away is refused as "not given"."""
    module = _script()
    assert module._labels(raw) is None
    assert module._labels(None) is None
    assert module._labels("momentum_v2, momentum_v4") == frozenset({"momentum_v2", "momentum_v4"})


def test_only_version_keeps_exactly_the_named_labels() -> None:
    module = _script()
    versions = [_Version("momentum_v1"), _Version("momentum_v2"), _Version("momentum_v4")]

    kept = module.keep_versions(versions, labels=frozenset({"momentum_v2"}))

    assert [version.label for version in kept] == ["momentum_v2"]


def test_a_label_the_manifest_does_not_have_stops_the_run() -> None:
    """Silently replaying a different population than the one asked for is the
    failure mode this refusal exists for."""
    module = _script()
    versions = [_Version("momentum_v1")]

    with pytest.raises(SystemExit, match="momentum_v9"):
        module.keep_versions(versions, labels=frozenset({"momentum_v9"}))


def test_cohort_keeps_one_population_out_of_three() -> None:
    """The same entry exists under two replay coortes; only one may be folded."""
    module = _script()
    live, arm_a, arm_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    cases = [_Case(live), _Case(arm_a), _Case(arm_b)]
    session = _Session({live: PROSPECTIVE, arm_a: REPLAY_A, arm_b: REPLAY_B})

    kept = asyncio.run(module.keep_cohorts(session, cases, cohorts=frozenset({REPLAY_A})))

    assert [case.signal_id for case in kept] == [arm_a]
    assert session.executed == 1


def test_a_cohort_that_selects_nothing_stops_the_run() -> None:
    """An empty population would render a document with no observations in it
    and a gate that "passed" over zero cases."""
    module = _script()
    only = uuid.uuid4()
    session = _Session({only: PROSPECTIVE})

    with pytest.raises(SystemExit, match="selected no frozen entry"):
        asyncio.run(module.keep_cohorts(session, [_Case(only)], cohorts=frozenset({REPLAY_A})))
