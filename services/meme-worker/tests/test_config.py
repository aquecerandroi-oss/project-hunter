"""``load_config`` — the one budget T4.75 makes an env knob: the pump.fun REST
poll ceiling (``MEME_PUMPFUN_REST_BUDGET_60S``). Mirrors
``test_config_trail.py``'s pattern for a single ``_int_env`` knob: default,
override, malformed-is-default."""

from __future__ import annotations

import pytest

from hunter_core.settings import Settings
from hunter_meme_worker.config import load_config

pytestmark = pytest.mark.unit


def test_the_default_is_60(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEME_PUMPFUN_REST_BUDGET_60S", raising=False)
    assert load_config(Settings()).rest_budget_per_minute == 60


def test_a_valid_override_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEME_PUMPFUN_REST_BUDGET_60S", "40")
    assert load_config(Settings()).rest_budget_per_minute == 40


def test_a_malformed_value_is_the_default_and_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEME_PUMPFUN_REST_BUDGET_60S", "many")
    assert load_config(Settings()).rest_budget_per_minute == 60
