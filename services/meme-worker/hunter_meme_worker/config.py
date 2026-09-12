"""What the meme radar runs on: cadences, budgets and one ceiling per source.

Every number here is a **cadence or a budget**, never a threshold: nothing in this
service concludes anything (T4-MEME-RADAR.md §0 — the slice is monitoring only, no
``RiskDecision``, no order). The budgets are the measured limits of the free
sources, not preferences:

- ``rest_budget_per_minute = 60`` is the ``frontend-api-v3.pump.fun`` limit read
  off its own ``x-ratelimit-*`` headers (T4.0 §2, re-confirmed live in T4.1). It is
  a **ceiling shared by IP**, so a second process on the same host halves it —
  declared here because the adapter's token bucket is per instance unless Redis
  backs it (T4.1's own stated limitation);
- ``rpc_top_k = 20`` against a public RPC that allows ~10 req/s *and* 40 calls per
  method/10 s: reconciling the whole tracked set against the chain is not available
  at this price, so the largest market caps are reconciled and the rest carries the
  REST mirror's word, labelled by ``meme_curve_snapshots.source``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hunter_core.logging import get_logger
from hunter_meme_worker.features import FEATURES_VERSION

if TYPE_CHECKING:
    from hunter_core.settings import Settings

ROLE = "meme"
"""``HUNTER_ROLE=meme``. The heartbeat is ``hb:meme:radar`` (``__main__``)."""

INSTANCE = "radar"
"""A **fixed** instance name, not ``host:pid``, and that is a decision.

PumpPortal serves one connection per client and documents that several
simultaneous connections can earn an hourly ban (T4.0 §2), so this collector is a
singleton by construction — the compose file runs one replica and the fixed
heartbeat key says so. The consequence is declared: two meme-workers would write
the *same* key rather than appear as two instances, so "only one is running" is
enforced by the deployment, not by the heartbeat.
"""

WS_STREAM = "pumpportal_ws"
CURVE_STREAM = "curve_poll"
FEATURES_STREAM = "features_1m"
"""The three ``meme_ingest_gaps.stream`` values — three different operator
problems: discovery dropped, the poll budget did not reach a mint, or a minute
produced no feature row at all."""


@dataclass(frozen=True, slots=True)
class MemeConfig:
    """Immutable; built once at startup from ``Settings``."""

    enabled: bool = False
    tracked_max: int = 120
    track_window_minutes: int = 1440
    young_minutes: int = 30
    """Inside the tracked set, the tier polled first. Thirty minutes because that
    is where a curve either starts moving or does not — and because a tier larger
    than the budget starves the rest, which the tracker reports as a gap instead of
    hiding (``tracker.py``)."""

    rest_budget_per_minute: int = 60
    rpc_top_k: int = 20
    retention_days: int = 90
    retention_batch: int = 5000
    features_version: str = FEATURES_VERSION

    poll_cycle_s: float = 60.0
    """One pass of the poll budget per minute: the budget *is* per 60 s."""

    features_cycle_s: float = 5.0
    """How often the folder checks whether a minute closed — not how often it
    folds. A 60 s timer would drift into the next minute and fold the wrong one."""

    retention_cycle_s: float = 3600.0
    reconcile_cycle_s: float = 300.0
    """RPC reconciliation of the top-K. Five minutes, not every cycle: the chain is
    the truth but the public RPC is the scarcest budget of the three."""

    lab_enabled: bool = True
    """The continuous paper Lab (T4.6). ``MEME_LAB_ENABLED`` defaults to **true**
    whenever the radar collects: the Lab reads only what the collector already
    wrote and speaks to one more endpoint (``/sol-price``, at most once a
    minute), so a second switch defaulting to off would only produce a radar
    that looks alive and proposes nothing. Off is for an operator who wants the
    collector without the loop, and the readiness body says so."""

    lab_cycle_s: float = 60.0
    """One tick per minute — the cadence of the closed minute it reads."""

    lab_proposal_ttl_s: int = 120
    """``expires_at = proposed_at + 120 s`` (contract): memes move fast."""

    lab_fill_window_s: int = 180
    """No snapshot strictly after the decision within 3 min → ``unfilled`` with
    ``no_later_snapshot`` (contract §Semântica 2). The same window bounds a
    sale: an exit that finds no later snapshot is ``rug_no_snapshot``."""

    lab_gate_backlog_minutes: int = 3
    """After a restart the gate re-reads at most this many closed minutes: a
    proposal for an older minute would expire before anyone could act on it."""

    lab_sol_usd_max_age_s: int = 60
    """The SOL/USD quote is re-read at most once a minute (its own upstream
    rate-limit group, 50/60 s), and only when a fill or a sale needs it."""


def _int_env(name: str, default: int) -> int:
    """An integer knob of this worker, or its default. A malformed value is the
    default **and a warning**, never a crash loop: a typo in one budget must not
    take down a collector whose other three budgets are fine."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        get_logger(__name__).warning("meme_config_invalid", variable=name, value=raw)
        return default


def load_config(settings: Settings) -> MemeConfig:
    """``Settings`` for the one number two subsystems share; the environment for
    this worker's own budgets.

    **The split is deliberate and it is where the line falls in this repo.**
    ``meme_retention_days`` is in ``Settings`` because
    ``infra/scripts/partition_retention.py`` reads the *same* number to drop a
    month of the three partitioned tables — two copies would be two retention
    policies that agree until the night one of them is edited (§1.3's own
    argument). The four budgets below are read by nobody else, and the precedent
    for a worker owning its own knob is ``hunter_scanner_worker.config``
    (``MARKET_EXCHANGE_CODE``, read straight from the environment).

    The declared reason they are not in ``Settings`` anyway: that file sits **at**
    the 350-line budget (``infra/scripts/check_file_size.py``), so four more
    documented fields would have forced a split of a module four other tasks are
    editing. Written down instead of discovered — if ``Settings`` gains room, these
    belong there.
    """
    return MemeConfig(
        enabled=_bool_env("MEME_ENABLED", default=False),
        tracked_max=_int_env("MEME_TRACKED_MINTS_MAX", 120),
        track_window_minutes=_int_env("MEME_TRACK_WINDOW_MINUTES", 1440),
        rpc_top_k=_int_env("MEME_RPC_TOP_K", 20),
        retention_days=settings.meme_retention_days,
        lab_enabled=_bool_env("MEME_LAB_ENABLED", default=True),
    )


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes"}
