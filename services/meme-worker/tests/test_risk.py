# pyright: reportPrivateUsage=false
"""``risk._pool_row`` — what one ``/in-memory-coin`` read teaches
``meme_tokens`` (T4.2d's pool signal; T4.26's reuse count)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hunter_exchanges.pumpfun.board_models import RISK_SOURCE, NormalizedRiskSnapshot
from hunter_meme_worker.risk import _pool_row

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)


def _snapshot(**overrides: object) -> NormalizedRiskSnapshot:
    base: dict[str, object] = {
        "mint": "MINT",
        "raw": {"mint": "MINT"},
        "observed_at": T0,
        "received_at": T0,
    }
    base.update(overrides)
    return NormalizedRiskSnapshot(**base)  # type: ignore[arg-type]


def test_a_reuse_count_is_written_even_without_a_graduation() -> None:
    """T4.26: before this fix, ``upsert_token`` only ran on a graduation frame
    — the reuse count would never reach ``meme_tokens`` for the overwhelming
    majority of reads that are not one."""
    row = _pool_row(_snapshot(twitter_reuse_count=4))
    assert row.twitter_reuse_count == 4
    assert row.twitter_reuse_observed_at == T0
    assert row.pool_created_at is None and row.pool_created_source is None


def test_no_reuse_count_and_no_graduation_writes_neither() -> None:
    row = _pool_row(_snapshot())
    assert row.twitter_reuse_count is None
    assert row.twitter_reuse_observed_at is None


def test_a_graduation_still_writes_the_pool_signal_alongside_the_reuse_count() -> None:
    row = _pool_row(_snapshot(graduated_at=T0, twitter_reuse_count=0))
    assert row.pool_created_at == T0 and row.pool_created_source == RISK_SOURCE
    assert row.twitter_reuse_count == 0
    assert row.twitter_reuse_observed_at == T0
