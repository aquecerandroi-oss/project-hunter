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

__all__ = ["CONSUMER_GROUP", "HEARTBEAT_KEY", "PRODUCER", "ShadowConfig", "load_config"]


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else int(raw)


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else float(raw)


@dataclass(frozen=True, slots=True)
class ShadowConfig:
    """Operational knobs. Defaults are what the compose service runs with."""

    cohort: str = ShadowCohort.PROSPECTIVE
    """``prospective`` here; a replay run passes its own ``replay:<run_id>``."""

    context_minutes: int = 1560
    """How much 1m history one evaluation may look at, in minutes.

    The longest frozen window in v1 is the ATR's 97 bars of 15m (1455 minutes);
    the rest (96 bars of 15m relative volume, 288 bars of 5m) fits inside it.
    Plus one hour of slack so a warm-up is a real warm-up and not a truncation.
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


def load_config() -> ShadowConfig:
    """Read the operational knobs from the environment."""
    return ShadowConfig(
        cohort=os.environ.get("SHADOW_COHORT", ShadowCohort.PROSPECTIVE).strip()
        or ShadowCohort.PROSPECTIVE,
        context_minutes=_int("SHADOW_CONTEXT_MINUTES", 1560),
        hot_state_tail=_int("SHADOW_HOT_STATE_TAIL", 20),
        eligibility_max_lag_s=_int("SHADOW_ELIGIBILITY_MAX_LAG_S", 300),
        outcome_poll_s=_float("SHADOW_OUTCOME_POLL_S", 10.0),
        outbox_poll_s=_float("SHADOW_OUTBOX_POLL_S", 1.0),
        outbox_lag_alert_s=_float("SHADOW_OUTBOX_LAG_ALERT_S", 60.0),
        censor_after_s=_int("SHADOW_CENSOR_AFTER_S", 7200),
        gap_recovery_max_s=_int("SHADOW_GAP_RECOVERY_MAX_S", 86_400),
        version_refresh_s=_float("SHADOW_VERSION_REFRESH_S", 60.0),
        consumer_stall_s=_float("SHADOW_CONSUMER_STALL_S", 300.0),
    )
