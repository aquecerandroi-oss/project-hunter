"""The crowd behind a rise — EXP-M19's four readings of **who** buys and sells
(T4.66, ``obsidian/05-EXPERIMENTS/EXP-M19-subida-com-gente-atras.md``), as a
pure, bounded ledger fed one fill at a time and folded at an instant.

The hypothesis: the rise that pays has new wallets coming in and the first
buyers (the snipers of blocks 1–3) **holding**; the one that does not is a
distribution — the first buyers selling to whoever arrives. Four numbers:

- ``early_retention_pct`` — of the tokens the early wallets bought, the
  fraction they still hold (``Σ max(bought − sold, 0) / Σ bought``, per wallet
  clamped at zero: a wallet that sold more than it bought here was fed by a
  transfer this ledger never saw, and that excess is not "negative holding");
- ``early_age_s`` — seconds since the earliest early buy;
- ``new_wallets_30s`` — distinct traders whose first trade on the mint fell
  in the last 30 s;
- ``quick_flip_share_30s`` — of the trades of the last 30 s, the share that
  are sells by a wallet whose first buy was less than 20 s earlier.

**Who is early.** Buyers (never the creator — its flow is the creator
criterion's) in the first :data:`DEFAULT_EARLY_SLOTS` slots counted from the
create slot when that slot is known, else the first :data:`DEFAULT_EARLY_BUYERS`
distinct buyers in arrival order. Either way the set is only meaningful when
the feed covered the mint from birth (``covered_from_birth``): a subscription
that began later saw a *later* ten, and the fold answers ``None``
(``not_covered_from_birth``) rather than a number about the wrong wallets.

**Fail closed, by name.** Every ``None`` carries a reason
(:data:`CROWD_REASONS`): the window not yet covered (``covered_since``), a
coverage gap (the early wallets' sells in the gap are unknowable, so their
retention is), a fill without a token amount, no early wallet seen yet, no
trade in the window (a share of zero trades), or more distinct wallets than
the ledger keeps (:data:`MAX_WALLETS`).

**Non-anticipation.** Every fill carries ``received_at``; the fold at
``as_of`` ignores what reached us later. Cost per fold: O(n) over the
bounded window deque and the early wallets' own fills, O(1) per ``push``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final

from hunter_core.domain.enums import FeatureCategory
from hunter_indicators.features.definitions import FeatureDefinition

__all__ = [
    "COVERAGE_GAP",
    "CROWD_DEFINITIONS",
    "CROWD_REASONS",
    "DEFAULT_EARLY_BUYERS",
    "DEFAULT_EARLY_SLOTS",
    "DEFAULT_QUICK_FLIP_S",
    "DEFAULT_WINDOW_S",
    "NOT_COVERED_FROM_BIRTH",
    "NO_EARLY_WALLETS",
    "NO_TRADES_IN_WINDOW",
    "TOKENS_UNKNOWN",
    "WALLETS_OVERFLOW",
    "WINDOW_NOT_COVERED",
    "CrowdFeatures",
    "CrowdLedger",
    "CrowdTrade",
]

DEFAULT_WINDOW_S: Final = 30
DEFAULT_QUICK_FLIP_S: Final = 20
DEFAULT_EARLY_SLOTS: Final = 3
DEFAULT_EARLY_BUYERS: Final = 10
"""EXP-M19's frozen numbers: the 30 s window, "quick" = bought < 20 s before
selling, blocks 1–3 (the create's slot and the two after it), ten buyers."""
MAX_RECENT: Final = 4000
MAX_EARLY_FILLS: Final = 2000
MAX_WALLETS: Final = 20000
"""Hard caps behind the time window: overflowing is a named unknown, never
a silent undercount."""

NOT_COVERED_FROM_BIRTH: Final = "not_covered_from_birth"
NO_EARLY_WALLETS: Final = "no_early_wallets"
TOKENS_UNKNOWN: Final = "tokens_unknown"
COVERAGE_GAP: Final = "coverage_gap"
WINDOW_NOT_COVERED: Final = "window_not_covered"
NO_TRADES_IN_WINDOW: Final = "no_trades_in_window"
WALLETS_OVERFLOW: Final = "wallets_overflow"
CROWD_REASONS: Final = frozenset({
    NOT_COVERED_FROM_BIRTH, NO_EARLY_WALLETS, TOKENS_UNKNOWN, COVERAGE_GAP,
    WINDOW_NOT_COVERED, NO_TRADES_IN_WINDOW, WALLETS_OVERFLOW,
})  # fmt: skip

_FRACTION = Decimal("0.000001")
_SECONDS = Decimal("0.001")
_ZERO = Decimal(0)

_INPUTS: Final = (
    "solana_rpc_ws.trade_event.user",
    "solana_rpc_ws.trade_event.is_buy",
    "solana_rpc_ws.trade_event.token_amount",
    "solana_rpc_ws.trade_event.timestamp",
    "solana_rpc_ws.notification.slot",
)
_EARLY_PARAMS: Final = {"early_slots": DEFAULT_EARLY_SLOTS, "early_buyers": DEFAULT_EARLY_BUYERS}
CROWD_DEFINITIONS: Final = (
    FeatureDefinition(
        key="early_retention_pct",
        version=1,
        category=FeatureCategory.MICROSTRUCTURE,
        inputs=_INPUTS,
        description=(
            "Σ max(bought − sold, 0) / Σ bought over the early wallets (buyers of the first "
            "3 slots, or the first 10 buyers when the slot is unknown; never the creator); "
            "unknown unless the feed covered the mint from birth (EXP-M19)."
        ),
        params=_EARLY_PARAMS,
    ),
    FeatureDefinition(
        key="early_age_s",
        version=1,
        category=FeatureCategory.MICROSTRUCTURE,
        inputs=_INPUTS,
        description="Seconds since the earliest early buy (EXP-M19).",
        params=_EARLY_PARAMS,
    ),
    FeatureDefinition(
        key="new_wallets_30s",
        version=1,
        category=FeatureCategory.MICROSTRUCTURE,
        inputs=_INPUTS,
        description=(
            "Distinct traders whose first trade on the mint fell in the last window_s; "
            "unknown while the feed has not covered the whole window (EXP-M19)."
        ),
        params={"window_s": DEFAULT_WINDOW_S},
    ),
    FeatureDefinition(
        key="quick_flip_share_30s",
        version=1,
        category=FeatureCategory.MICROSTRUCTURE,
        inputs=_INPUTS,
        description=(
            "Of the trades of the last window_s, the share that are sells by a wallet whose "
            "first buy was less than quick_flip_s earlier; unknown with no trade (EXP-M19)."
        ),
        params={"window_s": DEFAULT_WINDOW_S, "quick_flip_s": DEFAULT_QUICK_FLIP_S},
    ),
)
"""Registered as every feature is; a different window or rule is a new version."""


@dataclass(frozen=True, slots=True)
class CrowdTrade:
    """One fill as the ledger reads it. ``tokens`` is the fill's token amount
    (any unit, as long as it is the same for every fill of the mint — the
    retention is a ratio); ``None`` when the source did not say."""

    block_time: datetime
    received_at: datetime
    trader: str
    side: str
    tokens: Decimal | None
    slot: int | None = None


@dataclass(frozen=True, slots=True)
class CrowdFeatures:
    """The four readings at one instant, each ``None`` with a named reason."""

    early_retention_pct: Decimal | None
    early_age_s: Decimal | None
    new_wallets_30s: int | None
    quick_flip_share_30s: Decimal | None
    early_wallets: int
    early_reason: str | None
    window_reason: str | None


class CrowdLedger:
    """Per-mint memory of the crowd: the early wallets and their fills, every
    wallet's first trade/first buy, the last ``window_s`` of fills."""

    __slots__ = (
        "_early_fills",
        "_early_first_buy",
        "_first_buy_at",
        "_first_trade_at",
        "_newest_received",
        "_overflow",
        "_recent",
        "covered_since",
        "create_slot",
        "creator",
        "early_buyers",
        "early_slots",
        "gapped",
        "quick_flip_s",
        "window_s",
    )

    def __init__(
        self,
        *,
        covered_since: datetime,
        creator: str | None = None,
        create_slot: int | None = None,
        early_slots: int = DEFAULT_EARLY_SLOTS,
        early_buyers: int = DEFAULT_EARLY_BUYERS,
        window_s: int = DEFAULT_WINDOW_S,
        quick_flip_s: int = DEFAULT_QUICK_FLIP_S,
    ) -> None:
        if early_slots <= 0 or early_buyers <= 0 or window_s <= 0 or quick_flip_s <= 0:
            raise ValueError("early_slots, early_buyers, window_s and quick_flip_s are positive")
        self.covered_since = covered_since
        self.creator = creator
        self.create_slot = create_slot
        self.early_slots = early_slots
        self.early_buyers = early_buyers
        self.window_s = window_s
        self.quick_flip_s = quick_flip_s
        self.gapped = False
        self._early_first_buy: dict[str, datetime] = {}
        self._early_fills: deque[CrowdTrade] = deque()
        self._first_trade_at: dict[str, datetime] = {}
        self._first_buy_at: dict[str, datetime] = {}
        self._recent: deque[CrowdTrade] = deque()
        self._newest_received: datetime | None = None
        self._overflow = False

    @property
    def early_wallets(self) -> frozenset[str]:
        return frozenset(self._early_first_buy)

    # -- feeding ---------------------------------------------------------

    def push(self, trade: CrowdTrade) -> None:
        """O(1) amortized: the firsts, the early set, the window deque."""
        self._note_first(self._first_trade_at, trade)
        if trade.side == "buy":
            self._note_first(self._first_buy_at, trade)
            if trade.trader != self.creator and trade.trader not in self._early_first_buy:
                if self._admits_early(trade):
                    self._early_first_buy[trade.trader] = trade.block_time
        if trade.trader in self._early_first_buy:
            if len(self._early_fills) >= MAX_EARLY_FILLS:
                self.gapped = True  # the ledger lost a fill: retention is no longer a sum
            else:
                self._early_fills.append(trade)
        if len(self._recent) >= MAX_RECENT:
            self.mark_gap(trade.received_at)
        self._recent.append(trade)
        if self._newest_received is None or trade.received_at > self._newest_received:
            self._newest_received = trade.received_at
        horizon = self._newest_received - timedelta(seconds=self.window_s)
        while self._recent and self._recent[0].block_time <= horizon:
            self._recent.popleft()

    def mark_gap(self, at: datetime) -> None:
        """A dropped frame or a reconnect: the window warms again from ``at``
        and the early wallets' retention is unknowable from here on (a sell in
        the gap is a sell nobody counted)."""
        self.gapped = True
        self.covered_since = max(self.covered_since, at)
        self._recent.clear()

    def _admits_early(self, trade: CrowdTrade) -> bool:
        if self.create_slot is not None:
            return trade.slot is not None and 0 <= trade.slot - self.create_slot < self.early_slots
        return len(self._early_first_buy) < self.early_buyers

    def _note_first(self, firsts: dict[str, datetime], trade: CrowdTrade) -> None:
        seen = firsts.get(trade.trader)
        if seen is None:
            if len(firsts) >= MAX_WALLETS:
                self._overflow = True
                return
            firsts[trade.trader] = trade.block_time
        elif trade.block_time < seen:
            firsts[trade.trader] = trade.block_time

    # -- reading ---------------------------------------------------------

    def features(self, as_of: datetime, *, covered_from_birth: bool) -> CrowdFeatures:
        retention, age, early_reason = self._early(as_of, covered_from_birth)
        new_wallets, flips, window_reason = self._window(as_of)
        return CrowdFeatures(
            early_retention_pct=retention,
            early_age_s=age,
            new_wallets_30s=new_wallets,
            quick_flip_share_30s=flips,
            early_wallets=len(self._early_first_buy),
            early_reason=early_reason,
            window_reason=window_reason,
        )

    def _early(
        self, as_of: datetime, covered_from_birth: bool
    ) -> tuple[Decimal | None, Decimal | None, str | None]:
        if not covered_from_birth:
            return None, None, NOT_COVERED_FROM_BIRTH
        if self.gapped:
            return None, None, COVERAGE_GAP
        fills = [f for f in self._early_fills if f.received_at <= as_of]
        if not fills:
            return None, None, NO_EARLY_WALLETS
        if any(f.tokens is None for f in fills):
            return None, None, TOKENS_UNKNOWN
        bought: dict[str, Decimal] = {}
        sold: dict[str, Decimal] = {}
        first_buy: datetime | None = None
        for f in fills:
            amount = f.tokens or _ZERO
            if f.side == "buy":
                bought[f.trader] = bought.get(f.trader, _ZERO) + amount
                if first_buy is None or f.block_time < first_buy:
                    first_buy = f.block_time
            else:
                sold[f.trader] = sold.get(f.trader, _ZERO) + amount
        total = sum(bought.values(), _ZERO)
        if total <= 0 or first_buy is None:
            return None, None, NO_EARLY_WALLETS
        held = sum((max(b - sold.get(w, _ZERO), _ZERO) for w, b in bought.items()), _ZERO)
        retention = (held / total).quantize(_FRACTION, ROUND_HALF_EVEN)
        age = Decimal((as_of - first_buy).total_seconds()).quantize(_SECONDS, ROUND_HALF_EVEN)
        return retention, age, None

    def _window(self, as_of: datetime) -> tuple[int | None, Decimal | None, str | None]:
        start = as_of - timedelta(seconds=self.window_s)
        if self.covered_since > start:
            return None, None, WINDOW_NOT_COVERED
        if self._overflow:
            return None, None, WALLETS_OVERFLOW
        trades = [
            t for t in self._recent if t.received_at <= as_of and start < t.block_time <= as_of
        ]
        new_wallets = len({t.trader for t in trades if self._first_trade_at[t.trader] > start})
        if not trades:
            return new_wallets, None, NO_TRADES_IN_WINDOW
        quick = timedelta(seconds=self.quick_flip_s)
        flips = 0
        for t in trades:
            if t.side != "sell":
                continue
            first_buy = self._first_buy_at.get(t.trader)
            if first_buy is not None and timedelta(0) <= t.block_time - first_buy < quick:
                flips += 1
        share = (Decimal(flips) / Decimal(len(trades))).quantize(_FRACTION, ROUND_HALF_EVEN)
        return new_wallets, share, None
