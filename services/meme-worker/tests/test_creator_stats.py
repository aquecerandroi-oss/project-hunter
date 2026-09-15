"""T4.2h-b — the ``creator_watch_*`` heartbeat fields, without a database.

Two rules this file exists to keep:

- **an unmeasured number is ``""``, never ``0``.** A watch that has not run yet
  must not report "0 criadores vigiados, latência 0 s" — that is the shape of a
  healthy loop, and it would hide a dead one. The gauges are empty strings until
  a cycle happens; the rolling counters are honest ``0``s, because "no calls in
  the last minute" *is* a measurement.
- **the latency is a measurement, not an accumulator.** ``record_latency``
  replaces the sample wholesale (it comes from the rows every cycle), so a
  restart reports the same p50/p95 as the process that ran all day.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hunter_meme_worker.creator_stats import CreatorWatchStats
from hunter_meme_worker.creator_watch import CreatorWatchReport

NOW = datetime(2026, 9, 15, 19, 30, tzinfo=UTC)


def _report(**overrides: int | float) -> CreatorWatchReport:
    fields: dict[str, int | float] = {
        "mints": 12,
        "calls": 1,
        "drops": 2,
        "missing": 3,
        "duration_s": 0.42,
        "live_mints": 1,
    }
    fields.update(overrides)
    return CreatorWatchReport(**fields)  # type: ignore[arg-type]


def test_a_watch_that_never_ran_reports_absence_not_zero() -> None:
    fields = CreatorWatchStats().heartbeat_fields(NOW)
    assert fields["creator_watch_mints"] == ""
    assert fields["creator_watch_live_mints"] == ""
    assert fields["creator_watch_missing"] == ""
    assert fields["creator_watch_cycle_s"] == ""
    assert fields["creator_watch_last_cycle_at"] == ""
    assert fields["creator_watch_sale_to_exit_s_p50"] == ""
    assert fields["creator_watch_sale_to_exit_s_p95"] == ""
    assert fields["creator_watch_enabled"] == "true"
    assert fields["creator_watch_calls_60s"] == "0", "an empty minute is a measurement"
    assert fields["creator_watch_sale_to_exit_n"] == "0"


def test_a_cycle_publishes_the_gauges_and_the_live_mints_apart() -> None:
    stats = CreatorWatchStats()
    stats.record_cycle(NOW, _report())
    fields = stats.heartbeat_fields(NOW)
    assert fields["creator_watch_mints"] == "12"
    assert fields["creator_watch_live_mints"] == "1", "real money is counted apart from paper"
    assert fields["creator_watch_missing"] == "3"
    assert fields["creator_watch_calls_60s"] == "1"
    assert fields["creator_watch_drops_1h"] == "2"
    assert fields["creator_watch_cycle_s"] == "0.42"
    assert fields["creator_watch_last_cycle_at"] == NOW.isoformat()


def test_the_counters_slide_and_the_gauges_do_not() -> None:
    stats = CreatorWatchStats()
    stats.record_cycle(NOW, _report(calls=1, drops=1, mints=12))
    stats.record_cycle(NOW + timedelta(seconds=15), _report(calls=1, drops=0, mints=9))
    later = NOW + timedelta(seconds=70)  # the first cycle is now outside the 60 s window
    fields = stats.heartbeat_fields(later)
    assert fields["creator_watch_calls_60s"] == "1", "the first minute's call fell off the window"
    assert fields["creator_watch_drops_1h"] == "1", "the hour still holds the sale"
    assert fields["creator_watch_mints"] == "9", "a gauge is the last cycle's, not a sum"
    assert stats.heartbeat_fields(NOW + timedelta(hours=2))["creator_watch_drops_1h"] == "0"


def test_the_latency_is_the_rows_answer_replaced_wholesale() -> None:
    stats = CreatorWatchStats()
    stats.record_latency([15, 15, 18, 22, 149])
    fields = stats.heartbeat_fields(NOW)
    assert fields["creator_watch_sale_to_exit_s_p50"] == "18", "nearest rank over five samples"
    assert fields["creator_watch_sale_to_exit_s_p95"] == "149"
    assert fields["creator_watch_sale_to_exit_n"] == "5"
    stats.record_latency([15, 15])
    after = stats.heartbeat_fields(NOW)
    assert after["creator_watch_sale_to_exit_s_p95"] == "15", "a measurement, never an accumulator"
    assert after["creator_watch_sale_to_exit_n"] == "2"


def test_a_disabled_watch_says_so_and_still_reports_nothing_as_nothing() -> None:
    """The switch is the config's, read at write time — a watch that is off must
    be visibly off, not indistinguishable from one whose counters never moved."""
    fields = CreatorWatchStats().heartbeat_fields(NOW, enabled=False)
    assert fields["creator_watch_enabled"] == "false"
    assert fields["creator_watch_mints"] == ""


def test_every_field_is_a_string_and_prefixed() -> None:
    stats = CreatorWatchStats()
    stats.record_cycle(NOW, _report())
    stats.record_latency([15])
    fields = stats.heartbeat_fields(NOW)
    assert all(isinstance(value, str) for value in fields.values())
    assert all(key.startswith("creator_watch_") for key in fields)
