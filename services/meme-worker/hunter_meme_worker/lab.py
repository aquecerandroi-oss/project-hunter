"""The Lab tick: once a minute, the contract's §Semântica 1–5 over durable rows.

Order of one tick, and why that order:

1. **rule sets** — read fresh every tick, so retiring one in the database
   stops it without a restart;
2. **expiry** — ``proposed`` past ``expires_at`` becomes ``expired`` before
   anything else looks at it;
3. **cancel commands** — the operator's ``cancel`` on a proposal that has not
   filled, applied before the fill step can fill it;
4. **the gate** — every rule set over every closed minute not yet evaluated
   (``end_time <= now − 1 min``, at most ``lab_gate_backlog_minutes`` back);
5. **fills** — ``approved`` proposals against the first later snapshot;
6. **bets** — marks, exits, ``sell_now``, sales on the next snapshot;
7. **heartbeat** — ``lab_*`` fields on the worker's own ``hb:meme:radar``
   hash, so a loop that stopped is visible as a stale ``lab_last_tick_at``
   rather than as silence (§Semântica 5).

The loop keeps almost nothing in memory: the last minute the gate evaluated
(so a minute is not read twice per process), tick counters for the heartbeat,
and the cached SOL/USD quote. Everything that matters is a row.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol
from zoneinfo import ZoneInfo

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_worker.collect import minute_end
from hunter_meme_worker.lab_bets import BetsReport, FillReport, fill_approved, process_open_bets
from hunter_meme_worker.lab_models import RuleSetSpec, SolUsd
from hunter_meme_worker.lab_repo import (
    apply_command,
    cancel_proposal,
    expire_proposals,
    insert_proposals,
    load_active_rule_sets,
    load_gate_rows,
    open_mints_for,
    pending_commands,
)
from hunter_meme_worker.proposals import evaluate_gate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.models import NormalizedSolPrice
    from hunter_meme_worker.config import MemeConfig

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
HEARTBEAT_PREFIX = "lab_"


class SolUsdSource(Protocol):
    async def get_sol_price(self) -> NormalizedSolPrice: ...


HeartbeatWriter = Callable[[dict[str, str]], Awaitable[None]]


@dataclass
class LabState:
    """What survives between ticks — and nothing a restart could not rebuild."""

    last_gate_minute: datetime | None = None
    last_tick_at: datetime | None = None
    last_tick_minute: datetime | None = None
    rule_sets_active: int = 0
    rows_evaluated: int = 0
    refusals: dict[str, dict[str, int]] = field(default_factory=dict[str, dict[str, int]])
    proposals_last_tick: int = 0
    proposals_total: int = 0
    fills_total: int = 0
    unfilled_total: int = 0
    closes_total: int = 0
    bets_open: int = 0
    sol_usd: SolUsd | None = None
    sol_usd_error: str | None = None


@dataclass(frozen=True, slots=True)
class LabContext:
    config: MemeConfig
    session_factory: async_sessionmaker[AsyncSession]
    state: LabState
    quotes: SolUsdSource | None
    heartbeat: HeartbeatWriter | None

    async def sol_usd(self, now: datetime) -> SolUsd | None:
        """The observed quote, at most ``lab_sol_usd_max_age_s`` old; ``None`` and
        a named error when the source fails — a fill never waits on a price tag."""
        cached = self.state.sol_usd
        max_age = timedelta(seconds=self.config.lab_sol_usd_max_age_s)
        if cached is not None and now - cached.observed_at < max_age:
            return cached
        if self.quotes is None:
            self.state.sol_usd_error = "no_quote_source"
            return None
        try:
            quote = await self.quotes.get_sol_price()
        except Exception as exc:  # the price tag is not the trade
            self.state.sol_usd_error = type(exc).__name__
            logger.warning("meme_lab_sol_usd_unavailable", error=str(exc))
            return None
        self.state.sol_usd = SolUsd(
            price_usd=quote.price_usd,
            source=quote.source,
            as_of=quote.as_of,
            observed_at=quote.observed_at,
            stale=quote.stale,
        )
        self.state.sol_usd_error = None
        return self.state.sol_usd


@dataclass(frozen=True, slots=True)
class TickReport:
    minute: datetime | None
    minutes_evaluated: int
    rows_evaluated: int
    proposals: int
    expired: int
    cancelled: int
    fills: FillReport
    bets: BetsReport


def brasilia_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    """``[start, end)`` of the Brasília calendar day containing ``now``, in UTC."""
    local = now.astimezone(SAO_PAULO)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(now.tzinfo), (start + timedelta(days=1)).astimezone(now.tzinfo)


def closed_minutes(state: LabState, now: datetime, *, backlog: int) -> list[datetime]:
    """The minute ends the gate may read: ``end_time <= now − 1 min``, newest
    ``backlog`` of them, none the process already evaluated."""
    newest = minute_end(now - timedelta(minutes=1))
    oldest = newest - timedelta(minutes=backlog - 1)
    if state.last_gate_minute is not None:
        oldest = max(oldest, state.last_gate_minute + timedelta(minutes=1))
    minutes: list[datetime] = []
    cursor = oldest
    while cursor <= newest:
        minutes.append(cursor)
        cursor += timedelta(minutes=1)
    return minutes


async def _cancel_step(ctx: LabContext, *, now: datetime) -> int:
    cancelled = 0
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        for command in await pending_commands(session):
            if command.command != "cancel" or command.proposal_id is None:
                continue
            result = await cancel_proposal(session, command, now=now)
            await apply_command(session, command.id, now=now, result=result)
            cancelled += result["status"] == "applied"
    return cancelled


async def _gate_step(
    ctx: LabContext, specs: list[RuleSetSpec], minutes: list[datetime], *, now: datetime
) -> tuple[int, int]:
    rows_total = proposals_total = 0
    refusals: dict[str, Counter[str]] = {spec.name: Counter() for spec in specs}
    for minute in minutes:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            rows = await load_gate_rows(
                session, minute=minute, features_version=ctx.config.features_version
            )
            for spec in specs:
                already_open = await open_mints_for(session, spec.id)
                outcome = evaluate_gate(
                    spec,
                    rows,
                    now=now,
                    ttl_s=ctx.config.lab_proposal_ttl_s,
                    already_open=already_open,
                )
                refusals[spec.name].update(outcome.refusals)
                rows_total += outcome.evaluated
                proposals_total += await insert_proposals(session, outcome.drafts)
        ctx.state.last_gate_minute = minute
    ctx.state.refusals = {name: dict(counter) for name, counter in refusals.items()}
    return rows_total, proposals_total


async def lab_tick(ctx: LabContext, *, now: datetime | None = None) -> TickReport:
    """One pass of the seven steps. Raises on failure: the TaskGroup decides."""
    now = now or utcnow()
    day_start, day_end = brasilia_day_bounds(now)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        specs = await load_active_rule_sets(session)
        expired = await expire_proposals(session, now=now)
    cancelled = await _cancel_step(ctx, now=now)
    minutes = closed_minutes(ctx.state, now, backlog=ctx.config.lab_gate_backlog_minutes)
    rows, proposals = await _gate_step(ctx, specs, minutes, now=now)
    fills = await fill_approved(
        ctx, {spec.id: spec for spec in specs}, now=now, day_start=day_start, day_end=day_end
    )
    bets = await process_open_bets(ctx, now=now)
    state = ctx.state
    state.last_tick_at = now
    state.last_tick_minute = minutes[-1] if minutes else state.last_tick_minute
    state.rule_sets_active = len(specs)
    state.rows_evaluated = rows
    state.proposals_last_tick = proposals
    state.proposals_total += proposals
    state.fills_total += fills.filled
    state.unfilled_total += fills.unfilled
    state.closes_total += bets.closed
    state.bets_open = bets.open
    await write_lab_heartbeat(ctx)
    return TickReport(
        minute=state.last_tick_minute,
        minutes_evaluated=len(minutes),
        rows_evaluated=rows,
        proposals=proposals,
        expired=expired,
        cancelled=cancelled,
        fills=fills,
        bets=bets,
    )


def heartbeat_fields(state: LabState, *, enabled: bool = True) -> dict[str, str]:
    """The ``lab_*`` fields — strings, like every heartbeat field of the repo."""
    quote = state.sol_usd
    fields: dict[str, Any] = {
        "enabled": "true" if enabled else "false",
        "last_tick_at": state.last_tick_at.isoformat() if state.last_tick_at else "",
        "tick_minute": state.last_tick_minute.isoformat() if state.last_tick_minute else "",
        "rule_sets_active": str(state.rule_sets_active),
        "rows_evaluated": str(state.rows_evaluated),
        "gate_refusals": json.dumps(state.refusals, sort_keys=True),
        "proposals_last_tick": str(state.proposals_last_tick),
        "proposals_total": str(state.proposals_total),
        "fills_total": str(state.fills_total),
        "unfilled_total": str(state.unfilled_total),
        "closes_total": str(state.closes_total),
        "bets_open": str(state.bets_open),
        "sol_usd": "" if quote is None else str(quote.price_usd),
        "sol_usd_observed_at": "" if quote is None else quote.observed_at.isoformat(),
        "sol_usd_source": "" if quote is None else quote.source,
        "sol_usd_error": state.sol_usd_error or "",
    }
    return {HEARTBEAT_PREFIX + key: str(value) for key, value in fields.items()}


async def write_lab_heartbeat(ctx: LabContext, *, enabled: bool = True) -> None:
    if ctx.heartbeat is None:
        return
    try:
        await ctx.heartbeat(heartbeat_fields(ctx.state, enabled=enabled))
    except Exception:  # a heartbeat that cannot be written must not stop the Lab
        logger.warning("meme_lab_heartbeat_write_failed")


async def lab_once(ctx: LabContext) -> None:
    """The step ``collect.forever`` drives; a failure propagates to the TaskGroup."""
    await lab_tick(ctx)
