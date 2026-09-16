# pyright: reportPrivateUsage=false
"""T4.26 — the event ↔ mint matching job against a real Postgres at ``head``:
a handle match, a symbol match, the 60-minute window's edges, "earliest wins"
for a shared handle, linking an open proposal, the counts, and the ``EXPLAIN``
of the matching query over ≥ 100 k ``meme_tokens`` rows (the T4.24b post-
incident rule this task's brief names explicitly).

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_meme_worker.events_repo import (
    MATCH_WINDOW_MINUTES,
    count_events,
    link_proposals,
    match_events_once,
)
from hunter_meme_worker.repo import TokenRow, upsert_token

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
RESEARCH_ID = "01994d00-6c1a-7000-8000-000000000001"


def _token(
    mint: str, *, created_at: datetime, symbol: str | None = None, twitter: str | None = None
) -> TokenRow:
    return TokenRow(
        mint=mint,
        first_seen_source="pumpfun_rest",
        first_seen_at=created_at,
        last_seen_at=created_at,
        created_at=created_at,
        symbol=symbol,
        twitter=twitter,
        twitter_kind=None if twitter is None else "profile",
    )


async def _insert_event(
    session: AsyncSession,
    *,
    event_id: str,
    observed_at: datetime,
    handle_hint: str | None = None,
    symbol_hint: str | None = None,
    kind: str = "public_figure_launch",
    confidence: str = "confirmed",
) -> None:
    await session.execute(
        text(
            "INSERT INTO meme_events (id, observed_at, source, kind, title, "
            "handle_hint, symbol_hint, confidence, recorded_by) VALUES "
            "(:id, :observed_at, 'manual', :kind, 'test event', :handle_hint, :symbol_hint, "
            ":confidence, 'test')"
        ),
        {
            "id": event_id,
            "observed_at": observed_at,
            "kind": kind,
            "handle_hint": handle_hint,
            "symbol_hint": symbol_hint,
            "confidence": confidence,
        },
    )


async def test_a_handle_match_and_a_symbol_match_both_name_their_mint(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    handle_event = str(uuid.uuid4())
    symbol_event = str(uuid.uuid4())
    async with db_session_factory() as session:
        await upsert_token(
            session,
            _token(
                "T426_HANDLE",
                created_at=NOW + timedelta(minutes=5),
                twitter="x.com/CoachPatNFT/status/123",
            ),
        )
        await upsert_token(
            session, _token("T426_SYMBOL", created_at=NOW + timedelta(minutes=10), symbol="BUM")
        )
        await _insert_event(
            session, event_id=handle_event, observed_at=NOW, handle_hint="CoachPatNFT"
        )
        await _insert_event(session, event_id=symbol_event, observed_at=NOW, symbol_hint="BUM")
        await session.commit()

        matched = await match_events_once(session, now=NOW + timedelta(minutes=30))
        await session.commit()

    assert matched is not None
    by_event = {m.event_id: m.mint for m in matched}
    assert by_event[handle_event] == "T426_HANDLE"
    assert by_event[symbol_event] == "T426_SYMBOL"


async def test_a_mint_created_outside_the_window_is_not_matched(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_id = str(uuid.uuid4())
    async with db_session_factory() as session:
        await upsert_token(
            session,
            _token(
                "T426_LATE",
                created_at=NOW + timedelta(minutes=MATCH_WINDOW_MINUTES + 5),
                twitter="x.com/latecoach",
            ),
        )
        await _insert_event(session, event_id=event_id, observed_at=NOW, handle_hint="latecoach")
        await session.commit()

        matched = await match_events_once(session, now=NOW + timedelta(minutes=90))
        await session.commit()

    assert matched is not None
    assert event_id not in {m.event_id for m in matched}


async def test_a_shared_handle_matches_the_earliest_sibling_only(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """M-P33: several coins can carry the same announcer's link; one event
    names exactly one mint — the first created inside the window."""
    event_id = str(uuid.uuid4())
    async with db_session_factory() as session:
        await upsert_token(
            session,
            _token(
                "T426_SIB_FIRST",
                created_at=NOW + timedelta(minutes=2),
                twitter="x.com/toly/status/999",
            ),
        )
        await upsert_token(
            session,
            _token(
                "T426_SIB_SECOND",
                created_at=NOW + timedelta(minutes=3),
                twitter="x.com/toly/status/999",
            ),
        )
        await _insert_event(session, event_id=event_id, observed_at=NOW, handle_hint="toly")
        await session.commit()

        matched = await match_events_once(session, now=NOW + timedelta(minutes=30))
        await session.commit()

    assert matched is not None
    (m,) = [x for x in matched if x.event_id == event_id]
    assert m.mint == "T426_SIB_FIRST"


async def test_matching_links_an_open_proposal_by_mint(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_id = str(uuid.uuid4())
    proposal_id = str(uuid.uuid4())
    async with db_session_factory() as session:
        await upsert_token(
            session,
            _token("T426_LINK", created_at=NOW + timedelta(minutes=1), twitter="x.com/linkcoach"),
        )
        await session.execute(
            text(
                "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, "
                "expires_at, decision, decided_by, decided_at) VALUES "
                "(:id, 'T426_LINK', :rule_set, 'operator', 'approved', "
                "now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
            ),
            {"id": proposal_id, "rule_set": RESEARCH_ID},
        )
        await _insert_event(session, event_id=event_id, observed_at=NOW, handle_hint="linkcoach")
        await session.commit()

        matched = await match_events_once(session, now=NOW + timedelta(minutes=30))
        assert matched is not None
        linked = await link_proposals(session, matched)
        await session.commit()

        stored = (
            await session.execute(
                text("SELECT event_id::text FROM meme_proposals WHERE id = :id"),
                {"id": proposal_id},
            )
        ).scalar_one()
    assert linked == 1
    assert stored == event_id


async def test_count_events_reports_open_and_matched_1h(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_factory() as session:
        await upsert_token(session, _token("T426_COUNT", created_at=NOW))
        await session.execute(text("DELETE FROM meme_events WHERE title = 'count test'"), {})
        await session.execute(
            text(
                "INSERT INTO meme_events (id, observed_at, source, kind, title, "
                "confidence, recorded_by, matched_at, mint) VALUES "
                "(:id1, :now, 'manual', 'incident', 'count test', 'rumor', 'test', NULL, NULL), "
                "(:id2, :now, 'manual', 'incident', 'count test', 'rumor', 'test', "
                ":now, 'T426_COUNT')"
            ),
            {"id1": str(uuid.uuid4()), "id2": str(uuid.uuid4()), "now": NOW},
        )
        await session.commit()
        counts = await count_events(session, now=NOW)
    assert counts.open >= 1
    assert counts.matched_1h >= 1


async def test_explain_the_matching_query_uses_the_created_at_index_at_100k_rows(
    db_engine: AsyncEngine,
) -> None:
    """The T4.24b post-incident rule: bounded window + index, plan declared.
    150 k synthetic rows spread over ~156 days so a 60-minute window is a
    sliver, never a sequential scan of the whole table. Rolled back at the
    end: this must not leave 150 k rows behind for every other test in the
    shared container to scan."""
    from hunter_meme_worker.events_repo import _MATCH  # the frozen query itself

    conn = await db_engine.connect()
    trans = await conn.begin()
    try:
        await conn.execute(
            text(
                "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, "
                "last_seen_at, created_at, symbol) "
                "SELECT 'T426_BULK_' || gs, 'pumpfun_rest', now(), now(), "
                "  timestamptz '2026-01-01' + (gs * interval '90 seconds'), "
                "  'SYM' || (gs % 1000) "
                "FROM generate_series(1, 150000) AS gs "
                "ON CONFLICT (mint) DO NOTHING"
            )
        )
        await conn.execute(text("ANALYZE meme_tokens"))
        event_id = str(uuid.uuid4())
        await conn.execute(
            text(
                "INSERT INTO meme_events (id, observed_at, source, kind, title, "
                "symbol_hint, confidence, recorded_by) VALUES "
                "(:id, timestamptz '2026-03-01', 'manual', 'incident', 'explain test', "
                "'SYM7', 'rumor', 'test')"
            ),
            {"id": event_id},
        )
        plan_rows = (
            (
                await conn.execute(
                    text(f"EXPLAIN {_MATCH.text}"),
                    {
                        "since": datetime(2026, 1, 1, tzinfo=UTC),
                        "window_minutes": MATCH_WINDOW_MINUTES,
                        "now": datetime(2026, 3, 2, tzinfo=UTC),
                    },
                )
            )
            .scalars()
            .all()
        )
        plan = "\n".join(plan_rows)
        row_count = (await conn.execute(text("SELECT count(*) FROM meme_tokens"))).scalar_one()
    finally:
        await trans.rollback()
        await conn.close()
    assert row_count >= 100_000, "the plan must be declared over a table this size, not a fixture"
    assert "Seq Scan on meme_tokens" not in plan, plan
    notes_dir = Path(__file__).resolve().parents[3] / ".claude" / "state"  # noqa: ASYNC240
    notes_dir.joinpath("notes-T4.26-explain.txt").write_text(
        f"rows={row_count}\n{plan}", encoding="utf-8"
    )
