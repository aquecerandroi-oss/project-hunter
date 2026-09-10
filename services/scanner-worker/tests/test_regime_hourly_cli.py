"""The hand crank's arithmetic: what ``--repair-days`` actually asks the job for.

``regime_hourly.main`` is the only way an operator reaches the deep repair, and
until T3.76 nothing pinned the two lines that make it work — ``days =
max(backfill_days, repair_days)`` and ``repair_hours = repair_days * 24``. That
matters more than it looks: an hour written ``UNKNOWN`` during warm-up **has** a
row, so the backfill rule never looks at it again (``regime_window``), and the
only thing that can heal it after a deep candle backfill is a repair window that
reaches back that far. Getting the multiplication wrong would leave the operator
reading "repaired 90 days" in the log while the job repaired 90 *hours* — a
failure that is invisible from the outside, which is exactly the kind this
package writes tests for.

No database and no clock: ``_run_once`` is replaced by a recorder, because what
is under test is the translation from flags to arguments, not the pass.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from hunter_scanner_worker import regime_hourly
from hunter_scanner_worker.regime_job import RegimeRun

CUT = datetime(2026, 9, 10, 14, 0, tzinfo=UTC)


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """``main`` without its pass: the keyword arguments ``_run_once`` received."""
    seen: dict[str, Any] = {}

    async def _fake(exchange: str, *, days: int, repair_hours: int) -> RegimeRun:
        seen.update(exchange=exchange, days=days, repair_hours=repair_hours)
        return RegimeRun(cut=CUT)

    def _no_logging(*_args: object, **_kwargs: object) -> None:
        """``configure_logging`` would reconfigure the whole process's logging."""

    def _no_settings() -> None:
        """``get_settings`` would demand a database URL this test never uses."""

    monkeypatch.setattr(regime_hourly, "_run_once", _fake)
    monkeypatch.setattr(regime_hourly, "configure_logging", _no_logging)
    monkeypatch.setattr(regime_hourly, "get_settings", _no_settings)
    return seen


def _main(recorded: dict[str, Any], argv: list[str]) -> dict[str, Any]:
    import sys

    original = sys.argv
    sys.argv = ["regime_hourly", *argv]
    try:
        assert regime_hourly.main() == 0
    finally:
        sys.argv = original
    return recorded


def test_the_default_pass_repairs_three_days_and_fills_thirty_one(
    recorded: dict[str, Any],
) -> None:
    """The shipped defaults, in hours, so a change to either is a diff to read."""
    assert _main(recorded, ["--once", "--exchange", "binance"]) == {
        "exchange": "binance",
        "days": 31,
        "repair_hours": 72,
    }


def test_repair_days_is_multiplied_by_twenty_four_not_passed_through(
    recorded: dict[str, Any],
) -> None:
    """``--repair-days 90`` means ninety **days**: 2160 hours, never 90."""
    assert _main(recorded, ["--once", "--repair-days", "90"])["repair_hours"] == 2160


def test_repair_days_raises_the_backfill_window_to_match(recorded: dict[str, Any]) -> None:
    """Asking to repair deeper than the window would ask for hours no rule owns.

    ``--repair-days 90`` alone is the T3.76 command: it must widen the backfill
    window to ninety days on its own, or the hours between day 31 and day 90 --
    the ones with no row at all -- would be excluded from the answer.
    """
    assert _main(recorded, ["--once", "--repair-days", "90"])["days"] == 90


def test_the_wider_of_the_two_windows_wins(recorded: dict[str, Any]) -> None:
    """A backfill wider than the repair keeps its own width."""
    argv = ["--once", "--exchange", "binance", "--backfill-days", "90", "--repair-days", "3"]
    assert _main(recorded, argv) == {"exchange": "binance", "days": 90, "repair_hours": 72}


def test_a_pass_without_once_is_refused(recorded: dict[str, Any]) -> None:
    """The cadence belongs to the scanner: a bare invocation may not run a pass."""
    with pytest.raises(SystemExit):
        _main(recorded, [])
    assert recorded == {}
