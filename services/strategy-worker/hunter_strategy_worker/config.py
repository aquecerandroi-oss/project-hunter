"""Configuration of the shadow strategy-worker.

Everything here is operational (how often to poll, how long to wait for a
missing bar before censoring an outcome). Nothing here is part of the frozen
experiment: thresholds, windows, horizons and the cost hypothesis all live in
``strategy_versions.default_parameters`` and never in an environment variable —
otherwise a restart with a different env would silently be a different
experiment (SHADOW-LAB.md §1).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from hunter_core.domain.enums import ShadowCohort

CONSUMER_GROUP = "strategy-worker.shadow"
"""Own group on ``market.candles.closed`` — never shared with another service."""

HEARTBEAT_KEY = "hb:strategy:shadow"
PRODUCER = "strategy-worker.shadow"

__all__ = [
    "CONSUMER_GROUP",
    "EXPECTED_BAR_COST_S",
    "HEARTBEAT_KEY",
    "PRODUCER",
    "ShadowConfig",
    "default_claim_idle_ms",
    "load_config",
]


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else int(raw)


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else float(raw)


_CLAIM_IDLE_MS_UNSET: int = -1
"""Sentinel for ``ShadowConfig.claim_idle_ms``: 'derive it from
``worker_concurrency`` in ``__post_init__``', not a real duration -- kept an
``int`` (not ``int | None``) so the field's own type stays a plain ``int``
everywhere it is used (``consume()``'s ``claim_idle_ms: int`` parameter above
all), instead of forcing every caller to narrow an ``Optional`` that is never
actually ``None`` by the time ``__init__`` returns.
"""

EXPECTED_BAR_COST_S: float = 8.0
"""Conservative worst-case wall time of one ``handle_candle`` call under load,
grounding :data:`ShadowConfig.claim_idle_ms`'s default -- not a guess.

``docs/DEPLOYMENT.md``'s "Custo medido" measured ~1.4-1.5 evaluations/s per
*due version* on this shape of workload (T3.74b). A bar can have up to 11
versions of one family due at once (T3.74's roster) and ``handle_candle``'s
per-version loop is sequential by design -- the T3.74b family cache shares the
candle *read* across versions, never the ``evaluate_slot``/persist call, which
still pays its own DB round trips per version. 11 / 1.4 ~= 7.9s, rounded up.
"""


def default_claim_idle_ms(worker_concurrency: int) -> int:
    """Default for :data:`ShadowConfig.claim_idle_ms`: ``worker_concurrency ×
    EXPECTED_BAR_COST_S``, in milliseconds (T3.74d).

    See ``ShadowConfig.claim_idle_ms``'s own docstring for the review finding
    this answers and the bound it must respect.
    """
    return int(max(1, worker_concurrency) * EXPECTED_BAR_COST_S * 1000)


@dataclass(frozen=True, slots=True)
class ShadowConfig:
    """Operational knobs. Defaults are what the compose service runs with."""

    cohort: str = ShadowCohort.PROSPECTIVE
    """``prospective`` here; a replay run passes its own ``replay:<run_id>``."""

    context_minutes: int = 1560
    """The **floor** of how much 1m history one evaluation looks at, in minutes.

    Until T3.54b this was the whole answer, the same number for every version:
    the longest frozen window in v1 is the ATR's 97 bars of 15m (1455 minutes),
    the rest (96 bars of 15m relative volume, 288 bars of 5m) fits inside it,
    plus one hour of slack so a warm-up is a real warm-up and not a truncation.

    It was also a ceiling on what a version could *be*. A 1h grid with
    ``atr_bars = 97`` reaches 5820 minutes back, so the two variants T3.54
    activated were born mute — 5760 bars, 100 % ``atr_warmup`` — and the only
    knob available multiplied the candle reads of every other live version by
    ~3.8 (notes-T3.54 §3.4). Since T3.54b the requirement is derived per version
    from its own frozen parameters
    (:func:`hunter_strategy_worker.context_budget.required_context_minutes`) and
    this number is the floor under it: every version that needs less reads
    exactly what it read before, so no live population moves.
    """

    context_max_minutes: int = 6000
    """The ceiling over that requirement, in minutes.

    Not a safety net — a budget. One version with a long window costs candle
    reads on every bar it evaluates, and an unbounded derivation would let a
    single parameter make the whole process expensive without anyone deciding
    it. 6000 is a round number just over the widest window this build can
    produce today (``mean_reversion_h1_v1``: 5880), so it admits the 1h sibling
    and refuses the next escalation until someone raises this deliberately.

    A version whose requirement exceeds it is refused at **activation**
    (``infra/scripts/activate_strategy_version.py``); the worker clamps and
    records ``context_minutes`` in the envelope, so a context that was cut short
    reads as a reason instead of a mystery.
    """

    hot_state_tail: int = 20
    """Newest minutes read from Redis to cover what Postgres has not flushed yet."""

    eligibility_max_lag_s: int = 300
    """How stale a bar may be and still let ``markets.is_monitored`` stand as
    evidence of eligibility *at that bar's close*.

    Universe membership is overwritten in place by every refresh, so the current
    flag cannot prove what was true an hour ago (Astra, S2 design review,
    must-fix 4). Past that lag the evaluation is ``unavailable`` — it neither
    decides nor re-arms — instead of pretending the present is the past.

    300 s, not 120 s: the universe is refreshed every 900 s, so five minutes is
    still comfortably inside one refresh, and a tighter gate would swallow the
    ``no_entry: late`` accounting the plan asks for. With this gate at 120 s and
    ``max_entry_delay_s`` also at 120 s, a bar late enough to produce a late
    entry would have been dropped as unavailable first, and the coverage counts
    would silently lose that population.
    """

    outcome_poll_s: float = 10.0
    outbox_poll_s: float = 1.0
    outbox_lag_alert_s: float = 60.0
    """Oldest undispatched outbox row tolerated before ``/ready`` turns false."""

    decision_lag_p50_alert_s: float = 10.0
    decision_lag_p95_alert_s: float = 30.0
    """T3.80: the canonical numbers for "this process's decisions are
    running behind" -- above a 10 s median or a 30 s p95 of
    ``decision_lag_p50_s``/``_p95_s`` (T3.74c, this same heartbeat). Not read
    by ``/ready`` today (a slow decision is not a dead process); mirrored by
    ``replay.budget.ReplayBudget``'s own thresholds, which pause the replay
    lane on exactly these numbers -- T3.76 measured a live median of 90 s /
    p95 of 171 s while a replay ran inside this same worker's container."""

    censor_after_s: int = 7200
    """How long a missing 1m bar **that nobody registered** is waited for.

    Only this branch is a stopwatch now: when ``ingestion_gaps`` has a row
    covering the minute, :mod:`.gaps` decides from the collector's own state
    instead of the clock (risk-engine-guardian, S2 review, MUST-FIX 2).

    7200 s, up from 1800 s. 1800 s was a guess and it was too short in the wrong
    direction: the S2 proof recovered 786 gaps in about ten minutes, and a
    longer outage would have censored follow-ups that were about to be filled —
    a loss correlated with collector instability, which is the worst kind of
    bias for a research log. Two hours is what an unregistered hole is now given
    because gap detection runs every 60 s over a 1439-minute window
    (``recovery.py``): a *running* market-worker registers any missing minute
    within about three minutes of its close, so an unregistered hole two hours
    old means the collector was down for those two hours, and a collector that
    has been down two hours is not about to fill that minute quietly.
    """

    gap_recovery_max_s: int = 86_400
    """How long an ``open`` ``ingestion_gaps`` row is trusted to still be work
    in progress.

    An ``open`` gap vetoes censorship — that is the whole point of MUST-FIX 2 —
    but only the recovery loop ever moves a row to ``failed``, so a market-worker
    that is not running would hold the tracking (and the ``tracking_hold`` behind
    it) open for good, which ``notes-S2.md`` §6 refused. A day is generous by
    construction: the loop retries every 60 s, gives up after 5 attempts and
    reopens a ``failed`` gap an hour later, so a gap it is genuinely working on
    resolves or turns ``failed`` within hours.
    """

    version_refresh_s: float = 60.0
    consumer_stall_s: float = 300.0
    """No consumer iteration for this long makes ``/ready`` false."""

    worker_concurrency: int = 8
    """Bars handled concurrently by one process (T3.74c), bounded by the DB
    pool (``Settings.db_pool_size`` + ``db_max_overflow``, 5 + 5 = 10 today):
    a bar in flight holds at most one connection at a time (each
    ``role_session`` closes before the next opens), so 8 leaves headroom for
    the outbox/heartbeat loops' own short-lived sessions in the same process
    without starving them. Different markets never share state -- a session,
    a slot row, a candle window -- so processing them concurrently changes
    nothing about *what* is decided, only *when*; the ordering that does
    matter (two bars of the *same* market) is still enforced per-market
    (``consumer._market_key``), never by this number. 1 reproduces the
    strictly serial behaviour every version before T3.74c had.
    """

    late_delay_backlog_max_s: float = 120.0
    """Bar-level safety valve, not the fix (T3.74c).

    ``eligibility_max_lag_s`` (300 s) already refuses a bar too stale to *prove*
    eligibility, but only after the version loop has already paid for
    ``load_market``/``load_family_readers`` and is about to spend a context
    read per due version. During a real backlog (worker behind the stream by
    minutes, not seconds) that cost compounds: every extra bar processed late
    is itself slower to process, which makes the next one later still.

    This gate is checked once per **bar** (``handle_candle``, before any of
    that), not once per version, and at 120 s -- the ``max_entry_delay_s`` a
    version's own frozen costs use for ``late:delay`` (``plan.py``) is
    per-version and unknown this early, so 120 s is a conservative process-wide
    proxy for it, not a replacement. A bar this stale would almost always end
    up ``no_entry: late:delay`` anyway if it were fully evaluated and happened
    to trigger -- this only skips paying for that outcome when the backlog is
    real. Named and counted
    (``hunter_shadow_bars_skipped_total{reason="late_delay_backlog"}``), never
    silent: it trades a slice of the ``no_entry: late:delay`` research
    population for the worker's ability to catch back up, and only in the
    window where the alternative was compounding delay, not a clean decision.

    Independent of ``eligibility_max_lag_s``: a healthy worker never reaches
    120 s in the first place, so this only fires under exactly the backlog
    conditions T3.74c measured (median 22-65 s, p95 80-154 s on 10/09).
    """

    claim_idle_ms: int = _CLAIM_IDLE_MS_UNSET
    """How long, in ms, a message may sit unacked in this consumer's own
    pending list before ``consume()``'s ``XAUTOCLAIM``
    (``hunter_core.events.consume``) reclaims -- and redelivers -- it. Left
    unset (the default), it is derived from ``worker_concurrency`` in
    ``__post_init__`` (:func:`default_claim_idle_ms`); pass a number to pin it
    regardless of ``worker_concurrency``.

    **The bug this answers (T3.74d code review, HIGH).** ``BarDispatcher``
    (T3.74c) lets ``run_consumer`` keep reading past a bar still queued behind
    the concurrency semaphore or a busy per-market lock -- exactly the shape
    ``claim_idle_ms`` exists to reclaim *dead* work from, not slow-but-alive
    work. ``consume()``'s own flat default (30 000 ms) has no relationship to
    how long this process might legitimately hold a message: a deep burst, or
    a bar with several due versions each paying their own DB round trip,
    could exceed 30 s while still making real progress. Past that,
    ``XAUTOCLAIM`` redelivers a message this *same* consumer already holds,
    and without the dispatcher's own guard (``BarDispatcher.submit``,
    ``hunter_shadow_bars_skipped_total{reason="already_in_flight"}``) that
    redelivery would be resubmitted and run a second time -- doubling work
    exactly during the burst the dispatcher exists to absorb. That guard
    makes a redelivery like this safe (never double-run), but it is still a
    wasted ``XAUTOCLAIM`` round trip and a log line every time it fires, so
    the interval should still be sized to the real queueing delay.

    **The arithmetic.** ``worker_concurrency × EXPECTED_BAR_COST_S`` (both in
    this module): a conservative stand-in for "a bar queued behind a full
    dispatcher may have to wait for up to a full round of `worker_concurrency`
    already-running bars, each costing up to the worst-case per-bar time,
    before it is even handed to a handler" -- deliberately generous (not a
    tight queueing-theory bound) so the reclaim interval clears the reasoned
    worst case, not just the median. At the defaults (8 × 8.0 s) that is
    64 000 ms.

    **The bound.** Must stay well under ``consumer_stall_s`` (300 s, this same
    class): that is already the threshold at which ``/ready`` calls this
    process not making progress, so a truly dead consumer's pending messages
    should be reclaimable well before an operator or orchestrator would
    otherwise have to intervene on the liveness signal alone. Raising this
    much past a small fraction of ``consumer_stall_s`` would mean a crashed
    consumer's own backlog sits un-reclaimed for longer than the system
    already tolerates before declaring it dead by another signal -- never
    raise it that high. 64 000 ms is ~21 % of the 300 000 ms default.
    """

    def __post_init__(self) -> None:
        if self.claim_idle_ms == _CLAIM_IDLE_MS_UNSET:
            object.__setattr__(
                self, "claim_idle_ms", default_claim_idle_ms(self.worker_concurrency)
            )


def load_config() -> ShadowConfig:
    """Read the operational knobs from the environment."""
    return ShadowConfig(
        cohort=os.environ.get("SHADOW_COHORT", ShadowCohort.PROSPECTIVE).strip()
        or ShadowCohort.PROSPECTIVE,
        context_minutes=_int("SHADOW_CONTEXT_MINUTES", 1560),
        context_max_minutes=_int("SHADOW_CONTEXT_MAX_MINUTES", 6000),
        hot_state_tail=_int("SHADOW_HOT_STATE_TAIL", 20),
        eligibility_max_lag_s=_int("SHADOW_ELIGIBILITY_MAX_LAG_S", 300),
        outcome_poll_s=_float("SHADOW_OUTCOME_POLL_S", 10.0),
        outbox_poll_s=_float("SHADOW_OUTBOX_POLL_S", 1.0),
        outbox_lag_alert_s=_float("SHADOW_OUTBOX_LAG_ALERT_S", 60.0),
        decision_lag_p50_alert_s=_float("SHADOW_DECISION_LAG_P50_ALERT_S", 10.0),
        decision_lag_p95_alert_s=_float("SHADOW_DECISION_LAG_P95_ALERT_S", 30.0),
        censor_after_s=_int("SHADOW_CENSOR_AFTER_S", 7200),
        gap_recovery_max_s=_int("SHADOW_GAP_RECOVERY_MAX_S", 86_400),
        version_refresh_s=_float("SHADOW_VERSION_REFRESH_S", 60.0),
        consumer_stall_s=_float("SHADOW_CONSUMER_STALL_S", 300.0),
        worker_concurrency=_int("SHADOW_WORKER_CONCURRENCY", 8),
        late_delay_backlog_max_s=_float("SHADOW_LATE_DELAY_BACKLOG_MAX_S", 120.0),
        claim_idle_ms=_int("SHADOW_CLAIM_IDLE_MS", _CLAIM_IDLE_MS_UNSET),
    )
