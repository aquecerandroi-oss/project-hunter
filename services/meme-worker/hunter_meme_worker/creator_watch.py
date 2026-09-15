"""T4.2h — the creator's own token account, read from the chain every 15 s for
the mints the Lab holds, so ``creator_dump`` fires on the first sale, not when
the tape catches up.

**Measured cause (12/09/2026, 35 measured paper closes):** ``creator_dump`` was
the exit of 22 (−6,2 R), on average 14 min after the entry; the tape by batch
(T4.2g) carries no per-wallet sells and the per-mint tape covers few mints, so
the loop learned of the dump when the price had already fallen. A real position
(T4.14) would carry the same delay.

**What this loop does:** for every open paper bet **and every open real
position** (T4.2h-b, ``meme_live_positions``) whose token has a known
creator, derive the creator's associated token accounts (classic Token program
and Token-2022 — the ATA is a PDA over the token program, so both are read),
read them in **one** ``getMultipleAccounts`` (``jsonParsed``, ≤ 100 accounts
per call) and keep the last balance per mint in memory. The first **decrease**
between two readings is a sale: every open row on that mint — bet and
position, in one transaction — gets ``creator_sold_seen_at`` (the reading's
instant) and ``creator_sold_fraction`` (sold ÷ previous). ``lab_repo_bets``
reads that as ``creator_net_seller = true`` and the paper engine closes on the
next photo; the executor reads it on its own 5 s tick. A creator with **no**
token account is not "a creator who did not sell": the row carries
``creator_balance_reason = creator_ata_missing`` and stays unmeasured by this
watch. The chain client is the same ``ctx.chain`` (same budget); a fake without
``call`` makes the watch say so once and do nothing.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    associated_token_address,
)
from hunter_meme_worker.creator_stats import sale_to_exit_samples

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.config import MemeConfig
    from hunter_meme_worker.context import RadarContext

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
ACCOUNTS_PER_CALL = 100
ATA_MISSING = "creator_ata_missing"
_FRACTION = Decimal("0.000001")
_PARSED = {"encoding": "jsonParsed", "commitment": "confirmed"}

WATCHED_TABLES: tuple[str, ...] = ("meme_paper_bets", "meme_live_positions")
"""T4.2h-b: the paper bet and the **real** position carry the same three columns
(``0036``/``0038``), so one loop watches both and one query measures either."""

_WATCHED = text(
    "SELECT w.mint, w.creator, bool_or(w.live) AS live FROM ("
    "  SELECT b.mint AS mint, t.creator AS creator, false AS live FROM meme_paper_bets b "
    "    JOIN meme_tokens t ON t.mint = b.mint "
    "   WHERE b.status = 'open' AND b.creator_sold_seen_at IS NULL AND t.creator IS NOT NULL "
    "  UNION ALL "
    "  SELECT p.mint AS mint, t.creator AS creator, true AS live FROM meme_live_positions p "
    "    JOIN meme_tokens t ON t.mint = p.mint "
    "   WHERE p.status = 'open' AND p.creator_sold_seen_at IS NULL AND t.creator IS NOT NULL"
    ") w GROUP BY w.mint, w.creator"
)
_MARK_SOLD = tuple(
    text(
        f"UPDATE {table} SET creator_sold_seen_at = :at, creator_sold_fraction = :fraction, "  # noqa: S608
        "  creator_balance_reason = NULL "
        "WHERE mint = :mint AND status = 'open' AND creator_sold_seen_at IS NULL"
    )
    for table in WATCHED_TABLES
)
_MARK_REASON = tuple(
    text(
        f"UPDATE {table} SET creator_balance_reason = :reason "  # noqa: S608
        "WHERE mint = :mint AND status = 'open' AND creator_sold_seen_at IS NULL "
        "  AND creator_balance_reason IS DISTINCT FROM :reason"
    )
    for table in WATCHED_TABLES
)


@dataclass(frozen=True, slots=True)
class Drop:
    mint: str
    before: int
    after: int

    @property
    def fraction(self) -> Decimal:
        """Sold ÷ previous balance, six places."""
        return (Decimal(self.before - self.after) / Decimal(self.before)).quantize(
            _FRACTION, ROUND_HALF_EVEN
        )


@dataclass(slots=True)
class CreatorWatchState:
    """The last known balance per mint — memory only; a restart starts blind
    and waits for two readings, it never invents a previous balance."""

    balances: dict[str, int] = field(default_factory=dict[str, int])
    read_at: dict[str, datetime] = field(default_factory=dict[str, datetime])
    reasoned: set[str] = field(default_factory=set[str])
    unavailable_logged: bool = False


@dataclass(frozen=True, slots=True)
class CreatorWatchReport:
    mints: int
    calls: int
    drops: int
    missing: int
    duration_s: float = 0.0
    live_mints: int = 0
    """How many of ``mints`` carry an **open real position** (T4.2h-b) — the
    heartbeat says it apart, because a watch that stops mattering to paper and
    keeps mattering to money is two different incidents."""


def ata_targets(pairs: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """``(mint, address)`` for the creator's classic and Token-2022 ATAs, in order."""
    targets: list[tuple[str, str]] = []
    for mint, creator in pairs:
        for program in (TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
            targets.append((mint, associated_token_address(creator, mint, token_program=program)))
    return targets


def parse_token_amounts(value: Sequence[Any]) -> list[int | None]:
    """The raw ``amount`` of each ``jsonParsed`` token account; ``None`` when the
    account does not exist or is not a token account."""
    amounts: list[int | None] = []
    for item in value:
        try:
            amount = item["data"]["parsed"]["info"]["tokenAmount"]["amount"]
            amounts.append(int(amount))
        except (KeyError, TypeError, ValueError):
            amounts.append(None)
    return amounts


def balances_by_mint(
    targets: Sequence[tuple[str, str]], amounts: Sequence[int | None]
) -> dict[str, int | None]:
    """Sum of the creator's accounts per mint; ``None`` when none exists."""
    totals: dict[str, int | None] = {}
    for (mint, _address), amount in zip(targets, amounts, strict=True):
        if amount is None:
            totals.setdefault(mint, None)
        else:
            totals[mint] = (totals.get(mint) or 0) + amount
    return totals


def detect_drops(previous: Mapping[str, int], current: Mapping[str, int | None]) -> list[Drop]:
    """A decrease between two readings of the same mint, and nothing else:
    a first reading, a missing account or a rise are not sales."""
    drops: list[Drop] = []
    for mint, after in current.items():
        before = previous.get(mint)
        if before is None or after is None or after >= before:
            continue
        drops.append(Drop(mint=mint, before=before, after=after))
    return drops


def _accounts(result: Any, expected: int) -> list[Any] | None:
    """The ``value`` list of a ``getMultipleAccounts`` reply, only when it has
    exactly one entry per requested address; anything else is malformed."""
    value: Any = result.get("value") if hasattr(result, "get") else None
    if type(value) is not list:
        return None
    items = cast("list[Any]", value)
    return items if len(items) == expected else None


async def _watched(session: AsyncSession) -> tuple[list[tuple[str, str]], int]:
    """``[(mint, creator)]`` and how many of them carry an open real position."""
    rows = (await session.execute(_WATCHED)).all()
    return [(str(r[0]), str(r[1])) for r in rows], sum(1 for r in rows if bool(r[2]))


async def creator_watch_once(ctx: RadarContext, state: CreatorWatchState) -> CreatorWatchReport:
    """One reading of every watched creator; the drops written on the open bets
    **and** on the open real positions (T4.2h-b)."""
    started = time.monotonic()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        pairs, live = await _watched(session)
    if not pairs:
        return await _record(
            ctx,
            CreatorWatchReport(
                mints=0, calls=0, drops=0, missing=0, duration_s=_elapsed(started), live_mints=0
            ),
        )
    reader = cast(
        "Callable[[str, list[Any]], Awaitable[Any]] | None", getattr(ctx.chain, "call", None)
    )
    if reader is None:
        if not state.unavailable_logged:
            logger.warning("meme_creator_watch_unavailable", reason="chain_source_has_no_call")
            state.unavailable_logged = True
        return await _record(
            ctx,
            CreatorWatchReport(
                mints=len(pairs),
                calls=0,
                drops=0,
                missing=0,
                duration_s=_elapsed(started),
                live_mints=live,
            ),
        )
    targets = ata_targets(pairs)
    amounts: list[int | None] = []
    calls = 0
    for start in range(0, len(targets), ACCOUNTS_PER_CALL):
        chunk = targets[start : start + ACCOUNTS_PER_CALL]
        result: Any = await reader(
            "getMultipleAccounts", [[address for _, address in chunk], _PARSED]
        )
        calls += 1
        accounts = _accounts(result, len(chunk))
        if accounts is None:
            logger.warning("meme_creator_watch_malformed", chunk=len(chunk))
            amounts.extend([None] * len(chunk))
            continue
        amounts.extend(parse_token_amounts(accounts))
    read_at = utcnow()
    current = balances_by_mint(targets, amounts)
    drops = detect_drops(state.balances, current)
    missing = [mint for mint, balance in current.items() if balance is None]
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        for drop in drops:
            for statement in _MARK_SOLD:  # the paper bet and the real position
                await session.execute(
                    statement, {"at": read_at, "fraction": drop.fraction, "mint": drop.mint}
                )
            logger.info(
                "meme_creator_balance_dropped",
                mint=drop.mint,
                before=drop.before,
                after=drop.after,
                fraction=str(drop.fraction),
                previous_read_at=state.read_at.get(drop.mint),
                read_at=read_at,
            )
        for mint in missing:
            if mint not in state.reasoned:
                for statement in _MARK_REASON:
                    await session.execute(statement, {"reason": ATA_MISSING, "mint": mint})
                state.reasoned.add(mint)
        await session.commit()
    for mint, balance in current.items():
        if balance is not None:
            state.balances[mint] = balance
            state.read_at[mint] = read_at
    for mint in list(state.balances):
        if mint not in current:
            state.balances.pop(mint, None)
            state.read_at.pop(mint, None)
            state.reasoned.discard(mint)
    return await _record(
        ctx,
        CreatorWatchReport(
            mints=len(pairs),
            calls=calls,
            drops=len(drops),
            missing=len(missing),
            duration_s=_elapsed(started),
            live_mints=live,
        ),
    )


async def _record(ctx: RadarContext, report: CreatorWatchReport) -> CreatorWatchReport:
    """The heartbeat's gauges, and the sale → exit latency **measured from the
    rows** (T4.2h-b) — never from a counter in memory, so a restart does not
    reset the only number that says whether this loop is fast enough."""
    now = utcnow()
    ctx.creator.record_cycle(now, report)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        ctx.creator.record_latency(await sale_to_exit_samples(session))
    return report


def _elapsed(started: float) -> float:
    return round(time.monotonic() - started, 3)


def spawn_creator_watch(group: asyncio.TaskGroup, config: MemeConfig, ctx: RadarContext) -> None:
    """One task with its own memory, on ``config.creator_watch_cycle_s`` (main.py's wiring)."""
    from hunter_meme_worker.collect import (
        forever,
    )

    state = CreatorWatchState()

    async def step(c: RadarContext) -> object:
        return await creator_watch_once(c, state)

    group.create_task(
        forever("creator_watch", config.creator_watch_cycle_s, step, ctx),
        name="meme-creator-watch",
    )
