"""The four completion signals against a real Postgres at ``head`` (``0024``) —
one file, one container, run alone (``timeout 590``).

What only a database can prove: the six columns land through the real upsert;
each stamp is written once (``COALESCE``) while ``completed_at`` moves earlier
when a later observation brings an earlier signal (``LEAST``) and never later;
a REST ``complete`` with a zero reserve leaves ``completed_at`` NULL until a
pool corroborates it; the denominator and its source land as a pair;
``load_tracked`` excludes the mint whose REST photo said complete and brings
back, for one final read, the one classified by a board alone; the matrix view
counts today's cohort as ``hunter_app``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_meme_worker.graduation import GLOBAL_PARAMS, POOL_SOURCE_TRENCHES
from hunter_meme_worker.repo import TokenRow, load_tracked, upsert_token

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
APP = "hunter_app"
T0 = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
_SIGNALS = text(
    "SELECT completed_at, rest_complete_seen_at, curve_filled_seen_at, graduated_board_seen_at, "
    "pool_created_at, pool_created_source, initial_real_token_reserves, "
    "progress_denominator_source FROM meme_tokens WHERE mint = :mint"
)


def _token(mint: str, **kw: object) -> TokenRow:
    defaults: dict[str, object] = {
        "mint": mint,
        "first_seen_source": "pumpfun_rest",
        "first_seen_at": T0,
        "last_seen_at": T0,
        "created_at": T0,
    }
    defaults.update(kw)
    return TokenRow(**defaults)  # type: ignore[arg-type]


async def _signals(factory: async_sessionmaker[AsyncSession], mint: str) -> dict[str, object]:
    async with role_session(factory, db_role=WORKER) as session:
        return dict((await session.execute(_SIGNALS, {"mint": mint})).mappings().one())


async def test_a_zero_reserve_rest_complete_waits_for_a_pool_and_completed_at_moves_earlier(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mint = "GRAD_ZERO"
    async with role_session(db_session_factory, db_role=WORKER) as session:
        # The REST photo: complete, zero reserve — the reducer offers no completed_at.
        await upsert_token(session, _token(mint, rest_complete_seen_at=T0, completed_at=None))
    first = await _signals(db_session_factory, mint)
    assert first["rest_complete_seen_at"] == T0 and first["completed_at"] is None
    async with role_session(db_session_factory, db_role=WORKER) as session:
        # The board's retrospective gd: earlier than the photo, and evidence enough.
        gd = T0 - timedelta(seconds=40)
        await upsert_token(
            session,
            _token(
                mint,
                first_seen_source="trenches_ws",
                pool_created_at=gd,
                pool_created_source=POOL_SOURCE_TRENCHES,
                completed_at=gd,
                rest_complete_seen_at=T0 + timedelta(minutes=5),  # a second photo: ignored
            ),
        )
        # A later signal never moves completed_at later.
        await upsert_token(
            session,
            _token(mint, graduated_board_seen_at=T0 + timedelta(minutes=1), completed_at=T0),
        )
    row = await _signals(db_session_factory, mint)
    assert row["completed_at"] == T0 - timedelta(seconds=40)
    assert row["rest_complete_seen_at"] == T0, "the first photo is the signal, once"
    assert row["pool_created_source"] == POOL_SOURCE_TRENCHES
    assert row["graduated_board_seen_at"] == T0 + timedelta(minutes=1)
    assert row["curve_filled_seen_at"] is None


async def test_the_denominator_lands_with_its_source_once(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mint = "GRAD_DENOM"
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(session, _token(mint))  # discovered: nothing known yet
        await upsert_token(
            session,
            _token(
                mint,
                initial_real_token_reserves=Decimal("793100000"),
                progress_denominator_source=GLOBAL_PARAMS,
            ),
        )
        await upsert_token(
            session,
            _token(
                mint,
                initial_real_token_reserves=Decimal("1"),
                progress_denominator_source="observed_virgin",
            ),
        )
    row = await _signals(db_session_factory, mint)
    assert row["initial_real_token_reserves"] == Decimal("793100000")
    assert row["progress_denominator_source"] == GLOBAL_PARAMS


async def test_load_tracked_excludes_the_rest_photo_and_brings_back_the_board_verdict(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The budget rule: a curve whose REST photo said complete has static
    reserves; one classified by a board alone comes back for one final read,
    which records the REST word for the matrix."""
    now = datetime(2026, 12, 3, 12, 0, tzinfo=UTC)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        await upsert_token(
            session,
            _token(
                "GRAD_REST",
                first_seen_at=now,
                last_seen_at=now,
                created_at=now,
                rest_complete_seen_at=now,
            ),
        )
        await upsert_token(
            session,
            _token(
                "GRAD_BOARD",
                first_seen_at=now,
                last_seen_at=now,
                created_at=now,
                graduated_board_seen_at=now,
                completed_at=now,
            ),
        )
    async with role_session(db_session_factory, db_role=WORKER) as session:
        tracked = {
            t.mint: t for t in await load_tracked(session, cutoff=now - timedelta(hours=24), cap=50)
        }
    assert "GRAD_REST" not in tracked
    assert tracked["GRAD_BOARD"].final_read_pending and not tracked["GRAD_BOARD"].complete


async def test_the_matrix_view_counts_the_days_cohort_for_the_api_role(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with role_session(db_session_factory, db_role=APP) as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT mints, completed, rest_complete, graduated_board, pool_created, "
                        "signals_1, signals_2, disagree_rest_pool, rest_only_unclassified "
                        "FROM meme_graduation_matrix_v1 WHERE day_brt = '2026-10-05'"
                    )
                )
            )
            .mappings()
            .one()
        )
    # GRAD_ZERO (rest + board + pool, completed) is the only mint of that Brasília day
    # with a stamp; GRAD_DENOM carries none.
    assert dict(row) == {
        "mints": 1,
        "completed": 1,
        "rest_complete": 1,
        "graduated_board": 1,
        "pool_created": 1,
        "signals_1": 0,
        "signals_2": 0,
        "disagree_rest_pool": 0,
        "rest_only_unclassified": 0,
    }
