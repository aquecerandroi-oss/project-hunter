"""T1.7 item 5: operational proof against the real, already-running compose
stack (docker-compose.yml's ``market-worker`` against real Binance).

Gated two ways, per the brief:

- ``pytest.mark.live`` (CLAUDE.md: "live: hits a real exchange API; never in
  CI") -- excluded from the default ``uv run pytest`` run.
- ``HUNTER_LIVE_TESTS=1`` (module-level skip below) -- the brief's own extra
  gate, so ``-m live`` alone is not enough to accidentally hit the stack.

Postgres and Redis are not published to the host in ``docker-compose.yml``
(only the ``api``/``market-worker`` health/API ports are) -- and
``/api/v1/system/workers``/``/market-status`` require a Clerk-signed JWT this
suite has no way to mint without a real Clerk credential (which it must never
fabricate or read from ``.env``). So these tests read the live stack the way
an operator debugging it would: ``docker compose exec`` into the running
``redis``/``postgres`` containers, read-only. ``/api/v1/system/info`` (public,
unauthenticated) is used for the one HTTP-level check.

The two more disruptive scenarios in the brief (container restart without
duplicate candles; a 40s network disconnect and recovery) are written below
but gated behind a SECOND, separate opt-in (``HUNTER_LIVE_DISRUPTIVE_TESTS=1``)
and were NOT run as part of this task's verification: the dispatching
instructions explicitly say not to restart or reconfigure the already-running
stack. An operator who wants that proof sets both env vars deliberately.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime

import httpx
import pytest

pytestmark = [pytest.mark.live]

COMPOSE_FILE = "infra/docker/docker-compose.yml"
COMPOSE = ["docker", "compose", "-f", COMPOSE_FILE]
API_BASE = "http://localhost:8000"


def _skip_unless_live_tests_enabled() -> None:
    if os.environ.get("HUNTER_LIVE_TESTS") != "1":
        pytest.skip(
            "HUNTER_LIVE_TESTS != 1 -- opt-in only, per the brief and CLAUDE.md's 'live' marker"
        )


@pytest.fixture(autouse=True)
def _gate() -> None:  # pyright: ignore[reportUnusedFunction] - pytest autouse fixture
    _skip_unless_live_tests_enabled()


def _run(args: list[str]) -> str:
    """``subprocess.run`` decoded as UTF-8 with replacement, never the
    platform locale's codec (Windows' default ``cp1252`` cannot decode every
    byte a container's ``redis-cli``/``psql`` may write to stdout)."""
    result = subprocess.run(args, capture_output=True, timeout=15, check=True)
    return result.stdout.decode("utf-8", errors="replace").strip()


def _redis_cli(*args: str) -> str:
    return _run([*COMPOSE, "exec", "-T", "redis", "redis-cli", *args])


def _psql(sql: str) -> str:
    return _run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "hunter",
            "-d",
            "hunter",
            "-t",
            "-A",
            "-c",
            sql,
        ]
    )


def _hgetall(key: str) -> dict[str, str]:
    flat = _redis_cli("HGETALL", key).splitlines()
    return dict(zip(flat[0::2], flat[1::2], strict=True))


def test_worker_heartbeat_reports_connected_with_monitored_markets() -> None:
    heartbeat = _hgetall("hb:market:binance")
    assert heartbeat.get("ws_state") == "connected"
    assert int(heartbeat.get("markets_monitored", "0")) > 0
    last_event_at = datetime.fromisoformat(heartbeat["last_event_at"])
    age_s = (datetime.now(UTC) - last_event_at).total_seconds()
    assert age_s < 60, f"last_event_at is {age_s:.1f}s old -- worker looks stuck, not connected"


def test_at_least_one_monitored_market_has_a_fresh_ticker() -> None:
    keys = [k for k in _redis_cli("--scan", "--pattern", "mkt:binance:*:ticker").splitlines() if k]
    assert keys, "no mkt:binance:*:ticker keys found -- worker is not writing hot state"
    ticker = _hgetall(keys[0])
    assert "last" in ticker and "ts" in ticker
    age_s = (datetime.now(UTC) - datetime.fromisoformat(ticker["ts"])).total_seconds()
    assert age_s < 60, f"{keys[0]}'s ts is {age_s:.1f}s old"


def test_at_least_one_final_candle_was_persisted_recently() -> None:
    latest = _psql(
        "select max(open_time) from candles c "
        "join markets m on m.id = c.market_id join exchanges e on e.id = m.exchange_id "
        "where e.code = 'binance' and c.is_final = true;"
    )
    assert latest, "no final candle exists for binance yet"
    latest_dt = datetime.fromisoformat(latest.replace(" ", "T")).replace(tzinfo=UTC)
    age_s = (datetime.now(UTC) - latest_dt).total_seconds()
    # The worker closes a 1m candle once a minute per market; two minutes of
    # slack covers persistence lag (DETECTION_GRACE in recovery.py is itself
    # 2 minutes) without asserting on wall-clock-fragile "exactly this minute".
    assert age_s < 180, f"newest final candle is {age_s:.0f}s old"


def test_system_info_is_reachable_over_http() -> None:
    """The one HTTP-level check this suite can make without a Clerk token
    (public, unauthenticated) -- confirms the ``api`` container is actually
    the thing answering on :8000, not a stale healthcheck."""
    response = httpx.get(f"{API_BASE}/api/v1/system/info", timeout=10)
    assert response.status_code == 200
    assert response.json()["environment"] in {"development", "production", "staging", "test"}


# ---------------------------------------------------------------------------
# Disruptive scenarios -- written per the brief, NOT executed by this task
# (see module docstring). Both require the extra opt-in below.
# ---------------------------------------------------------------------------


def _skip_unless_disruptive_tests_enabled() -> None:
    if os.environ.get("HUNTER_LIVE_DISRUPTIVE_TESTS") != "1":
        pytest.skip(
            "HUNTER_LIVE_DISRUPTIVE_TESTS != 1 -- restarts/disconnects the live "
            "compose stack; opt-in separately from HUNTER_LIVE_TESTS on purpose"
        )


def test_container_restart_does_not_duplicate_candles() -> None:
    _skip_unless_disruptive_tests_enabled()
    before = int(
        _psql(
            "select count(*) from candles c join markets m on m.id = c.market_id "
            "join exchanges e on e.id = m.exchange_id where e.code = 'binance' and c.is_final = true;"
        )
    )
    before_distinct = int(
        _psql(
            "select count(distinct (market_id, timeframe, open_time)) from candles c "
            "join markets m on m.id = c.market_id join exchanges e on e.id = m.exchange_id "
            "where e.code = 'binance' and c.is_final = true;"
        )
    )
    assert before == before_distinct  # sanity: no duplicates even before the restart

    subprocess.run([*COMPOSE, "restart", "market-worker"], check=True, timeout=60)
    _wait_for_healthy("market-worker", timeout_s=90)

    after = int(
        _psql(
            "select count(*) from candles c join markets m on m.id = c.market_id "
            "join exchanges e on e.id = m.exchange_id where e.code = 'binance' and c.is_final = true;"
        )
    )
    after_distinct = int(
        _psql(
            "select count(distinct (market_id, timeframe, open_time)) from candles c "
            "join markets m on m.id = c.market_id join exchanges e on e.id = m.exchange_id "
            "where e.code = 'binance' and c.is_final = true;"
        )
    )
    assert after >= before
    assert after == after_distinct  # still one row per (market, timeframe, open_time)


def test_network_disconnect_for_40s_reconnects_and_recovers_the_gap() -> None:
    """Astra's second opinion (T1.7): the previous version of this test only
    checked ``ws_state == "connected"`` after reconnect, which would also
    pass with gap recovery entirely disabled. This version additionally
    waits past ``recovery.CHECK_INTERVAL_S`` (60s) + ``DETECTION_GRACE``
    (2 min) for the worker's own recovery cycle to run, and confirms no
    ``failed`` gap for ``binance`` is left over from the outage window.
    """
    _skip_unless_disruptive_tests_enabled()
    import time

    network = _market_worker_network()
    subprocess.run(
        ["docker", "network", "disconnect", network, "docker-market-worker-1"], check=True
    )
    try:
        time.sleep(40)
    finally:
        subprocess.run(
            ["docker", "network", "connect", network, "docker-market-worker-1"], check=True
        )
    _wait_for_healthy("market-worker", timeout_s=120)
    heartbeat = _hgetall("hb:market:binance")
    assert heartbeat.get("ws_state") == "connected"

    # Give the worker's own recovery loop (60s cadence + 2min detection
    # grace, services/market-worker/hunter_market_worker/recovery.py) a
    # chance to detect and backfill whatever minute(s) the outage cost.
    time.sleep(180)
    failed_gaps = _psql(
        "select count(*) from ingestion_gaps g join markets m on m.id = g.market_id "
        "join exchanges e on e.id = m.exchange_id "
        "where e.code = 'binance' and g.status = 'failed' "
        "and g.detected_at > now() - interval '10 minutes';"
    )
    assert failed_gaps == "0", f"{failed_gaps} gap(s) opened by the outage never recovered"
    fresh_ticker = _hgetall(
        _redis_cli("--scan", "--pattern", "mkt:binance:*:ticker").splitlines()[0]
    )
    age_s = (datetime.now(UTC) - datetime.fromisoformat(fresh_ticker["ts"])).total_seconds()
    assert age_s < 60, "ticker still stale after the reconnect + recovery window"


def _market_worker_network() -> str:
    result = subprocess.run(
        [
            "docker",
            "inspect",
            "-f",
            "{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}",
            "docker-market-worker-1",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _wait_for_healthy(service: str, *, timeout_s: float) -> None:
    """Polls ``docker compose ps`` until ``service``'s healthcheck reports
    ``healthy`` -- an exact match, not a substring: ``"healthy" in
    "unhealthy".lower()`` is ``True`` (Astra's second-opinion catch, T1.7),
    which would have let this helper return the instant a just-restarted,
    still-recovering container went ``unhealthy`` instead of waiting for it
    to actually come back. ``State == "running"`` alone is not accepted
    either -- a container can be running while its healthcheck is still
    ``starting`` or already failing.
    """
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = subprocess.run(
            [*COMPOSE, "ps", "--format", "json", service],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            state = json.loads(line)
            if state.get("Health") == "healthy":
                return
        time.sleep(3)
    raise TimeoutError(f"{service} did not become healthy within {timeout_s}s")
