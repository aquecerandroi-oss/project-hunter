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

**T4.89b (H-015): the creation-slot bundle.** ``push`` also sums, past the 60 s
tape window, the SOL bought in the mint's own creation slot (``create_slot``,
``event_state.MintEventState.crowd.create_slot``, T4.70) by wallets other than
the creator, and how many of them — ``creation_block_lamports``/
``creation_block_wallets``, read by
:func:`hunter_meme_worker.decision_tape_creation.creation_bundle_json`. The
creator's own buy in that same slot is a fact of the ``create`` frame, not of
the subscription's coverage: :meth:`seed_initial_buy` records it once
(``creator_initial_buy_lamports``), independent of ``push``.

**``crowd.create_slot`` is inferred, not proven** (Astra, T4.89b review): it is
the slot of the *first trade the subscription received*, which is not always
the slot of the ``create`` transaction itself (the create frame carries no
slot at all). Rather than call an RPC on this hot path to prove it,
:data:`EARLY_SLOTS_MAX` distinct slots are kept as they are first seen
(``early_slots``, each with its own ``sol_others``/``wallets_others``/
``creator_sol``) so research can resolve the true creation slot later, out of
band, from :attr:`WalletLedger.create_signature` (recorded by
:meth:`record_create_signature`, unconditionally — independent of whether the
create frame also carried an initial buy) and read the matching entry instead
of trusting the inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.models import NormalizedCurveTrade

__all__ = [
    "COVERAGE_GAP",
    "EARLY_SLOTS_MAX",
    "MAX_WALLETS",
    "NOT_COVERED_FROM_BIRTH",
    "TOKENS_UNKNOWN",
    "WALLETS_OVERFLOW",
    "EarlySlot",
    "WalletFlow",
    "WalletLedger",
]

MAX_WALLETS: Final = 20000
"""The crowd ledger's own cap (``hunter_indicators.meme.crowd.MAX_WALLETS``)."""
NOT_COVERED_FROM_BIRTH: Final = "not_covered_from_birth"
COVERAGE_GAP: Final = "coverage_gap"
WALLETS_OVERFLOW: Final = "wallets_overflow"
TOKENS_UNKNOWN: Final = "tokens_unknown"
EARLY_SLOTS_MAX: Final = 5


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


@dataclass(slots=True)
class EarlySlot:
    """T4.89b (H-015): one of the first :data:`EARLY_SLOTS_MAX` distinct slots
    ``push`` saw a buy in — raw evidence for research to align, later, with
    whichever slot the create transaction really landed in."""

    slot: int
    sol_others: int = 0
    wallets_others: set[str] = field(default_factory=set[str])
    creator_sol: int = 0


class WalletLedger:
    """Per-mint ``wallet → WalletFlow`` since the subscription."""

    __slots__ = (
        "create_signature",
        "creation_block_lamports",
        "creation_block_wallets",
        "creator_initial_buy_lamports",
        "early_slots",
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
        self.creator_initial_buy_lamports: int | None = None
        """T4.89b: the creator's own buy inside the ``create`` transaction, in
        raw lamports — set once by :meth:`seed_initial_buy`, never by ``push``."""
        self.creation_block_lamports = 0
        """T4.89b: Σ raw lamports bought in the creation slot by every wallet
        but the creator (H-015's ``sol_no_slot_de_criacao``)."""
        self.creation_block_wallets: set[str] = set()
        """T4.89b: the distinct non-creator wallets that bought in that slot."""
        self.create_signature: str | None = None
        """T4.89b: the create transaction's own signature, set unconditionally
        by :meth:`record_create_signature` — independent of whether the frame
        also carried an initial buy, so research can resolve its real slot."""
        self.early_slots: dict[int, EarlySlot] = {}
        """T4.89b: the first :data:`EARLY_SLOTS_MAX` distinct slots a buy was
        seen in, insertion order (:meth:`push`)."""

    def seed_initial_buy(
        self, creator: str, *, sol: Decimal, tokens: Decimal, signature: str
    ) -> None:
        """The creator's buy inside the ``create`` transaction, from the
        create frame (SOL and whole tokens), once."""
        if self.seed_signature is not None:
            return
        self.seed_signature = signature
        lamports = int(sol.scaleb(9))
        self.creator_initial_buy_lamports = lamports
        flow = self._flow(creator)
        if flow is None:
            return
        self._apply(flow, "buy", lamports, int(tokens.scaleb(6)))

    def record_create_signature(self, signature: str) -> None:
        """The create transaction's signature, whether or not it also carried
        an initial buy — called once, from ``subscribe_at_create``."""
        self.create_signature = signature

    def push(
        self,
        trade: NormalizedCurveTrade,
        *,
        create_slot: int | None = None,
        creator: str | None = None,
    ) -> None:
        if self.newest_received is None or trade.received_at > self.newest_received:
            self.newest_received = trade.received_at
        if trade.signature == self.seed_signature and trade.side == "buy":
            return  # the create's own buy, already seeded from the frame
        if trade.side == "buy":
            self._push_early_slot(trade, creator=creator)
        if (
            create_slot is not None
            and trade.slot == create_slot
            and trade.side == "buy"
            and trade.trader != creator
        ):
            self.creation_block_lamports += int(trade.lamports)
            self._bounded_add(self.creation_block_wallets, trade.trader)
        flow = self._flow(trade.trader)
        if flow is None:
            return
        subunits = 0
        if trade.token_amount is None:
            self.tokens_missing = True
        else:
            subunits = int(trade.token_amount)
        self._apply(flow, trade.side, int(trade.lamports), subunits)

    def _push_early_slot(self, trade: NormalizedCurveTrade, *, creator: str | None) -> None:
        agg = self.early_slots.get(trade.slot)
        if agg is None:
            if len(self.early_slots) >= EARLY_SLOTS_MAX:
                return
            agg = self.early_slots[trade.slot] = EarlySlot(slot=trade.slot)
        if trade.trader == creator:
            agg.creator_sol += int(trade.lamports)
        else:
            agg.sol_others += int(trade.lamports)
            self._bounded_add(agg.wallets_others, trade.trader)

    def _bounded_add(self, wallets: set[str], wallet: str) -> None:
        """Astra (T4.89b round 2), MEDIUM: a wallet set fed outside ``_flow``
        must obey the same :data:`MAX_WALLETS` ceiling, or it grows past the
        ledger's own bounded-memory guarantee — physically impossible within
        one Solana slot, but never assumed. Past the cap, ``overflow`` trips
        (the same flag ``_flow`` sets), so a truncated count is never reported
        as exact: it nulls ``creation_bundle.sol``/``wallets`` too."""
        if wallet in wallets:
            return
        if len(wallets) >= MAX_WALLETS:
            self.overflow = True
            return
        wallets.add(wallet)

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
