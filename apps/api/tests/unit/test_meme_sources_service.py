"""``services/meme_sources.py`` — pure assembly of ``GET /meme/sources`` (T4.2c):
every source named with a status word and a reason, the database witness beside
the worker's, and every way the heartbeat can be absent."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from hunter_api.repositories.meme_sources import SOURCE_TABLES, LatestRow
from hunter_api.schemas.meme_sources import DISCOVERY_BLIND_EXPLANATION, MEME_SOURCES_LABEL
from hunter_api.services.meme_sources import SOURCE_NAMES, build_meme_sources, source_status

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
KEY = "hb:meme:radar"


def _block(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "enabled": True,
        "connected": None,
        "last_observed_at": (AS_OF - timedelta(seconds=5)).isoformat(),
        "last_received_at": (AS_OF - timedelta(seconds=4)).isoformat(),
        "lag_s": 1.0,
        "age_s": 4.0,
        "used_60s": 12,
        "budget_60s": 60,
        "errors_1h": 0,
        "last_error": None,
        "last_error_at": None,
        "reason": None,
    }
    base.update(overrides)
    return base


def _heartbeat(**fields: str) -> dict[str, str]:
    base = {
        "ts": AS_OF.isoformat(),
        "sources_at": (AS_OF - timedelta(seconds=10)).isoformat(),
        "tracked": "117",
        "budget_used_60s": "58",
        "budget_60s": "60",
        "gaps_60s": "1",
        "ws_malformed_60s": "3",
        "last_snapshot_observed_at": (AS_OF - timedelta(seconds=7)).isoformat(),
        "lag_s": "0.412",
        "trenches_connected": "true",
        "trenches_patches_60s": "840",
        "swap_api_used_60s": "610",
        "swap_api_budget_60s": "900",
        "sources": json.dumps(
            {
                "pumpportal_ws": _block(connected=True),
                "pumpfun_rest": _block(),
                "solana_rpc": _block(
                    errors_1h=2,
                    last_error="RateLimited",
                    last_error_at=(AS_OF - timedelta(seconds=1)).isoformat(),
                ),
                "trenches_ws": _block(connected=False),
                "swap_api": _block(used_60s=610, budget_60s=900),
                "indexer_risk": _block(enabled=False, last_observed_at=None, reason="disabled"),
            }
        ),
    }
    base.update(fields)
    return base


def _latest(**observed: datetime | None) -> dict[str, LatestRow]:
    return {
        name: LatestRow(table=table, observed_at=observed.get(name, AS_OF - timedelta(seconds=30)))
        for name, (table, _column) in SOURCE_TABLES.items()
    }


def test_every_source_is_named_with_a_status_word_and_the_database_witness() -> None:
    out = build_meme_sources(_heartbeat(), _latest(swap_api=None), as_of=AS_OF, heartbeat_key=KEY)
    assert out.label == MEME_SOURCES_LABEL and out.radar_status == "alive"
    assert out.tracked == 117 and out.budget_used_60s == 58 and out.gaps_60s == 1
    assert out.ws_malformed_60s == 3 and out.lag_s == pytest.approx(0.412)
    assert out.trenches_connected is True and out.trenches_patches_60s == 840
    assert out.swap_api_used_60s == 610 and out.swap_api_budget_60s == 900
    by_name = {s.name: s for s in out.sources}
    assert list(by_name) == list(SOURCE_NAMES)
    assert by_name["pumpportal_ws"].status == "connected"
    assert by_name["trenches_ws"].status == "disconnected"
    assert by_name["pumpfun_rest"].status == "ok" and by_name["pumpfun_rest"].used_60s == 12
    assert by_name["solana_rpc"].status == "erroring", "an error newer than the last observation"
    assert (
        by_name["indexer_risk"].status == "disabled"
        and by_name["indexer_risk"].reason == "disabled"
    )
    assert by_name["swap_api"].table == "meme_trades"
    assert by_name["swap_api"].last_row_observed_at is None
    assert by_name["swap_api"].row_reason == "no_rows", "an empty table is said, not implied"
    assert by_name["pumpfun_rest"].row_reason is None
    assert by_name["pumpfun_rest"].last_row_observed_at == AS_OF - timedelta(seconds=30)


@pytest.mark.parametrize(
    ("heartbeat", "error", "status"),
    [
        (None, "ConnectionError", "redis_unavailable"),
        ({}, None, "heartbeat_missing"),
        ({"ts": AS_OF.isoformat()}, None, "never"),
        (_heartbeat(sources_at=(AS_OF - timedelta(seconds=61)).isoformat()), None, "stale"),
        (_heartbeat(), None, "alive"),
    ],
)
def test_the_radar_status_names_every_way_the_heartbeat_can_be_absent(
    heartbeat: dict[str, str] | None, error: str | None, status: str
) -> None:
    out = build_meme_sources(
        heartbeat, _latest(), as_of=AS_OF, heartbeat_key=KEY, redis_error=error
    )
    assert out.radar_status == status
    assert (out.radar_reason is None) == (status == "alive")
    if status != "alive":
        assert all(
            s.status in ("unknown", "connected", "disconnected", "ok", "erroring", "disabled")
            for s in out.sources
        )
    if status in ("redis_unavailable", "heartbeat_missing", "never"):
        assert all(s.status == "unknown" and s.reason == "heartbeat_missing" for s in out.sources)
        assert all(s.last_row_observed_at is not None for s in out.sources), (
            "the database still speaks"
        )


def test_the_declared_blindness_is_exposed_with_its_explanation() -> None:
    """T4.2d, item 3: the share of the ``new`` board that runs on a program
    other than ``pump`` — invisible to the discovery socket by construction —
    with the worker's counts beside it and the fixed explanation. An hour the
    board listed nothing is ``None``, never a ``0`` that reads as full coverage."""
    out = build_meme_sources(
        _heartbeat(new_board_entries_1h="50", new_board_non_pump_1h="8", blind_share_1h="0.16"),
        _latest(),
        as_of=AS_OF,
        heartbeat_key=KEY,
    )
    assert out.discovery_blind_share_1h == pytest.approx(0.16)
    assert out.discovery_new_board_entries_1h == 50
    assert out.discovery_non_pump_entries_1h == 8
    assert out.discovery_blind_explanation == DISCOVERY_BLIND_EXPLANATION
    assert "programa fora do escopo do adaptador" in DISCOVERY_BLIND_EXPLANATION
    empty = build_meme_sources(
        _heartbeat(new_board_entries_1h="0", new_board_non_pump_1h="0", blind_share_1h=""),
        _latest(),
        as_of=AS_OF,
        heartbeat_key=KEY,
    )
    assert empty.discovery_blind_share_1h is None
    assert empty.discovery_new_board_entries_1h == 0
    older = build_meme_sources(_heartbeat(), _latest(), as_of=AS_OF, heartbeat_key=KEY)
    assert older.discovery_blind_share_1h is None, "a worker before T4.2d says nothing"
    assert older.discovery_new_board_entries_1h is None


def test_the_coverage_of_the_last_fold_and_the_tape_cycle_are_the_workers_numbers() -> None:
    """T4.2e: ``tape_coverage_pct``/``progress_coverage_pct`` come from the
    heartbeat as written; a worker before T4.2e (or an empty minute, ``""``)
    yields ``None``, never a ``0`` that reads as "nothing covered"."""
    out = build_meme_sources(
        _heartbeat(
            progress_coverage_pct="54.8",
            tape_coverage_pct="56.4",
            fold_minute=(AS_OF - timedelta(seconds=20)).isoformat(),
            fold_rows="250",
            tape_tracked_mints="250",
            tape_covered_mints="247",
            tape_never_pulled="2",
            tape_cycle_s="9.412",
            tape_deferred_60s="3",
            mayhem_pending="7",
            mayhem_written_60s="18",
        ),
        _latest(),
        as_of=AS_OF,
        heartbeat_key=KEY,
    )
    assert out.progress_coverage_pct == pytest.approx(54.8)
    assert out.tape_coverage_pct == pytest.approx(56.4)
    assert out.fold_minute == AS_OF - timedelta(seconds=20) and out.fold_rows == 250
    assert (out.tape_tracked_mints, out.tape_covered_mints, out.tape_never_pulled) == (250, 247, 2)
    assert out.tape_cycle_s == pytest.approx(9.412) and out.tape_deferred_60s == 3
    assert out.mayhem_pending == 7 and out.mayhem_denominators_60s == 18
    assert "not_polled" in out.coverage_explanation and "MayhemState" in out.coverage_explanation
    empty = build_meme_sources(
        _heartbeat(progress_coverage_pct="", tape_coverage_pct="", fold_rows="0"),
        _latest(),
        as_of=AS_OF,
        heartbeat_key=KEY,
    )
    assert empty.progress_coverage_pct is None and empty.tape_coverage_pct is None
    assert empty.fold_rows == 0
    older = build_meme_sources(_heartbeat(), _latest(), as_of=AS_OF, heartbeat_key=KEY)
    assert older.tape_coverage_pct is None and older.mayhem_pending is None


def test_the_chain_loop_and_the_edges_budget_are_the_workers_numbers() -> None:
    """T4.2f: the chain loop's last cycle and the tape budget the edge enforces
    come from the heartbeat as written; a worker before T4.2f yields ``None``."""
    blocked = AS_OF + timedelta(seconds=40)
    out = build_meme_sources(
        _heartbeat(
            chain_cycle_s="1.284",
            chain_tracked_mints="141",
            chain_read_mints="115",
            chain_calls_60s="4",
            chain_refused_1h="26",
            swap_api_effective_budget_60s="12",
            swap_api_measured_60s="16",
            swap_api_429_1h="1",
            swap_api_blocked_until=blocked.isoformat(),
        ),
        _latest(),
        as_of=AS_OF,
        heartbeat_key=KEY,
    )
    assert out.chain_cycle_s == pytest.approx(1.284)
    assert (out.chain_tracked_mints, out.chain_read_mints) == (141, 115)
    assert (out.chain_calls_60s, out.chain_refused_1h) == (4, 26)
    assert out.swap_api_effective_budget_60s == 12 and out.swap_api_measured_60s == 16
    assert out.swap_api_429_1h == 1 and out.swap_api_blocked_until == blocked
    assert (
        "Cloudflare" in out.coverage_explanation and "chain_read_mints" in out.coverage_explanation
    )
    older = build_meme_sources(_heartbeat(), _latest(), as_of=AS_OF, heartbeat_key=KEY)
    assert older.chain_read_mints is None and older.swap_api_effective_budget_60s is None
    assert older.swap_api_blocked_until is None


def test_source_status_reads_the_workers_word_and_never_infers_health() -> None:
    assert source_status("swap_api", None) == ("unknown", "heartbeat_missing")
    assert source_status("swap_api", {"enabled": False}) == ("disabled", "disabled")
    assert source_status("swap_api", {"enabled": True, "reason": "never_observed"}) == (
        "unknown",
        "never_observed",
    )
    assert source_status("swap_api", {"enabled": True, "errors_1h": 4}) == (
        "erroring",
        "never_observed",
    )
    assert source_status("trenches_ws", {"enabled": True}) == ("unknown", "never_connected")
    observed = (AS_OF - timedelta(seconds=5)).isoformat()
    older_error = (AS_OF - timedelta(seconds=50)).isoformat()
    assert source_status(
        "pumpfun_rest",
        {
            "enabled": True,
            "last_observed_at": observed,
            "errors_1h": 1,
            "last_error_at": older_error,
        },
    ) == ("ok", None), "an error older than the newest observation is history"


def test_a_source_the_worker_reports_but_this_api_does_not_know_is_still_listed() -> None:
    heartbeat = _heartbeat()
    blocks = json.loads(heartbeat["sources"])
    blocks["nats_ws"] = _block()
    heartbeat["sources"] = json.dumps(blocks)
    out = build_meme_sources(heartbeat, _latest(), as_of=AS_OF, heartbeat_key=KEY)
    extra = next(s for s in out.sources if s.name == "nats_ws")
    assert extra.status == "ok" and extra.table is None and extra.row_reason == "no_table"
