"""The late-facts half of the copy executor (H-037): what the chain said afterwards about a fact we acted on
(the confirmation delay and the ``ideal`` post-trade reserves, an invalidation, an ``unverified`` flag).
Split from ``copy_exec.py`` for the 350-line budget.

A late fact is written **only onto a row that exists, and for an exit only after the close landed**
(R2 fix B6): a confirmation of an exit that overtakes its own close raises :class:`NotYet` and is parked; a
zero-row update raises :class:`RowMissing` and is retried — it is never consumed as a success.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_meme_worker.copy_repo import set_copy_fact

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.copy_book import CopyBook
    from hunter_meme_worker.copy_events import ConfirmIntent, InvalidateIntent, UnverifiedIntent
    from hunter_meme_worker.copy_position import Live
    from hunter_meme_worker.copy_stats import CopyStats

__all__ = ["FactJobs", "NotYet", "RowMissing"]

WORKER_ROLE = "hunter_worker"


class NotYet(Exception):
    """The row this fact belongs to has not landed yet: park the job, do not count a failure."""


class RowMissing(Exception):
    """The update touched no row: the fact was NOT written."""


class FactJobs:
    live: dict[str, Live]
    _sessions: async_sessionmaker[AsyncSession]
    _book: CopyBook
    _stats: CopyStats
    _closed: dict[str, str]
    _clock: Callable[[], Any]

    def _bet_when_ready(self, key: str, kind: str) -> str | None:
        """The bet a late fact belongs to; ``NotYet`` while its entry (or, for an exit, its close) has not
        landed; ``None`` when the copy is unknown to this process (restarted, evicted): nothing to write."""
        live = self.live.get(key)
        if kind == "exit":
            if live is not None:
                raise NotYet  # the close has not landed: the confirmation must not overtake it
            return self._closed.get(key)
        if live is not None:
            return live.bet_id
        bet = self._closed.get(key)
        if bet is None and self._book.position(key) is not None:
            raise NotYet  # the copy exists in the book but its row has not landed yet
        return bet

    async def _set(self, bet_id: str, where: str, name: str, value: Any) -> None:
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            if not await set_copy_fact(session, bet_id, where=where, name=name, value=value):
                raise RowMissing(f"{where}.copy.{name} on {bet_id}")

    async def _confirm(self, job: ConfirmIntent) -> None:
        bet_id = self._bet_when_ready(job.key, job.kind)
        if bet_id is None:
            self._stats.record_confirmation(job.delay_ms)
            return
        await self._set(bet_id, job.kind, "confirmation_delay_ms", job.delay_ms)
        if job.post_reserves is not None:
            await self._set(bet_id, job.kind, "ideal_post_reserves", job.post_reserves)
        self._stats.record_confirmation(job.delay_ms)

    async def _invalidate(self, job: InvalidateIntent) -> None:
        """The event behind a copy was not confirmed: the reason is written on the copy and the copy
        **stays** in the primary with its economic result — an open one was already sent to market
        (``invalidated``) by the book, ahead of this job in the same lock."""
        bet_id = self._bet_when_ready(job.key, "entry")
        if bet_id is not None:
            await self._set(bet_id, "entry", "invalid_reason", job.reason)
            await self._set(bet_id, "entry", "invalid_event", job.kind)
        self._stats.record_invalidated()

    async def _unverified(self, job: UnverifiedIntent) -> None:
        """Only ``rpc_error`` ever answered: flagged and kept — never liquidated on a node's silence."""
        bet_id = self._bet_when_ready(job.key, "entry")
        if bet_id is not None:
            await self._set(bet_id, "entry", "unverified", True)
            await self._set(bet_id, "entry", "unverified_event", job.kind)
        self._stats.unverified += 1
