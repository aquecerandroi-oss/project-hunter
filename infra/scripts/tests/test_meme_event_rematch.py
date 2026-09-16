"""``meme_event_rematch.rematch`` — the backfill entry point (T4.26b): the
same symbol/handle rule the per-minute job uses, dry-run by default,
idempotent on ``--apply`` (a pair the fake already carries is not
double-counted, the same ``ON CONFLICT DO NOTHING`` the real table enforces),
and it always advances every scanned event's cursor.

No database: the fake connection serves canned rows keyed by which table the
statement's SQL names. Run:
``uv run pytest infra/scripts/tests/test_meme_event_rematch.py -q``
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _load(name: str) -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}_ut", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Rows:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class FakeConn:
    def __init__(
        self,
        *,
        events: list[dict[str, Any]],
        tokens: list[dict[str, Any]],
        already: set[tuple[str, str]] | None = None,
    ) -> None:
        self.events = events
        self.tokens = tokens
        self.already = already if already is not None else set()
        self.statements: list[tuple[str, Any]] = []

    async def execute(self, statement: Any, parameters: Any = None, /) -> _Rows:
        sql = str(statement)
        self.statements.append((sql, parameters))
        if "SELECT" in sql and "FROM meme_events" in sql:
            since = parameters["since"]
            return _Rows([e for e in self.events if e["observed_at"] >= since])
        if "FROM meme_tokens" in sql:
            floor, now = parameters["floor"], parameters["now"]
            return _Rows([t for t in self.tokens if floor < t["created_at"] <= now])
        if sql.lstrip().startswith("INSERT INTO meme_event_matches"):
            key = (parameters["event_id"], parameters["mint"])
            if key in self.already:
                return _Rows([])
            self.already.add(key)
            return _Rows([{"event_id": parameters["event_id"]}])
        return _Rows([])

    def writes(self) -> list[str]:
        return [s for s, _ in self.statements]


def _event(
    event_id: str,
    *,
    observed_at: datetime,
    symbol_hint: str | None = None,
    handle_hint: str | None = None,
    notes: dict[str, Any] | None = None,
    cursor: datetime | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "observed_at": observed_at,
        "symbol_hint": symbol_hint,
        "handle_hint": handle_hint,
        "notes": notes or {},
        "last_scanned_created_at": cursor,
    }


def _token(
    mint: str,
    *,
    created_at: datetime,
    symbol: str | None = None,
    name: str | None = None,
    twitter: str | None = None,
) -> dict[str, Any]:
    return {
        "mint": mint,
        "symbol": symbol,
        "name": name,
        "twitter": twitter,
        "created_at": created_at,
    }


async def test_dry_run_reports_matches_and_writes_nothing() -> None:
    script = _load("meme_event_rematch")
    event = _event("E1", observed_at=NOW - timedelta(hours=8), symbol_hint="BUM")
    token = _token("MINT1", created_at=NOW - timedelta(hours=7, minutes=45), symbol="BUM")
    conn = FakeConn(events=[event], tokens=[token])
    code, report = await script.rematch(conn, hours=72, now=NOW, apply=False)
    assert code == 0
    assert "1 rule matches" in report
    assert "dry-run" in report
    assert not any(s.lstrip().startswith("INSERT") for s in conn.writes())


async def test_apply_inserts_the_match_and_advances_the_cursor() -> None:
    script = _load("meme_event_rematch")
    event = _event("E1", observed_at=NOW - timedelta(hours=8), symbol_hint="BUM")
    token = _token("MINT1", created_at=NOW - timedelta(hours=7, minutes=45), symbol="BUM")
    conn = FakeConn(events=[event], tokens=[token])
    code, report = await script.rematch(conn, hours=72, now=NOW, apply=True)
    assert code == 0 and "applied: 1 new meme_event_matches rows" in report
    insert_sql, insert_params = next(
        s for s in conn.statements if s[0].lstrip().startswith("INSERT INTO meme_event_matches")
    )
    assert insert_params == {"event_id": "E1", "mint": "MINT1", "match_kind": "buy"}
    cursor_sql, cursor_params = next(
        s for s in conn.statements if s[0].lstrip().startswith("UPDATE meme_events")
    )
    assert cursor_params == {"now": NOW, "ids": ["E1"]}
    _, audit_params = next(s for s in conn.statements if "system_events" in s[0])
    assert audit_params["event"] == "rematched"


async def test_an_avoid_event_marks_its_match_as_avoid() -> None:
    script = _load("meme_event_rematch")
    event = _event(
        "E8", observed_at=NOW - timedelta(hours=1), symbol_hint="WOTF", notes={"action": "avoid"}
    )
    token = _token("CLONE1", created_at=NOW - timedelta(minutes=10), symbol="WOTF")
    conn = FakeConn(events=[event], tokens=[token])
    await script.rematch(conn, hours=72, now=NOW, apply=True)
    _, params = next(
        s for s in conn.statements if s[0].lstrip().startswith("INSERT INTO meme_event_matches")
    )
    assert params["match_kind"] == "avoid"


async def test_a_pair_already_matched_is_not_recounted() -> None:
    """The fake's own ``ON CONFLICT DO NOTHING``: a pair already in the ledger
    contributes zero to ``inserted``, exactly like the real table."""
    script = _load("meme_event_rematch")
    event = _event("E1", observed_at=NOW - timedelta(hours=2), symbol_hint="BUM")
    token = _token("MINT1", created_at=NOW - timedelta(hours=1), symbol="BUM")
    conn = FakeConn(events=[event], tokens=[token], already={("E1", "MINT1")})
    code, report = await script.rematch(conn, hours=72, now=NOW, apply=True)
    assert code == 0 and "applied: 0 new meme_event_matches rows" in report


async def test_no_events_in_window_writes_nothing() -> None:
    script = _load("meme_event_rematch")
    conn = FakeConn(events=[], tokens=[])
    code, report = await script.rematch(conn, hours=72, now=NOW, apply=True)
    assert code == 0 and "0 events" in report
    assert not any(
        s.lstrip().startswith(("INSERT", "UPDATE")) for s in conn.writes()
    ), "only the read of meme_events itself; nothing to write with no events in the window"


async def test_a_coin_created_before_this_events_own_cursor_is_not_its_candidate() -> None:
    """T4.26b's per-event cursor: the single ``meme_tokens`` query is floored
    at the *earliest* of every event's cursor (never a per-event query), so a
    coin between two events' cursors comes back for both — this event's own
    cursor still excludes it, in Python, before it counts as a match."""
    script = _load("meme_event_rematch")
    warm = _event(
        "E_WARM",
        observed_at=NOW - timedelta(hours=5),
        symbol_hint="BUM",
        cursor=NOW - timedelta(hours=1),
    )
    cold = _event("E_COLD", observed_at=NOW - timedelta(hours=5), symbol_hint="BUM")
    between = _token("MINT_BETWEEN", created_at=NOW - timedelta(hours=3), symbol="BUM")
    conn = FakeConn(events=[warm, cold], tokens=[between])
    code, report = await script.rematch(conn, hours=72, now=NOW, apply=True)
    assert code == 0
    matches = [
        s for s in conn.statements if s[0].lstrip().startswith("INSERT INTO meme_event_matches")
    ]
    assert [p["event_id"] for _, p in matches] == ["E_COLD"], (
        "the warm event's own cursor already passed this coin by"
    )
