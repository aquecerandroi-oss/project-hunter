"""``identity_breaker.py`` — the per-mint circuit breaker (T4.97b/R80 must-fix
1): opens after a run of by-mint failures, probes sparsely while open, closes
on the probe's success. Pure, no IO, no clock of its own — the caller passes
``now``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hunter_meme_worker.identity_breaker import IdentityBreaker

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def test_closed_breaker_never_filters_anything() -> None:
    breaker = IdentityBreaker(trip_threshold=5)
    mints = ("a", "b", "c")
    selected, suspended = breaker.filter(mints, T0)
    assert (selected, suspended) == (mints, ())
    assert not breaker.is_open


def test_it_opens_after_the_threshold_of_consecutive_failures_and_not_before() -> None:
    breaker = IdentityBreaker(trip_threshold=3)
    for _ in range(2):
        breaker.record_failure()
    assert not breaker.is_open
    breaker.record_failure()
    assert breaker.is_open


def test_open_it_suspends_everything_but_a_single_sparse_probe() -> None:
    breaker = IdentityBreaker(trip_threshold=1, probe_interval=timedelta(minutes=5))
    breaker.record_failure()
    assert breaker.is_open
    mints = ("a", "b", "c")
    selected, suspended = breaker.filter(mints, T0)
    assert selected == ("a",)
    assert suspended == ("b", "c")
    # Immediately after: the probe was just spent, none is due yet.
    selected_again, suspended_again = breaker.filter(mints, T0 + timedelta(seconds=1))
    assert selected_again == ()
    assert suspended_again == mints


def test_a_probe_is_granted_again_once_the_interval_has_passed() -> None:
    breaker = IdentityBreaker(trip_threshold=1, probe_interval=timedelta(minutes=5))
    breaker.record_failure()
    breaker.filter(("a", "b"), T0)  # spends the first probe (rotates to "a")
    too_soon = breaker.filter(("a", "b"), T0 + timedelta(minutes=4))
    assert too_soon == ((), ("a", "b"))
    due = breaker.filter(("a", "b"), T0 + timedelta(minutes=5))
    assert due == (("b",), ("a",)), "the next probe rotates off the mint just tried"


def test_the_probe_rotates_so_one_permanently_broken_mint_never_blocks_the_others() -> None:
    """Astra's must-fix (T4.97b review round 2): the breaker's job is to
    detect the *route* recovering, not one specific mint — a probe that
    always retried ``mints[0]`` would stay open forever if that one mint (not
    the route) never answers, even after every other mint would succeed."""
    breaker = IdentityBreaker(trip_threshold=1, probe_interval=timedelta(seconds=0))
    breaker.record_failure()
    mints = ("always_broken", "recovers")
    probed: list[str] = []
    for _ in range(4):
        selected, _ = breaker.filter(mints, T0)
        probed.extend(selected)
        breaker.record_failure()  # every probe still fails in this test
    assert "recovers" in probed, "the rotation must eventually offer the other mint"


def test_a_successful_probe_closes_the_breaker() -> None:
    breaker = IdentityBreaker(trip_threshold=1, probe_interval=timedelta(minutes=5))
    breaker.record_failure()
    assert breaker.is_open
    breaker.record_success()
    assert not breaker.is_open
    assert breaker.consecutive_failures == 0
    # Closed again: filter stops restricting immediately, no leftover cooldown.
    selected, suspended = breaker.filter(("a", "b"), T0)
    assert (selected, suspended) == (("a", "b"), ())


def test_a_failed_probe_stays_open_and_keeps_the_full_interval() -> None:
    breaker = IdentityBreaker(trip_threshold=1, probe_interval=timedelta(minutes=5))
    breaker.record_failure()
    breaker.filter(("a", "b"), T0)  # spends the probe on "a"
    breaker.record_failure()  # the probe itself failed
    assert breaker.is_open
    too_soon = breaker.filter(("a", "b"), T0 + timedelta(minutes=4))
    assert too_soon == ((), ("a", "b"))


def test_an_empty_candidate_list_is_never_treated_as_a_spent_probe() -> None:
    breaker = IdentityBreaker(trip_threshold=1, probe_interval=timedelta(minutes=5))
    breaker.record_failure()
    assert breaker.filter((), T0) == ((), ())
    # last_probe_at was never touched by the empty call, so a probe is still due now.
    selected, suspended = breaker.filter(("a",), T0)
    assert selected == ("a",)
    assert suspended == ()
