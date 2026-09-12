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
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.indexer_rest import AdvancedIndexerClient
from hunter_exchanges.pumpfun.swap_api import MEASURED_CAPACITY, SwapApiClient
from hunter_exchanges.pumpfun.trenches import TrenchesWsClient
from hunter_meme_worker.boards import BoardCollector
from hunter_meme_worker.config import TRENCHES_STREAM
from hunter_meme_worker.metrics import meme_gaps_total, meme_rows_total, meme_source_messages_total
from hunter_meme_worker.repo import GapRow, record_gap, upsert_token
from hunter_meme_worker.risk import RiskReader
from hunter_meme_worker.sources import INDEXER_RISK, SWAP_API, TRENCHES_WS, SourcesState
from hunter_meme_worker.tracker import TIER_GRADUATING, TIER_NEW, TIER_OPEN_BET, TIER_REST
from hunter_meme_worker.trades import TradesPuller, pull_once

if TYPE_CHECKING:
    from hunter_meme_worker.config import MemeConfig
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.tracker import MintTracker

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
HeartbeatWriter = Callable[[dict[str, str]], Awaitable[None]]


def build_sources(config: MemeConfig) -> SourcesState:
    sources = SourcesState()
    sources["pumpfun_rest"].budget_60s = config.rest_budget_per_minute
    sources[TRENCHES_WS].enabled = config.trenches_enabled
    sources[TRENCHES_WS].connected = False if config.trenches_enabled else None
    sources[SWAP_API].enabled = config.swap_api_enabled
    sources[SWAP_API].budget_60s = min(config.swap_api_budget_60s, MEASURED_CAPACITY)
    sources[INDEXER_RISK].enabled = config.risk_enabled
    sources[INDEXER_RISK].budget_60s = 60
    return sources


def build_boards(
    config: MemeConfig, tracker: MintTracker
) -> tuple[BoardCollector, dict[str, TrenchesWsClient]] | tuple[None, dict[str, TrenchesWsClient]]:
    if not config.trenches_enabled:
        return None, {}
    clients = {board: TrenchesWsClient(board) for board in config.boards}
    return BoardCollector(tracker, boards=config.boards), clients


def build_trades(config: MemeConfig, sources: SourcesState) -> TradesPuller | None:
    if not config.swap_api_enabled:
        return None
    capacity = min(max(1, config.swap_api_budget_60s), MEASURED_CAPACITY)
    return TradesPuller(
        SwapApiClient(capacity=capacity),
        budget_60s=capacity,
        cycle_s=config.trades_cycle_s,
        max_pages=config.trades_max_pages,
        sources=sources,
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


def tape_tiers(ctx: RadarContext) -> dict[str, int]:
    """Every mint the tape should cover, with its tier (``tracker.py``'s order)."""
    tiers: dict[str, int] = {}
    for tracked in ctx.tracker.snapshot():
        if tracked.quote_unsupported:
            continue
        tier = TIER_REST
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
    report = await pull_once(ctx.trades, ctx.session_factory, tiers=tape_tiers(ctx), now=utcnow())
    meme_rows_total.labels(table="meme_trades").inc(report.rows)
    meme_source_messages_total.labels(source=SWAP_API).inc(report.pages)


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
    try:
        await write(ctx.sources.heartbeat_fields(now, tracked=len(ctx.tracker)))
    except Exception:  # a heartbeat that cannot be written must not stop the radar
        logger.warning("meme_radar_heartbeat_write_failed")
