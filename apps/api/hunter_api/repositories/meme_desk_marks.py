"""The ``0029`` columns of ``meme_paper_bets`` — ``mark_source`` and
``mark_stale_s`` (T4.11) — read **tolerantly**, so the desk keeps answering on
a database still at ``0028``.

``repositories/meme_desk_tables.py`` declares the bet table as every reader
``select(meme_paper_bets)``s it (the desk, T4.13's ``/meme/tests``); a column
added there is a column every one of those reads requires to exist. The two
of ``0029`` are therefore kept out of it and read here in a second step:
one catalogue probe (``information_schema.columns``, which raises nothing),
then — only when both columns exist — one read by id, folded into the
:class:`~hunter_api.repositories.meme_desk_rows.BetRow`s with
:func:`dataclasses.replace`. Below ``0029`` the rows keep ``None`` in both
fields: "the source is not known", never a fabricated ``curve``.

The probe is asked on every read, on purpose: it is one catalogue lookup on
one table (microseconds next to the desk's own joins), and a cached answer
would be a statement about *a* database when a process may talk to more than
one (the integration tests do). The deploy that applies ``0029`` is therefore
seen by the next read, with no restart of this reader.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Final

from sqlalchemy import Column, Integer, MetaData, Table, Text, select, text
from sqlalchemy.dialects.postgresql import UUID

from hunter_api.repositories.meme_desk_rows import BetRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["MARK_COLUMNS_0029", "marks_0029_present", "with_marks_0029"]

MARK_COLUMNS_0029: Final[tuple[str, ...]] = ("mark_source", "mark_stale_s")
"""``ddl/meme_moonshot.py``'s ``BET_COLUMNS_0029``, spelled here so this
module imports nothing from ``infra/migrations``."""

_PROBE = text(
    "SELECT count(*) FROM information_schema.columns "
    "WHERE table_schema = 'public' AND table_name = 'meme_paper_bets' "
    "  AND column_name IN ('mark_source', 'mark_stale_s')"
)
"""Two when ``0029`` ran, zero before it; ``information_schema`` lists the
columns of every table the role may read, which ``hunter_app`` may."""

_marks_0029 = Table(
    "meme_paper_bets",
    MetaData(),
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("mark_source", Text),
    Column("mark_stale_s", Integer),
)
"""A private view of the same table with only the ``0029`` columns — on its
own ``MetaData`` so ``meme_desk_tables.meme_paper_bets`` stays exactly the
pre-``0029`` shape every other reader selects."""


async def marks_0029_present(session: AsyncSession) -> bool:
    """Whether both ``0029`` columns exist on the database this session sees."""
    count = await session.scalar(_PROBE)
    return int(count or 0) == len(MARK_COLUMNS_0029)


async def with_marks_0029(
    session: AsyncSession, bets: Mapping[uuid.UUID, BetRow]
) -> dict[uuid.UUID, BetRow]:
    """The same rows with ``mark_source``/``mark_stale_s`` filled in when the
    database has them; untouched (``None``) when it does not."""
    out = dict(bets)
    if not out or not await marks_0029_present(session):
        return out
    rows = (
        await session.execute(select(_marks_0029).where(_marks_0029.c.id.in_(list(out))))
    ).mappings()
    for r in rows:
        bet = out.get(r["id"])
        if bet is None:
            continue
        out[r["id"]] = replace(
            bet,
            mark_source=None if r["mark_source"] is None else str(r["mark_source"]),
            mark_stale_s=None if r["mark_stale_s"] is None else int(r["mark_stale_s"]),
        )
    return out
