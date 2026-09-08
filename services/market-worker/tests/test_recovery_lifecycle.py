"""T3.7d item 3, pinned as pure unit tests: a `failed` gap reopens a bounded
number of times, with doubling backoff, then becomes `unrecoverable`
(`reason=exhausted`) instead of looping forever.

``reopen_stale_failed`` only ever reads/writes plain attributes on whatever it
is handed (no session, no query) — a ``SimpleNamespace`` stands in for
``IngestionGap`` exactly like ``test_recovery_gate.py``'s ``_open_gap()``.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from hunter_core.domain.types import utcnow
from hunter_market_worker import recovery_lifecycle

pytestmark = pytest.mark.unit

MAX_ATTEMPTS = 5
RETRY_AFTER_S = 3600.0


def _failed_gap(attempts: int, detected_at: Any, market_id: int = 1) -> Any:
    return SimpleNamespace(
        status="failed",
        attempts=attempts,
        detected_at=detected_at,
        market_id=market_id,
        gap_start=utcnow(),
        gap_end=utcnow(),
    )


def test_a_failed_gap_within_its_cooldown_is_not_reopened() -> None:
    now = utcnow()
    gap = _failed_gap(MAX_ATTEMPTS, now - timedelta(seconds=10))

    reopened, exhausted = recovery_lifecycle.reopen_stale_failed(
        {1: [gap]}, now, 20, retry_after_s=RETRY_AFTER_S, max_attempts=MAX_ATTEMPTS
    )

    assert (reopened, exhausted) == (0, [])
    assert gap.status == "failed"


def test_a_failed_gap_past_its_cooldown_reopens_without_resetting_attempts() -> None:
    """T3.7d: unlike before this task, a reopen never zeroes ``attempts`` —
    the column stays the true, cumulative total."""
    now = utcnow()
    gap = _failed_gap(MAX_ATTEMPTS, now - timedelta(seconds=RETRY_AFTER_S + 1))

    reopened, exhausted = recovery_lifecycle.reopen_stale_failed(
        {1: [gap]}, now, 20, retry_after_s=RETRY_AFTER_S, max_attempts=MAX_ATTEMPTS
    )

    assert (reopened, exhausted) == (1, [])
    assert gap.status == "open"
    assert gap.attempts == MAX_ATTEMPTS  # unchanged -- never reset


def test_backoff_doubles_with_every_life() -> None:
    """life_count = 2 (``attempts = 2 * MAX_ATTEMPTS``): the cooldown for its
    *next* reopen is ``2 * RETRY_AFTER_S``, not the base value again."""
    now = utcnow()
    just_short = now - timedelta(seconds=2 * RETRY_AFTER_S - 1)
    gap = _failed_gap(2 * MAX_ATTEMPTS, just_short)

    reopened, _ = recovery_lifecycle.reopen_stale_failed(
        {1: [gap]},
        now,
        20,
        retry_after_s=RETRY_AFTER_S,
        max_attempts=MAX_ATTEMPTS,
        max_reopens=3,
    )
    assert reopened == 0  # one second short of the doubled cooldown

    gap.detected_at = now - timedelta(seconds=2 * RETRY_AFTER_S + 1)
    reopened, _ = recovery_lifecycle.reopen_stale_failed(
        {1: [gap]},
        now,
        20,
        retry_after_s=RETRY_AFTER_S,
        max_attempts=MAX_ATTEMPTS,
        max_reopens=3,
    )
    assert reopened == 1
    assert gap.status == "open"


def test_a_gap_past_max_reopens_is_exhausted_regardless_of_cooldown() -> None:
    """The incident's exact failure mode: a gap that can never actually
    succeed must stop being reopened *at all*, not merely less often. Cooldown
    is irrelevant once the life count is past the cap -- ``detected_at`` here
    is `now` itself, deep inside every cooldown, and it is still exhausted."""
    now = utcnow()
    gap = _failed_gap(2 * MAX_ATTEMPTS, now)  # life_count = 2

    reopened, exhausted = recovery_lifecycle.reopen_stale_failed(
        {1: [gap]},
        now,
        20,
        retry_after_s=RETRY_AFTER_S,
        max_attempts=MAX_ATTEMPTS,
        max_reopens=1,
    )

    assert reopened == 0
    assert exhausted == [gap]
    assert gap.status == "unrecoverable"


def test_reopen_and_exhausted_are_both_bounded_per_cycle() -> None:
    now = utcnow()
    stale = now - timedelta(seconds=RETRY_AFTER_S + 1)
    reopenable = [_failed_gap(MAX_ATTEMPTS, stale, market_id=i) for i in range(3)]
    doomed = [_failed_gap(3 * MAX_ATTEMPTS, now, market_id=100 + i) for i in range(3)]

    reopened, exhausted = recovery_lifecycle.reopen_stale_failed(
        {g.market_id: [g] for g in (*reopenable, *doomed)},
        now,
        4,  # fewer than the 6 candidates
        retry_after_s=RETRY_AFTER_S,
        max_attempts=MAX_ATTEMPTS,
        max_reopens=1,
    )

    assert reopened + len(exhausted) == 4
    untouched = [g for g in (*reopenable, *doomed) if g.status == "failed"]
    assert len(untouched) == 2  # the two the per-cycle budget never reached


def test_an_open_or_recovered_gap_is_never_touched() -> None:
    now = utcnow()
    open_gap: Any = SimpleNamespace(
        status="open", attempts=1, detected_at=now, market_id=1, gap_start=now, gap_end=now
    )
    recovered_gap: Any = SimpleNamespace(
        status="recovered", attempts=1, detected_at=now, market_id=1, gap_start=now, gap_end=now
    )

    reopened, exhausted = recovery_lifecycle.reopen_stale_failed(
        {1: [open_gap, recovered_gap]},
        now,
        20,
        retry_after_s=RETRY_AFTER_S,
        max_attempts=MAX_ATTEMPTS,
    )

    assert (reopened, exhausted) == (0, [])
    assert open_gap.status == "open"
    assert recovered_gap.status == "recovered"


def test_max_reopens_defaults_to_the_module_constant_read_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pinned so a monkeypatch of the module attribute actually changes this
    function's behaviour instead of being shadowed by a default argument
    bound once at import time."""
    monkeypatch.setattr(recovery_lifecycle, "MAX_REOPEN_ATTEMPTS", 0)
    now = utcnow()
    gap = _failed_gap(MAX_ATTEMPTS, now)  # life_count = 1, now > the patched cap of 0

    reopened, exhausted = recovery_lifecycle.reopen_stale_failed(
        {1: [gap]}, now, 20, retry_after_s=RETRY_AFTER_S, max_attempts=MAX_ATTEMPTS
    )

    assert reopened == 0
    assert exhausted == [gap]
    assert gap.status == "unrecoverable"
