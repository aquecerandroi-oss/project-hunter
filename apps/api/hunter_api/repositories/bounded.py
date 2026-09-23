"""``BoundedRows`` — a capped list that says when the cap bit (T4.82).

Two reads of the confluence screen answer a **bounded window** rather than a
cursor-paginated listing (the ``meme_live`` shape: a handful of rows a day, a
window the caller chose). A plain ``LIMIT`` on those is a quiet lie, so the
cap is reported instead of hidden. One module because two sibling
repositories share it, and a repository should not import another repository
for a dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["BoundedRows", "bounded"]


@dataclass(frozen=True, slots=True)
class BoundedRows[T]:
    """Rows, and whether the cap swallowed at least one more of them.

    Astra's review of T4.82 named the failure a silent ``LIMIT`` causes here:
    a window holding one more eligible position than the cap, where the row
    that is dropped is precisely the old one that was open at the cursor,
    lets the screen conclude "nada estava vigente" from a page that merely ran
    out of room. Reordering only changes *which* facts vanish, so the reads
    ask for one row past the cap and report whether it was there. These lists
    carry no cursor by design (a bounded window, like ``meme_live``'s), so
    ``truncated`` means "ask for a narrower window", not "fetch page 2".
    """

    rows: list[T]
    truncated: bool


async def bounded[T](
    session: AsyncSession, statement: Select[tuple[T]], limit: int
) -> BoundedRows[T]:
    """Run ``statement`` (already built with ``LIMIT limit + 1``) and split."""
    fetched = list((await session.execute(statement)).scalars().all())
    return BoundedRows(rows=fetched[:limit], truncated=len(fetched) > limit)
