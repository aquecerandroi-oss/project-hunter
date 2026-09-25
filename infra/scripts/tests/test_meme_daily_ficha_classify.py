"""``meme_daily_ficha_classify.py`` — the automatic loss class, pure.

No database. Run: ``uv run pytest infra/scripts/tests/test_meme_daily_ficha_classify.py -q``
"""

from __future__ import annotations

import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from meme_daily_ficha_classify import LossClassInputs, classify_loss, rose_after_buy  # noqa: E402

pytestmark = pytest.mark.unit


def _inputs(**overrides: object) -> LossClassInputs:
    fixed: dict[str, object] = {
        "pnl_sol": Decimal("-0.01"),
        "cost_sol": Decimal("0.07"),
        "high_water_sol": Decimal("0.08"),
        "exit_reason": "trailing",
        "distinct_sellers_one_slot": None,
        "since_prior_exit": None,
        "round_trip_cost_sol": Decimal("0.002"),
    }
    fixed.update(overrides)
    return LossClassInputs(**fixed)  # type: ignore[arg-type]


def test_a_winning_position_has_no_loss_class() -> None:
    assert classify_loss(_inputs(pnl_sol=Decimal("0.01"))) is None
    assert classify_loss(_inputs(pnl_sol=Decimal("0"))) is None


def test_comprou_no_topo_when_the_peak_never_beat_the_cost() -> None:
    assert (
        classify_loss(_inputs(high_water_sol=Decimal("0.06"), cost_sol=Decimal("0.07")))
        == "comprou_no_topo"
    )
    # the peak equal to the cost still counts (peak <= cost, not strictly less)
    assert (
        classify_loss(_inputs(high_water_sol=Decimal("0.07"), cost_sol=Decimal("0.07")))
        == "comprou_no_topo"
    )


def test_golpe_do_criador_by_exit_reason_or_by_the_chain() -> None:
    assert (
        classify_loss(_inputs(exit_reason="creator_dump", high_water_sol=Decimal("0.09")))
        == "golpe_do_criador"
    )
    assert (
        classify_loss(
            _inputs(
                exit_reason="dead",
                high_water_sol=Decimal("0.09"),
                distinct_sellers_one_slot=10,
            )
        )
        == "golpe_do_criador"
    )
    # nine distinct sellers in a slot is not yet the threshold
    assert (
        classify_loss(
            _inputs(
                exit_reason="dead",
                high_water_sol=Decimal("0.09"),
                distinct_sellers_one_slot=9,
            )
        )
        != "golpe_do_criador"
    )


def test_recompra_within_the_300s_pause_window() -> None:
    assert (
        classify_loss(
            _inputs(
                high_water_sol=Decimal("0.09"),
                exit_reason="dead",
                since_prior_exit=timedelta(seconds=299),
            )
        )
        == "recompra"
    )
    assert (
        classify_loss(
            _inputs(
                high_water_sol=Decimal("0.09"),
                exit_reason="dead",
                since_prior_exit=timedelta(seconds=301),
            )
        )
        != "recompra"
    )


def test_recompra_boundary_is_not_truncated_to_a_whole_second() -> None:
    """Astra (T4.92 review, MEDIUM): a 300,9 s gap must stay outside the <=300 s
    window -- an ``int()`` truncation used to read it as 300 and wrongly match."""
    assert (
        classify_loss(
            _inputs(
                high_water_sol=Decimal("0.09"),
                exit_reason="dead",
                since_prior_exit=timedelta(seconds=300.9),
            )
        )
        != "recompra"
    )
    assert (
        classify_loss(
            _inputs(
                high_water_sol=Decimal("0.09"),
                exit_reason="dead",
                since_prior_exit=timedelta(seconds=300),
            )
        )
        == "recompra"
    )


def test_custo_when_the_loss_is_smaller_than_the_round_trip_cost() -> None:
    assert (
        classify_loss(
            _inputs(
                pnl_sol=Decimal("-0.001"),
                high_water_sol=Decimal("0.09"),
                exit_reason="dead",
                round_trip_cost_sol=Decimal("0.0016"),
            )
        )
        == "custo"
    )


def test_saida_normal_is_the_catch_all() -> None:
    assert (
        classify_loss(
            _inputs(
                pnl_sol=Decimal("-0.03"),
                high_water_sol=Decimal("0.09"),
                exit_reason="dead",
                round_trip_cost_sol=Decimal("0.0016"),
            )
        )
        == "saida_normal"
    )


def test_missing_inputs_never_invent_a_class_the_rule_is_skipped() -> None:
    # no high_water, no creator_dump, no sellers-in-a-slot data, no prior exit,
    # no round-trip cost: nothing to prove any of the first four rules -> saida_normal
    assert (
        classify_loss(
            _inputs(
                high_water_sol=None,
                exit_reason="dead",
                distinct_sellers_one_slot=None,
                since_prior_exit=None,
                round_trip_cost_sol=None,
            )
        )
        == "saida_normal"
    )


def test_order_comprou_no_topo_wins_over_golpe_do_criador() -> None:
    """Both rules match; the first in the documented order (comprou_no_topo) wins."""
    assert (
        classify_loss(
            _inputs(
                high_water_sol=Decimal("0.05"),
                cost_sol=Decimal("0.07"),
                exit_reason="creator_dump",
            )
        )
        == "comprou_no_topo"
    )


def test_rose_after_buy_is_none_without_a_recorded_mark() -> None:
    assert rose_after_buy(high_water_sol=None, cost_sol=Decimal("0.07")) is None
    assert rose_after_buy(high_water_sol=Decimal("0.08"), cost_sol=Decimal("0.07")) is True
    assert rose_after_buy(high_water_sol=Decimal("0.05"), cost_sol=Decimal("0.07")) is False
