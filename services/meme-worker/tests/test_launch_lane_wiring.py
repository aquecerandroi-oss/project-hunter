"""``launch_lane_wiring.build_launch_lane`` — the actual "off ⇒ nothing"
boundary: ``main.py`` never builds a runtime at all when the flag is off, so
``discovery.py``'s own guard (``if ctx.launch_lane is not None``) never calls
this module — pure, no Docker.
"""

from __future__ import annotations

from typing import Any

import pytest

from hunter_meme_worker.launch_lane_wiring import build_launch_lane, register_launch_lane_health


class _Waker:
    async def __call__(self) -> None:
        return None


async def _heartbeat(_: dict[str, str]) -> None:
    return None


def test_the_lane_is_none_when_the_flag_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEME_LAUNCH_LANE", raising=False)
    lane = build_launch_lane(None, _Waker(), _heartbeat)  # type: ignore[arg-type]
    assert lane is None


def test_the_lane_is_none_when_the_flag_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEME_LAUNCH_LANE", "off")
    lane = build_launch_lane(None, _Waker(), _heartbeat)  # type: ignore[arg-type]
    assert lane is None


def test_the_lane_builds_a_runtime_in_paper_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEME_LAUNCH_LANE", "paper")
    lane = build_launch_lane(None, _Waker(), _heartbeat)  # type: ignore[arg-type]
    assert lane is not None
    assert lane.config.mode == "paper"
    assert lane.config.enabled is True
    runtime = _Runtime()
    register_launch_lane_health(runtime, lane)  # type: ignore[arg-type]
    assert "launch_lane" in runtime.status_details
    assert "paper" in runtime.status_details["launch_lane"]()


class _Runtime:
    def __init__(self) -> None:
        self.status_details: dict[str, Any] = {}


def test_health_reports_disabled_when_the_lane_is_none() -> None:
    runtime = _Runtime()
    register_launch_lane_health(runtime, None)  # type: ignore[arg-type]
    assert runtime.status_details["launch_lane"]() == "disabled (MEME_LAUNCH_LANE=off)"
