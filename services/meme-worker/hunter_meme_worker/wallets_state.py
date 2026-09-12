"""The wallet loop's state and its wiring (T4.12): cursors per wallet, the
rolling counts the heartbeat carries, the last real trade seen — and the
builder that turns ``MEME_WATCH_WALLETS`` into a watcher with its own RPC
bucket (two requests a second on the public endpoint, beside the chain loop's).

Split from ``wallets.py`` for the 350-line budget: the loop is there, what it
remembers between cycles is here.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from hunter_exchanges.pumpfun.rpc import SolanaRpcClient
from hunter_exchanges.pumpfun.rpc_wallet import WalletRpc
from hunter_exchanges.rate_limit import TokenBucketRateLimiter
from hunter_meme_worker.sources import RollingCounter

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hunter_meme_worker.config import MemeConfig
    from hunter_meme_worker.context import WalletChainSource
    from hunter_meme_worker.sources import SourcesState

__all__ = ["WalletsWatcher", "build_wallets"]


class WalletsWatcher:
    """The loop's state: cursors, rolling counts, the last real trade seen."""

    def __init__(
        self,
        chain: WalletChainSource,
        *,
        wallets: Sequence[str],
        features_version: str,
        page: int = 100,
        sources: SourcesState | None = None,
    ) -> None:
        self.chain = chain
        self.wallets: tuple[str, ...] = tuple(wallets)
        self.features_version = features_version
        self.page = page
        self.sources = sources
        self.cursors: dict[str, str | None] = {}
        self.affected: set[tuple[str, str]] = set()
        self.trades_60s = RollingCounter(60)
        self.unknown_1h = RollingCounter(3600)
        self.errors_1h = RollingCounter(3600)
        self.calls_60s = RollingCounter(60)
        self.last_trade_at: datetime | None = None
        self.last_cycle_at: datetime | None = None
        self.last_cycle_s: float | None = None
        self.positions_open: int | None = None

    def heartbeat_fields(self, now: datetime) -> dict[str, str]:
        fields: dict[str, Any] = {
            "wallets_watched": len(self.wallets),
            "wallets_trades_60s": self.trades_60s.total(now),
            "wallets_unknown_1h": self.unknown_1h.total(now),
            "wallets_errors_1h": self.errors_1h.total(now),
            "wallets_calls_60s": self.calls_60s.total(now),
            "wallets_last_trade_at": None if self.last_trade_at is None else self.last_trade_at,
            "wallets_last_cycle_at": None if self.last_cycle_at is None else self.last_cycle_at,
            "wallets_cycle_s": self.last_cycle_s,
            "wallets_positions_open": self.positions_open,
        }
        return {
            key: ""
            if value is None
            else (value.isoformat() if isinstance(value, datetime) else str(value))
            for key, value in fields.items()
        }

    def describe(self, now: datetime) -> str:
        if self.last_cycle_at is None:
            return f"{len(self.wallets)} wallet(s), starting"
        age = int((now - self.last_cycle_at).total_seconds())
        last = (
            "no trade yet"
            if self.last_trade_at is None
            else f"last trade {self.last_trade_at.isoformat()}"
        )
        return f"{len(self.wallets)} wallet(s), {age}s since last cycle, {last}"

    async def aclose(self) -> None:
        closer = getattr(self.chain, "aclose", None)
        if closer is not None:
            await closer()


def build_wallets(config: MemeConfig, sources: SourcesState | None) -> WalletsWatcher | None:
    """``None`` without ``MEME_WATCH_WALLETS`` — no loop, and the readiness says so."""
    if not config.watch_wallets:
        return None
    chain = WalletRpc(
        SolanaRpcClient(
            rate_limiter=TokenBucketRateLimiter(
                "solana_rpc_wallets",
                capacity=max(1, config.wallets_rpc_per_s),
                refill_period_s=1.0,
            )
        )
    )
    return WalletsWatcher(
        chain,
        wallets=config.watch_wallets,
        features_version=config.features_version,
        page=config.wallets_signature_page,
        sources=sources,
    )
