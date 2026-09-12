"""The T4.2c loops and their wiring: board streams, the tape puller, the risk
reader and the radar heartbeat — built by ``main.py``, driven by ``collect.forever``.

Each source is optional and says so: a switch off (``MEME_TRENCHES_ENABLED``,
``MEME_SWAP_API_ENABLED``, ``MEME_RISK_ENABLED``) leaves the field ``enabled =
false`` in the heartbeat and ``disabled`` in the readiness detail, never a
zero that reads as health.

**A board stream that fails is a degraded source, not a dead radar**: the
trenches client reconnects forever with the site's backoff, so
:func:`run_board` only ends when cancelled. The tape and risk loops are
cadences like the poller's.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.indexer_rest import AdvancedIndexerClient
from hunter_exchanges.pumpfun.rest import PumpFunRestClient
from hunter_exchanges.pumpfun.swap_api import MEASURED_LIMIT, SwapApiClient
from hunter_exchanges.pumpfun.trenches import TrenchesWsClient
from hunter_exchanges.rate_limit import TokenBucketRateLimiter
from hunter_meme_worker.activity import ActivityPuller
from hunter_meme_worker.boards import BoardCollector
from hunter_meme_worker.config import TRENCHES_STREAM
from hunter_meme_worker.metrics import meme_gaps_total, meme_rows_total, meme_source_messages_total
from hunter_meme_worker.repo import GapRow, record_gap, upsert_token
from hunter_meme_worker.risk import RiskReader
from hunter_meme_worker.sources import (
    INDEXER_RISK,
    SWAP_API,
    SWAP_API_ACTIVITY,
    TRENCHES_WS,
    SourcesState,
)
from hunter_meme_worker.tracker import (
    TIER_GRADUATING,
    TIER_NEW,
    TIER_OPEN_BET,
    TIER_REST,
    TIER_YOUNG,
)
from hunter_meme_worker.trades import TradesPuller, pull_once

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_meme_worker.config import MemeConfig
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.tracker import MintTracker

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
HeartbeatWriter = Callable[[dict[str, str]], Awaitable[None]]
SOL_PRICE_BUDGET_PER_MINUTE = 50
"""``/sol-price`` is its own upstream rate-limit group (50/60 s, ``docs/PUMPFUN.md``
§1.4): the batch loop's quote client gets its own bucket, like the Lab's."""


def build_sources(config: MemeConfig) -> SourcesState:
    sources = SourcesState()
    sources["pumpfun_rest"].budget_60s = config.rest_budget_per_minute
    sources[TRENCHES_WS].enabled = config.trenches_enabled
    sources[TRENCHES_WS].connected = False if config.trenches_enabled else None
    sources[SWAP_API].enabled = config.swap_api_enabled
    sources[SWAP_API].budget_60s = min(config.swap_api_budget_60s, MEASURED_LIMIT)
    sources[INDEXER_RISK].enabled = config.risk_enabled
    sources[INDEXER_RISK].budget_60s = 60
    sources[SWAP_API_ACTIVITY].enabled = config.swap_api_enabled and config.activity_enabled
    sources[SWAP_API_ACTIVITY].budget_60s = -(-config.tracked_max // 50)  # calls a minute, ceil
    return sources


def build_activity(
    config: MemeConfig,
    sources: SourcesState,
    trades: TradesPuller | None,
    client: SwapApiClient | None,
) -> ActivityPuller | None:
    """The tape by batch (T4.2g), on the tape's own client and budget: the
    same host, the same edge rule, one reservation off the top."""
    if trades is None or client is None or not config.activity_enabled:
        return None
    return ActivityPuller(
        client,
        budget=trades.budget,
        quotes=PumpFunRestClient(
            rate_limiter=TokenBucketRateLimiter(
                "pumpfun_sol_price_activity",
                capacity=SOL_PRICE_BUDGET_PER_MINUTE,
                refill_period_s=60.0,
            )
        ),
        sources=sources,
        max_age_s=config.activity_max_age_s,
        quote_max_age_s=config.activity_quote_max_age_s,
    )


def build_boards(
    config: MemeConfig, tracker: MintTracker
) -> tuple[BoardCollector, dict[str, TrenchesWsClient]] | tuple[None, dict[str, TrenchesWsClient]]:
    if not config.trenches_enabled:
        return None, {}
    clients = {board: TrenchesWsClient(board) for board in config.boards}
    return BoardCollector(tracker, boards=config.boards), clients


def build_swap_api(config: MemeConfig) -> SwapApiClient | None:
    """The one ``swap-api`` client: the tape and the batch loop (T4.2g) share
    it, and with it the bucket and the edge's rule."""
    if not config.swap_api_enabled:
        return None
    return SwapApiClient(capacity=min(max(1, config.swap_api_budget_60s), MEASURED_LIMIT))


def build_trades(
    config: MemeConfig, sources: SourcesState, client: SwapApiClient | None = None
) -> TradesPuller | None:
    if not config.swap_api_enabled:
        return None
    capacity = min(max(1, config.swap_api_budget_60s), MEASURED_LIMIT)
    return TradesPuller(
        client or SwapApiClient(capacity=capacity),
        budget_60s=capacity,
        cycle_s=config.trades_cycle_s,
        max_pages=config.trades_max_pages,
        sources=sources,
        concurrency=config.trades_concurrency,
        stale_s=config.tape_stale_s,
    )


def build_risk(config: MemeConfig, sources: SourcesState) -> RiskReader | None:
    if not config.risk_enabled:
        return None
    return RiskReader(
        AdvancedIndexerClient(), min_interval_s=config.risk_min_interval_s, sources=sources
    )


async def run_board(ctx: RadarContext, client: TrenchesWsClient) -> None:
    """Consume one board forever; every event goes to the collector, every new
    pump/SOL mint to ``meme_tokens``, every reconnect to the gap ledger."""
    collector, sources = ctx.boards, ctx.sources
    assert collector is not None
    last_session: int | None = None
    async for event in client.stream():
        session_key = client.state.reconnects + client.state.resyncs
        if sources is not None:
            sources[TRENCHES_WS].connected = client.state.ws_state == "connected"
            sources[TRENCHES_WS].record_ok(
                observed_at=event.observed_at, received_at=event.received_at
            )
            sources.trenches_patches_60s.add(event.received_at, sum(event.patch_ops.values()))
            sources.sample_counter(
                f"trenches_malformed:{client.board}",
                client.state.malformed,
                event.received_at,
                sources.ws_malformed_60s,
            )
        meme_source_messages_total.labels(source=TRENCHES_WS).inc()
        if last_session is not None and session_key != last_session:
            await _record_board_gap(ctx, client, session_key)
        last_session = session_key
        listed = collector.ingest(event, session_key=session_key)
        if sources is not None and client.board == "new":
            for entry in listed:  # the declared blindness: listed here, unseen by discovery
                sources.record_new_listing(entry.received_at, in_scope=entry.program == "pump")
        tokens = collector.take_tokens()
        if tokens:
            async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
                for row in tokens:
                    await upsert_token(session, row)


async def _record_board_gap(ctx: RadarContext, client: TrenchesWsClient, session_key: int) -> None:
    start, end = client.state.last_received_at, utcnow()
    if start is None or end <= start:
        return
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await record_gap(
            session,
            GapRow(
                stream=TRENCHES_STREAM,
                gap_start=start,
                gap_end=end,
                reason="ws_reconnected",
                generation=session_key,
                detail={"board": client.board, "resyncs": client.state.resyncs},
            ),
        )
    meme_gaps_total.labels(stream=TRENCHES_STREAM, reason="ws_reconnected").inc()
    if ctx.sources is not None:
        ctx.sources.gaps_60s.add(end)


def tape_tiers(ctx: RadarContext, now: datetime | None = None) -> dict[str, int]:
    """Every mint the tape should cover, with its tier (``tracker.py``'s order:
    open bet, ``graduating``, ``new``, young, rest)."""
    at = now or utcnow()
    young = timedelta(minutes=ctx.config.young_minutes)
    tiers: dict[str, int] = {}
    for tracked in ctx.tracker.snapshot():
        if tracked.quote_unsupported:
            continue
        tier = TIER_YOUNG if at - tracked.age_anchor <= young else TIER_REST
        if tracked.board == "graduating":
            tier = TIER_GRADUATING
        elif tracked.board == "new":
            tier = TIER_NEW
        tiers[tracked.mint] = tier
    for mint in ctx.state.open_bets:
        tiers[mint] = TIER_OPEN_BET
    return tiers


async def trades_once(ctx: RadarContext) -> None:
    assert ctx.trades is not None
    now = utcnow()
    tiers = tape_tiers(ctx, now)
    report = await pull_once(ctx.trades, ctx.session_factory, tiers=tiers, now=now, clock=utcnow)
    meme_rows_total.labels(table="meme_trades").inc(report.rows)
    meme_source_messages_total.labels(source=SWAP_API).inc(report.pages)
    if ctx.sources is not None:
        stats = ctx.trades.stats(tiers)
        ctx.sources.record_tape_cycle(
            now,
            duration_s=report.duration_s,
            planned=report.planned,
            deferred=report.deferred,
            tracked=stats.tracked,
            covered=stats.covered,
            never_pulled=stats.never_pulled,
        )
        budget = ctx.trades.budget
        ctx.sources.record_tape_budget(
            now,
            effective=budget.effective,
            measured=budget.measured,
            refused_429=report.refused_429,
            blocked_until=budget.blocked_until,
        )


async def risk_once(ctx: RadarContext) -> None:
    assert ctx.risk is not None
    candidates = set(ctx.state.open_bets)
    if ctx.boards is not None:
        candidates |= {mint for mint in ctx.boards.listed_on("graduating") if mint in ctx.tracker}
    report = await ctx.risk.read_once(ctx.session_factory, candidates, now=utcnow())
    meme_rows_total.labels(table="meme_risk_snapshots").inc(report.read)


async def heartbeat_once(ctx: RadarContext, write: HeartbeatWriter) -> None:
    """The radar's own fields on ``hb:meme:radar`` (the adendo's list)."""
    if ctx.sources is None:
        return
    now = utcnow()
    ctx.sources.sample_counter(
        "pumpportal_malformed",
        ctx.events.state.malformed_messages,
        now,
        ctx.sources.ws_malformed_60s,
    )
    ctx.sources["pumpportal_ws"].connected = ctx.events.state.ws_state == "connected"
    fields = ctx.sources.heartbeat_fields(now, tracked=len(ctx.tracker))
    if ctx.wallets is not None:  # T4.12: the observed wallets' own counters
        fields.update(ctx.wallets.heartbeat_fields(now))
    try:
        await write(fields)
    except Exception:  # a heartbeat that cannot be written must not stop the radar
        logger.warning("meme_radar_heartbeat_write_failed")
