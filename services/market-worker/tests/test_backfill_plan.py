"""Turning one ``market.backfill.requested`` window into ``ingestion_gaps`` rows.

Pure unit tests: no Postgres, no Redis. Everything here is arithmetic over
minutes — the half-open request interval of the scanner
(``hunter_scanner_worker.backfill``) against the **inclusive** interval
``recovery.expected_times`` reads, the ceiling per request, the coverage
already held, and the row budget of one pass.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hunter_market_worker import backfill_plan as plan

MINUTE = timedelta(minutes=1)


def at(hour: int, minute: int, *, day: int = 3) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def minutes(start: datetime, count: int) -> set[datetime]:
    return {start + MINUTE * n for n in range(count)}


# --------------------------------------------------------------------------
# normalize_window: half-open -> inclusive, clamped, capped
# --------------------------------------------------------------------------


def test_the_half_open_request_becomes_an_inclusive_last_minute() -> None:
    window = plan.normalize_window(at(10, 0), at(10, 3), detection_last=at(23, 0))

    assert window.first_minute == at(10, 0)
    # 10:00, 10:01 and 10:02 are the three minutes named by [10:00, 10:03).
    assert window.last_minute == at(10, 2)
    assert window.minutes == 3
    assert not window.truncated


def test_the_window_is_clamped_to_the_last_minute_detection_would_look_at() -> None:
    # detection_last is align_open_time(server_now) - DETECTION_GRACE: the
    # newest minute the collector itself considers settled. Asking for the
    # minute still being written would open a gap for a candle that is simply
    # not closed yet.
    window = plan.normalize_window(at(10, 0), at(10, 30), detection_last=at(10, 5))

    assert window.last_minute == at(10, 5)
    assert window.minutes == 6


def test_a_window_entirely_in_the_future_is_refused() -> None:
    with pytest.raises(plan.Refused) as excinfo:
        plan.normalize_window(at(11, 0), at(11, 30), detection_last=at(10, 5))

    assert excinfo.value.reason == "future_window"


def test_an_empty_or_inverted_window_is_refused() -> None:
    with pytest.raises(plan.Refused) as excinfo:
        plan.normalize_window(at(10, 5), at(10, 5), detection_last=at(23, 0))

    assert excinfo.value.reason == "empty_window"


def test_a_naive_timestamp_is_refused_instead_of_being_assumed_utc() -> None:
    with pytest.raises(plan.Refused) as excinfo:
        plan.normalize_window(
            datetime(2026, 9, 3, 10, 0),  # noqa: DTZ001
            at(10, 30),
            detection_last=at(23, 0),
        )

    assert excinfo.value.reason == "naive_timestamp"


def test_seconds_inside_the_request_are_floored_to_whole_minutes() -> None:
    window = plan.normalize_window(
        at(10, 0) + timedelta(seconds=30),
        at(10, 3) + timedelta(seconds=45),
        detection_last=at(23, 0),
    )

    assert (window.first_minute, window.last_minute) == (at(10, 0), at(10, 2))


def test_a_request_longer_than_the_ceiling_keeps_the_most_recent_minutes() -> None:
    last = at(10, 0)
    # +499 with a half-open end one minute past ``last``: 500 minutes too many.
    first = last - MINUTE * (plan.MAX_REQUEST_MINUTES + 499)

    window = plan.normalize_window(first, last + MINUTE, detection_last=at(23, 0))

    assert window.truncated
    assert window.minutes == plan.MAX_REQUEST_MINUTES
    assert window.last_minute == last
    assert window.first_minute == last - MINUTE * (plan.MAX_REQUEST_MINUTES - 1)
    assert window.requested_minutes == plan.MAX_REQUEST_MINUTES + 500


# --------------------------------------------------------------------------
# plan_chunks: coverage subtraction, merging, chunking, row budget
# --------------------------------------------------------------------------


def test_an_untouched_window_becomes_chunks_that_cover_every_minute_once() -> None:
    window = plan.normalize_window(at(0, 0), at(0, 0, day=4), detection_last=at(23, 0, day=9))

    result = plan.plan_chunks(window, persisted=set(), blocked=set())

    assert result.planned_minutes == 1440
    assert result.deferred_minutes == 0
    assert all((end - start) / MINUTE + 1 <= plan.CHUNK_MINUTES for start, end in result.chunks)
    covered: set[datetime] = set()
    for start, end in result.chunks:
        assert start <= end
        covered |= minutes(start, int((end - start) / MINUTE) + 1)
    assert covered == minutes(at(0, 0), 1440)


def test_persisted_minutes_are_not_asked_for_again() -> None:
    window = plan.normalize_window(at(10, 0), at(11, 0), detection_last=at(23, 0))

    result = plan.plan_chunks(window, persisted=minutes(at(10, 0), 50), blocked=set())

    assert result.chunks == [(at(10, 50), at(10, 59))]
    assert result.planned_minutes == 10


def test_a_short_persisted_stretch_is_swallowed_instead_of_splitting_the_request() -> None:
    # 10:00-10:04 missing, 10:05-10:09 present, 10:10-10:14 missing. Refetching
    # the five present minutes is free (the upsert is by natural key) and one
    # row costs one REST call instead of two.
    window = plan.normalize_window(at(10, 0), at(10, 15), detection_last=at(23, 0))

    result = plan.plan_chunks(window, persisted=minutes(at(10, 5), 5), blocked=set())

    assert result.chunks == [(at(10, 0), at(10, 14))]


def test_a_long_persisted_stretch_splits_the_request_in_two() -> None:
    window = plan.normalize_window(at(10, 0), at(12, 0), detection_last=at(23, 0))

    result = plan.plan_chunks(window, persisted=minutes(at(10, 5), 90), blocked=set())

    assert result.chunks == [(at(10, 0), at(10, 4)), (at(11, 35), at(11, 59))]


def test_minutes_already_covered_by_an_open_gap_are_never_planned_again() -> None:
    window = plan.normalize_window(at(10, 0), at(11, 0), detection_last=at(23, 0))

    result = plan.plan_chunks(window, persisted=set(), blocked=minutes(at(10, 10), 20))

    assert result.chunks == [(at(10, 0), at(10, 9)), (at(10, 30), at(10, 59))]


def test_the_merge_never_reaches_across_a_gap_that_already_exists() -> None:
    """Astra, T2.5-backfill design review, must-fix 2.

    A ``failed`` gap sitting between two fresh holes is serving a cooldown
    (``recovery.FAILED_RETRY_AFTER_S``). Merging over it would recreate those
    minutes as a brand-new ``open`` gap and walk straight around the cooldown,
    which is the difference between "refetching a present minute is free" and
    "refetching a minute that is failing every time is a retry loop".
    """
    window = plan.normalize_window(at(10, 0), at(10, 15), detection_last=at(23, 0))

    result = plan.plan_chunks(window, persisted=set(), blocked=minutes(at(10, 5), 5))

    assert result.chunks == [(at(10, 0), at(10, 4)), (at(10, 10), at(10, 14))]


def test_a_window_that_is_already_complete_plans_nothing() -> None:
    window = plan.normalize_window(at(10, 0), at(11, 0), detection_last=at(23, 0))

    result = plan.plan_chunks(window, persisted=minutes(at(10, 0), 60), blocked=set())

    assert result.chunks == []
    assert result.planned_minutes == 0
    assert result.deferred_minutes == 0
    assert result.complete


def test_a_window_left_to_an_existing_gap_is_not_complete_even_with_no_new_rows() -> None:
    window = plan.normalize_window(at(10, 0), at(11, 0), detection_last=at(23, 0))

    result = plan.plan_chunks(
        window, persisted=minutes(at(10, 0), 30), blocked=minutes(at(10, 30), 30)
    )

    assert result.chunks == []
    assert not result.complete


def test_the_row_budget_keeps_the_newest_holes_and_reports_what_it_deferred() -> None:
    """A fragmented window: more separate holes than one pass may write.

    The kept rows are the **most recent** ones (they are what a baseline
    bootstrap needs first) and the rest is reported as deferred, which is what
    stops the consumer from marking the request finished — the next
    republication of the same ``event_id`` plans the older ones, because by
    then the newest are covered by the rows this pass created.
    """
    window = plan.normalize_window(at(0, 0), at(0, 0, day=4), detection_last=at(23, 0, day=9))
    # One missing minute every 120 minutes: 12 holes, all far enough apart that
    # the merge never joins them.
    present = minutes(at(0, 0), 1440) - {at(0, 0) + timedelta(minutes=120 * n) for n in range(12)}

    result = plan.plan_chunks(window, persisted=present, blocked=set(), max_rows=5)

    assert len(result.chunks) == 5
    assert result.chunks[-1] == (at(0, 0) + timedelta(minutes=120 * 11),) * 2
    assert result.chunks[0] == (at(0, 0) + timedelta(minutes=120 * 7),) * 2
    assert result.planned_minutes == 5
    assert result.deferred_minutes == 7
    assert not result.complete


def test_the_chunk_size_is_one_klines_page_and_the_ceiling_is_seven_days() -> None:
    """The two numbers a reviewer should be able to check without reading code.

    ``CHUNK_MINUTES`` must stay under ``_KLINES_PAGE_LIMIT`` (1500) so one gap
    is one REST page inside ``recovery.FETCH_TIMEOUT_S``, and the ceiling is
    the seven days of the baseline bootstrap window.
    """
    assert plan.CHUNK_MINUTES <= 1500
    assert plan.MAX_REQUEST_MINUTES == 7 * 24 * 60


def test_the_unsettled_tail_is_counted_and_not_forgotten() -> None:
    """Astra, T2.5-backfill diff review, must-fix 1.

    A window whose end reaches past ``detection_last`` is clamped, and the
    minutes cut off are **temporary** — they close in a few minutes. Recording
    them is what stops the consumer from marking the request processed and
    losing them at the republication.
    """
    window = plan.normalize_window(at(10, 0), at(10, 30), detection_last=at(10, 5))

    assert window.clamped_minutes == 24
    assert window.requested_minutes == 30
    assert not window.truncated


def test_a_window_entirely_in_the_past_clamps_nothing() -> None:
    window = plan.normalize_window(at(10, 0), at(10, 30), detection_last=at(23, 0))

    assert window.clamped_minutes == 0


def test_a_second_pass_plans_the_holes_the_row_budget_deferred() -> None:
    """Progress across republications, without the producer inventing a new id.

    The first pass keeps the newest holes; the rows it wrote are coverage, so
    the second pass — same window, same identity — sees them as blocked and
    plans the older ones.
    """
    window = plan.normalize_window(at(0, 0), at(0, 0, day=4), detection_last=at(23, 0, day=9))
    present = minutes(at(0, 0), 1440) - {at(0, 0) + timedelta(minutes=120 * n) for n in range(12)}

    first = plan.plan_chunks(window, persisted=present, blocked=set(), max_rows=5)
    written: set[datetime] = set()
    for start, end in first.chunks:
        written |= minutes(start, int((end - start) / MINUTE) + 1)
    second = plan.plan_chunks(window, persisted=present, blocked=written, max_rows=5)

    assert second.planned_minutes == 5
    assert second.deferred_minutes == 2
    assert set(second.chunks).isdisjoint(set(first.chunks))
    assert max(start for start, _ in second.chunks) < min(start for start, _ in first.chunks)


def test_the_word_and_the_mark_never_disagree() -> None:
    """``outcome_name`` says ``partial`` for exactly what withholds the mark."""
    window = plan.normalize_window(at(10, 0), at(11, 0), detection_last=at(23, 0))
    blocked_result = plan.plan_chunks(window, persisted=set(), blocked=minutes(at(10, 30), 30))
    left_out = blocked_result.deferred_minutes + blocked_result.blocked_minutes

    assert plan.outcome_name(blocked_result, window, left_out) == "partial"
    assert not blocked_result.complete

    clean = plan.plan_chunks(window, persisted=set(), blocked=set())
    assert plan.outcome_name(clean, window, 0) == "accepted"
    assert clean.complete


def test_a_pass_that_wrote_nothing_and_still_owes_minutes_says_partial() -> None:
    """The invariant: ``partial`` if and only if the mark is withheld.

    Seen in the operational recheck — a request whose tail had not closed yet
    planned no rows (everything settled was already persisted) and came out
    ``empty`` while the ``event_id`` was deliberately left unmarked. One word
    said "done", the acknowledgement said "not done".
    """
    window = plan.normalize_window(at(10, 0), at(11, 0), detection_last=at(10, 40))
    result = plan.plan_chunks(window, persisted=minutes(at(10, 0), 41), blocked=set())

    assert result.chunks == []
    assert plan.outcome_name(result, window, window.clamped_minutes) == "partial"
    assert plan.outcome_name(result, window, 0) == "empty"
