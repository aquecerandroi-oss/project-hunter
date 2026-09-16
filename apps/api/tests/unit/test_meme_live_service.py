"""``services/meme_live.py::read_executor`` (T4.28c) -- the stage-1 "modo
sozinho" fields the heartbeat carries since T4.28/T4.28d/T4.28f: ``auto_approve``,
the hourly counters, the scope counters and the gates reload bookkeeping. Pure:
a fake decoded Redis hash (``dict[str, str]``, exactly what ``hgetall`` returns
after decoding) in, the Pydantic schema out -- no DB, no Redis.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_api.services.meme_live import read_executor

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 16, 15, 0, tzinfo=UTC)
ALIVE_BASE: dict[str, str] = {
    "ts": AS_OF.isoformat(),
    "executor_ts": AS_OF.isoformat(),
    "last_entries_tick_at": (AS_OF - timedelta(seconds=5)).isoformat(),
}


def test_the_stage_1_fields_are_absent_before_t4_28_ever_wrote_them() -> None:
    """A heartbeat from before this feature existed names nothing invented."""
    out = read_executor(ALIVE_BASE, as_of=AS_OF, key="hb:meme:executor", error=None)
    assert out.status == "alive"
    assert out.auto_approve is None
    assert out.auto_approve_max_per_hour is None
    assert out.auto_approved_1h is None
    assert out.auto_refused_1h == {}
    assert out.auto_skipped == {}
    assert out.small_test_used_sol is None
    assert out.small_test_trades_done is None
    assert out.small_test_remaining_sol is None
    assert out.small_test_exhausted is None
    assert out.gates_mtime is None
    assert out.gates_reloaded_at is None
    assert out.gates_reload_error is None


def test_stage_1_on_with_a_partly_spent_scope_and_a_recent_reload() -> None:
    fields = {
        **ALIVE_BASE,
        "auto_approve": "true",
        "auto_approve_max_per_hour": "5",
        "auto_approved_1h": "2",
        "auto_refused_1h": '{"progress_below_window": 4, "bundled_share_unmeasurable": 1}',
        "auto_skipped": '{"mint_busy": 3, "recently_refused": 2, "scope_exhausted:max_total_sol": 1}',
        "small_test_used_sol": "0.18",
        "small_test_trades_done": "3",
        "small_test_remaining_sol": "0.07",
        "small_test_exhausted": "",
        "gates_mtime": (AS_OF - timedelta(minutes=6)).isoformat(),
        "gates_reloaded_at": (AS_OF - timedelta(minutes=6)).isoformat(),
        "gates_reload_error": "",
    }
    out = read_executor(fields, as_of=AS_OF, key="hb:meme:executor", error=None)
    assert out.auto_approve is True
    assert out.auto_approve_max_per_hour == 5
    assert out.auto_approved_1h == 2
    assert out.auto_refused_1h == {"progress_below_window": 4, "bundled_share_unmeasurable": 1}
    assert out.auto_skipped == {
        "mint_busy": 3,
        "recently_refused": 2,
        "scope_exhausted:max_total_sol": 1,
    }
    assert out.small_test_used_sol == Decimal("0.18")
    assert out.small_test_trades_done == 3
    assert out.small_test_remaining_sol == Decimal("0.07")
    assert out.small_test_exhausted is None
    assert out.gates_mtime == AS_OF - timedelta(minutes=6)
    assert out.gates_reloaded_at == AS_OF - timedelta(minutes=6)
    assert out.gates_reload_error is None


def test_an_exhausted_scope_and_a_deferred_gates_failure_are_named() -> None:
    fields = {
        **ALIVE_BASE,
        "auto_approve": "false",
        "small_test_exhausted": "max_trades",
        "gates_reload_error": "deferred:gates_file_invalid",
    }
    out = read_executor(fields, as_of=AS_OF, key="hb:meme:executor", error=None)
    assert out.auto_approve is False
    assert out.small_test_exhausted == "max_trades"
    assert out.gates_reload_error == "deferred:gates_file_invalid"


def test_a_malformed_count_never_crashes_the_read() -> None:
    """A bad row in the JSON dicts (or a non-numeric scalar) is dropped, not a 500."""
    fields = {
        **ALIVE_BASE,
        "auto_approve_max_per_hour": "not-a-number",
        "auto_approved_1h": "not-a-number",
        "auto_refused_1h": '{"progress_below_window": "four"}',
        "auto_skipped": "not-json",
    }
    out = read_executor(fields, as_of=AS_OF, key="hb:meme:executor", error=None)
    assert out.auto_approve_max_per_hour is None
    assert out.auto_approved_1h is None
    assert out.auto_refused_1h == {}
    assert out.auto_skipped == {}
