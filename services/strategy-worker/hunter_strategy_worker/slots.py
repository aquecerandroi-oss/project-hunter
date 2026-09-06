"""The durable tracking slot: locking, checkpointing, arming, releasing.

``shadow_episodes`` holds one row per ``(strategy_version_id, market_id,
cohort)``. Every read-modify-write of it happens inside one transaction that
took ``SELECT ... FOR UPDATE`` on the row first, so two consumers handling the
same bar (or the same market from two instances) serialise into a single
tracking instead of two.

Two invariants the DDL cannot state and this module must (DATABASE.md §16.3):

- the outcome a slot points at is *open* (``pending_entry``/``active``);
- ``last_bar_close`` is a **barrier**, not just a bookkeeping stamp. A bar is
  only evaluated when it closes strictly after it, and when a tracking ends the
  barrier is pushed to the end instant. Re-arming needs a bar where the entry
  condition was false *after* the previous tracking ended (SHADOW-LAB.md §4),
  and without the barrier a bar that closed **before** the end but was
  delivered after it would re-arm the slot on stale evidence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.agents_shadow import ShadowEpisode
from hunter_core.domain.types import ensure_utc, uuid7

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
"""``last_bar_close`` of a slot that has never evaluated anything. The column is
``NOT NULL``, and an honest "nothing yet" beats a fabricated recent stamp."""

__all__ = ["EPOCH", "Slot", "advance", "lock_slot", "release_tracking"]


@dataclass(frozen=True, slots=True)
class Slot:
    """One locked ``shadow_episodes`` row."""

    id: uuid.UUID
    strategy_version_id: uuid.UUID
    market_id: uuid.UUID
    cohort: str
    episode_id: uuid.UUID
    last_bar_close: datetime
    armed: bool
    open_outcome_signal_id: uuid.UUID | None

    @property
    def tracking_open(self) -> bool:
        return self.open_outcome_signal_id is not None

    def accepts(self, bar_close: datetime) -> bool:
        """Whether this bar is still ahead of the barrier."""
        return ensure_utc(bar_close) > self.last_bar_close


async def lock_slot(
    session: AsyncSession,
    *,
    strategy_version_id: uuid.UUID,
    market_id: uuid.UUID,
    cohort: str,
) -> Slot:
    """Create the slot if it does not exist, then lock it ``FOR UPDATE``.

    The insert runs first and swallows the conflict: two transactions racing to
    create the same slot serialise on the unique index, and the loser then finds
    the row and waits for the winner's lock (Astra, S2 design review,
    must-fix 1). A ``SELECT ... FOR UPDATE`` alone locks nothing when the row
    does not exist yet, which is exactly the first-bar case.
    """
    await session.execute(
        pg_insert(ShadowEpisode)
        .values(
            id=uuid7(),
            strategy_version_id=strategy_version_id,
            market_id=market_id,
            cohort=cohort,
            episode_id=uuid7(),
            last_bar_close=EPOCH,
            armed=True,
        )
        .on_conflict_do_nothing(constraint="uq_shadow_episodes_slot")
    )
    row = (
        await session.execute(
            select(ShadowEpisode)
            .where(
                ShadowEpisode.strategy_version_id == strategy_version_id,
                ShadowEpisode.market_id == market_id,
                ShadowEpisode.cohort == cohort,
            )
            .with_for_update()
        )
    ).scalar_one()
    return Slot(
        id=row.id,
        strategy_version_id=row.strategy_version_id,
        market_id=row.market_id,
        cohort=row.cohort,
        episode_id=row.episode_id,
        last_bar_close=ensure_utc(row.last_bar_close),
        armed=row.armed,
        open_outcome_signal_id=row.open_outcome_signal_id,
    )


async def advance(
    session: AsyncSession,
    slot: Slot,
    *,
    bar_close: datetime,
    armed: bool,
    open_outcome_signal_id: uuid.UUID | None = None,
    new_episode: bool = False,
) -> None:
    """Move the barrier and the arming state of a locked slot."""
    values: dict[str, object] = {
        "last_bar_close": func.greatest(ShadowEpisode.last_bar_close, ensure_utc(bar_close)),
        "armed": armed,
    }
    if open_outcome_signal_id is not None:
        values["open_outcome_signal_id"] = open_outcome_signal_id
    if new_episode:
        values["episode_id"] = uuid7()
    await session.execute(update(ShadowEpisode).where(ShadowEpisode.id == slot.id).values(**values))


async def release_tracking(
    session: AsyncSession, *, signal_id: uuid.UUID, ended_at: datetime
) -> None:
    """Free the slot a finished tracking held and set the re-arm barrier.

    ``armed`` goes to ``false`` and the barrier to the end instant, so only a
    bar closing strictly after the end can prove the entry condition false and
    re-arm the slot. Matched by ``open_outcome_signal_id`` rather than by slot
    id: a tracking may only release the slot it actually occupies.
    """
    await session.execute(
        update(ShadowEpisode)
        .where(ShadowEpisode.open_outcome_signal_id == signal_id)
        .values(
            open_outcome_signal_id=None,
            armed=False,
            last_bar_close=func.greatest(ShadowEpisode.last_bar_close, ensure_utc(ended_at)),
        )
    )
