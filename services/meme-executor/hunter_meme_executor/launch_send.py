"""T4.67b — the prebuilt send of the launch lane: a blockhash already in hand,
a priority fee with the launch's own floor, a submit policy that may skip the
executor's simulation.

The buy of a launch is a race against the block after the ``create``. Three
things are taken off its critical path here: the ``getLatestBlockhash`` round
trip (``BlockhashCache``, refreshed every :data:`BLOCKHASH_REFRESH_S` by the
launch loop and the kill-switch tick — never fetched while a buy is being
built, unless the cache is *unusable*, which is fetched and counted), the
priority-fee read (the T4.55 reader's cached p75 raised to the launch floor —
:func:`launch_priority_fee`, pure), and optionally the ``simulateTransaction``
before signing (``SubmitPolicy.skip_simulation``; the node's preflight stays).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from hunter_core.execution.meme.submit import SubmitPolicy
from hunter_core.logging import get_logger
from hunter_meme_executor.launch_config import BLOCKHASH_REFRESH_S, LaunchConfig
from hunter_meme_executor.priority_fee import PriorityFeeChoice, cap_micro_lamports

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.tx_rpc import SolanaTxRpcClient
    from hunter_meme_executor.config import ExecutorConfig

__all__ = [
    "BLOCKHASH_MAX_AGE_S",
    "BlockhashCache",
    "BlockhashSource",
    "CachedBlockhash",
    "launch_priority_fee",
    "launch_submit_policy",
]

logger = get_logger(__name__)

BLOCKHASH_MAX_AGE_S = 30.0
"""Older than this the cached blockhash is not used for a signature: a blockhash
lives ~60 s (150 slots) and a buy signed at the edge of it would expire before
the re-send loop could land it. The buy then fetches one (counted as
``launch_blockhash_fetched_on_path``) instead of signing against a stale one."""


class BlockhashSource(Protocol):
    """What the cache reads from — ``ChainReader.blockhash`` (a fake in tests)."""

    def blockhash(self) -> tuple[str, int]: ...


@dataclass(frozen=True, slots=True)
class CachedBlockhash:
    blockhash: str
    last_valid_block_height: int
    fetched_at: datetime

    def age_s(self, now: datetime) -> float:
        return (now - self.fetched_at).total_seconds()


@dataclass(slots=True)
class BlockhashCache:
    """One blockhash per process, refreshed off the critical path."""

    value: CachedBlockhash | None = None
    refreshes: int = 0
    refresh_failures: int = 0
    fetched_on_path: int = 0
    """Buys that found the cache unusable and paid the round trip themselves."""

    def is_fresh(self, now: datetime, *, max_age_s: float = BLOCKHASH_REFRESH_S) -> bool:
        return self.value is not None and self.value.age_s(now) < max_age_s

    def usable(self, now: datetime) -> CachedBlockhash | None:
        """The cached value if younger than :data:`BLOCKHASH_MAX_AGE_S`, else ``None``."""
        if self.value is None or self.value.age_s(now) >= BLOCKHASH_MAX_AGE_S:
            return None
        return self.value

    def refresh(self, chain: BlockhashSource, *, now: datetime) -> CachedBlockhash | None:
        """Fetch and store; a failure keeps the previous value (aging, visible
        in the heartbeat) and is counted — never raises out of a tick."""
        try:
            blockhash, last_valid = chain.blockhash()
        except Exception as exc:
            self.refresh_failures += 1
            logger.warning("meme_launch_blockhash_refresh_failed", error_type=type(exc).__name__)
            return self.value
        self.value = CachedBlockhash(blockhash, last_valid, now)
        self.refreshes += 1
        return self.value

    def refresh_if_stale(self, chain: BlockhashSource, *, now: datetime) -> None:
        if not self.is_fresh(now):
            self.refresh(chain, now=now)

    def for_signing(self, chain: BlockhashSource, *, now: datetime) -> CachedBlockhash | None:
        """What the buy signs against: the cache when usable; else one fetch on the
        path (counted). ``None`` only when that fetch failed too."""
        cached = self.usable(now)
        if cached is not None:
            return cached
        self.fetched_on_path += 1
        return self.refresh(chain, now=now)

    def describe(self, now: datetime) -> dict[str, str]:
        age = "" if self.value is None else f"{self.value.age_s(now):.1f}"
        return {
            "launch_blockhash_age_s": age,
            "launch_blockhash_refreshes": str(self.refreshes),
            "launch_blockhash_refresh_failures": str(self.refresh_failures),
            "launch_blockhash_fetched_on_path": str(self.fetched_on_path),
        }


def launch_priority_fee(
    choice: PriorityFeeChoice, *, launch_floor: int, max_sol: Decimal, compute_unit_limit: int
) -> PriorityFeeChoice:
    """Pure: ``min(max(p75, launch_floor), cap)`` — the T4.55 choice (already
    ``max(p75, floor)``, capped) raised to the launch's floor and capped again
    by ``MEME_PRIORITY_FEE_MAX_SOL``. The source names which bound won:
    ``launch_floor`` when the floor lifted the price, ``cap`` when the cap held
    it, else the reader's own source (``p75``, ``floor:…``)."""
    cap = cap_micro_lamports(max_sol, compute_unit_limit)
    lifted = max(choice.micro_lamports, launch_floor)
    if lifted >= cap:
        return replace(
            choice,
            micro_lamports=cap,
            source="cap",
            floor_micro_lamports=launch_floor,
            cap_micro_lamports=cap,
        )
    source = "launch_floor" if lifted > choice.micro_lamports else choice.source
    return replace(
        choice,
        micro_lamports=lifted,
        source=source,
        floor_micro_lamports=launch_floor,
        cap_micro_lamports=cap,
    )


def launch_submit_policy(
    cfg: ExecutorConfig, launch: LaunchConfig, rpc: SolanaTxRpcClient
) -> SubmitPolicy:
    """The entries' policy with a 0,5 s confirmation poll (a 6 s position cannot
    wait a full second to learn it exists) and the owner's simulation choice."""
    return SubmitPolicy(
        allow_send=cfg.live and rpc.allow_send,
        cluster=cfg.cluster,
        confirm_timeout_s=cfg.confirm_timeout_s,
        poll_interval_s=0.5,
        resend_interval_s=cfg.send.resend_interval_s,
        skip_simulation=launch.skip_simulation,
    )
