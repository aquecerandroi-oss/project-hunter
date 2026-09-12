"""The executor's kill switch reader (§7): four sources, one effective state, a
durable latch, and a re-read every 10 s with or without an event.

Sources, each independent and each visible in the heartbeat:

- ``SYSTEM_KILL_SWITCH`` from the environment (the system scope);
- Redis ``meme:kill`` — a plain string ``ACTIVE|WARNING|TRADING_DISABLED|EMERGENCY``
  the operator sets by hand (``docs/DEPLOYMENT.md``, "desligar em 5 s");
- a file named by ``MEME_KILL_FILE``: **existing** means ``EMERGENCY`` (a
  ``touch`` on the host is the fastest stop that needs no Redis);
- the row ``meme_live_kill_switch (scope = 'wallet')`` — the **latched** daily
  state the executor itself writes when the day's loss reaches the cap, and
  which only an owner's manual ``UPDATE`` releases.

``effective`` is the most restrictive of the four. The engine receives them as
``MemeKillSwitchInputs`` (system = env ⊕ redis ⊕ file, wallet = the row) and
``daily_loss_latched`` from the row's ``latched_at``.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.enums import KillSwitchState
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_risk_meme import MemeKillSwitchInputs, most_restrictive

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = ["REDIS_KEY", "WORKER_ROLE", "DayAnchor", "KillSwitchReader"]

logger = get_logger(__name__)
REDIS_KEY = "meme:kill"
WORKER_ROLE = "hunter_worker"

_ROW = text(
    "SELECT state, reason, latched_at, released_at, day_start_utc, day_start_sol_equity, "
    "       peak_sol_equity, anchor_observed_at "
    "FROM meme_live_kill_switch WHERE scope = 'wallet'"
)
_LATCH = text(
    "UPDATE meme_live_kill_switch SET state = 'TRADING_DISABLED', reason = :reason, "
    "  latched_at = :now, released_at = NULL, released_by = NULL, updated_at = :now "
    "WHERE scope = 'wallet' AND (latched_at IS NULL OR released_at IS NOT NULL) RETURNING scope"
)
"""Latch while not latched — a row the owner released by hand (``released_at`` set)
is latchable again: the next day's cap must bite even after yesterday's release."""
_ANCHOR = text(
    "UPDATE meme_live_kill_switch SET day_start_utc = :day_start, "
    "  day_start_sol_equity = :equity, peak_sol_equity = :peak, anchor_observed_at = :now, "
    "  updated_at = :now WHERE scope = 'wallet'"
)
_PEAK = text(
    "UPDATE meme_live_kill_switch SET peak_sol_equity = :peak, updated_at = :now "
    "WHERE scope = 'wallet' AND peak_sol_equity IS NOT NULL AND peak_sol_equity < :peak"
)


@dataclass(frozen=True, slots=True)
class DayAnchor:
    day_start_utc: datetime
    day_start_sol_equity: Decimal
    peak_sol_equity: Decimal
    observed_at: datetime


def _parse(raw: Any) -> KillSwitchState | None:
    if raw is None:
        return None
    value = raw.decode() if isinstance(raw, bytes) else str(raw)
    try:
        return KillSwitchState(value.strip().upper())
    except ValueError:
        logger.warning("meme_kill_unknown_state", value=value[:40])
        return KillSwitchState.EMERGENCY  # an unreadable stop order is a stop order


@dataclass(slots=True)
class KillSwitchReader:
    redis: redis_asyncio.Redis
    session_factory: async_sessionmaker[AsyncSession]
    system: KillSwitchState
    kill_file: str | None
    redis_state: KillSwitchState | None = None
    file_state: KillSwitchState | None = None
    wallet_state: KillSwitchState = KillSwitchState.ACTIVE
    latched: bool = False
    latch_reason: str | None = None
    anchor: DayAnchor | None = None
    last_read_at: datetime | None = None
    legible: bool = False
    errors: dict[str, str] = field(default_factory=lambda: dict[str, str]())

    @property
    def effective(self) -> KillSwitchState:
        states = [self.system, self.wallet_state]
        if self.redis_state is not None:
            states.append(self.redis_state)
        if self.file_state is not None:
            states.append(self.file_state)
        if self.latched:
            states.append(KillSwitchState.TRADING_DISABLED)
        return most_restrictive(*states)

    @property
    def blocks_entries(self) -> bool:
        return self.effective in (KillSwitchState.TRADING_DISABLED, KillSwitchState.EMERGENCY)

    def inputs(self) -> MemeKillSwitchInputs:
        system = most_restrictive(
            self.system,
            self.redis_state or KillSwitchState.ACTIVE,
            self.file_state or KillSwitchState.ACTIVE,
        )
        return MemeKillSwitchInputs(
            system=system, wallet=self.wallet_state, daily_loss_latched=self.latched
        )

    async def refresh(self) -> None:
        """Re-read every source. A source that cannot be read is **EMERGENCY** for
        that source (fail closed) and named in ``errors``."""
        self.errors = {}
        try:
            self.redis_state = _parse(await self.redis.get(REDIS_KEY))
        except Exception as exc:
            self.redis_state = KillSwitchState.EMERGENCY
            self.errors["redis"] = type(exc).__name__
        file_present = self.kill_file is not None and await asyncio.to_thread(
            os.path.exists, self.kill_file
        )
        self.file_state = KillSwitchState.EMERGENCY if file_present else None
        try:
            async with role_session(self.session_factory, db_role=WORKER_ROLE) as session:
                row = (await session.execute(_ROW)).mappings().first()
            if row is None:
                raise RuntimeError("meme_live_kill_switch has no 'wallet' row")
            self.wallet_state = KillSwitchState(str(row["state"]))
            self.latched = row["latched_at"] is not None and row["released_at"] is None
            self.latch_reason = row["reason"]
            self.anchor = (
                None
                if row["day_start_utc"] is None
                else DayAnchor(
                    row["day_start_utc"],
                    Decimal(row["day_start_sol_equity"]),
                    Decimal(row["peak_sol_equity"]),
                    row["anchor_observed_at"],
                )
            )
            self.legible = True
        except Exception as exc:
            self.wallet_state = KillSwitchState.EMERGENCY
            self.legible = False
            self.errors["postgres"] = type(exc).__name__
        self.last_read_at = utcnow()

    async def latch(self, reason: str) -> bool:
        """Persist the daily block. Idempotent: a second latch changes nothing."""
        async with role_session(self.session_factory, db_role=WORKER_ROLE) as session:
            latched = (await session.execute(_LATCH, {"reason": reason, "now": utcnow()})).scalar()
        if latched is not None:
            self.latched, self.latch_reason = True, reason
            logger.warning("meme_daily_loss_latched", reason=reason)
            return True
        return False

    async def anchor_day(self, day_start_utc: datetime, equity: Decimal) -> DayAnchor:
        now = utcnow()
        async with role_session(self.session_factory, db_role=WORKER_ROLE) as session:
            await session.execute(
                _ANCHOR,
                {"day_start": day_start_utc, "equity": equity, "peak": equity, "now": now},
            )
        self.anchor = DayAnchor(day_start_utc, equity, equity, now)
        return self.anchor

    async def raise_peak(self, equity: Decimal) -> None:
        if self.anchor is None or equity <= self.anchor.peak_sol_equity:
            return
        async with role_session(self.session_factory, db_role=WORKER_ROLE) as session:
            await session.execute(_PEAK, {"peak": equity, "now": utcnow()})
        self.anchor = DayAnchor(
            self.anchor.day_start_utc,
            self.anchor.day_start_sol_equity,
            equity,
            self.anchor.observed_at,
        )

    def describe(self) -> dict[str, str]:
        return {
            "kill_switch": self.effective.value,
            "kill_switch_system": self.system.value,
            "kill_switch_redis": "" if self.redis_state is None else self.redis_state.value,
            "kill_switch_file": "" if self.file_state is None else self.file_state.value,
            "kill_switch_wallet": self.wallet_state.value,
            "kill_switch_latched": str(self.latched).lower(),
            "kill_switch_latch_reason": self.latch_reason or "",
            "kill_switch_read_at": ""
            if self.last_read_at is None
            else self.last_read_at.isoformat(),
            "kill_switch_errors": ",".join(f"{k}:{v}" for k, v in self.errors.items()),
        }
