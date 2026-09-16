"""T4.43 — the per-mint refusal trail's own per-tick cap, read fresh from the
environment every tick, never a crash on a typo or a negative number."""

from __future__ import annotations

import pytest

from hunter_meme_worker.config_trail import trail_max_rows_per_tick
from hunter_meme_worker.gate_refusal_trail import DEFAULT_TRAIL_CAP

pytestmark = pytest.mark.unit


def test_the_default_is_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEME_GATE_TRAIL_MAX_ROWS_PER_TICK", raising=False)
    assert trail_max_rows_per_tick() == DEFAULT_TRAIL_CAP == 200


def test_a_valid_override_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEME_GATE_TRAIL_MAX_ROWS_PER_TICK", "50")
    assert trail_max_rows_per_tick() == 50


def test_zero_is_a_legal_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEME_GATE_TRAIL_MAX_ROWS_PER_TICK", "0")
    assert trail_max_rows_per_tick() == 0


def test_a_malformed_value_is_the_default_and_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEME_GATE_TRAIL_MAX_ROWS_PER_TICK", "many")
    assert trail_max_rows_per_tick() == DEFAULT_TRAIL_CAP


def test_a_negative_value_is_the_default_and_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEME_GATE_TRAIL_MAX_ROWS_PER_TICK", "-1")
    assert trail_max_rows_per_tick() == DEFAULT_TRAIL_CAP
