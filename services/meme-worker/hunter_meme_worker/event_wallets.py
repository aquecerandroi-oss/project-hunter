"""Every wallet's flow on one mint since the subscription (T4.89) — pure,
bounded, O(1) per fill, no clock.

R73/H-010 (``.claude/state/notes-R73.md`` §2) needed "the largest cumulative
net buyer since birth" at the decision instant and could not have it: the
event lane's in-memory tape keeps 60 s, and ``meme_trades`` is a polling copy
~44 s late. This ledger is the missing sum, fed by
:meth:`~hunter_meme_worker.event_state.MintEventState.apply_trade` with the
same fills the gate reads, and read only by
:mod:`hunter_meme_worker.decision_tape` when a decision is recorded.

**The creator's buy inside the ``create`` transaction.** The subscription opens
after the create, so its own ``TradeEvent`` usually never reaches the logs
subscription; :meth:`WalletLedger.seed_initial_buy` takes it from the create
frame (``NormalizedMemeTokenCreated.creator_initial_sol/_tokens``, T4.45)
instead, keyed by the create's signature so the same fill arriving over the WS
after all is never counted twice.

**What it cannot claim, by name** (``decision_tape`` reads the flags): a
coverage gap loses fills for good (``COVERAGE_GAP``); more than
:data:`MAX_WALLETS` wallets stops adding new ones, so a maximum is partial
(``WALLETS_OVERFLOW``); a fill without a token amount makes every token sum
unknown — never a zero (``TOKENS_UNKNOWN``). "Since birth" is not a flag here:
``decision_tape`` asks the curve (Σ net SOL of every wallet against the
curve's real SOL) instead of trusting the subscription's timing. Transfers
between wallets are not fills: a token sum is the net *traded* here, not a
balance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.models import NormalizedCurveTrade

__all__ = [
    "COVERAGE_GAP",
    "MAX_WALLETS",
    "NOT_COVERED_FROM_BIRTH",
    "TOKENS_UNKNOWN",
    "WALLETS_OVERFLOW",
    "WalletFlow",
    "WalletLedger",
]

MAX_WALLETS: Final = 20000
"""The crowd ledger's own cap (``hunter_indicators.meme.crowd.MAX_WALLETS``)."""
NOT_COVERED_FROM_BIRTH: Final = "not_covered_from_birth"
COVERAGE_GAP: Final = "coverage_gap"
WALLETS_OVERFLOW: Final = "wallets_overflow"
TOKENS_UNKNOWN: Final = "tokens_unknown"


@dataclass(slots=True)
class WalletFlow:
    """Σ of one wallet's fills: raw lamports and raw token subunits. The two
    nets are fields, not properties: the leader scan reads them for every
    wallet, on the decision's path."""

    bought_lamports: int = 0
    sold_lamports: int = 0
    bought_subunits: int = 0
    sold_subunits: int = 0
    buys: int = 0
    sells: int = 0
    net_lamports: int = 0
    net_subunits: int = 0


class WalletLedger:
    """Per-mint ``wallet → WalletFlow`` since the subscription."""

    __slots__ = (
        "flows",
        "gapped",
        "net_lamports_sum",
        "newest_received",
        "overflow",
        "seed_signature",
        "tokens_missing",
    )

    def __init__(self) -> None:
        self.flows: dict[str, WalletFlow] = {}
        self.net_lamports_sum = 0
        """Σ net SOL of every wallet — the curve's real SOL when every fill
        since birth was seen (the pump curve starts at zero)."""
        self.gapped = False
        self.overflow = False
        self.tokens_missing = False
        self.newest_received: datetime | None = None
        self.seed_signature: str | None = None

    def seed_initial_buy(
        self, creator: str, *, sol: Decimal, tokens: Decimal, signature: str
    ) -> None:
        """The creator's buy inside the ``create`` transaction, from the
        create frame (SOL and whole tokens), once."""
        if self.seed_signature is not None:
            return
        self.seed_signature = signature
        flow = self._flow(creator)
        if flow is None:
            return
        self._apply(flow, "buy", int(sol.scaleb(9)), int(tokens.scaleb(6)))

    def push(self, trade: NormalizedCurveTrade) -> None:
        if self.newest_received is None or trade.received_at > self.newest_received:
            self.newest_received = trade.received_at
        if trade.signature == self.seed_signature and trade.side == "buy":
            return  # the create's own buy, already seeded from the frame
        flow = self._flow(trade.trader)
        if flow is None:
            return
        subunits = 0
        if trade.token_amount is None:
            self.tokens_missing = True
        else:
            subunits = int(trade.token_amount)
        self._apply(flow, trade.side, int(trade.lamports), subunits)

    def mark_gap(self) -> None:
        """A fill in the gap is a fill nobody summed — from here on, partial."""
        self.gapped = True

    def leaders(self) -> tuple[tuple[str, WalletFlow] | None, tuple[str, WalletFlow] | None]:
        """``(largest net SOL buyer, largest net token buyer)`` in one pass,
        each ``None`` when no wallet is a net buyer by that measure; a tie goes
        to the wallet seen first."""
        by_sol: tuple[str, WalletFlow] | None = None
        by_tokens: tuple[str, WalletFlow] | None = None
        top_sol = top_tokens = 0
        for wallet, flow in self.flows.items():
            if flow.net_lamports > top_sol:
                top_sol, by_sol = flow.net_lamports, (wallet, flow)
            if flow.net_subunits > top_tokens:
                top_tokens, by_tokens = flow.net_subunits, (wallet, flow)
        return by_sol, by_tokens

    def _flow(self, wallet: str) -> WalletFlow | None:
        flow = self.flows.get(wallet)
        if flow is None:
            if len(self.flows) >= MAX_WALLETS:
                self.overflow = True
                return None
            flow = self.flows[wallet] = WalletFlow()
        return flow

    def _apply(self, flow: WalletFlow, side: str, lamports: int, subunits: int) -> None:
        if side == "buy":
            flow.bought_lamports += lamports
            flow.bought_subunits += subunits
            flow.buys += 1
        else:
            flow.sold_lamports += lamports
            flow.sold_subunits += subunits
            flow.sells += 1
            lamports, subunits = -lamports, -subunits
        flow.net_lamports += lamports
        flow.net_subunits += subunits
        self.net_lamports_sum += lamports
