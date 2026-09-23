"""T4.82: the shared ``since``/``until`` window — validation and the server-side
cap, with no database anywhere near it.

Three endpoints of the confluence screen take the same pair (candles,
``/lab/shadow/signals``, ``/markets/.../desk``), so the rules live in one
module and are asserted once:

- an inverted or empty window is a 422, never an empty list (an empty list
  would read as "nothing happened here", which is a different fact);
- a window wider than the endpoint can answer completely is a 422 too, rather
  than a silent truncation that makes the caller believe it holds the whole
  period;
- naive datetimes never reach here — ``UtcDatetime``/``ensure_utc`` rejects
  them at the boundary — so everything below is tz-aware UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hunter_api.time_window import (
    TimeWindowTooWideError,
    TimeWindowUnorderedError,
    check_window,
    resolve_window,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 23, 14, 45, tzinfo=UTC)
HOUR = timedelta(hours=1)


class TestCheckWindow:
    """``check_window`` validates without defaulting — the candles endpoint
    stays backward compatible, where "neither bound given" means the plain
    ``limit`` most recent rows it has always answered."""

    def test_both_bounds_absent_is_allowed_and_caps_nothing(self) -> None:
        check_window(since=None, until=None, now=NOW, max_span=HOUR)

    def test_a_window_inside_the_cap_passes(self) -> None:
        check_window(since=NOW - HOUR, until=NOW, now=NOW, max_span=HOUR)

    @pytest.mark.parametrize(
        ("since", "until"),
        [
            (NOW, NOW),  # empty
            (NOW, NOW - timedelta(minutes=1)),  # inverted
        ],
    )
    def test_an_empty_or_inverted_window_is_refused(self, since: datetime, until: datetime) -> None:
        with pytest.raises(TimeWindowUnorderedError) as raised:
            check_window(since=since, until=until, now=NOW, max_span=HOUR)
        assert raised.value.status_code == 422

    def test_a_window_wider_than_the_cap_is_refused(self) -> None:
        with pytest.raises(TimeWindowTooWideError) as raised:
            check_window(since=NOW - HOUR - timedelta(seconds=1), until=NOW, now=NOW, max_span=HOUR)
        assert raised.value.status_code == 422
        assert "3600" in (raised.value.detail or ""), "the cap is named in seconds, not implied"

    def test_since_alone_is_capped_against_now(self) -> None:
        """No ``until`` means "up to now" — the span to cap is ``now - since``,
        otherwise an open-ended ``since`` would dodge the cap entirely."""
        with pytest.raises(TimeWindowTooWideError):
            check_window(since=NOW - 2 * HOUR, until=None, now=NOW, max_span=HOUR)

    def test_until_alone_is_not_a_span_and_is_never_capped(self) -> None:
        """Only an upper bound: how far back it reaches is decided by ``limit``,
        which is already bounded, so there is no span to measure."""
        check_window(since=None, until=NOW - 10 * HOUR, now=NOW, max_span=HOUR)


class TestResolveWindow:
    """``resolve_window`` defaults — the desk and events reads always answer a
    concrete window, and echo it back so the caller never has to guess which
    one the server applied."""

    def test_both_absent_defaults_to_the_default_span_ending_now(self) -> None:
        window = resolve_window(
            since=None, until=None, now=NOW, default_span=HOUR, max_span=24 * HOUR
        )
        assert window.until == NOW
        assert window.since == NOW - HOUR

    def test_since_alone_keeps_now_as_the_upper_bound(self) -> None:
        window = resolve_window(
            since=NOW - 3 * HOUR, until=None, now=NOW, default_span=HOUR, max_span=24 * HOUR
        )
        assert (window.since, window.until) == (NOW - 3 * HOUR, NOW)

    def test_until_alone_walks_the_default_span_back_from_it(self) -> None:
        window = resolve_window(
            since=None, until=NOW - HOUR, now=NOW, default_span=HOUR, max_span=24 * HOUR
        )
        assert (window.since, window.until) == (NOW - 2 * HOUR, NOW - HOUR)

    def test_an_inverted_window_is_refused_before_anything_is_read(self) -> None:
        with pytest.raises(TimeWindowUnorderedError):
            resolve_window(
                since=NOW, until=NOW - HOUR, now=NOW, default_span=HOUR, max_span=24 * HOUR
            )

    def test_a_window_wider_than_the_cap_is_refused(self) -> None:
        with pytest.raises(TimeWindowTooWideError):
            resolve_window(
                since=NOW - 25 * HOUR, until=NOW, now=NOW, default_span=HOUR, max_span=24 * HOUR
            )

    def test_the_resolved_window_is_utc(self) -> None:
        window = resolve_window(
            since=None, until=None, now=NOW, default_span=HOUR, max_span=24 * HOUR
        )
        assert window.since.tzinfo is UTC and window.until.tzinfo is UTC
