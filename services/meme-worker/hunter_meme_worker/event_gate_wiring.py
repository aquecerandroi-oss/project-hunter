"""``main.py``'s own event-gate glue (T4.52b-3), split out for the 350-line
budget: build the runtime (or not, when the flag is ``off`` or the Lab is
disabled — the event gate has nothing to read without it) and register its
``/ready`` detail, the same discipline ``_register_lab_health`` already uses.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.rpc_ws import SolanaWsClient
from hunter_meme_worker.event_gate_config import load_event_gate_config
from hunter_meme_worker.event_gate_runtime import EventGateRuntime

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from hunter_core.runtime import WorkerRuntime
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.event_gate_config import EventGateConfig
    from hunter_meme_worker.lab import LabContext

logger = get_logger(__name__)

__all__ = ["build_event_gate", "load_event_gate_config", "register_event_gate_health"]


def build_event_gate(
    runtime: WorkerRuntime,
    ctx: RadarContext,
    lab: LabContext | None,
    config: EventGateConfig,
    heartbeat: Callable[[dict[str, str]], Awaitable[None]],
) -> EventGateRuntime | None:
    """``None`` when the flag is ``off``, or when the Lab is disabled (its
    caches are the event gate's only input — plan-T4.52b.md §4 (iv))."""
    if not config.enabled:
        return None
    if lab is None:
        logger.warning("meme_event_gate_disabled", reason="MEME_LAB_ENABLED is false")
        return None
    return EventGateRuntime(
        radar=ctx,
        lab=lab,
        ws=SolanaWsClient(url=config.ws_url),
        config=config,
        heartbeat=heartbeat,
    )


def register_event_gate_health(runtime: WorkerRuntime, gate: EventGateRuntime | None) -> None:
    """Same discipline as ``_register_lab_health``: a degraded event gate is a
    detail, never a red ``/ready`` (plan §4, "``/ready`` não fica vermelho")."""
    if gate is None:
        runtime.status_details["event_gate"] = lambda: "disabled (MEME_EVENT_GATE=off)"
        return

    def describe() -> str:
        stats = gate.stats
        age = "" if stats.last_event_at is None else f", last event {_age_s(stats.last_event_at)}s"
        return (
            f"{gate.config.mode} ws={stats.ws_state} subs={stats.subscriptions} "
            f"reconnects={stats.reconnects}{age}"
        )

    runtime.status_details["event_gate"] = describe


def _age_s(at: datetime) -> int:
    return int((utcnow() - at).total_seconds())
