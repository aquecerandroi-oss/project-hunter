"""The discovery loop: PumpPortal's two free channels become durable rows.

``subscribeNewToken`` and ``subscribeMigration`` are the two channels that cost
nothing (T4-MEME-RADAR.md §8 decision 1), and they are the two that matter for a
radar: a mint appearing and a curve leaving for PumpSwap. Everything else about a
token — its reserves, its progress, its market cap — comes from the poller, because
the free WS never re-sends a curve snapshot for an existing token.

Two things this loop refuses to do:

- **invent a block time.** The PumpPortal frame carries none (verified against
  T4.1's live capture), so ``created_at``/``migrated_at`` are the frame's receive
  time, which is what the adapter's models already say in their own docstrings. The
  row records ``first_seen_source = 'pumpportal_ws'`` so a later reader knows which
  clock it is looking at;
- **treat a reconnect as a recovery.** A new connection generation means frames
  were missed, and the only honest response is a ``meme_ingest_gaps`` row for the
  window between the last event and now (the adapter's ``state.reconnects`` is the
  hook T4.1 left for exactly this). Nothing back-fills those frames: the free
  channels have no replay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.models import NormalizedMemeMigration, NormalizedMemeTokenCreated
from hunter_meme_worker.config import WS_STREAM
from hunter_meme_worker.metrics import meme_events_total, meme_gaps_total, meme_ws_generation
from hunter_meme_worker.repo import GapRow, TokenRow, record_gap, upsert_token
from hunter_meme_worker.tracker import TrackedMint

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_exchanges.pumpfun.ws import MemeEvent
    from hunter_meme_worker.context import RadarContext

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"

RECONNECT_REASON = "ws_disconnected"


def _identity(value: str | None) -> str | None:
    """An empty identity string is "not observed", not an identity.

    The adapter lets ``name``/``symbol``/``uri`` be ``""`` (PumpPortal does emit
    creates with an empty ``uri``; one arrived at 08:52:32Z on 12/09 and killed the
    discovery TaskGroup), and ``meme_tokens`` refuses an empty string by CHECK
    (``ck_meme_tokens_an_observed_identity_is_not_empty``). ``NULL`` is the value
    the schema reserves for "still unknown", so that is what an empty string maps
    to — and a later REST read may still fill it once.
    """
    return value if value else None


def token_row_from_event(event: MemeEvent) -> TokenRow:
    """One normalized frame -> one upsert. Unknown fields stay ``None``."""
    if isinstance(event, NormalizedMemeTokenCreated):
        return TokenRow(
            mint=event.mint,
            first_seen_source=event.source,
            first_seen_at=event.observed_at,
            last_seen_at=event.observed_at,
            name=_identity(event.name),
            symbol=_identity(event.symbol),
            uri=_identity(event.uri),
            creator=_identity(event.creator),
            created_at=event.created_at,
            bonding_curve=event.bonding_curve,
            initial_virtual_sol_reserves=event.initial_virtual_sol_reserves,
            initial_virtual_token_reserves=event.initial_virtual_token_reserves,
            pool=event.pool,
            mayhem_enabled=event.mayhem_enabled,
            mayhem_mode=event.mayhem_mode,
        )
    return TokenRow(
        mint=event.mint,
        first_seen_source=event.source,
        first_seen_at=event.observed_at,
        last_seen_at=event.observed_at,
        migrated_at=event.migrated_at,
        migrated_pool=event.pool,
    )
    # A migration-first row carries no identity at all, and that is the honest
    # shape: the curve may have existed long before this process did. The columns
    # stay NULL until a creation frame or a REST read fills them once.


def _tracked_from_row(row: TokenRow) -> TrackedMint:
    return TrackedMint(
        mint=row.mint,
        first_seen_at=row.first_seen_at,
        created_at=row.created_at,
        bonding_curve=row.bonding_curve,
        mayhem_state=row.mayhem_state,
        migrated=row.migrated_at is not None,
    )


async def run_discovery(ctx: RadarContext) -> None:
    """Consume the stream forever; one transaction per frame, one row per frame."""
    async for event in ctx.events.stream():
        await _handle(ctx, event)


async def _handle(ctx: RadarContext, event: MemeEvent) -> None:
    kind = "migration" if isinstance(event, NormalizedMemeMigration) else "created"
    row = token_row_from_event(event)
    generation = ctx.events.state.reconnects
    try:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await upsert_token(session, row)
            if generation > ctx.state.ws_generation:
                await _record_reconnect_gap(ctx, session, generation, event_at=row.last_seen_at)
    except IntegrityError as exc:
        # One frame the schema refuses must cost one row, not the whole loop:
        # an unhandled error here propagates through the TaskGroup and restarts
        # the process (seen in production at 08:52:33Z on 12/09), which drops the
        # tracked set and every in-flight poll. Named, counted, skipped.
        logger.warning(
            "meme_token_upsert_rejected",
            mint=row.mint,
            kind=kind,
            error=str(exc.orig)[:200] if exc.orig is not None else str(exc)[:200],
        )
        meme_events_total.labels(kind="rejected").inc()
        return
    ctx.tracker.observe(_tracked_from_row(row))
    ctx.state.last_event_at = row.last_seen_at
    meme_events_total.labels(kind=kind).inc()
    meme_ws_generation.set(generation)


async def _record_reconnect_gap(
    ctx: RadarContext, session: AsyncSession, generation: int, *, event_at: datetime
) -> None:
    """A generation bump is a hole: from the last frame we saw to the first we see now."""
    start = ctx.state.last_event_at or event_at
    end = event_at if event_at > start else utcnow()
    if end <= start:
        # A gap has to be a window (``ck_meme_ingest_gaps_a_gap_is_a_window``); a
        # reconnect inside the same instant is one we cannot bound, so it is
        # counted and logged instead of written as a zero-width lie.
        logger.warning("meme_reconnect_gap_unbounded", generation=generation)
        ctx.state.ws_generation = generation
        return
    await record_gap(
        session,
        GapRow(
            stream=WS_STREAM,
            gap_start=start,
            gap_end=end,
            reason=RECONNECT_REASON,
            generation=generation,
            detail={"previous_generation": ctx.state.ws_generation},
        ),
    )
    ctx.state.ws_generation = generation
    meme_gaps_total.labels(stream=WS_STREAM, reason=RECONNECT_REASON).inc()
    logger.warning(
        "meme_discovery_gap_recorded",
        generation=generation,
        gap_start=start.isoformat(),
        gap_end=end.isoformat(),
    )
