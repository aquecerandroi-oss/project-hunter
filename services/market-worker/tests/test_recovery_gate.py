"""L3: run_recovery's cadence gate, pinned as pure unit tests.

Split out of ``test_recovery.py`` (which is an integration module and was at
the 350-line budget); an inverted operator here would silently change the
gap-detection frequency with nothing failing.
"""

from __future__ import annotations

from hunter_market_worker import recovery


def test_should_check_gate_no_check_before_interval() -> None:
    gate = recovery._should_check  # pyright: ignore[reportPrivateUsage]
    assert gate(50.0, 0.0, 0, 0, ["BTCUSDT"]) is False


def test_should_check_gate_checks_at_the_interval() -> None:
    gate = recovery._should_check  # pyright: ignore[reportPrivateUsage]
    assert gate(float(recovery.CHECK_INTERVAL_S), 0.0, 0, 0, ["BTCUSDT"]) is True


def test_should_check_gate_checks_immediately_on_reconnect() -> None:
    gate = recovery._should_check  # pyright: ignore[reportPrivateUsage]
    assert gate(1.0, 0.0, reconnects=1, last_reconnects=0, symbols=["BTCUSDT"]) is True


def test_should_check_gate_never_checks_an_empty_universe() -> None:
    gate = recovery._should_check  # pyright: ignore[reportPrivateUsage]
    assert gate(10_000.0, 0.0, reconnects=5, last_reconnects=0, symbols=[]) is False
