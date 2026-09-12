"""``infra/scripts/meme_close_stats.py`` — the ruler every lesson of the daily
close is measured with: IC 95 % by hour blocks, the paired contrast, terciles.

No database. Run: ``uv run pytest infra/scripts/tests/test_meme_close_stats.py -q``
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from meme_close_stats import (  # noqa: E402
    MIN_N,
    Sample,
    block_ci,
    block_contrast,
    passes_ruler,
    tercile_edges,
    tercile_label,
)

pytestmark = pytest.mark.unit


def _sample(values: list[str], blocks: list[str]) -> Sample:
    return Sample(blocks=tuple(blocks), values=tuple(Decimal(v) for v in values))


def test_the_interval_is_by_hour_blocks_deterministic_and_undefined_with_one_block() -> None:
    losers = _sample(
        ["-1", "-0.5", "-1", "-0.5", "-1", "-0.5"], ["09", "09", "10", "10", "11", "11"]
    )
    interval = block_ci(losers)
    assert interval.n == 6 and interval.blocks == 3
    assert interval.mean == Decimal("-0.75") and interval.total == Decimal("-4.5")
    assert interval.ci95 is not None
    low, high = interval.ci95
    assert Decimal("-1") <= low <= high <= Decimal("-0.5")
    assert block_ci(losers).ci95 == interval.ci95, "same seed, same interval"
    single = block_ci(_sample(["0.2", "-0.4"], ["09", "09"]))
    assert single.blocks == 1 and single.ci95 is None, "one block cannot be resampled"
    empty = block_ci(_sample([], []))
    assert empty.n == 0 and empty.mean is None and empty.total == Decimal(0)


def test_the_contrast_pairs_the_blocks_and_the_ruler_needs_thirty_ten_ten_and_three_blocks() -> (
    None
):
    blocks = [f"{9 + i % 6:02d}" for i in range(20)]
    same_slot = _sample(["-1"] * 20, blocks)
    others = _sample(["0.3", "-0.2"] * 10, blocks)
    contrast = block_contrast(same_slot, others)
    assert contrast.n_a == 20 and contrast.n_b == 20 and contrast.blocks == 6
    assert contrast.delta == Decimal("-1.05")
    assert contrast.ci95 is not None and contrast.ci95[1] < 0
    assert passes_ruler(contrast, total_n=40)
    assert not passes_ruler(contrast, total_n=MIN_N - 1), "n < 30 never passes"
    thin = block_contrast(_sample(["-1"] * 5, blocks[:5]), others)
    assert not passes_ruler(thin, total_n=40), "a cell below 10 never passes"
    noisy = block_contrast(
        _sample(["0.5", "-0.5"] * 10, blocks), _sample(["-0.5", "0.5"] * 10, blocks)
    )
    assert noisy.ci95 is not None and noisy.ci95[0] < 0 < noisy.ci95[1]
    assert not passes_ruler(noisy, total_n=40), "an interval that crosses zero never passes"
    two_blocks = block_contrast(
        _sample(["-1"] * 10, ["09", "10"] * 5), _sample(["1"] * 10, ["09", "10"] * 5)
    )
    assert not passes_ruler(two_blocks, total_n=40), "fewer than 3 blocks never passes"


def test_terciles_split_known_values_and_leave_the_unknown_apart() -> None:
    values = [Decimal(v) for v in ("1", "2", "3", "4", "5", "6", "7", "8", "9")]
    edges = tercile_edges(values)
    assert edges == (Decimal(3), Decimal(6))
    assert tercile_label(Decimal(2), edges) == "baixo (≤ 3)"
    assert tercile_label(Decimal(5), edges) == "médio (3–6)"
    assert tercile_label(Decimal(9), edges) == "alto (> 6)"
    assert tercile_label(None, edges) == "desconhecido"
    assert tercile_edges([Decimal(1)]) is None and tercile_label(Decimal(1), None) == "conhecido"
