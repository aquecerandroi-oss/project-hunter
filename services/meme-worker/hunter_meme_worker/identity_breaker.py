"""Circuit breaker for the per-mint identity read (T4.97b/R80 must-fix 1).

``GET /coins/{mint}`` is the only call ``poll_once`` (``collect.py``) still
makes per mint once the chain loop is healthy and narrows the REST plan to
identity-only reads (``tracker.needs_rest`` under ``chain_covered=True``,
``collect.chain_covered``). That route has answered 404 for every mint tried
live since ~2026-09-25 17:13Z (T4.97, ``identity_sweep.py``). Left unguarded,
every cycle still spends up to the whole budget on it — the same shared
``pumpfun_rest`` bucket the identity sweep's listing call (``GET /coins``,
succeeding every ~20 s) and the tracker's Mayhem/final-read reads compete for.

**Its own counter, never ``SourceStats.consecutive_failures``** (T4.97b/R80's
own review, ``.claude/state/astra-review-T4.97b-design.md``): that field is
the whole ``pumpfun_rest`` source's health, and the identity sweep's
listing successes reset it every ~20 s — a shared counter would almost never
reach a trip threshold while the by-mint route stays dead, which is exactly
the accounting bug this breaker exists to avoid. ``SourceStats`` keeps its
existing meaning (failures since *any* success on the source); this module
answers a narrower question — has the by-mint route itself answered once —
and is deliberately blind to the listing call's own outcome.

Open, it does not retry forever nor stop retrying forever: a sparse probe —
at most one mint, rotating so one permanently broken mint never blocks the
diagnosis of the others — is let through every ``probe_interval``, so the
breaker closes itself the moment pump.fun restores the route, with no deploy
and no operator action.

**Known gap** (T4.97b review round 2): this breaker's own state — open or
closed, consecutive by-mint failures, next probe due — is not on the
heartbeat or the API. Only the pre-existing, source-wide
``SourceStats.consecutive_failures`` (``source_stats.py``) reaches
``GET /meme/sources``, and the identity sweep's listing successes reset
*that* field every ~20 s regardless of this breaker's own state — an operator
watching the tooltip can see "falhas seguidas: 0" while this breaker is open
and suspending reads. Wiring this breaker's own diagnostics through
``sources.py`` (already at the 350-line ceiling), the API schema and the web
panel is left for a follow-up, not folded into this task's file scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

__all__ = ["DEFAULT_PROBE_INTERVAL_S", "DEFAULT_TRIP_THRESHOLD", "IdentityBreaker"]

DEFAULT_TRIP_THRESHOLD = 5
"""Consecutive by-mint failures before the breaker opens. Small on purpose: a
single cycle can select up to the whole REST budget (60) for identity-only
reads, and every one of them costs the bucket the identity sweep and the
tracker's other REST needs share — five is enough to conclude "this route is
down right now" without spending the rest of the budget finding out twice."""

DEFAULT_PROBE_INTERVAL_S = 300.0
"""How often an open breaker lets one mint through: five minutes — frequent
enough to notice pump.fun restoring the route without a deploy, sparse enough
that the outage stops costing what it cost before the breaker opened."""


@dataclass
class IdentityBreaker:
    """One breaker for the by-mint identity read, shared across mints.

    Mutable, like ``SourceStats``/``MintTracker``: a single instance lives on
    ``RadarContext`` (``context.py``) for the process's whole run.
    """

    trip_threshold: int = DEFAULT_TRIP_THRESHOLD
    probe_interval: timedelta = field(
        default_factory=lambda: timedelta(seconds=DEFAULT_PROBE_INTERVAL_S)
    )
    consecutive_failures: int = 0
    last_probe_at: datetime | None = None
    _probe_index: int = 0
    """Rotates which mint is offered the sparse probe (Astra's must-fix,
    T4.97b review round 2): picking the same ``mints[0]`` every time means a
    mint whose *own* read fails for a reason that has nothing to do with the
    route (delisted, malformed) could keep the breaker open forever even
    after pump.fun restores the route for everyone else."""

    @property
    def is_open(self) -> bool:
        return self.consecutive_failures >= self.trip_threshold

    def record_success(self) -> None:
        """The by-mint route answered — close the breaker and forget the past
        failures. Never called from the listing call: only a by-mint read of
        this exact route counts."""
        self.consecutive_failures = 0
        self.last_probe_at = None
        self._probe_index = 0

    def record_failure(self) -> None:
        """Only :meth:`filter` reads or writes ``last_probe_at``, and only
        while the breaker is open — this method never touches it."""
        self.consecutive_failures += 1

    def filter(
        self, mints: tuple[str, ...], now: datetime
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Split ``mints`` into ``(selected, suspended)``.

        Closed: everything is selected, unchanged. Open: at most one mint
        every ``probe_interval`` — the rest is suspended, never attempted,
        never spending the budget the failing route was burning before it
        tripped. Selecting a probe stamps ``last_probe_at`` now, whatever the
        probe's own outcome turns out to be — the next one is due a full
        interval later either way, not immediately on a failed probe.
        """
        if not self.is_open or not mints:
            return mints, ()
        if self.last_probe_at is None or now - self.last_probe_at >= self.probe_interval:
            self.last_probe_at = now
            index = self._probe_index % len(mints)
            self._probe_index += 1
            probe = mints[index]
            rest = mints[:index] + mints[index + 1 :]
            return (probe,), rest
        return (), mints
