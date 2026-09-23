"""``market_event.py`` — the audited script the plantão uses to record a
non-meme headline (T4.82, design §8).

Mirrors ``test_meme_event.py``: no database, a connection that records the
statements it receives and answers a canned id for the ``RETURNING``.

What is asserted beyond the meme twin, because the confluence screen depends
on it:

- ``published_at`` and ``observed_at`` are **two** parameters, and omitting
  ``--published-at`` writes ``NULL`` rather than copying ``observed_at`` — an
  invented publication instant would land on the chart as a vertical line at a
  time nobody published anything (§3, overlay 4);
- the insert is idempotent on ``(source, url)``, which is what lets the shift
  re-run the same link without doubling the row;
- ``--symbol`` is required and uppercased, because it is the join key the
  screen reads by.

Run: ``uv run pytest infra/scripts/tests/test_market_event.py -q``
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
EVENT_ID = "00000000-0000-4000-8000-00000000fa11"


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


class _Result:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return self._values


class FakeConn:
    def __init__(self, inserted: list[Any] | None = None) -> None:
        self.statements: list[tuple[str, Any]] = []
        self._inserted = [EVENT_ID] if inserted is None else inserted

    async def execute(self, statement: Any, parameters: Any = None, /) -> _Result:
        sql = str(statement)
        self.statements.append((sql, parameters))
        if sql.lstrip().startswith("INSERT INTO market_events"):
            return _Result(self._inserted)
        return _Result([])

    def writes(self) -> list[str]:
        return [s for s, _ in self.statements]


BASE: dict[str, Any] = {
    "symbol": "ZECUSDT",
    "exchange": "binance",
    "kind": "listing",
    "title": "Binance lista ZEC em novos pares",
    "url": "https://www.binance.com/en/support/announcement/123",
    "confidence": "reported",
    "source": "baha",
    "published_at": datetime(2026, 9, 23, 14, 32, tzinfo=UTC),
    "observed_at": datetime(2026, 9, 23, 14, 40, tzinfo=UTC),
    "notes": None,
    "recorded_by": "everton",
}


async def test_dry_run_writes_nothing_and_names_the_plan() -> None:
    script = _load("market_event")
    conn = FakeConn()
    code, report = await script.run(conn, apply=False, **BASE)
    assert code == 0 and "dry-run" in report
    assert conn.writes() == []
    assert "ZECUSDT" in report and "listing" in report


async def test_apply_inserts_and_leaves_an_audit_row() -> None:
    script = _load("market_event")
    conn = FakeConn()
    code, report = await script.run(conn, apply=True, **BASE)
    assert code == 0 and f"market_events {EVENT_ID}" in report
    insert_sql, params = conn.statements[0]
    assert "INSERT INTO market_events" in insert_sql
    assert params["symbol"] == "ZECUSDT"
    assert params["kind"] == "listing" and params["confidence"] == "reported"
    _, audit = next(s for s in conn.statements if "system_events" in s[0])
    assert audit["component"] == "market_events"
    assert audit["event"] == "added"
    assert EVENT_ID in audit["message"] and "everton" in audit["message"]


class TestTheTwoInstantsStaySeparate:
    async def test_published_at_and_observed_at_are_two_parameters(self) -> None:
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **BASE)
        _, params = conn.statements[0]
        assert params["published_at"] == BASE["published_at"]
        assert params["observed_at"] == BASE["observed_at"]
        assert params["published_at"] != params["observed_at"]

    async def test_without_a_published_at_the_column_stays_null(self) -> None:
        """Never copied from ``observed_at``: a made-up publication instant
        would be drawn on the chart as a line at a time nobody published."""
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **{**BASE, "published_at": None})
        _, params = conn.statements[0]
        assert params["published_at"] is None
        assert params["observed_at"] is not None

    async def test_observed_at_defaults_to_now_and_is_utc(self) -> None:
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **{**BASE, "observed_at": None})
        _, params = conn.statements[0]
        assert params["observed_at"].tzinfo is not None
        assert params["observed_at"].utcoffset() == UTC.utcoffset(None)


class TestRefusals:
    @pytest.mark.parametrize(
        ("field", "value", "reason"),
        [
            ("kind", "pump", "kind_unknown"),
            ("confidence", "sure", "confidence_unknown"),
            ("source", "telegram_dm", "source_unknown"),
            ("recorded_by", None, "recorded_by_required"),
            ("recorded_by", "   ", "recorded_by_required"),
            ("symbol", "", "symbol_required"),
            ("symbol", "   ", "symbol_required"),
            ("title", "  ", "title_required"),
        ],
    )
    async def test_refuses_by_name_before_writing_anything(
        self, field: str, value: str | None, reason: str
    ) -> None:
        script = _load("market_event")
        conn = FakeConn()
        with pytest.raises(script.Refused, match=reason):
            await script.run(conn, apply=True, **{**BASE, field: value})
        assert conn.statements == [], "refused before touching the database"

    async def test_an_inverted_pair_of_instants_is_refused(self) -> None:
        """Observing something before it was published is not a late reading,
        it is a typo — and it would put the row in the wrong block of §4."""
        script = _load("market_event")
        conn = FakeConn()
        overrides = {
            **BASE,
            "published_at": datetime(2026, 9, 23, 15, 0, tzinfo=UTC),
            "observed_at": datetime(2026, 9, 23, 14, 0, tzinfo=UTC),
        }
        with pytest.raises(script.Refused, match="observed_before_published"):
            await script.run(conn, apply=True, **overrides)
        assert conn.statements == []

    async def test_a_naive_instant_is_refused(self) -> None:
        script = _load("market_event")
        conn = FakeConn()
        overrides = {**BASE, "published_at": datetime(2026, 9, 23, 14, 32)}  # noqa: DTZ001
        with pytest.raises(script.Refused, match="naive_datetime"):
            await script.run(conn, apply=True, **overrides)
        assert conn.statements == []


class TestIdempotence:
    async def test_the_insert_does_nothing_on_a_conflicting_source_url_and_symbol(self) -> None:
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **BASE)
        insert_sql, _ = conn.statements[0]
        assert "ON CONFLICT (source, url, symbol)" in insert_sql
        assert "DO NOTHING" in insert_sql

    async def test_the_conflict_target_carries_the_symbol(self) -> None:
        """Astra, review of T4.82: on ``(source, url)`` alone, one Binance
        announcement naming ZECUSDT *and* BTCUSDT would have its second filing
        swallowed, and the BTCUSDT screen would never show it."""
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **BASE)
        insert_sql, _ = conn.statements[0]
        assert "ON CONFLICT (source, url)" not in insert_sql.replace(
            "ON CONFLICT (source, url, symbol)", ""
        )

    async def test_a_conflict_reports_the_duplicate_and_writes_no_audit_row(self) -> None:
        """``RETURNING`` yields no row when the partial unique swallowed the
        insert. Reporting "already recorded" is the truth; an audit row saying
        "added" would not be."""
        script = _load("market_event")
        conn = FakeConn(inserted=[])
        code, report = await script.run(conn, apply=True, **BASE)
        assert code == 0
        assert "already recorded" in report
        assert not any("system_events" in sql for sql in conn.writes())


class TestTheMarketIdIsOnlyFilledWhenItIsUnambiguous:
    """Astra, review of T4.82, must-fix 3: the first version of this sub-select
    matched on ``symbol`` alone and took the oldest row, so an item filed as
    Bybit ZECUSDT was stamped with Binance's market id — a payload whose
    ``exchange`` and ``market_id`` contradict each other."""

    async def test_the_venue_is_part_of_the_match(self) -> None:
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **BASE)
        insert_sql, _ = conn.statements[0]
        assert "JOIN exchanges e ON e.id = m.exchange_id" in insert_sql
        assert "e.code = :exchange" in insert_sql

    async def test_an_ambiguous_symbol_resolves_to_null_rather_than_to_a_guess(self) -> None:
        """``HAVING count(*) = 1`` makes the aggregate return no row — and so
        the scalar sub-select ``NULL`` — whenever the pair is listed twice on
        the venue, or no venue was given at all."""
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **BASE)
        insert_sql, _ = conn.statements[0]
        assert "HAVING count(*) = 1" in insert_sql

    async def test_no_exchange_cannot_resolve_a_market_id(self) -> None:
        """With ``exchange`` null, ``e.code = :exchange`` matches nothing, the
        count is zero and the HAVING rejects it — no market id is invented."""
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **{**BASE, "exchange": None})
        _, params = conn.statements[0]
        assert params["exchange"] is None


class TestNormalisation:
    async def test_the_exchange_is_lowercased_to_match_the_catalogue(self) -> None:
        """``exchanges.code`` is lower-case and the read matches ``exchange``
        exactly; a row filed as "Binance" would be invisible on the
        ``/binance/...`` route (Astra)."""
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **{**BASE, "exchange": " Binance "})
        _, params = conn.statements[0]
        assert params["exchange"] == "binance"

    async def test_the_symbol_is_uppercased_because_it_is_the_join_key(self) -> None:
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **{**BASE, "symbol": " zecusdt "})
        _, params = conn.statements[0]
        assert params["symbol"] == "ZECUSDT"

    async def test_no_exchange_means_the_headline_is_about_no_single_venue(self) -> None:
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **{**BASE, "exchange": None})
        _, params = conn.statements[0]
        assert params["exchange"] is None

    async def test_notes_default_to_an_empty_object_not_to_null(self) -> None:
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **BASE)
        _, params = conn.statements[0]
        assert json.loads(params["notes"]) == {}

    async def test_hand_written_notes_are_passed_through(self) -> None:
        script = _load("market_event")
        conn = FakeConn()
        await script.run(conn, apply=True, **{**BASE, "notes": '{"fonte_secundaria": "theblock"}'})
        _, params = conn.statements[0]
        assert json.loads(params["notes"]) == {"fonte_secundaria": "theblock"}
