"""T4.58 — the ``policy`` blob of ``hb:meme:executor`` publishes the curve-progress
window this process admits with, so the desk can see that its own
``max_progress_pct`` gate cannot exceed the executor's ceiling in practice."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from hunter_meme_executor.heartbeat import policy_fields
from hunter_risk_meme import MEME_PAPER_V0, limits_from_env

pytestmark = pytest.mark.unit

POLICY = {
    "MEME_WALLET_MAX_SOL": "0.2",
    "MEME_MAX_SOL_PER_TRADE": "0.02",
    "MEME_DAILY_LOSS_CAP_SOL": "0.05",
    "MEME_MAX_OPEN_POSITIONS": "2",
    "MEME_COOLDOWN_S": "3600",
}


def test_the_paper_preset_publishes_the_default_window() -> None:
    policy = json.loads(json.dumps(policy_fields(MEME_PAPER_V0)))
    assert policy["curve_progress_min_pct"] == "0.02"
    assert policy["curve_progress_max_pct"] == "0.50"
    # The five the owner writes are still there, unchanged by the new keys.
    assert policy["profile"] == "meme_paper_v0"
    assert policy["max_open_positions"] == 3


def test_the_window_from_the_env_is_the_one_published() -> None:
    limits = limits_from_env({**POLICY, "MEME_CURVE_PROGRESS_MAX_PCT": "1.0"})
    policy = policy_fields(limits)
    assert Decimal(str(policy["curve_progress_min_pct"])) == Decimal("0.02")
    assert Decimal(str(policy["curve_progress_max_pct"])) == Decimal("1.0")
    json.dumps(policy)  # every value is JSON-serialisable, as the heartbeat needs
