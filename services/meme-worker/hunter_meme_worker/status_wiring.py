"""``/ready`` details for the radar's own collectors and the Lab (split out of
``main.py`` for the 350-line budget): each one a lambda ``runtime.status_details``
reads on demand, never a verdict — a degraded source is a detail next to a
green readiness check (contract §Semântica 5), and the one real readiness
check (discovery connected) lives in :func:`register_health` alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from hunter_core.runtime import WorkerRuntime
    from hunter_exchanges.pumpfun.trenches import TrenchesWsClient
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.lab import LabContext

__all__ = ["STALE_EVENT_AFTER_S", "register_health", "register_lab_health"]

STALE_EVENT_AFTER_S = 600
"""No new token for ten minutes is *suspicious*, not fatal: pump.fun genuinely has
quiet stretches, and T4.1's acceptance criterion separates "the socket is alive"
from "there is activity". It shows up as a status detail, never as a red
``/ready`` (``hunter_core.runtime`` keeps the two apart)."""


def _last_event_age(ctx: RadarContext) -> str:
    last = ctx.state.last_event_at
    if last is None:
        return "never"
    age = int((utcnow() - last).total_seconds())
    return f"{age}s{' (stale)' if age > STALE_EVENT_AFTER_S else ''}"


def register_health(
    runtime: WorkerRuntime, ctx: RadarContext, boards: dict[str, TrenchesWsClient]
) -> None:
    """Readiness answers "should traffic reach me"; the details answer "what is degraded"."""

    async def discovery_connected() -> bool:
        return ctx.events.state.ws_state == "connected"

    runtime.readiness_checks.append(discovery_connected)
    runtime.status_details["discovery_stream"] = lambda: ctx.events.state.ws_state
    runtime.status_details["tracked_mints"] = lambda: str(len(ctx.tracker))
    runtime.status_details["last_event_age_s"] = lambda: _last_event_age(ctx)
    runtime.status_details["ws_generation"] = lambda: str(ctx.state.ws_generation)
    runtime.status_details["trenches"] = lambda: (
        "disabled (MEME_TRENCHES_ENABLED=false)"
        if not boards
        else ", ".join(f"{b}:{c.state.ws_state}" for b, c in boards.items())
    )
    runtime.status_details["swap_api"] = lambda: (
        "disabled (MEME_SWAP_API_ENABLED=false)"
        if ctx.trades is None
        else f"{len(ctx.trades.coverage)} mints covered"
    )
    runtime.status_details["risk"] = lambda: (
        "disabled (MEME_RISK_ENABLED=false)"
        if ctx.risk is None
        else f"{len(ctx.risk.last_read)} mints read"
    )
    runtime.status_details["activity"] = lambda: (
        "disabled (MEME_ACTIVITY_ENABLED=false or swap_api off)"
        if ctx.activity is None
        else f"{len(ctx.activity.readings)} mints with a 1m reading"
    )
    runtime.status_details["wallets"] = lambda: (
        "disabled (MEME_WATCH_WALLETS empty)"
        if ctx.wallets is None
        else ctx.wallets.describe(utcnow())
    )


def register_lab_health(runtime: WorkerRuntime, lab: LabContext | None) -> None:
    """The Lab's liveness as a detail, never a verdict: a stopped loop must be
    visible next to a green collector, and a quiet gate must not turn ``/ready``
    red (contract §Semântica 5)."""
    if lab is None:
        runtime.status_details["lab"] = lambda: "disabled (MEME_LAB_ENABLED=false)"
        return

    def describe() -> str:
        last = lab.state.last_tick_at
        if last is None:
            return "starting"
        age = int((utcnow() - last).total_seconds())
        stalled = age > 3 * lab.config.lab_cycle_s
        return f"{age}s since last tick" + (" (stalled)" if stalled else "")

    runtime.status_details["lab"] = describe
