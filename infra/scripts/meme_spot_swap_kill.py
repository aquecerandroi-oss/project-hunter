"""The kill switch's effective state, read the same four ways
``hunter_meme_executor.kill_switch.KillSwitchReader`` does (T4.73) — spelled
here in ~30 lines instead of importing that class, because this script
already holds a bare owner ``AsyncConnection`` (``meme_ops_db.migration_url``)
rather than the ``role_session`` sessionmaker the reader wants, and a script
that only ever reads has no business asking for that role's write grants.

``--apply`` requires **exactly** ``ACTIVE`` (Everton's brief): stricter than
the executor's own ``blocks_entries`` (which still trades under ``WARNING``)
— a manual ops script backs off at the first sign of trouble, not just at the
latch.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Protocol

from sqlalchemy import text

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_meme import most_restrictive

__all__ = ["read_effective_kill_switch_state"]

_ROW = text(
    "SELECT state, latched_at, released_at FROM meme_live_kill_switch WHERE scope = 'wallet'"
)


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


def _parse(raw: bytes | str | None) -> KillSwitchState | None:
    if raw is None:
        return None
    value = raw.decode() if isinstance(raw, bytes) else raw
    try:
        return KillSwitchState(value.strip().upper())
    except ValueError:
        return KillSwitchState.EMERGENCY  # an unreadable stop order is a stop order


async def read_effective_kill_switch_state(conn: Connection, redis: Any) -> KillSwitchState:
    system = _parse(os.environ.get("SYSTEM_KILL_SWITCH")) or KillSwitchState.ACTIVE
    try:
        redis_state = _parse(await redis.get("meme:kill"))
    except Exception:
        redis_state = KillSwitchState.EMERGENCY
    kill_file = os.environ.get("MEME_KILL_FILE")
    file_present = kill_file is not None and await asyncio.to_thread(os.path.exists, kill_file)
    file_state = KillSwitchState.EMERGENCY if file_present else None
    row = (await conn.execute(_ROW)).mappings().first()
    if row is None:
        wallet_state = KillSwitchState.EMERGENCY
    else:
        wallet_state = KillSwitchState(str(row["state"]))
        if row["latched_at"] is not None and row["released_at"] is None:
            wallet_state = most_restrictive(wallet_state, KillSwitchState.TRADING_DISABLED)
    states = [system, wallet_state]
    if redis_state is not None:
        states.append(redis_state)
    if file_state is not None:
        states.append(file_state)
    return most_restrictive(*states)
