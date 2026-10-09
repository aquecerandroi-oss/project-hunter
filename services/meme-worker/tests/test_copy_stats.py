"""The copy lane's counters and latency percentiles on ``hb:meme:radar`` (H-037): strings, an absent
number is ``""``, latencies in milliseconds with three decimals."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from hunter_meme_worker.copy_stats import CopyStats, heartbeat_fields

from .copy_support import LEADER_A, LEADER_B, T0

pytestmark = pytest.mark.unit


def _stats() -> CopyStats:
    return CopyStats([LEADER_A, LEADER_B])


def test_an_untouched_lane_reports_zero_counters_and_empty_latencies() -> None:
    fields = heartbeat_fields(_stats(), now=T0, open_count=0, queue_depth=0)
    assert fields["copy_leaders"] == "2"
    assert fields["copy_events_seen"] == "0" and fields["copy_entries"] == "0"
    assert fields["copy_last_event_at"] == ""
    assert fields["copy_observed_to_decided_ms_p50"] == ""  # unmeasured is not zero
    assert json.loads(fields["copy_per_leader"])[LEADER_A]["events"] == 0


def test_latency_percentiles_are_nearest_rank_in_milliseconds() -> None:
    stats = _stats()
    for micros in range(1, 101):  # 1..100 us
        stats.record_decision(
            LEADER_A,
            observed_to_decided_us=micros * 1000,
            fields_to_decided_us=micros * 500,
            block_to_decided_us=micros * 2000,
            decide_us=micros,
            at=T0,
        )
    fields = heartbeat_fields(stats, now=T0, open_count=0, queue_depth=0)
    assert fields["copy_observed_to_decided_ms_p50"] == "50.000"
    assert fields["copy_observed_to_decided_ms_p95"] == "95.000"
    assert fields["copy_observed_to_decided_ms_p99"] == "99.000"
    assert fields["copy_block_to_decided_ms_p99"] == "198.000"
    assert fields["copy_decide_us_p99"] == "99"
    assert fields["copy_events_seen"] == "100"


def test_missing_block_time_is_left_out_of_that_percentile_only() -> None:
    stats = _stats()
    stats.record_decision(
        LEADER_A,
        observed_to_decided_us=2000,
        fields_to_decided_us=1000,
        block_to_decided_us=None,
        decide_us=5,
        at=T0,
    )
    fields = heartbeat_fields(stats, now=T0, open_count=0, queue_depth=0)
    assert fields["copy_block_to_decided_ms_p50"] == ""
    assert fields["copy_observed_to_decided_ms_p50"] == "2.000"


def test_per_leader_counters_and_censors_by_reason() -> None:
    stats = _stats()
    stats.record_entry(LEADER_A, at=T0)
    stats.record_entry(LEADER_A, at=T0)
    stats.record_exit(LEADER_A)
    stats.record_censored(LEADER_B, "leader_gap_entry")
    stats.record_censored(LEADER_B, "leader_gap_entry")
    stats.record_censored(LEADER_A, "no_curve_read")
    stats.record_skip("already_observed")
    stats.record_rejected("abaixo_do_piso")
    stats.record_rejected("abaixo_do_piso")
    stats.record_rejected("lacuna")
    stats.record_event(LEADER_A, at=T0 + timedelta(seconds=3))
    fields = heartbeat_fields(stats, now=T0, open_count=1, queue_depth=4)
    per = json.loads(fields["copy_per_leader"])
    assert per[LEADER_A]["entries"] == 2 and per[LEADER_A]["exits"] == 1
    assert per[LEADER_A]["censored"] == 1 and per[LEADER_B]["censored"] == 2
    assert per[LEADER_A]["last_event_at"] == (T0 + timedelta(seconds=3)).isoformat(
        timespec="milliseconds"
    )
    assert fields["copy_censored"] == "3"
    assert json.loads(fields["copy_censored_by_reason"]) == {
        "leader_gap_entry": 2,
        "no_curve_read": 1,
    }
    assert json.loads(fields["copy_skipped_by_reason"]) == {"already_observed": 1}
    assert json.loads(fields["copy_rejected_by_reason"]) == {"abaixo_do_piso": 2, "lacuna": 1}
    assert fields["copy_open"] == "1" and fields["copy_persist_queue_depth"] == "4"
    assert fields["copy_exits"] == "1" and fields["copy_entries"] == "2"


def test_confirmation_delay_and_invalidations_are_published_separately() -> None:
    stats = _stats()
    for ms in (100, 200, 300):
        stats.record_confirmation(ms)
    stats.record_invalidated()
    fields = heartbeat_fields(stats, now=T0, open_count=0, queue_depth=0)
    assert fields["copy_confirm_delay_ms_p50"] == "200"
    assert fields["copy_invalidated"] == "1"
