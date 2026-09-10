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
    assert load_config().claim_idle_ms == default_claim_idle_ms(8)
