# pyright: reportPrivateUsage=false
"""T4.26b — the event ↔ mint matching job against a real Postgres at
``head``: a handle match, a symbol match, an ``avoid`` match, the cursor
never re-scanning what it already judged, idempotency of the ledger,
linking an open proposal, the counts, and the ``EXPLAIN`` of the candidate
scan over ≥ 100 k ``meme_tokens`` rows (the T4.24b post-incident rule this
task's brief names explicitly).

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from hunter_meme_worker.events_repo import count_events, link_proposals, match_events_once
from hunter_meme_worker.repo import TokenRow, upsert_token

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
RESEARCH_ID = "01994d00-6c1a-7000-8000-000000000001"


def _token(
    mint: str,
    *,
    created_at: datetime,
    symbol: str | None = None,
    twitter: str | None = None,
    name: str | None = None,
) -> TokenRow:
    return TokenRow(
        mint=mint,
        first_seen_source="pumpfun_rest",
        first_seen_at=created_at,
        last_seen_at=created_at,
        created_at=created_at,
        symbol=symbol,
        name=name,
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
    notes: dict[str, Any] | None = None,
    kind: str = "public_figure_launch",
    confidence: str = "confirmed",
) -> None:
    await session.execute(
        text(
            "INSERT INTO meme_events (id, observed_at, source, kind, title, "
            "handle_hint, symbol_hint, confidence, recorded_by, notes) VALUES "
            "(:id, :observed_at, 'manual', :kind, 'test event', :handle_hint, :symbol_hint, "
            ":confidence, 'test', CAST(:notes AS jsonb))"
        ),
        {
            "id": event_id,
            "observed_at": observed_at,
            "kind": kind,
            "handle_hint": handle_hint,
            "symbol_hint": symbol_hint,
            "confidence": confidence,
            "notes": json.dumps(notes or {}),
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
    by_event = {m.event_id: (m.mint, m.match_kind) for m in matched}
    assert by_event[handle_event] == ("T426_HANDLE", "buy")
    assert by_event[symbol_event] == ("T426_SYMBOL", "buy")


async def test_an_avoid_event_marks_every_coin_it_names_as_avoid_not_just_one(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """KB-0100 event 8: the clone viveiro names *several* coins, not one — the
    singleton ``meme_events.mint`` (0041) could never record that."""
    event_id = str(uuid.uuid4())
    async with db_session_factory() as session:
        await upsert_token(
            session, _token("T426B_CLONE1", created_at=NOW + timedelta(minutes=1), symbol="WOTF")
        )
        await upsert_token(
            session, _token("T426B_CLONE2", created_at=NOW + timedelta(minutes=2), symbol="WOTF")
        )
        await _insert_event(
            session,
            event_id=event_id,
            observed_at=NOW,
            symbol_hint="WOTF",
            notes={"action": "avoid"},
        )
        await session.commit()

        matched = await match_events_once(session, now=NOW + timedelta(hours=1))
        await session.commit()

    assert matched is not None
    mints = {m.mint: m.match_kind for m in matched if m.event_id == event_id}
    assert mints == {"T426B_CLONE1": "avoid", "T426B_CLONE2": "avoid"}


async def test_a_coin_born_hours_before_a_retroactively_registered_event_still_matches(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """KB-0100's own bug: a plantão event is routinely registered hours after
    the fact (median 172,8 min that day) with a retroactive ``observed_at`` —
    the coin was born *before* the event row exists, inside the 30-minute
    backward grace."""
    event_id = str(uuid.uuid4())
    observed_at = NOW - timedelta(hours=3)
    async with db_session_factory() as session:
        await upsert_token(
            session,
            _token(
                "T426B_RETRO",
                created_at=observed_at - timedelta(minutes=20),
                symbol="ARC",
            ),
        )
        await _insert_event(session, event_id=event_id, observed_at=observed_at, symbol_hint="ARC")
        await session.commit()

        matched = await match_events_once(session, now=NOW)
        await session.commit()

    assert matched is not None
    assert {m.mint for m in matched if m.event_id == event_id} == {"T426B_RETRO"}


async def test_an_event_older_than_the_window_is_not_scanned(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from hunter_meme_worker.events_config import MATCH_WINDOW_H_DEFAULT

    event_id = str(uuid.uuid4())
    stale_observed_at = NOW - timedelta(hours=MATCH_WINDOW_H_DEFAULT + 1)
    async with db_session_factory() as session:
        await upsert_token(
            session,
            _token(
                "T426B_STALE", created_at=stale_observed_at + timedelta(minutes=5), symbol="OLD"
            ),
        )
        await _insert_event(
            session, event_id=event_id, observed_at=stale_observed_at, symbol_hint="OLD"
        )
        await session.commit()

        matched = await match_events_once(session, now=NOW)
        await session.commit()

    assert matched is not None
    assert event_id not in {m.event_id for m in matched}


async def test_a_pair_matched_once_stays_matched_across_ticks(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Idempotency, end to end: a second tick over the same window finds the
    pair already recorded and does not return it again."""
    event_id = str(uuid.uuid4())
    async with db_session_factory() as session:
        await upsert_token(
            session, _token("T426B_ONCE", created_at=NOW + timedelta(minutes=1), symbol="BUM")
        )
        await _insert_event(session, event_id=event_id, observed_at=NOW, symbol_hint="BUM")
        await session.commit()

        first = await match_events_once(session, now=NOW + timedelta(minutes=5))
        await session.commit()
        second = await match_events_once(session, now=NOW + timedelta(minutes=10))
        await session.commit()

    assert first is not None and second is not None
    assert {(m.event_id, m.mint) for m in first} == {(event_id, "T426B_ONCE")}
    assert (event_id, "T426B_ONCE") not in {(m.event_id, m.mint) for m in second}


async def test_the_cursor_advances_so_a_later_tick_does_not_rescan(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_id = str(uuid.uuid4())
    async with db_session_factory() as session:
        await _insert_event(session, event_id=event_id, observed_at=NOW, symbol_hint="LATE")
        await session.commit()
        await match_events_once(session, now=NOW + timedelta(minutes=1))
        await session.commit()

        cursor = (
            await session.execute(
                text("SELECT last_scanned_created_at FROM meme_events WHERE id = :id"),
                {"id": event_id},
            )
        ).scalar_one()
    assert cursor is not None

    async with db_session_factory() as session:
        # A coin born before the cursor must never surface as a candidate again,
        # even though it is well inside the event's own 72h window.
        await upsert_token(
            session,
            _token("T426B_BEFORE_CURSOR", created_at=NOW - timedelta(minutes=25), symbol="LATE"),
        )
        await session.commit()
        matched = await match_events_once(session, now=NOW + timedelta(minutes=2))
        await session.commit()
    assert matched is not None
    assert "T426B_BEFORE_CURSOR" not in {m.mint for m in matched}


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
        await session.execute(text("DELETE FROM meme_events WHERE title = 'count test'"), {})
        open_id, matched_id = str(uuid.uuid4()), str(uuid.uuid4())
        await upsert_token(session, _token("T426B_COUNT", created_at=NOW))
        await session.execute(
            text(
                "INSERT INTO meme_events (id, observed_at, source, kind, title, "
                "confidence, recorded_by) VALUES "
                "(:id1, :now, 'manual', 'incident', 'count test', 'rumor', 'test'), "
                "(:id2, :now, 'manual', 'incident', 'count test', 'rumor', 'test')"
            ),
            {"id1": open_id, "id2": matched_id, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO meme_event_matches (event_id, mint, match_kind, matched_at) "
                "VALUES (:id, :mint, 'buy', :now)"
            ),
            {"id": matched_id, "mint": "T426B_COUNT", "now": NOW},
        )
        await session.commit()
        counts = await count_events(session, now=NOW)
    assert counts.open >= 1
    assert counts.matched_1h >= 1


async def test_explain_the_candidate_scan_uses_the_created_at_index_at_100k_rows(
    db_engine: AsyncEngine,
) -> None:
    """The T4.24b post-incident rule: bounded floor + index, plan declared.
    150 k synthetic rows spread over ~156 days so the floor leaves only a
    sliver of the table to read, never a sequential scan. Rolled back at the
    end: this must not leave 150 k rows behind for every other test in the
    shared container to scan."""
    from hunter_meme_worker.events_repo import _CANDIDATE_TOKENS  # the frozen query itself

    conn = await db_engine.connect()
    trans = await conn.begin()
    try:
        await conn.execute(
            text(
                "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, "
                "last_seen_at, created_at, symbol) "
                "SELECT 'T426B_BULK_' || gs, 'pumpfun_rest', now(), now(), "
                "  timestamptz '2026-01-01' + (gs * interval '90 seconds'), "
                "  'SYM' || (gs % 1000) "
                "FROM generate_series(1, 150000) AS gs "
                "ON CONFLICT (mint) DO NOTHING"
            )
        )
        await conn.execute(text("ANALYZE meme_tokens"))
        plan_rows = (
            (
                await conn.execute(
                    text(f"EXPLAIN {_CANDIDATE_TOKENS.text}"),
                    {
                        "floor": datetime(2026, 3, 1, tzinfo=UTC),
                        "now": datetime(2026, 3, 1, 1, 0, tzinfo=UTC),
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
    notes_dir.joinpath("notes-T4.26b-explain.txt").write_text(
        f"rows={row_count}\n{plan}", encoding="utf-8"
    )
