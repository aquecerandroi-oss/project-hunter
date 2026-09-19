"""What the launch lane's loops share (T4.67a): one watch per mint the gate
has already approved, and the one object every loop reads from and writes to
— the same shape ``event_gate_runtime.py`` settled on, split out for the
350-line budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hunter_meme_worker.launch_lane_stats import LaunchLaneStats
from hunter_meme_worker.launch_lane_symbols import RecentSymbols

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.event_gate_runtime import SolanaWs
    from hunter_meme_worker.event_state import MintEventState
    from hunter_meme_worker.lab_models import BetEntry
    from hunter_meme_worker.launch_lane_config import LaunchLaneConfig
    from hunter_meme_worker.launch_lane_repo import LaunchRuleSpec

__all__ = ["LaunchLaneRuntime", "LaunchWatch"]


@dataclass(slots=True)
class LaunchWatch:
    """One mint the gate approved and the lane is now pricing."""

    mint: str
    spec: LaunchRuleSpec
    proposal_id: str
    rule_set_id: str
    created_at: datetime
    creation_buyers: frozenset[str]
    initial_real_token_reserves: Decimal | None
    logs_id: int
    account_id: int
    state: MintEventState
    entered: bool = False
    bet_id: str | None = None
    entry: BetEntry | None = None
    closed: bool = False


@dataclass
class LaunchLaneRuntime:
    """Everything the loops share — one object a test builds and reads back."""

    config: LaunchLaneConfig
    ws: SolanaWs
    session_factory: async_sessionmaker[AsyncSession]
    wake: Callable[[], Awaitable[None]] | None = None
    heartbeat: Callable[[dict[str, str]], Awaitable[None]] | None = None
    recent_symbols: RecentSymbols = field(default_factory=RecentSymbols)
    specs: tuple[LaunchRuleSpec, ...] = ()
    watches: dict[str, LaunchWatch] = field(default_factory=dict[str, "LaunchWatch"])
    subs_by_logical: dict[int, str] = field(default_factory=dict[int, str])
    stats: LaunchLaneStats = field(default_factory=LaunchLaneStats)
