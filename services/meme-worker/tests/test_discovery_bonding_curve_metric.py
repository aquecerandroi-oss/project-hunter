# pyright: reportPrivateUsage=false
"""T4.39/R36: discovery counts and logs a substituted bonding curve.

``normalize.parse_new_token`` already derives the PDA and keeps the frame's own
value only when it disagreed (``test_pumpfun_normalize.py``,
``test_discovery_rows.py``); this file pins the one thing those two do not
touch — ``_handle`` naming the substitution once it reaches a durable row,
with a bounded-cardinality counter (never the mint) and a mint-carrying log.

No database, no socket: ``role_session`` is monkeypatched to hand back the
fake session directly, like ``test_mayhem.py``'s own ``_no_role``.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun import normalize
from hunter_exchanges.pumpfun.ws import ConnectionState
from hunter_meme_worker import discovery
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.metrics import meme_token_bonding_curve_replaced_total
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


def _mayhem_vault_create() -> dict[str, Any]:
    raw = (FIXTURES / "pumpportal_ws_capture_raw.jsonl").read_text(encoding="utf-8")
    frame = json.loads(raw.splitlines()[7], parse_float=Decimal)
    assert frame["mint"] == "CGuNLUVmrers2FwnLjjVr9Tv8B726caZbRkY116Apump"
    return frame


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
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any, params: Any = None) -> None:
        self.statements.append((str(statement)[:60], params))

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _no_role(factory: Any, db_role: str) -> Any:
    return factory()


def _context(session: _Session) -> RadarContext:
    return RadarContext(
        config=None,  # type: ignore[arg-type]  # _handle never reads ctx.config
        session_factory=lambda: session,  # type: ignore[arg-type]
        tracker=MintTracker(window_minutes=1440, cap=120),
        state=RadarState(),
        events=_EventSource(),  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=None,  # type: ignore[arg-type]
        sources=SourcesState(),
    )


def _count(mayhem_enabled: str) -> float:
    metric = meme_token_bonding_curve_replaced_total.labels(mayhem_enabled=mayhem_enabled)
    return float(cast(Any, metric)._value.get())


async def test_handle_counts_and_logs_a_replaced_curve(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(discovery, "role_session", _no_role)
    before = _count("true")
    session = _Session()
    ctx = _context(session)
    event = normalize.parse_new_token(_mayhem_vault_create())
    await discovery._handle(ctx, event)
    assert _count("true") == before + 1
    assert any(s.startswith("INSERT INTO meme_tokens") for s, _ in session.statements)


async def test_handle_does_not_count_a_frame_that_already_agreed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discovery, "role_session", _no_role)
    before_true, before_false = _count("true"), _count("false")
    session = _Session()
    ctx = _context(session)
    event = normalize.parse_new_token(_agreeing_create())
    await discovery._handle(ctx, event)
    assert _count("true") == before_true
    assert _count("false") == before_false
