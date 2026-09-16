"""The Mayhem flag of the minute clock's gate rows (T4.27) — read beside
``lab_repo.load_gate_rows`` until that query carries ``t.mayhem_enabled`` /
``t.mayhem_state`` itself (its file was in another task's hands when this
landed; the 15-second rows read the two columns in ``lab_repo_fast`` directly).

One bounded query per closed minute — ``meme_tokens`` by primary key, for the
minute's mints only (the tracked set, ~130) — inside a savepoint with its own
statement timeout (the T4.24b rule for anything the Lab loop runs per tick).
If it fails, the rows keep ``mayhem_enabled = None`` and every gate refuses
them ``mayhem_unknown`` by name: **fail closed**, a flag nobody read is not
"not Mayhem". ``EXPLAIN`` in ``.claude/state/notes-T4.27.md``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from hunter_core.logging import get_logger
from hunter_meme_worker.lab_repo import load_gate_rows

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.proposals import GateRow

__all__ = ["MayhemFlag", "load_gate_rows_with_mayhem", "mayhem_flags_for", "with_mayhem_flags"]

_logger = get_logger(__name__)

STATEMENT_TIMEOUT_MS = 2000
"""A primary-key read of ~130 rows; anything slower is a database in trouble,
and the tick must go on (refusing by name) rather than die on it."""

_FLAGS = text("SELECT mint, mayhem_enabled, mayhem_state FROM meme_tokens WHERE mint = ANY(:mints)")

MayhemFlag = tuple[bool | None, str | None]
"""``(mayhem_enabled, mayhem_state)`` as the token row carries them."""


async def mayhem_flags_for(session: AsyncSession, mints: Sequence[str]) -> dict[str, MayhemFlag]:
    """The flag and the agent state of each mint, or ``{}`` when the read failed."""
    if not mints:
        return {}
    try:
        async with session.begin_nested():
            await session.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
            rows = (await session.execute(_FLAGS, {"mints": list(mints)})).mappings().all()
    except DBAPIError as exc:
        _logger.warning("meme_mayhem_flags_read_failed", mints=len(mints), error=type(exc).__name__)
        return {}
    return {str(r["mint"]): (r["mayhem_enabled"], r["mayhem_state"]) for r in rows}


def with_mayhem_flags(rows: Sequence[GateRow], flags: dict[str, MayhemFlag]) -> list[GateRow]:
    """Every row with its token's flag; a mint absent from ``flags`` stays unknown."""
    out: list[GateRow] = []
    for row in rows:
        flag = flags.get(row.mint)
        if flag is None:
            out.append(row)
            continue
        enabled, state = flag
        out.append(replace(row, mayhem_enabled=enabled, mayhem_state=state))
    return out


async def load_gate_rows_with_mayhem(
    session: AsyncSession, *, minute: datetime, features_version: str
) -> list[GateRow]:
    """``lab_repo.load_gate_rows`` plus the Mayhem flag of every row's token."""
    rows = await load_gate_rows(session, minute=minute, features_version=features_version)
    if not rows:
        return rows
    return with_mayhem_flags(rows, await mayhem_flags_for(session, sorted({r.mint for r in rows})))
