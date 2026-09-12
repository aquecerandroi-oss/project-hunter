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

from collections import Counter, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol
from zoneinfo import ZoneInfo

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_worker.collect import minute_end
from hunter_meme_worker.lab_bets import BetsReport, FillReport, fill_approved, process_open_bets
from hunter_meme_worker.lab_fast import fast_gate_step
from hunter_meme_worker.lab_heartbeat import HEARTBEAT_PREFIX, heartbeat_fields, write_lab_heartbeat
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
from hunter_meme_worker.lab_repo_bets import count_indeterminate
from hunter_meme_worker.lab_repo_fast import pedigree_for
from hunter_meme_worker.lab_repo_lines import open_probes_for, scaled_parent_ids
from hunter_meme_worker.lab_ticks import record_tick
from hunter_meme_worker.proposals import evaluate_gate
from hunter_meme_worker.proposals_scale import REFUSAL_SCALE_GATE_INACTIVE, evaluate_scale

__all__ = [
    "HEARTBEAT_PREFIX",
    "LabContext",
    "LabState",
    "TickReport",
    "brasilia_day_bounds",
    "closed_minutes",
    "heartbeat_fields",
    "lab_once",
    "lab_tick",
    "write_lab_heartbeat",
]

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.models import NormalizedSolPrice
    from hunter_meme_worker.config import MemeConfig
    from hunter_meme_worker.proposals import GateRow

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
SAO_PAULO = ZoneInfo("America/Sao_Paulo")


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
    # T4.16: the 15-second gate, the measured decision-to-fill, the indeterminate closes.
    last_fast_as_of: datetime | None = None
    fast_rows_evaluated: int = 0
    fast_proposals_total: int = 0
    fill_delays: deque[int] = field(default_factory=lambda: deque(maxlen=FILL_DELAY_SAMPLE))
    """``entry.decision_to_fill_s`` of the last fills this process made — the
    sample ``lab_decision_to_fill_s_p50``/``_p95`` are taken over (measured,
    never the cadence assumed)."""
    bets_indeterminate_total: int | None = None

    def record_fill_delay(self, seconds: int) -> None:
        self.fill_delays.append(seconds)


FILL_DELAY_SAMPLE = 200


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
) -> tuple[int, int, dict[str, Counter[str]]]:
    """The closed-minute gate for the sets on the minute clock; the refusal
    counters come back so the 15-second step adds to them (T4.16)."""
    rows_total = proposals_total = 0
    refusals: dict[str, Counter[str]] = {spec.name: Counter() for spec in specs}
    minute_specs = [spec for spec in specs if spec.clock == "1m"]
    for minute in minutes:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            rows = await load_gate_rows(
                session, minute=minute, features_version=ctx.config.features_version
            )
            # T4.16 (EXP-M6): the pedigree of the minute's mints, read once.
            pedigree = await pedigree_for(session, sorted({row.mint for row in rows}))
            for spec in minute_specs:
                already_open = await open_mints_for(session, spec.id)
                outcome = evaluate_gate(
                    spec,
                    rows,
                    now=now,
                    ttl_s=ctx.config.lab_proposal_ttl_s,
                    already_open=already_open,
                    pedigree=pedigree,
                )
                refusals[spec.name].update(outcome.refusals)
                rows_total += outcome.evaluated
                proposals_total += await insert_proposals(session, outcome.drafts)
            proposals_total += await _scale_step(ctx, session, specs, rows, refusals, now=now)
        ctx.state.last_gate_minute = minute
    return rows_total, proposals_total, refusals


async def _scale_step(
    ctx: LabContext,
    session: AsyncSession,
    specs: list[RuleSetSpec],
    rows: list[GateRow],
    refusals: dict[str, Counter[str]],
    *,
    now: datetime,
) -> int:
    """T4.10: for every set that scales, the open probes not yet scaled are
    judged by the line set's gate on this minute's rows (``proposals_scale``)."""
    by_label = {spec.label: spec for spec in specs}
    inserted = 0
    for spec in specs:
        if not spec.scales or spec.scale_gate is None:
            continue
        trend = by_label.get(spec.scale_gate)
        if trend is None:
            refusals[spec.name][REFUSAL_SCALE_GATE_INACTIVE] += 1
            continue
        probes = await open_probes_for(session, spec.id)
        if not probes:
            continue
        outcome = evaluate_scale(
            spec,
            trend,
            rows,
            open_probes=probes,
            already_scaled=await scaled_parent_ids(session, spec.id),
            now=now,
            ttl_s=ctx.config.lab_proposal_ttl_s,
        )
        refusals[spec.name].update(outcome.refusals)
        inserted += await insert_proposals(session, outcome.drafts)
    return inserted


async def lab_tick(ctx: LabContext, *, now: datetime | None = None) -> TickReport:
    """One pass of the seven steps. Raises on failure: the TaskGroup decides."""
    now = now or utcnow()
    day_start, day_end = brasilia_day_bounds(now)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        specs = await load_active_rule_sets(session)
        expired = await expire_proposals(session, now=now)
    cancelled = await _cancel_step(ctx, now=now)
    minutes = closed_minutes(ctx.state, now, backlog=ctx.config.lab_gate_backlog_minutes)
    rows, proposals, refusals = await _gate_step(ctx, specs, minutes, now=now)
    fast_rows, fast_proposals = await fast_gate_step(ctx, specs, refusals, now=now)
    ctx.state.refusals = {name: dict(counter) for name, counter in refusals.items()}
    fills = await fill_approved(
        ctx, {spec.id: spec for spec in specs}, now=now, day_start=day_start, day_end=day_end
    )
    bets = await process_open_bets(ctx, now=now)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        indeterminate = await count_indeterminate(session)
    state = ctx.state
    state.last_tick_at = now
    state.last_tick_minute = minutes[-1] if minutes else state.last_tick_minute
    state.rule_sets_active = len(specs)
    state.rows_evaluated = rows
    state.proposals_last_tick = proposals + fast_proposals
    state.proposals_total += proposals + fast_proposals
    state.fast_rows_evaluated = fast_rows
    state.fast_proposals_total += fast_proposals
    state.fills_total += fills.filled
    state.unfilled_total += fills.unfilled
    state.closes_total += bets.closed
    state.bets_open = bets.open
    state.bets_indeterminate_total = indeterminate
    report = TickReport(
        minute=state.last_tick_minute,
        minutes_evaluated=len(minutes),
        rows_evaluated=rows + fast_rows,
        proposals=proposals + fast_proposals,
        expired=expired,
        cancelled=cancelled,
        fills=fills,
        bets=bets,
    )
    await record_tick(ctx.session_factory, state, report, now=now)
    await write_lab_heartbeat(ctx)
    return report


async def lab_once(ctx: LabContext) -> None:
    """The step ``collect.forever`` drives; a failure propagates to the TaskGroup."""
    await lab_tick(ctx)
