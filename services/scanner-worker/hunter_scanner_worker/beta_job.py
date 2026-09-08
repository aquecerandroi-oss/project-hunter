"""One pass of the beta producer: every monitored market, one closed hour.

T3.7 delivered the estimator (``beta_v1``) and T3.7's schema note delivered the
table; nothing ever ran them. With ``market_betas`` empty the admission check
answers ``unavailable`` for every candidate — "sem beta validado só shadow" — so
the wallet refuses every entry. This module is the missing half hour of work,
and it is deliberately the *smallest* thing that closes it: read, estimate,
write, count.

Three decisions worth stating, because each one is a fork somebody will
otherwise take differently later:

**The cut is the closed bar, never the clock.** ``as_of`` written on the row is
``floor_bar(now)`` — 12:37 measures the window that ended at 12:00 — so a rerun
inside the same hour is the *same* cut and therefore a retry, and idempotency is
a property of the key rather than of the caller's discipline. The wall clock
survives on the row as ``computed_at``/``available_at``, which is where it
belongs: when the answer became knowable, not what it is an answer about.

**The reference is measured once and the identity is never estimated.** The
reference market's bars are read one time per pass and reused by every other
market, and the reference's own row is :func:`reference_beta` — ``beta = 1`` by
definition, ``estimator = definition``, ``n = 0``, no ``R^2``. Feeding the
reference to the regression would produce the same 1 with a fabricated ``R^2 =
1`` next to it, and a consumer averaging that into a distribution of estimates
would be averaging a tautology.

**A market with no reference gets no row, and says so.** ``reference_market_id``
is ``NOT NULL``: a beta against nothing cannot be represented, and inventing a
self-reference would make the market look like a second BTC. The pass counts it
(``outcome="no_reference"``) and writes nothing — the only case in which silence
is the honest answer, because every other refusal *is* representable and is
therefore stored with its reason.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_indicators.beta import (
    DEFAULT_SPEC,
    BetaSpec,
    compute_beta,
    floor_bar,
    reference_beta,
    returns_from_closes,
)
from hunter_scanner_worker.beta_repo import bar_closes
from hunter_scanner_worker.beta_writer import UNCHANGED, write_revision
from hunter_scanner_worker.metrics import beta_revisions_total, beta_valid_markets
from hunter_scanner_worker.persist import DB_ROLE
from hunter_scanner_worker.regime import BTC_SYMBOL

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_indicators.beta import BetaEstimate, HourlyReturn
    from hunter_scanner_worker.registry import MarketRef

logger = get_logger(__name__)

STALE_AFTER = timedelta(hours=2)
"""Age at which the producer is *degraded*, never down.

Two hours is one missed hour plus its retry: a beta is recomputed every closed
hour and stays valid for one, so at two hours every revision in the table has
already expired and admission has started refusing on freshness. That is worth
saying out loud next to ``/ready`` — and it is not a reason to take the scanner
out of rotation, because the Radar, the baselines and the regime are unaffected.
"""

__all__ = ["STALE_AFTER", "BetaHealth", "BetaRun", "run_beta_once"]


@dataclass(slots=True)
class BetaRun:
    """What one pass did, in the numbers the heartbeat and the metrics publish."""

    as_of: datetime
    window_end: datetime
    outcomes: Counter[str] = field(default_factory=Counter[str])
    valid_markets: int = 0
    markets: int = 0
    duration_s: float = 0.0


@dataclass(slots=True)
class BetaHealth:
    """The producer's last pass, read by ``/ready`` and by ``hb:scanner:*``."""

    last_run_at: datetime | None = None
    last_window_end: datetime | None = None
    valid_markets: int = 0
    markets: int = 0

    def stale(self, now: datetime, *, after: timedelta = STALE_AFTER) -> bool:
        return self.last_run_at is None or (now - self.last_run_at) > after

    def describe(self, now: datetime) -> str:
        """A sentence, never a verdict — the same shape ``rest_gate`` uses."""
        if self.last_run_at is None:
            return "never ran"
        age = (now - self.last_run_at).total_seconds() / 3600
        state = "stale" if self.stale(now) else "ok"
        return f"{state} ({self.valid_markets}/{self.markets} valid, {age:.1f}h ago)"

    def record(self, run: BetaRun, *, now: datetime) -> None:
        self.last_run_at = now
        self.last_window_end = run.window_end
        self.valid_markets = run.valid_markets
        self.markets = run.markets


def _outcome(estimate: BetaEstimate, written: str) -> str:
    """One word for the metric: what the pass *did*, then what it concluded."""
    if written == UNCHANGED:
        return UNCHANGED
    return "valid" if estimate.valid else "invalid"


async def _estimate_for(
    session: AsyncSession,
    ref: MarketRef,
    *,
    reference: MarketRef,
    reference_returns: Sequence[HourlyReturn],
    as_of: datetime,
    spec: BetaSpec,
) -> BetaEstimate:
    if ref.market_id == reference.market_id:
        return reference_beta(as_of=as_of, market=ref.symbol, spec=spec)
    closes = await bar_closes(session, ref.market_id, as_of=as_of, spec=spec)
    return compute_beta(
        returns_from_closes(closes, as_of=as_of, spec=spec),
        reference_returns,
        as_of=as_of,
        spec=spec,
        market=ref.symbol,
        reference=reference.symbol,
    )


async def _one_market(
    factory: async_sessionmaker[AsyncSession],
    ref: MarketRef,
    *,
    reference: MarketRef,
    reference_returns: Sequence[HourlyReturn],
    as_of: datetime,
    now: datetime,
    spec: BetaSpec,
    run: BetaRun,
) -> None:
    """Read, estimate and store one market — in one transaction of its own.

    Per market rather than per pass, because the failure modes are per market:
    a coefficient too wide for ``NUMERIC(18,8)`` (which the loader must refuse
    rather than truncate) or a concurrent producer racing the current-revision
    index must cost that market its hour, not the other 199 theirs.
    """
    try:
        async with role_session(factory, db_role=DB_ROLE) as session:
            estimate = await _estimate_for(
                session,
                ref,
                reference=reference,
                reference_returns=reference_returns,
                as_of=as_of,
                spec=spec,
            )
            written = await write_revision(
                session,
                estimate,
                market_id=ref.market_id,
                reference_market_id=reference.market_id,
                now=now,
            )
    except Exception:
        logger.exception("scanner_beta_market_failed", symbol=ref.symbol, as_of=as_of.isoformat())
        run.outcomes["failed"] += 1
        beta_revisions_total.labels(outcome="failed").inc()
        return
    outcome = _outcome(estimate, written)
    run.outcomes[outcome] += 1
    beta_revisions_total.labels(outcome=outcome).inc()
    if estimate.valid:
        run.valid_markets += 1


async def run_beta_once(
    factory: async_sessionmaker[AsyncSession],
    refs: Sequence[MarketRef],
    *,
    now: datetime,
    spec: BetaSpec = DEFAULT_SPEC,
    reference_symbol: str = BTC_SYMBOL,
) -> BetaRun:
    """Produce one revision per market for the hour that closed at or before ``now``."""
    now = ensure_utc(now)
    as_of = floor_bar(now, spec)
    run = BetaRun(as_of=as_of, window_end=as_of, markets=len(refs))
    started = time.monotonic()
    reference = next((ref for ref in refs if ref.symbol == reference_symbol), None)
    if reference is None:
        # Nothing is written: the row could not name a reference, and a beta
        # that names none is not a beta. Loud, because it means the universe
        # lost the market every other market is measured against.
        logger.error("scanner_beta_no_reference", reference=reference_symbol, markets=len(refs))
        run.outcomes["no_reference"] += len(refs)
        beta_revisions_total.labels(outcome="no_reference").inc(len(refs))
        # Zeroed, not left at the last pass's value: the gauge answers "how many
        # markets are admissible right now", and holding yesterday's number
        # while the reference is gone is the one answer nobody can act on.
        beta_valid_markets.set(0)
        return run
    async with role_session(factory, db_role=DB_ROLE) as session:
        closes = await bar_closes(session, reference.market_id, as_of=as_of, spec=spec)
    reference_returns = returns_from_closes(closes, as_of=as_of, spec=spec)
    for ref in refs:
        await _one_market(
            factory,
            ref,
            reference=reference,
            reference_returns=reference_returns,
            as_of=as_of,
            now=now,
            spec=spec,
            run=run,
        )
    run.duration_s = time.monotonic() - started
    beta_valid_markets.set(run.valid_markets)
    logger.info(
        "scanner_beta_pass",
        as_of=as_of.isoformat(),
        markets=run.markets,
        valid=run.valid_markets,
        reference_bars=len(reference_returns),
        outcomes=dict(run.outcomes),
        duration_s=round(run.duration_s, 3),
    )
    return run
