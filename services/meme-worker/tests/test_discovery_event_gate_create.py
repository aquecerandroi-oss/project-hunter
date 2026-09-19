"""T4.70 (notes-T4.66.md §7, P0): ``discovery._handle`` calls the event
gate's own create hook exactly like it already calls the launch lane's
(T4.67a) — independent of ``MEME_LAUNCH_LANE``, and only when
``ctx.event_gate`` is wired (``MEME_EVENT_GATE`` is ``shadow``/``on``).

No database, no socket: ``role_session`` is monkeypatched to hand back the
fake session directly, the same double ``test_discovery_bonding_curve_metric.py``
already uses.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun import normalize
from hunter_exchanges.pumpfun.models import NormalizedMemeTokenCreated
from hunter_exchanges.pumpfun.ws import ConnectionState
from hunter_meme_worker import discovery
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.sources import SourcesState
from hunter_meme_worker.tracker import MintTracker

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)


def _agreeing_create() -> dict[str, Any]:
    raw = (FIXTURES / "pumpportal_ws_capture_raw.jsonl").read_text(encoding="utf-8")
    for line in raw.splitlines():
        frame = json.loads(line, parse_float=Decimal)
        if frame.get("txType") == "create" and frame.get("pool") == "pump":
            return frame
    raise AssertionError("the T4.1 capture no longer carries a pump.fun create")


class _EventSource:
    def __init__(self) -> None:
        self.state = ConnectionState()

    def stream(self) -> Any:
        raise AssertionError("_handle is driven directly in this test")


class _Session:
    async def execute(self, statement: Any, params: Any = None) -> None:
        return None

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _no_role(factory: Any, db_role: str) -> Any:
    return factory()


def _context(*, event_gate: object | None) -> RadarContext:
    return RadarContext(
        config=None,  # type: ignore[arg-type]  # _handle never reads ctx.config
        session_factory=lambda: _Session(),  # type: ignore[arg-type]
        tracker=MintTracker(window_minutes=1440, cap=120),
        state=RadarState(),
        events=_EventSource(),  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=None,  # type: ignore[arg-type]
        sources=SourcesState(),
        event_gate=event_gate,  # type: ignore[arg-type]
    )


async def test_handle_calls_the_event_gate_hook_when_wired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discovery, "role_session", _no_role)
    calls: list[tuple[object, NormalizedMemeTokenCreated]] = []

    async def fake_subscribe_at_create(
        event_gate: object, event: NormalizedMemeTokenCreated, *, now: Any
    ) -> None:
        calls.append((event_gate, event))

    monkeypatch.setattr(discovery, "subscribe_at_create", fake_subscribe_at_create)
    sentinel = object()
    ctx = _context(event_gate=sentinel)
    event = normalize.parse_new_token(_agreeing_create())
    await discovery._handle(ctx, event)
    assert len(calls) == 1
    assert calls[0][0] is sentinel
    assert calls[0][1].mint == event.mint


async def test_handle_calls_nothing_when_the_event_gate_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discovery, "role_session", _no_role)
    called = False

    async def fake_subscribe_at_create(*_a: object, **_k: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(discovery, "subscribe_at_create", fake_subscribe_at_create)
    ctx = _context(event_gate=None)
    event = normalize.parse_new_token(_agreeing_create())
    await discovery._handle(ctx, event)
    assert called is False
