"""``services/meme_sources.py`` — pure assembly of ``GET /meme/sources`` (T4.2c):
every source named with a status word and a reason, the database witness beside
the worker's, and every way the heartbeat can be absent."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from hunter_api.repositories.meme_sources import SOURCE_TABLES, LatestRow
from hunter_api.schemas.meme_sources import MEME_SOURCES_LABEL
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
