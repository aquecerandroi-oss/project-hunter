"""pump.fun realtime latency probe (2026-10-06) — which NATS subjects the probe opens (pure, no IO).

The site subscribes per coin (``unifiedTradeEvent.processed.<mint>`` on a coin page,
``unifiedTradeEvent.lite.<mint>`` in lists) and per wallet (``account_balance_change.<wallet>.*``). The
probe holds a bounded set of each, like a visitor with a few tabs open — never a wildcard.
"""

from __future__ import annotations

from collections import Counter

PROCESSED = "unifiedTradeEvent.processed"
LITE = "unifiedTradeEvent.lite"
BALANCE = "account_balance_change"


class MintPlan:
    """Newly created coins, each held ``hold_s`` seconds, at most ``max_mints`` at once."""

    def __init__(self, *, max_mints: int, hold_s: float, lite_max: int) -> None:
        self.max_mints, self.hold_s, self.lite_max = max_mints, hold_s, lite_max
        self._active: dict[str, tuple[float, bool]] = {}  # mint -> (opened at, has lite)
        self.skipped = 0
        self.opened: Counter[str] = Counter()

    def is_active(self, mint: str) -> bool:
        return mint in self._active

    def on_creation(self, mint: str, *, now: float) -> list[str]:
        if mint in self._active:
            return []
        if len(self._active) >= self.max_mints:
            self.skipped += 1
            return []
        with_lite = sum(1 for _, lite in self._active.values() if lite) < self.lite_max
        self._active[mint] = (now, with_lite)
        self.opened["processed"] += 1
        subjects = [f"{PROCESSED}.{mint}"]
        if with_lite:
            self.opened["lite"] += 1
            subjects.append(f"{LITE}.{mint}")
        return subjects

    def expire(self, *, now: float) -> list[str]:
        out: list[str] = []
        for mint, (opened_at, lite) in list(self._active.items()):
            if now - opened_at > self.hold_s:
                out.append(f"{PROCESSED}.{mint}")
                if lite:
                    out.append(f"{LITE}.{mint}")
                del self._active[mint]
        return out


class WalletPlan:
    """Wallets that traded at least ``min_trades`` times in the mints being watched, held for the run."""

    def __init__(self, *, max_wallets: int, min_trades: int) -> None:
        self.max_wallets, self.min_trades = max_wallets, min_trades
        self.followed: set[str] = set()
        self._seen: Counter[str] = Counter()

    def on_trade(self, wallet: str) -> str | None:
        if wallet in self.followed or len(self.followed) >= self.max_wallets:
            return None
        self._seen[wallet] += 1
        if self._seen[wallet] < self.min_trades:
            return None
        self.followed.add(wallet)
        return f"{BALANCE}.{wallet}.*"
