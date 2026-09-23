"""Sell absorption — EXP-M22's per-mint state machine (T4.79,
``obsidian/05-EXPERIMENTS/EXP-M22-absorcao-de-venda.md``): pure, bounded,
no I/O, no clock — every instant is an argument, every number a ``Decimal``.

The hypothesis (Astra, 20/09/2026, over R62/R64): a sell ≥ 5 % of the
curve's real SOL is the trigger that precedes the dumps (KB-0143), but alone
it does not tell a dump from a shake-out — **who absorbs it does**. So:

1. **sell seen** — the first ``sell`` whose ``sol`` (what leaves the curve,
   before fees) is ≥ :data:`DEFAULT_SELL_SHARE` of the **pre-sell** real
   reserve (``real_post + sol``). The pre-sell price is derived from the
   same event (``(v_sol_post + sol) / (v_tok_post − tokens)``), so neither
   depends on the previous trade nor on coverage;
2. **recovered** — the first later trade (either side) whose post price is
   ≥ that level, no later than :data:`DEFAULT_RECOVERY_WINDOW_S` after the
   sell; later than that the episode is ``recovery_late``;
3. **confirmed** — :data:`DEFAULT_HOLD_S` after the recovery with no trade
   below the level (silence moves no price, so it counts as holding); a dip
   before that undoes the recovery (it may recover again inside the window).
   ``confirmed_at`` is computed (``recovered_at + hold``), never observed —
   the gate reads at ``as_of``; it lives :data:`DEFAULT_CONFIRM_TTL_S`.

**Second large sell.** Before the confirmation it **restarts** the episode
at that sell (the first was not absorbed); after it, it **ends** the mint's
episode (``second_sell_after_confirm``): one confirmed episode per mint,
ever. The control arm's anchor (``sell_seen``) is the **first** large sell
only, for :data:`DEFAULT_SELL_SEEN_TTL_S`, regardless of restarts.

**Fail closed.** A coverage gap (``mark_gap``) makes both readings ``None``
(``coverage_gap``) for the rest of the mint's life — a sell in the gap is a
sell nobody counted. A sell without a token amount falls back to the last
post-trade price as its level; a drained curve (zero virtual tokens) is not
a price. Reads are meant at-or-after the newest push (the gate's ``now``);
a read before the first sell's ``received_at`` sees no sell.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING, Final

from hunter_exchanges.pumpfun.curve import raw_lamports_to_sol

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.models import NormalizedCurveTrade

__all__ = [
    "ABSORB_REASONS",
    "CONFIRMATION_EXPIRED",
    "COVERAGE_GAP",
    "DEFAULT_CONFIRM_TTL_S",
    "DEFAULT_HOLD_S",
    "DEFAULT_RECOVERY_WINDOW_S",
    "DEFAULT_SELL_SEEN_TTL_S",
    "DEFAULT_SELL_SHARE",
    "HOLDING",
    "NO_LARGE_SELL",
    "PRICE_UNKNOWN",
    "RECOVERING",
    "RECOVERY_LATE",
    "SECOND_SELL_AFTER_CONFIRM",
    "AbsorbFeatures",
    "AbsorbTracker",
    "AbsorbTrade",
]

DEFAULT_SELL_SHARE: Final = Decimal("0.05")
DEFAULT_RECOVERY_WINDOW_S: Final = 30
DEFAULT_HOLD_S: Final = 10
DEFAULT_SELL_SEEN_TTL_S: Final = 30
DEFAULT_CONFIRM_TTL_S: Final = 60
"""EXP-M22's frozen numbers (no grid): 5 % of the pre-sell real reserve, back
at the level within 30 s, held 10 s; the control's window equals the
recovery window; a confirmation is good for 60 s."""

NO_LARGE_SELL: Final = "no_large_sell"
COVERAGE_GAP: Final = "coverage_gap"
PRICE_UNKNOWN: Final = "price_unknown"
RECOVERING: Final = "recovering"
HOLDING: Final = "holding"
RECOVERY_LATE: Final = "recovery_late"
CONFIRMATION_EXPIRED: Final = "confirmation_expired"
SECOND_SELL_AFTER_CONFIRM: Final = "second_sell_after_confirm"
ABSORB_REASONS: Final = frozenset({
    NO_LARGE_SELL, COVERAGE_GAP, PRICE_UNKNOWN, RECOVERING, HOLDING,
    RECOVERY_LATE, CONFIRMATION_EXPIRED, SECOND_SELL_AFTER_CONFIRM,
})  # fmt: skip
"""Why ``confirmed`` is not ``True`` (``None`` on both readings only for
``coverage_gap``); ``sell_seen`` past its window needs no name — ``sell_at``
says when."""

_FRACTION = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class AbsorbTrade:
    """One fill as the tracker reads it: ``sol`` in SOL (what crossed the
    curve, before fees), ``tokens`` in the event's own subunits (``None`` when
    the source lacks the field), post-trade reserves in human units."""

    block_time: datetime
    received_at: datetime
    side: str
    sol: Decimal
    tokens: Decimal | None
    virtual_sol: Decimal
    virtual_token: Decimal
    real_sol: Decimal

    @classmethod
    def from_curve_trade(cls, trade: NormalizedCurveTrade, *, block_time: datetime) -> AbsorbTrade:
        return cls(
            block_time=block_time,
            received_at=trade.received_at,
            side=trade.side,
            sol=raw_lamports_to_sol(int(trade.lamports)),
            tokens=trade.token_amount,
            virtual_sol=trade.virtual_sol_reserves,
            virtual_token=trade.virtual_token_reserves,
            real_sol=trade.real_sol_reserves,
        )


@dataclass(frozen=True, slots=True)
class AbsorbFeatures:
    """The two readings at one instant, with their timestamps; ``None`` on
    both only when the coverage cannot answer (``coverage_gap``)."""

    sell_seen: bool | None
    confirmed: bool | None
    sell_at: datetime | None
    """The first large sell (the control's anchor)."""
    reference_sell_at: datetime | None
    """The sell the current episode measures against (moves on a restart)."""
    sell_share: Decimal | None
    recovered_at: datetime | None
    confirmed_at: datetime | None
    sells_seen: int
    reason: str | None


class AbsorbTracker:
    """Per-mint memory of one absorption episode; O(1) per push."""

    __slots__ = (
        "_first_received_at",
        "_last_price",
        "confirm_ttl_s",
        "first_sell_at",
        "gapped",
        "hold_s",
        "pre_price",
        "recovered_at",
        "recovery_window_s",
        "sell_at",
        "sell_seen_ttl_s",
        "sell_share",
        "sell_share_min",
        "sells_seen",
        "spent_reason",
    )

    def __init__(
        self,
        *,
        sell_share_min: Decimal = DEFAULT_SELL_SHARE,
        recovery_window_s: int = DEFAULT_RECOVERY_WINDOW_S,
        hold_s: int = DEFAULT_HOLD_S,
        sell_seen_ttl_s: int = DEFAULT_SELL_SEEN_TTL_S,
        confirm_ttl_s: int = DEFAULT_CONFIRM_TTL_S,
    ) -> None:
        if (
            sell_share_min <= 0
            or min(recovery_window_s, hold_s, sell_seen_ttl_s, confirm_ttl_s) <= 0
        ):
            raise ValueError("the share and every window are positive")
        self.sell_share_min = sell_share_min
        self.recovery_window_s = recovery_window_s
        self.hold_s = hold_s
        self.sell_seen_ttl_s = sell_seen_ttl_s
        self.confirm_ttl_s = confirm_ttl_s
        self.gapped = False
        self.sells_seen = 0
        self.first_sell_at: datetime | None = None
        self._first_received_at: datetime | None = None
        self.sell_at: datetime | None = None
        self.sell_share: Decimal | None = None
        self.pre_price: Decimal | None = None
        self.recovered_at: datetime | None = None
        self.spent_reason: str | None = None
        self._last_price: Decimal | None = None

    # -- feeding ---------------------------------------------------------

    def push(self, trade: AbsorbTrade) -> None:
        if self.gapped or trade.virtual_token <= 0 or trade.virtual_sol <= 0:
            return  # a gap answers nothing; a drained curve is not a price
        price = trade.virtual_sol / trade.virtual_token
        share = self._large_share(trade)
        if share is not None:
            self._on_large_sell(trade, share)
        elif self.pre_price is not None and self.spent_reason is None:
            self._fold(price, trade.block_time)
        self._last_price = price

    def mark_gap(self, at: datetime) -> None:
        """A dropped frame or a reconnect: a sell in the gap is a sell nobody
        counted, so nothing about this mint can be answered from here on."""
        self.gapped = True

    def _large_share(self, trade: AbsorbTrade) -> Decimal | None:
        if trade.side != "sell" or trade.sol <= 0:
            return None
        pre_real = trade.real_sol + trade.sol
        if pre_real <= 0:
            return None
        share = (trade.sol / pre_real).quantize(_FRACTION, ROUND_HALF_EVEN)
        return share if share >= self.sell_share_min else None

    def _on_large_sell(self, trade: AbsorbTrade, share: Decimal) -> None:
        self.sells_seen += 1
        if self.first_sell_at is None:
            self.first_sell_at, self._first_received_at = trade.block_time, trade.received_at
        if self.spent_reason is not None:
            return
        if self._confirmed_by(trade.block_time) is not None:
            self.spent_reason = SECOND_SELL_AFTER_CONFIRM  # one confirmed episode per mint
            return
        self.sell_at, self.sell_share, self.recovered_at = trade.block_time, share, None
        self.pre_price = self._pre_sell_price(trade)

    def _pre_sell_price(self, trade: AbsorbTrade) -> Decimal | None:
        if trade.tokens is None:
            return self._last_price
        pre_tokens = trade.virtual_token - trade.tokens
        if pre_tokens <= 0:
            return self._last_price
        return (trade.virtual_sol + trade.sol) / pre_tokens

    def _fold(self, price: Decimal, at: datetime) -> None:
        assert self.pre_price is not None and self.sell_at is not None
        if self.recovered_at is None:
            if price >= self.pre_price and at - self.sell_at <= timedelta(
                seconds=self.recovery_window_s
            ):
                self.recovered_at = at
        elif price < self.pre_price and at < self.recovered_at + timedelta(seconds=self.hold_s):
            self.recovered_at = None  # the hold broke; it may recover again inside the window

    def _confirmed_by(self, as_of: datetime) -> datetime | None:
        if self.recovered_at is None:
            return None
        confirmed_at = self.recovered_at + timedelta(seconds=self.hold_s)
        return confirmed_at if as_of >= confirmed_at else None

    # -- reading ---------------------------------------------------------

    def features(self, as_of: datetime) -> AbsorbFeatures:
        if self.gapped:
            return self._features(as_of, None, None, COVERAGE_GAP)
        if self.first_sell_at is None or (
            self._first_received_at is not None and self._first_received_at > as_of
        ):
            return AbsorbFeatures(False, False, None, None, None, None, None, 0, NO_LARGE_SELL)
        sell_seen = as_of - self.first_sell_at <= timedelta(seconds=self.sell_seen_ttl_s)
        confirmed, reason = self._confirmation(as_of)
        return self._features(as_of, sell_seen, confirmed, reason)

    def _confirmation(self, as_of: datetime) -> tuple[bool, str | None]:
        if self.spent_reason is not None:
            return False, self.spent_reason
        if self.pre_price is None or self.sell_at is None:
            return False, PRICE_UNKNOWN
        confirmed_at = self._confirmed_by(as_of)
        if confirmed_at is not None:
            if as_of - confirmed_at <= timedelta(seconds=self.confirm_ttl_s):
                return True, None
            return False, CONFIRMATION_EXPIRED
        if self.recovered_at is not None:
            return False, HOLDING
        if as_of - self.sell_at <= timedelta(seconds=self.recovery_window_s):
            return False, RECOVERING
        return False, RECOVERY_LATE

    def _features(
        self, as_of: datetime, sell_seen: bool | None, confirmed: bool | None, reason: str | None
    ) -> AbsorbFeatures:
        return AbsorbFeatures(
            sell_seen=sell_seen,
            confirmed=confirmed,
            sell_at=self.first_sell_at,
            reference_sell_at=self.sell_at,
            sell_share=self.sell_share,
            recovered_at=self.recovered_at,
            confirmed_at=None if self.spent_reason else self._confirmed_by(as_of),
            sells_seen=self.sells_seen,
            reason=reason,
        )
