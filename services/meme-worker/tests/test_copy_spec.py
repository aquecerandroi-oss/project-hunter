"""The copy rule set's parameters (EXP-M28 "Parâmetros congelados"): the seed and the lane read the
same names, a bad document is refused by name at load, never half-read."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_meme_worker.copy_spec import CopySpec

from .copy_support import LEADER_A, LEADER_B, PARAMS

pytestmark = pytest.mark.unit

FROZEN = {
    "clock": "copy",
    "leaders": [{"wallet": LEADER_A, "stratum": "regra"}, {"wallet": LEADER_B, "stratum": "regra"}],
    "size_sol": "0.05",
    "min_trigger_sol": "0.1",
    "exit_leader_drop_fraction": "0.5",
    "stop_fraction": "0.5",
    "time_cap_s": 3600,
    "exec_latency_s": "1.65",
    "fill_window_s": 30,
    "exit_window_s": 60,
    "max_attempts_per_leader_day": 20,
    "max_open_per_stratum": 100,
    "fee_pct": "1.25",
    "priority_fee_sol": "0.00005",
    "venues": ["curve"],
}


def _parse(**overrides: object) -> CopySpec:
    return CopySpec.from_params(id="x", name="copy_v0", version="1", params={**FROZEN, **overrides})


def test_the_frozen_experiment_parameters_parse_to_the_registered_numbers() -> None:
    spec = _parse()
    assert spec.size_sol == Decimal("0.05") and spec.min_trigger_sol == Decimal("0.1")
    assert spec.min_trigger_lamports == 100_000_000
    assert spec.exec_latency_s == Decimal("1.65") and spec.execution_latency_ms == 1650
    assert spec.exit_leader_drop_fraction == Decimal("0.5") and spec.stop_fraction == Decimal("0.5")
    assert (spec.time_cap_s, spec.fill_window_s, spec.exit_window_s) == (3600, 30, 60)
    assert (spec.max_attempts_per_leader_day, spec.max_open_per_stratum) == (20, 100)
    assert spec.fee_pct == Decimal("1.25") and spec.priority_fee_sol == Decimal("0.00005")
    assert spec.venues == ("curve",) and spec.wallets == {LEADER_A, LEADER_B}
    assert spec.label == "copy_v0/1"
    assert spec.act_on_unconfirmed is True  # decide on the first trustworthy signal by default


def test_the_test_fixture_params_use_the_same_names() -> None:
    assert set(FROZEN) - {"clock", "venues", "leaders"} <= set(PARAMS)


@pytest.mark.parametrize(
    ("override", "why"),
    [
        ({"leaders": []}, "name the set's stratum"),
        (
            {"stratum": "regra", "leaders": [{"wallet": LEADER_A, "stratum": "x"}]},
            "outside the set",
        ),
        ({"leaders": [{"wallet": LEADER_A, "stratum": "r"}] * 2}, "twice"),
        ({"stop_fraction": "1.5"}, "fraction"),
        ({"exit_leader_drop_fraction": "0"}, "fraction"),
        ({"size_sol": "0"}, "positive"),
        ({"venues": ["pumpswap"]}, "curve is always"),
        ({"time_cap_s": "3600"}, "bare non-negative JSON integer"),
        ({"size_sol": 0.05}, "float"),
    ],
)
def test_a_bad_document_is_refused_by_name(override: dict[str, object], why: str) -> None:
    with pytest.raises((ValueError, TypeError), match=why):
        _parse(**override)


def test_the_secondary_set_may_be_seeded_with_no_leader_and_is_never_the_primary() -> None:
    empty = _parse(leaders=[], stratum="escolha_everton")
    assert (
        empty.wallets == frozenset() and not empty.is_primary and empty.stratum == "escolha_everton"
    )
    assert _parse().is_primary and _parse().stratum == "regra"
    assert _parse().horizon_days == 30  # emenda 4


def test_a_retired_set_stops_accepting_entries_but_still_parses() -> None:
    spec = CopySpec.from_params(
        id="x", name="copy_v0", version="1", params=dict(FROZEN), status="retired"
    )
    assert not spec.accepting_entries and _parse().accepting_entries
