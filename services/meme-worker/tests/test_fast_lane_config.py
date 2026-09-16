"""T4.42 — the fast lane's own RPC commitment, read fresh from the
environment every tick, never cached and never a crash on a typo."""

from __future__ import annotations

import pytest

from hunter_meme_worker.fast_lane_config import (
    FAST_LANE_COMMITMENT_DEFAULT,
    fast_lane_commitment,
)

pytestmark = pytest.mark.unit


def test_the_default_is_confirmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEME_FAST_LANE_COMMITMENT", raising=False)
    assert fast_lane_commitment() == "confirmed" == FAST_LANE_COMMITMENT_DEFAULT


def test_finalized_may_be_asked_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEME_FAST_LANE_COMMITMENT", "finalized")
    assert fast_lane_commitment() == "finalized"


def test_case_and_whitespace_are_forgiving(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEME_FAST_LANE_COMMITMENT", "  Confirmed \n")
    assert fast_lane_commitment() == "confirmed"


def test_an_unknown_value_is_the_default_and_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEME_FAST_LANE_COMMITMENT", "processed")
    assert fast_lane_commitment() == "confirmed", "a typo must never reach the RPC as-is"
