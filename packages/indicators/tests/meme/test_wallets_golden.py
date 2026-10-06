"""The engine still produces the frozen outputs of the untouched code (CPU plan step 2).

A step-2 optimization of a helper shared by the batch and the bounded engine could move both
sides of the differential tests together; this test compares both against digests frozen from
commit ``84704fa1`` (``wallets_golden.json``), an independent reference (fixtures, not data).
"""

from __future__ import annotations

import json

import pytest

from packages.indicators.tests.meme.wallets_golden import GOLDEN, compute

pytestmark = pytest.mark.unit


def test_the_engine_reproduces_the_frozen_reference() -> None:
    frozen = json.loads(GOLDEN.read_text(encoding="utf-8"))
    now = compute()
    assert set(now) == set(frozen)
    for key in sorted(frozen):
        assert now[key] == frozen[key], key


def test_the_dense_world_is_dense() -> None:
    """The frozen copies cover many triggers per mint (the cost the plan attacks)."""
    frozen = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert int(frozen["dense_copies"]["default_count"]) >= 600
