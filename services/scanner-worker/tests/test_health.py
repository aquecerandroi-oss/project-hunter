"""Readiness: what makes the scanner red, and what deliberately does not.

Every case here came out of the operational proof. The first one turned
``/ready`` red for half an hour on a perfectly healthy worker, because a stream
that publishes sixty events in thirty minutes looks exactly like a stuck loop if
you only ever record progress when a message arrives.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from hunter_core.events.outbox import OutboxHealth
from hunter_scanner_worker.baseline_runner import BootstrapProgress
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.beta_job import BetaHealth
from hunter_scanner_worker.config import ScannerConfig
from hunter_scanner_worker.consumers import ConsumerHealth
from hunter_scanner_worker.health import CycleHealth, readiness_checks, write_heartbeat
from hunter_scanner_worker.regime_job import RegimeHealth
from hunter_scanner_worker.registry import MarketRegistry
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState

from .policies import build_policy

NOW = datetime.now(UTC)
NOW_HOUR = NOW.replace(minute=0, second=0, microsecond=0)
QUIET_STREAM = "market.liquidations"


class FakeHeartbeat:
    """``hset``/``expire`` only: what ``write_heartbeat`` actually touches."""

    def __init__(self) -> None:
        self.mapping: dict[str, str] = {}

    async def hset(self, key: str, mapping: dict[str, str]) -> None:
        del key
        self.mapping = mapping

    async def expire(self, key: str, seconds: int) -> None:
        del key, seconds


class FakeRuntime:
    instance = "test"
    error_count = 0


class FakeStreams:
    """``XREVRANGE`` only: the newest id of each stream, or nothing."""

    def __init__(self, newest: dict[str, datetime | None]) -> None:
        self.newest = newest

    async def xrevrange(self, stream: str, count: int = 1) -> list[Any]:
        del count
        moment = self.newest.get(stream)
        if moment is None:
            return []
        return [(f"{int(moment.timestamp() * 1000)}-0", {})]


def _checks(
    consumers: ConsumerHealth,
    redis: Any,
    *,
    cycle: CycleHealth | None = None,
    progress: BootstrapProgress | None = None,
) -> dict[str, Any]:
    policy = build_policy()
    scanner = Scanner(
        config=ScannerConfig(),
        policy=policy,
        registry=MarketRegistry(exchange="binance"),
        state=ScannerState(),
    )
    scanner.cache = BaselineCache(gate=policy.gate)
    outbox = OutboxHealth(last_sweep_at=NOW)
    built = readiness_checks(
        scanner, consumers, cycle or CycleHealth(), outbox, ScannerConfig(), redis, progress
    )
    return {check.__name__: check for check in built}


async def test_a_quiet_stream_is_idle_not_stuck() -> None:
    consumers = ConsumerHealth(started_at=NOW - timedelta(minutes=30))
    consumers.last_iteration_at[QUIET_STREAM] = NOW - timedelta(minutes=25)
    # The stream itself has published nothing since the consumer last moved.
    redis = FakeStreams({QUIET_STREAM: NOW - timedelta(minutes=25)})

    assert await _checks(consumers, redis)["scanner_consumers"]() is True


async def test_a_consumer_that_fell_behind_a_moving_stream_is_red() -> None:
    consumers = ConsumerHealth(started_at=NOW - timedelta(minutes=30))
    consumers.last_iteration_at[QUIET_STREAM] = NOW - timedelta(minutes=25)
    # The stream moved on without it: that is a stuck loop, and the only case
    # this check exists to catch.
    redis = FakeStreams({QUIET_STREAM: NOW - timedelta(seconds=5)})

    assert await _checks(consumers, redis)["scanner_consumers"]() is False


async def test_a_stream_nobody_ever_published_to_does_not_hold_readiness_down() -> None:
    consumers = ConsumerHealth(started_at=NOW - timedelta(minutes=30))
    consumers.last_iteration_at[QUIET_STREAM] = NOW - timedelta(minutes=25)
    redis = FakeStreams({QUIET_STREAM: None})

    assert await _checks(consumers, redis)["scanner_consumers"]() is True


async def test_a_worker_with_no_consumers_at_all_is_red() -> None:
    consumers = ConsumerHealth(started_at=NOW)

    assert await _checks(consumers, FakeStreams({}))["scanner_consumers"]() is False


async def test_a_stalled_evaluation_cycle_is_red_even_with_healthy_consumers() -> None:
    consumers = ConsumerHealth(started_at=NOW)
    consumers.last_iteration_at["market.ticks"] = NOW
    cycle = CycleHealth()
    cycle.last_cycle_at = NOW - timedelta(minutes=5)

    checks = _checks(consumers, FakeStreams({}), cycle=cycle)
    # This is the check that matters most: consumers that mark work nobody
    # performs would otherwise report a perfectly healthy worker producing
    # nothing.
    assert await checks["scanner_evaluation"]() is False


async def test_an_empty_baseline_archive_is_not_a_readiness_failure() -> None:
    consumers = ConsumerHealth(started_at=NOW)
    consumers.last_iteration_at["market.ticks"] = NOW
    cycle = CycleHealth()
    cycle.baselines_loaded = True

    checks = _checks(consumers, FakeStreams({}), cycle=cycle)
    # A fresh install has no seven-day history. "Under construction" is a state
    # the Radar shows, not a reason to refuse traffic; what would be a failure
    # is not knowing, which is what ``baselines_loaded`` records.
    assert await checks["scanner_baselines"]() is True


def _loaded_cycle() -> CycleHealth:
    cycle = CycleHealth()
    cycle.baselines_loaded = True
    return cycle


async def test_a_bootstrap_still_walking_the_universe_declares_itself_instead_of_going_red() -> (
    None
):
    consumers = ConsumerHealth(started_at=NOW)
    consumers.last_iteration_at["market.ticks"] = NOW
    progress = BootstrapProgress(total=200, declared=10, running="BTCUSDT")
    progress.touch()

    checks = _checks(consumers, FakeStreams({}), cycle=_loaded_cycle(), progress=progress)

    assert await checks["scanner_baselines"]() is True
    assert progress.describe() == "bootstrapping BTCUSDT (10/200)"


async def test_a_bootstrap_that_stopped_advancing_below_the_ratio_is_red() -> None:
    consumers = ConsumerHealth(started_at=NOW)
    consumers.last_iteration_at["market.ticks"] = NOW
    progress = BootstrapProgress(total=200, declared=10)
    progress.last_advance_at = NOW - timedelta(hours=1)

    checks = _checks(consumers, FakeStreams({}), cycle=_loaded_cycle(), progress=progress)

    # Nothing is advancing and 190 markets have no declared baseline state: this
    # worker will never score anything, which is a failure and not a phase.
    assert await checks["scanner_baselines"]() is False


async def test_eighty_percent_declared_is_green_with_nothing_running() -> None:
    consumers = ConsumerHealth(started_at=NOW)
    consumers.last_iteration_at["market.ticks"] = NOW
    progress = BootstrapProgress(total=200, declared=160)

    checks = _checks(consumers, FakeStreams({}), cycle=_loaded_cycle(), progress=progress)

    assert await checks["scanner_baselines"]() is True


async def test_a_stale_beta_producer_is_a_sentence_and_never_a_red_check() -> None:
    """T3.7b: beta gates the wallet, not the Radar — so it is a status detail.

    The two states an operator has to be able to tell apart are here: a
    producer that ran twenty minutes ago with a handful of admissible markets,
    and one that has not run since before every revision in the table expired.
    Neither of them is in the list ``readiness_checks`` returns, and that is the
    assertion — a beta outage must not take a scanner out of rotation.
    """
    consumers = ConsumerHealth(started_at=NOW)
    consumers.last_iteration_at["market.ticks"] = NOW
    checks = _checks(consumers, FakeStreams({}), cycle=_loaded_cycle())
    assert not [name for name in checks if "beta" in name]

    fresh = BetaHealth(last_run_at=NOW - timedelta(minutes=20), valid_markets=12, markets=200)
    stale = BetaHealth(last_run_at=NOW - timedelta(hours=3), valid_markets=1, markets=200)

    assert fresh.stale(NOW) is False
    assert fresh.describe(NOW) == "ok (12/200 valid, 0.3h ago)"
    assert stale.stale(NOW) is True
    assert stale.describe(NOW).startswith("stale (1/200 valid, 3.0h")
    assert BetaHealth().describe(NOW) == "never ran"
    assert BetaHealth().stale(NOW) is True


async def test_the_heartbeat_carries_when_beta_last_ran_and_how_many_are_valid() -> None:
    """``hb:scanner:*`` is what an operator reads during an incident."""
    policy = build_policy()
    scanner = Scanner(
        config=ScannerConfig(),
        policy=policy,
        registry=MarketRegistry(exchange="binance"),
        state=ScannerState(),
    )
    scanner.cache = BaselineCache(gate=policy.gate)
    redis = FakeHeartbeat()
    beta = BetaHealth(last_run_at=NOW - timedelta(minutes=5), valid_markets=7, markets=200)

    await write_heartbeat(
        redis,  # type: ignore[arg-type]
        FakeRuntime(),  # type: ignore[arg-type]
        scanner,
        CycleHealth(),
        ConsumerHealth(started_at=NOW),
        None,
        beta,
    )

    assert redis.mapping["beta_valid"] == "7"
    assert redis.mapping["beta_last_run"] == beta.last_run_at.isoformat()  # type: ignore[union-attr]

    # A process that has not produced a pass yet says so with an empty string,
    # never with a fabricated timestamp: "no beta yet" and "beta from an hour
    # ago" are different incidents.
    await write_heartbeat(
        redis,  # type: ignore[arg-type]
        FakeRuntime(),  # type: ignore[arg-type]
        scanner,
        CycleHealth(),
        ConsumerHealth(started_at=NOW),
        None,
        BetaHealth(),
    )
    assert redis.mapping["beta_last_run"] == ""
    assert redis.mapping["beta_valid"] == "0"


def _status_detail_keys() -> tuple[set[str], set[str]]:
    """``(registered, cleared)`` — the two sides of ``main.run``'s bookkeeping.

    Read from the source because that is where the asymmetry lives: registering
    a detail is one line at the top of ``run`` and removing it is one line in a
    ``finally`` two hundred lines below, and nothing at runtime notices when the
    second line is missing — the worker is already shutting down. What it costs
    is a ``/status`` that keeps answering with the numbers of a producer that no
    longer exists (``regime_hourly`` was exactly that, code-reviewer MEDIUM-2).
    """
    import ast
    import inspect

    from hunter_scanner_worker import main as scanner_main

    tree = ast.parse(inspect.getsource(scanner_main))
    registered: set[str] = set()
    cleared: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "status_details"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            registered.add(node.slice.value)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "pop"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "status_details"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            cleared.add(str(node.args[0].value))
    return registered, cleared


def test_every_status_detail_the_scanner_registers_is_removed_when_it_stops() -> None:
    """Symmetry, not a list: a fourth detail added tomorrow fails this too."""
    registered, cleared = _status_detail_keys()

    assert registered == {"baselines", "beta", "regime_hourly", "breadth"}
    assert cleared == registered


async def test_a_stale_hourly_regime_producer_is_a_sentence_and_never_a_red_check() -> None:
    """T3.43: a hole in the research series costs a cohort its context split.

    It costs the live path nothing — nothing on it reads these rows — so, like
    beta, the producer is a status detail and never a readiness check.
    """
    consumers = ConsumerHealth(started_at=NOW)
    consumers.last_iteration_at["market.ticks"] = NOW
    checks = _checks(consumers, FakeStreams({}), cycle=_loaded_cycle())
    assert not [name for name in checks if "regime" in name]

    fresh = RegimeHealth(last_run_at=NOW - timedelta(minutes=20), last_ts=NOW_HOUR, hours=1)
    stale = RegimeHealth(last_run_at=NOW - timedelta(hours=3), last_ts=NOW_HOUR, hours=745)

    assert fresh.stale(NOW) is False
    assert fresh.describe(NOW) == f"ok (last hour {NOW_HOUR.isoformat()}, 1 written, 0.3h ago)"
    assert stale.stale(NOW) is True
    assert stale.describe(NOW).startswith(f"stale (last hour {NOW_HOUR.isoformat()}, 745 written")
    assert RegimeHealth().describe(NOW) == "never ran"
    assert RegimeHealth().stale(NOW) is True
