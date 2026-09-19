"""``main.py``'s own launch-lane glue (T4.67a), split out for the 350-line
budget — the same shape ``event_gate_wiring.py`` settled on. The lane reads
the event gate's own resolved WS URL/commitment (``solana_rpc_ws_url``/
``event_gate_commitment``) so one provider and one commitment policy serve
both, whether or not the event gate itself is enabled.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_exchanges.pumpfun.rpc_ws import SolanaWsClient
from hunter_meme_worker.event_gate_config import event_gate_commitment, solana_rpc_ws_url
from hunter_meme_worker.launch_lane_config import load_launch_lane_config
from hunter_meme_worker.launch_lane_runtime import LaunchLaneRuntime

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime

__all__ = ["build_launch_lane", "register_launch_lane_health"]


def build_launch_lane(
    session_factory: async_sessionmaker[AsyncSession],
    wake: Callable[[], Awaitable[None]],
    heartbeat: Callable[[dict[str, str]], Awaitable[None]],
) -> LaunchLaneRuntime | None:
    """``None`` when ``MEME_LAUNCH_LANE=off`` — no subscription opens, no
    proposal is ever written by this lane."""
    config = load_launch_lane_config(ws_url=solana_rpc_ws_url(), commitment=event_gate_commitment())
    if not config.enabled:
        return None
    return LaunchLaneRuntime(
        config=config,
        ws=SolanaWsClient(url=config.ws_url),
        session_factory=session_factory,
        wake=wake,
        heartbeat=heartbeat,
    )


def register_launch_lane_health(runtime: WorkerRuntime, lane: LaunchLaneRuntime | None) -> None:
    """Same discipline as ``register_event_gate_health``: a degraded launch
    lane is a detail, never a red ``/ready``."""
    if lane is None:
        runtime.status_details["launch_lane"] = lambda: "disabled (MEME_LAUNCH_LANE=off)"
        return

    def describe() -> str:
        stats = lane.stats
        return (
            f"{lane.config.mode} watches={len(lane.watches)} "
            f"proposals={stats.proposals_total} paper_open={stats.paper_open} "
            f"paper_closed={stats.paper_closed_total}"
        )

    runtime.status_details["launch_lane"] = describe
