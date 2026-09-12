"""``PostgresOrderJournal`` — the durable ``OrderJournal`` of §9.4, written *synchronously*
from the submitter's thread.

``MemeSubmitter`` (T4.8) is synchronous and runs in a worker thread
(``asyncio.to_thread``); the executor's database is asyncpg on the main loop. Each
journal call therefore schedules a coroutine on the main loop and **blocks the
thread until that coroutine's transaction committed**
(``run_coroutine_threadsafe(...).result()``). That is what makes rule 2 of §9.4
true on disk: the signature is in ``meme_live_orders.signatures`` before
``sendTransaction`` is called, so a crash between the two leaves a row that
``reconcile`` settles on the next boot — never a second signature.

The journal is keyed by the row's ``client_order_id`` (the submitter's
``proposal_id`` parameter is that string): ``meme:{proposal_id}`` for the buy,
``meme:{proposal_id}:exit:{n}`` for a sell attempt.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar, cast

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.journal import OrderRecord, SigningLocked, SubmitState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = ["WORKER_ROLE", "PostgresOrderJournal", "fill_jsonable", "record_from_row"]

WORKER_ROLE = "hunter_worker"
_T = TypeVar("_T")

_GET = text(
    "SELECT client_order_id, proposal_id, signatures, status, reason, fill, signing_at, "
    "       last_valid_block_height "
    "FROM meme_live_orders WHERE client_order_id = :key"
)
_BY_SIGNATURE = text(
    "SELECT client_order_id, proposal_id, signatures, status, reason, fill, signing_at, "
    "       last_valid_block_height "
    "FROM meme_live_orders WHERE signatures @> CAST(:sig AS jsonb) LIMIT 1"
)
_LOCK = text(
    "UPDATE meme_live_orders SET signing_at = :now, updated_at = :now "
    "WHERE client_order_id = :key AND signing_at IS NULL RETURNING client_order_id"
)
_UNLOCK = text(
    "UPDATE meme_live_orders SET signing_at = NULL, updated_at = :now WHERE client_order_id = :key"
)
_SIGNATURE = text(
    "UPDATE meme_live_orders SET signatures = signatures || CAST(:sig AS jsonb), "
    "  tx_signature = :signature, last_valid_block_height = :height, "
    "  status = 'simulated', simulated_at = coalesce(simulated_at, :now), updated_at = :now "
    "WHERE client_order_id = :key AND NOT (signatures @> CAST(:sig AS jsonb))"
)
_STATE = text(
    "UPDATE meme_live_orders SET status = :state, reason = :reason, "
    "  fill = CAST(:fill AS jsonb), "
    "  submitted_at = CASE WHEN :state IN ('submitted_unconfirmed', 'confirmed') "
    "                      THEN coalesce(submitted_at, CAST(:now AS timestamptz)) "
    "                      ELSE submitted_at END, "
    "  settled_at = CASE WHEN :state IN ('confirmed', 'failed') THEN CAST(:now AS timestamptz) "
    "               ELSE settled_at END, "
    "  updated_at = :now "
    "WHERE client_order_id = :key AND status <> 'confirmed'"
)


def fill_jsonable(fill: Any) -> Any:
    """The fill as JSON: dataclasses/objects with ``as_json`` or ``__dict__`` are flattened."""
    if fill is None:
        return None
    as_json = getattr(fill, "as_json", None)
    if callable(as_json):
        return as_json()
    if hasattr(fill, "__dict__"):
        fields = cast(dict[str, Any], vars(fill))
        return {
            k: (list(cast(tuple[Any, ...], v)) if isinstance(v, tuple) else v)
            for k, v in fields.items()
        }
    return fill


def record_from_row(row: Any) -> OrderRecord:
    raw_state = row["status"]
    state = raw_state if raw_state in {s.value for s in SubmitState} else None
    return OrderRecord(
        proposal_id=str(row["client_order_id"]),
        client_order_id=str(row["client_order_id"]),
        signatures=[str(s) for s in cast(list[Any], row["signatures"] or [])],
        state=None if state is None else SubmitState(state),
        reason=row["reason"] or "",
        fill=row["fill"],
        signing=row["signing_at"] is not None,
        last_valid_block_height=row["last_valid_block_height"],
    )


class PostgresOrderJournal:
    """Sync facade over async rows; every method commits its own transaction."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        loop: asyncio.AbstractEventLoop,
        *,
        timeout_s: float = 15.0,
    ) -> None:
        self._sessions = session_factory
        self._loop = loop
        self._timeout = timeout_s

    def _run(self, work: Callable[[AsyncSession], Awaitable[_T]]) -> _T:
        async def transaction() -> _T:
            async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
                return await work(session)

        try:
            running: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None:
            # Blocking on the loop's own thread would deadlock the coroutine we wait for.
            raise RuntimeError("PostgresOrderJournal must be driven from a worker thread")
        return asyncio.run_coroutine_threadsafe(transaction(), self._loop).result(self._timeout)

    # ---------------------------------------------------------------- reads
    def get(self, proposal_id: str) -> OrderRecord | None:
        async def work(session: AsyncSession) -> OrderRecord | None:
            row = (await session.execute(_GET, {"key": proposal_id})).mappings().first()
            return None if row is None else record_from_row(row)

        return self._run(work)

    def find_by_signature(self, signature: str) -> OrderRecord | None:
        async def work(session: AsyncSession) -> OrderRecord | None:
            row = (
                (await session.execute(_BY_SIGNATURE, {"sig": json.dumps([signature])}))
                .mappings()
                .first()
            )
            return None if row is None else record_from_row(row)

        return self._run(work)

    # --------------------------------------------------------------- writes
    def begin_signing(self, proposal_id: str) -> OrderRecord:
        """Take the row's signing lock (VM9). The row must already exist: the executor
        inserts it with the admission before the submitter ever sees it."""

        async def work(session: AsyncSession) -> OrderRecord:
            locked = (await session.execute(_LOCK, {"key": proposal_id, "now": utcnow()})).scalar()
            if locked is None:
                row = (await session.execute(_GET, {"key": proposal_id})).mappings().first()
                if row is None:
                    raise SigningLocked(f"{proposal_id}: no admitted row to sign")
                raise SigningLocked(proposal_id)
            row = (await session.execute(_GET, {"key": proposal_id})).mappings().one()
            return record_from_row(row)

        return self._run(work)

    def record_signature(
        self, proposal_id: str, signature: str, *, last_valid_block_height: int | None
    ) -> None:
        async def work(session: AsyncSession) -> None:
            await session.execute(
                _SIGNATURE,
                {
                    "key": proposal_id,
                    "sig": json.dumps([signature]),
                    "signature": signature,
                    "height": last_valid_block_height,
                    "now": utcnow(),
                },
            )

        self._run(work)

    def record_state(self, proposal_id: str, state: SubmitState, reason: str, fill: Any) -> None:
        async def work(session: AsyncSession) -> None:
            await session.execute(
                _STATE,
                {
                    "key": proposal_id,
                    "state": state.value,
                    "reason": reason,
                    "fill": json.dumps(fill_jsonable(fill), default=str),
                    "now": utcnow(),
                },
            )

        self._run(work)

    def release_signing(self, proposal_id: str) -> None:
        async def work(session: AsyncSession) -> None:
            await session.execute(_UNLOCK, {"key": proposal_id, "now": utcnow()})

        self._run(work)
