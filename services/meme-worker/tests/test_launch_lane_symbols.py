"""``launch_lane_symbols.RecentSymbols`` — the 60-second, in-memory ticker
clone guard (T4.67a), pure."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hunter_meme_worker.launch_lane_symbols import RecentSymbols, normalize_symbol

T0 = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)


def test_normalize_folds_case_and_surrounding_whitespace() -> None:
    assert normalize_symbol(" PUMP ") == normalize_symbol("pump")
    assert normalize_symbol("Pump") == "pump"


def test_a_mint_is_never_its_own_clone() -> None:
    recent = RecentSymbols()
    assert recent.is_recent_clone("PUMP", T0) is False
    recent.observe("PUMP", T0)
    assert len(recent) == 1


def test_the_same_symbol_within_the_window_is_a_clone() -> None:
    recent = RecentSymbols()
    recent.observe("MOON", T0)
    assert recent.is_recent_clone("moon", T0 + timedelta(seconds=59)) is True
    assert recent.is_recent_clone("MOON ", T0 + timedelta(seconds=59)) is True


def test_a_different_symbol_is_not_a_clone() -> None:
    recent = RecentSymbols()
    recent.observe("MOON", T0)
    assert recent.is_recent_clone("SUN", T0 + timedelta(seconds=1)) is False


def test_the_symbol_ages_out_of_the_window() -> None:
    recent = RecentSymbols()
    recent.observe("MOON", T0)
    assert recent.is_recent_clone("MOON", T0 + timedelta(seconds=61)) is False
    assert len(recent) == 0, "pruned on read, not left to grow unbounded"


def test_a_refused_create_is_still_observed_for_the_next_arrival() -> None:
    recent = RecentSymbols()
    recent.observe("DOGE", T0)
    recent.observe("DOGE", T0 + timedelta(seconds=1))
    assert recent.is_recent_clone("doge", T0 + timedelta(seconds=2)) is True
