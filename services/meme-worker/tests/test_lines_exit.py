"""T4.10 — the support line projected to a snapshot's instant, and the streak
of closes below it, from durable rows and nothing else."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_meme_worker.lines_exit import SupportLine, below_support, next_streak, support_at

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 12, 12, 15, tzinfo=UTC)
LINES = [
    SupportLine(end_time=T0, support_sol=Decimal(48), slope_per_min=Decimal(1)),
    SupportLine(
        end_time=T0 + timedelta(minutes=1), support_sol=Decimal(50), slope_per_min=Decimal(2)
    ),
]


def test_the_newest_line_at_or_before_the_instant_is_projected_to_it() -> None:
    assert support_at(LINES, T0 + timedelta(seconds=30)) == Decimal("48.5")
    assert support_at(LINES, T0 + timedelta(minutes=1)) == Decimal(50)
    assert support_at(LINES, T0 + timedelta(minutes=2, seconds=30)) == Decimal(53)
    assert support_at(LINES, T0 - timedelta(seconds=1)) is None, (
        "a minute folded later is not known"
    )
    assert support_at([], T0) is None


def test_below_and_the_streak() -> None:
    assert below_support(Decimal(47), Decimal(48)) is True
    assert below_support(Decimal(48), Decimal(48)) is False
    assert below_support(None, Decimal(48)) is None
    assert below_support(Decimal(47), None) is None
    assert below_support(Decimal(47), Decimal(0)) is None
    assert next_streak(None, None) is None
    assert next_streak(3, None) is None
    assert next_streak(None, True) == 1
    assert next_streak(1, True) == 2
    assert next_streak(2, False) == 0
    assert next_streak(None, False) == 0
