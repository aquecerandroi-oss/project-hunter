"""Funding and open interest for one context cut: durable first, hot state fallback
— except open interest, whose durable side can never stand alone (see below).

Two buckets, one contract: the last observation with ``ts <= cut``, from the
same anti-look-ahead cut the candle series already obeys (SHADOW-LAB.md §7,
``hunter_core.strategies.base.build_context``). **Funding** reads Postgres
(``funding_rates``) first because it is durable; the hot state (:mod:`.hot_state`)
is used only when the durable side has no row at or before the cut, or the row
it has cannot be turned into a value the context requires
(:class:`~hunter_core.domain.market.NormalizedFunding` requires ``mark_price``,
which a durable ``funding_rates`` row may not carry). **Open interest does not
follow that order**: its durable ``ts`` can never prove ``<= cut`` by itself
(see the first bullet below), so the hot state's own ``oi_ts`` is the only
source ever trusted, durable row or not.

The source actually used (``"durable"`` | ``"hot_state"``) and, when there is
no observation at all, why, are returned alongside the value so the caller can
put both in the decision's provenance: a strategy that never priced funding
because the market simply has none yet must look different from one that
priced it and got a null reading (notes-S2.md).

Two look-ahead traps that are not obvious from the schema alone (Astra,
S2-context review):

- **Open interest's durable timestamp is a poll-round bucket, not the reading's
  own instant, and no finite slack fixes that.** ``hunter_market_worker.persist_rows``
  computes one bucket (rounded down to 5 minutes, ``OI_BUCKET_MINUTES``) for
  the *whole* round and then polls every market in it sequentially over REST,
  so a market polled late in the round can have its real reading land strictly
  after the bucket it is stored under. A first pass here required
  ``cut >= row.ts + one_bucket_width`` before trusting a durable row — Astra's
  review (round 2) produced a concrete counter-example that breaks it: a round
  starting at ``12:04:59`` (bucket ``12:00``, since ``oi_bucket`` floors the
  round's own start) reading a market at ``12:05:02`` writes ``ts=12:00``, and
  an evaluation cut at ``12:05:00`` — three seconds *before* that real read —
  would have accepted it as "safely five minutes past its bucket". Any finite
  slack has the same failure mode: it reduces exposure without ever
  establishing a guarantee, because nothing bounds how long one round may run.
  **Durable ``open_interest_history`` is therefore never treated as proof of
  ``<= cut`` here, full stop** — only the hot state's own ``oi_ts`` (the
  reading's real instant, ``hunter_market_worker.hot_state.write_open_interest``)
  is. A durable-only row is reported as ``timestamp_unprovable``, not used.
  The fix that actually closes this is out of this task's scope (it may not
  touch ``services/market-worker/**``): preserving each reading's own
  timestamp in ``open_interest_history`` instead of the round's bucket.
- **A realized settlement's hot-state write never touches the mark-price
  fields.** ``hunter_market_worker.hot_state.write_funding`` only updates the
  mark-price group when ``realized=False``, so after a settlement write the
  mark fields still hold whatever an earlier (or later) *unrelated* estimated
  snapshot left there. Combining them would fabricate an observation that was
  never actually made together; :func:`_resolve_funding` refuses unless
  ``funding_ts == mark_ts`` proves they came from the same write. Funding does
  not have the bucket problem above: ``funding_rates.funding_time`` is the
  settlement's own instant, not a poll-round artefact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from hunter_core.domain.market import NormalizedFunding, NormalizedOpenInterest
from hunter_strategy_worker import hot_state
from hunter_strategy_worker.repo import (
    FundingRow,
    OpenInterestRow,
    load_latest_funding_row,
    load_latest_open_interest_row,
)

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_strategy_worker.hot_state import DerivRaw
    from hunter_strategy_worker.repo import MarketRow

__all__ = ["DerivativesObservation", "load_derivatives"]


@dataclass(frozen=True, slots=True)
class DerivativesObservation:
    """What the context received for funding/open interest, and where from."""

    funding: NormalizedFunding | None
    funding_ts: datetime | None
    funding_source: str | None
    """``"durable"`` or ``"hot_state"``; ``None`` when ``funding`` is ``None``."""
    funding_reason: str | None
    """Populated only when ``funding`` is ``None``: ``"no_data"`` (nothing
    usable found), ``"no_mark_price"`` (a reading exists but not paired with a
    mark price it can be trusted to belong to)."""
    open_interest: NormalizedOpenInterest | None
    open_interest_ts: datetime | None
    open_interest_source: str | None
    open_interest_reason: str | None
    """``"no_data"`` (nothing anywhere), ``"no_open_interest_value"`` (a
    durable row exists, value is ``NULL``, and the hot state has nothing
    either), or ``"timestamp_unprovable"`` (a durable row has a value, but its
    poll-round bucket can never be proven ``<= cut`` — see module docstring —
    and the hot state has nothing fresher to use instead)."""


def _resolve_funding(
    market: MarketRow, row: FundingRow | None, raw: DerivRaw | None
) -> tuple[NormalizedFunding | None, str | None, str | None]:
    if row is not None and row.mark_price is not None:
        # One durable row, one settlement event: rate and mark come from the
        # same insert (``hunter_market_worker.durable``), so pairing them
        # fabricates nothing. ``funding_rates`` only ever holds settlements.
        funding = NormalizedFunding(
            exchange=market.exchange,
            symbol=market.symbol,
            funding_rate=row.rate,
            mark_price=row.mark_price,
            funding_kind="realized",
            ts=row.ts,
            received_at=row.ts,
        )
        return funding, "durable", None
    if (
        raw is not None
        and raw.funding_rate is not None
        and raw.mark_price is not None
        and raw.funding_ts is not None
        and raw.funding_ts == raw.mark_ts
    ):
        kind = raw.funding_kind if raw.funding_kind in ("estimated", "realized") else "estimated"
        funding = NormalizedFunding(
            exchange=market.exchange,
            symbol=market.symbol,
            funding_rate=raw.funding_rate,
            mark_price=raw.mark_price,
            funding_kind=kind,
            ts=raw.funding_ts,
            received_at=raw.funding_ts,
        )
        return funding, "hot_state", None
    had_a_rate = row is not None or (raw is not None and raw.funding_rate is not None)
    return None, None, "no_mark_price" if had_a_rate else "no_data"


def _resolve_open_interest(
    market: MarketRow, row: OpenInterestRow | None, raw: DerivRaw | None
) -> tuple[NormalizedOpenInterest | None, str | None, str | None]:
    """The hot state's own ``oi_ts`` is the only source ever trusted as proof
    of ``<= cut`` (module docstring, must-fix 1): it is tried first regardless
    of what the durable row says."""
    if raw is not None and raw.open_interest is not None and raw.open_interest_ts is not None:
        oi = NormalizedOpenInterest(
            exchange=market.exchange,
            symbol=market.symbol,
            open_interest=raw.open_interest,
            open_interest_value=None,
            ts=raw.open_interest_ts,
            received_at=raw.open_interest_ts,
        )
        return oi, "hot_state", None
    if row is not None and row.open_interest is not None:
        return None, None, "timestamp_unprovable"
    reason = "no_open_interest_value" if row is not None else "no_data"
    return None, None, reason


async def load_derivatives(
    session: AsyncSession,
    redis: redis_asyncio.Redis,
    *,
    market: MarketRow,
    cut: datetime,
) -> DerivativesObservation:
    """The last funding/open-interest observation with ``ts <= cut``."""
    funding_row = await load_latest_funding_row(session, market_id=market.id, until=cut)
    oi_row = await load_latest_open_interest_row(session, market_id=market.id, until=cut)
    # OI's durable ``ts`` never proves ``<= cut`` on its own (module docstring,
    # must-fix 1), so the hot state is unconditionally consulted for it.
    raw = await hot_state.read_derivatives(
        redis, exchange=market.exchange, symbol=market.symbol, cut=cut
    )
    funding, funding_source, funding_reason = _resolve_funding(market, funding_row, raw)
    oi, oi_source, oi_reason = _resolve_open_interest(market, oi_row, raw)
    return DerivativesObservation(
        funding=funding,
        funding_ts=None if funding is None else funding.ts,
        funding_source=funding_source,
        funding_reason=funding_reason,
        open_interest=oi,
        open_interest_ts=None if oi is None else oi.ts,
        open_interest_source=oi_source,
        open_interest_reason=oi_reason,
    )
