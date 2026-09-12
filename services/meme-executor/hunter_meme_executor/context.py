"""What every loop of the executor runs on: the config, the mode, the signer (or
none), the chain reader, the durable journal, the kill switch and the counters.

Built once by ``main.py``; every loop step receives it. The signer is the only
object in the process that can sign, and it is ``None`` whenever the live flag
is off — a paper executor has nothing to sign with, by construction.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.execution.meme.gates import MemeExecutionMode
    from hunter_core.execution.meme.signer import MemeSigner
    from hunter_meme_executor.chain import ChainReader
    from hunter_meme_executor.config import ExecutorConfig
    from hunter_meme_executor.journal_db import PostgresOrderJournal
    from hunter_meme_executor.kill_switch import KillSwitchReader

HeartbeatWriter = "Callable[[dict[str, str]], Awaitable[None]]"


@dataclass(slots=True)
class ExecutorState:
    last_entries_tick_at: datetime | None = None
    last_exits_tick_at: datetime | None = None
    last_signature: str | None = None
    last_refusal: str | None = None
    entries_seen: int = 0
    entries_refused: int = 0
    entries_confirmed: int = 0
    exits_confirmed: int = 0
    exits_blocked: int = 0
    rpc_errors: int = 0
    wallet_lamports: int | None = None
    wallet_read_at: datetime | None = None
    blocked_exits: dict[str, str] = field(default_factory=lambda: dict[str, str]())


@dataclass(slots=True)
class ExecutorContext:
    config: ExecutorConfig
    mode: MemeExecutionMode
    signer: MemeSigner | None
    session_factory: async_sessionmaker[AsyncSession]
    chain: ChainReader
    journal: PostgresOrderJournal
    kill: KillSwitchReader
    heartbeat: Callable[[dict[str, str]], Awaitable[None]]
    loop: asyncio.AbstractEventLoop
    state: ExecutorState = field(default_factory=ExecutorState)
