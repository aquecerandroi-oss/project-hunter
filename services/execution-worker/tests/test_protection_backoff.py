"""T3.5b item 5 — a degraded protection retries with a backoff, not per second.

A stop that fired and found no book leaves the intention ``open`` and degraded,
and the next cycle retries it without waiting for a new crossing — that is what
stops a stop disappearing when the tape goes quiet, and it stays true.

What was not true is the cadence. Every retry writes an ``orders`` row (an
attempt has its own identity, always), so a market that stopped printing a book
produced **one refused row per second, for ever**: 86.400 a day for a quantity
nobody can sell, while ``intents_repo._applied_attempts`` rebuilt a UNION over
all of them on every single cycle. The retry now doubles from 1 s to a ceiling
of 60 s, and between two allowed instants **nothing is written at all**.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from hunter_execution_worker.triggering import BACKOFF_START_S, DegradedRetries

from .builders import create_tenant
from .scenarios import CYCLE_AT, count_of, no_book_snapshot, open_a_position, protect

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

CYCLES = 11
"""Eleven passes of the 1 s protection loop, from the crossing onwards."""

ALLOWED = (0, 1, 3, 7)
"""The offsets a 1 s → 2 s → 4 s → 8 s backoff lets through. Everything between
them is a cycle that writes nothing."""


class TestADegradedProtectionBacksOff:
    async def test_eleven_seconds_without_a_book_write_four_attempts_not_eleven(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        tenant = await create_tenant(db_engine)
        wallet = await open_a_position(db_session_factory, db_engine, tenant)
        retries = DegradedRetries()

        attempted: list[int] = []
        rows_after: list[int] = []
        for offset in range(CYCLES):
            at = CYCLE_AT + timedelta(seconds=offset)
            outcomes = await protect(
                db_session_factory,
                wallet,
                no_book_snapshot(tenant, ts=at, trade_id=100 + offset),
                now=at,
                retries=retries,
            )
            if outcomes:
                assert [outcome.status for outcome in outcomes] == ["pending_degraded"]
                attempted.append(offset)
            rows_after.append(await count_of(db_engine, wallet, "orders"))

        assert tuple(attempted) == ALLOWED
        # One entry order plus one exit order per allowed attempt, and the row
        # count never moves on a cycle the backoff refused.
        assert rows_after == [1 + sum(1 for a in ALLOWED if a <= o) for o in range(CYCLES)]
        assert await count_of(db_engine, wallet, "fills") == 1

    async def test_nothing_is_lost_the_book_comes_back_and_the_stop_fills(
        self,
        db_engine: AsyncEngine,
        db_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """A backoff that swallowed the recovery would be worse than the bug."""
        from .scenarios import gap_snapshot

        tenant = await create_tenant(db_engine)
        wallet = await open_a_position(db_session_factory, db_engine, tenant)
        retries = DegradedRetries()

        degraded = await protect(
            db_session_factory,
            wallet,
            no_book_snapshot(tenant),
            now=CYCLE_AT,
            retries=retries,
        )
        assert [outcome.status for outcome in degraded] == ["pending_degraded"]

        # One second later — the first step of the backoff — the book is back.
        recovered = await protect(
            db_session_factory,
            wallet,
            gap_snapshot(tenant, trade_id=3),
            now=CYCLE_AT + timedelta(seconds=BACKOFF_START_S),
            retries=retries,
        )

        assert [outcome.status for outcome in recovered] == ["filled"]
        assert retries.delay_s == {}
        assert retries.next_at == {}
