"""``ShadowConfig.claim_idle_ms`` -- derived default and the bound (T3.74d).

Not the redelivery-safety proof itself (``test_reclaim_dedup.py`` and
``test_dispatch.py::TestDuplicateMessageIsRefused`` cover that); this is the
arithmetic that sizes the interval and the guard rail that keeps it well under
``consumer_stall_s``, so a change to either default cannot silently drift past
the bound documented in ``ShadowConfig.claim_idle_ms``.
"""

from __future__ import annotations

import pytest

from hunter_strategy_worker.config import (
    CLAIM_IDLE_MS_CEILING,
    EXPECTED_BAR_COST_S,
    ShadowConfig,
    default_claim_idle_ms,
    load_config,
)

pytestmark = pytest.mark.unit


def test_the_default_is_worker_concurrency_times_expected_bar_cost() -> None:
    assert default_claim_idle_ms(8) == int(8 * EXPECTED_BAR_COST_S * 1000)


def test_a_config_with_no_override_derives_it_from_its_own_worker_concurrency() -> None:
    config = ShadowConfig(worker_concurrency=4)
    assert config.claim_idle_ms == default_claim_idle_ms(4)
    assert config.claim_idle_ms != default_claim_idle_ms(8)


def test_the_default_is_capped_so_a_high_concurrency_never_approaches_the_stall_bound() -> None:
    """T3.74e: a 200-market burst (the whole monitored universe sharing one
    15m/30m/1h boundary) needs a ``worker_concurrency`` well above the T3.74c
    default (8) to drain in single-digit seconds -- the naive product
    (``worker_concurrency x EXPECTED_BAR_COST_S``) would then push the reclaim
    window uncomfortably close to ``consumer_stall_s`` (notes-T3.74e.md §2).
    A ceiling keeps the interval meaningful at high concurrency without
    reproducing that risk."""
    uncapped = int(64 * EXPECTED_BAR_COST_S * 1000)
    assert uncapped > CLAIM_IDLE_MS_CEILING, "the test needs a concurrency that would overflow"
    assert default_claim_idle_ms(64) == CLAIM_IDLE_MS_CEILING


def test_an_explicit_value_is_never_overridden() -> None:
    config = ShadowConfig(worker_concurrency=8, claim_idle_ms=5_000)
    assert config.claim_idle_ms == 5_000


def test_the_default_stays_well_under_the_consumer_stall_bound() -> None:
    """The bound stated in ``ShadowConfig.claim_idle_ms``'s docstring: a truly
    dead consumer's own backlog must be reclaimable well before
    ``consumer_stall_s`` would otherwise be the only signal something is
    wrong."""
    config = ShadowConfig()
    assert config.claim_idle_ms < config.consumer_stall_s * 1000
    # "well under", not merely under -- less than half the stall budget.
    assert config.claim_idle_ms < (config.consumer_stall_s * 1000) / 2


def test_load_config_reads_the_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHADOW_CLAIM_IDLE_MS", "12345")
    assert load_config().claim_idle_ms == 12345


def test_load_config_derives_the_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHADOW_CLAIM_IDLE_MS", raising=False)
    monkeypatch.delenv("SHADOW_WORKER_CONCURRENCY", raising=False)
    config = load_config()
    assert config.worker_concurrency == 32, (
        "T3.74e raised the live default from 8 -- see ShadowConfig.worker_concurrency"
    )
    assert config.claim_idle_ms == default_claim_idle_ms(32)


def test_the_new_default_projects_the_measured_burst_under_the_p95_alert() -> None:
    """Encodes the arithmetic ``ShadowConfig.worker_concurrency``'s docstring
    argues from, so a future change to either number cannot silently drift
    past the projection without this test also changing.

    ``MEASURED_BURST_WORK_S`` is the real total (T3.74e, notes-T3.74e.md §1):
    ``hunter_shadow_stage_seconds`` summed across every stage, for one live
    200-market burst on the VPS at the old concurrency (8) -- market_lookup
    32.23 + family_preload 43.47 + context_load 237.36 + evaluate 11.25 +
    persist 1.10 = 325.41 s. Dividing by the new default projects the
    burst-drain time a market at the back of the queue would see.
    """
    MEASURED_BURST_WORK_S = 325.41
    config = ShadowConfig()
    projected_drain_s = MEASURED_BURST_WORK_S / config.worker_concurrency
    assert projected_drain_s < config.decision_lag_p95_alert_s, (
        f"projected drain {projected_drain_s:.1f}s at concurrency="
        f"{config.worker_concurrency} would still miss the p95 alert budget "
        f"({config.decision_lag_p95_alert_s}s) -- raise worker_concurrency "
        "(and the matching DB pool override) further"
    )
