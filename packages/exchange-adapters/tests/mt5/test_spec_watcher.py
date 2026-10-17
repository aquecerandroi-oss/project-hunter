"""The specification watcher (contract §3.9, check 23): a changed spec or tick size refuses."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.mt5.spec import SpecSnapshot, SpecStatus, SpecWatcher

from .factories import SYMBOL

pytestmark = pytest.mark.unit


def snap(**over: Any) -> SpecSnapshot:
    base: dict[str, Any] = {
        "symbol": SYMBOL,
        "trade_tick_size": Decimal("5"),
        "trade_tick_value": Decimal("1"),
        "point": Decimal("1"),
        "digits": 0,
        "volume_min": Decimal("1"),
        "volume_step": Decimal("1"),
        "volume_max": Decimal("1000"),
        "trade_mode": 4,
        "filling_mode": 3,
        "expiration_mode": 15,
        "account_margin_mode": "exchange",
        "terminal_version": "5.4755",
        "package_version": "5.0.6231",
    }
    return SpecSnapshot(**{**base, **over})


def test_an_identical_read_is_ok_and_does_not_refuse() -> None:
    watcher = SpecWatcher(snap())
    assert watcher.observe(snap()) is SpecStatus.OK
    assert watcher.refuses_entries is False
    assert watcher.diffs == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trade_tick_size", Decimal("10")),
        ("trade_tick_value", Decimal("2")),
        ("point", Decimal("0.5")),
        ("digits", 1),
        ("volume_min", Decimal("2")),
        ("volume_step", Decimal("2")),
        ("volume_max", Decimal("10")),
        ("trade_mode", 3),
        ("filling_mode", 1),
        ("expiration_mode", 1),
        ("account_margin_mode", "retail_netting"),
        ("terminal_version", "5.4800"),
        ("package_version", "5.0.9999"),
        ("symbol", "WINJ27"),
    ],
)
def test_any_pinned_field_that_differs_refuses_and_names_the_field(
    field: str, value: object
) -> None:
    watcher = SpecWatcher(snap())
    assert watcher.observe(snap(**{field: value})) is SpecStatus.CHANGED
    assert watcher.refuses_entries is True
    assert [d.field for d in watcher.diffs] == [field]
    assert watcher.diffs[0].pinned != watcher.diffs[0].now


def test_a_good_read_never_clears_a_divergence_already_seen() -> None:
    watcher = SpecWatcher(snap())
    watcher.observe(snap(trade_tick_size=Decimal("10")))
    assert watcher.observe(snap()) is SpecStatus.CHANGED  # back to normal, still refused
    assert watcher.refuses_entries is True
    assert [d.field for d in watcher.diffs] == ["trade_tick_size"]


def test_failures_below_the_limit_do_not_refuse_three_in_a_row_do() -> None:
    watcher = SpecWatcher(snap())
    assert watcher.observe_failure() is SpecStatus.OK
    assert watcher.observe_failure() is SpecStatus.OK
    assert watcher.observe_failure() is SpecStatus.UNREADABLE
    assert watcher.refuses_entries is True


def test_a_good_read_between_failures_resets_the_count() -> None:
    watcher = SpecWatcher(snap())
    watcher.observe_failure()
    watcher.observe_failure()
    watcher.observe(snap())
    assert watcher.observe_failure() is SpecStatus.OK
    assert watcher.consecutive_failures == 1


def test_unreadable_clears_with_a_matching_read_but_changed_does_not() -> None:
    watcher = SpecWatcher(snap())
    for _ in range(3):
        watcher.observe_failure()
    assert watcher.observe(snap()) is SpecStatus.OK
    watcher.observe(snap(digits=2))
    for _ in range(3):
        watcher.observe_failure()
    assert watcher.status is SpecStatus.CHANGED  # unreadable never downgrades a change


def test_diffs_accumulate_across_reads() -> None:
    watcher = SpecWatcher(snap())
    watcher.observe(snap(trade_tick_size=Decimal("10")))
    watcher.observe(snap(trade_tick_size=Decimal("10"), volume_step=Decimal("2")))
    assert {d.field for d in watcher.diffs} == {"trade_tick_size", "volume_step"}


def test_rearm_with_a_new_pin_is_the_only_way_back() -> None:
    watcher = SpecWatcher(snap())
    watcher.observe(snap(trade_tick_size=Decimal("10")))
    new_pin = snap(trade_tick_size=Decimal("10"))
    watcher.rearm(new_pin)
    assert watcher.status is SpecStatus.OK
    assert watcher.diffs == ()
    assert watcher.pin == new_pin
    assert watcher.observe(new_pin) is SpecStatus.OK


def test_the_snapshot_refuses_floats() -> None:
    with pytest.raises(TypeError, match="float"):
        snap(trade_tick_size=5.0)
