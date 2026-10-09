"""NATS balance legs -> :class:`LeaderEvent` (H-037) — pure, no IO, no clock (times come in).

``account_balance_change`` carries **absolute** balances, one frame per asset (SOL, each token), so a
wallet's delta needs the previous balance: learned from the previous leg of the same (wallet, asset), or
**seeded** once per (re)connect from the chain. A seed is a complete snapshot but its reads happen at
different slots, so every entry carries its own **slot cut**: a leg at or before the cut is already
inside the snapshot and is never a delta of it (it would compare past with future), and a mint the lists
did not hold is zero only for legs *after* the newest token read. Without a baseline there is no event
(``no_baseline``): the on-chain source covers that transaction and the source announces the wallet as
unseeded.

The SOL leg of a transaction may arrive before or after its token leg, so it is **never** defaulted:

* a **sell** is emitted at once (the exit needs only the observed position), with the SOL leg if it was
  already seen and ``None`` otherwise;
* a **buy** whose SOL leg is unknown waits at most :data:`PAIR_WAIT_S` and is emitted the instant the
  SOL leg arrives (``fields_complete_at`` = that instant) or, at the deadline, with ``None``;
* a transaction with several token legs is ``multi_mint`` and carries no SOL (one debit is not N);
* tokens in with SOL not out, or tokens out with SOL not in, are labelled ``kind="transfer"`` (they
  still move the position, so they are emitted, not dropped).

``first_seen_at`` is our clock at the first leg of the transaction; ``server_ts`` the NATS server's
stamp of the token leg. A leg arriving after the event was emitted never rewrites it.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

from hunter_exchanges.pumpfun.leader_events import LeaderEvent
from hunter_exchanges.pumpfun.leader_source_nats_io import WalletSnapshot
from hunter_exchanges.pumpfun.leader_source_nats_wire import WSOL_MINT, BalanceLeg

SOL = "SOL"
PAIR_WAIT_S = 0.3
_SEED_TX = 2**62
_KEEP = 512

__all__ = ["PAIR_WAIT_S", "BalanceBook", "LegOutcome", "LegProcessor"]


class BalanceBook:
    """Last known absolute balance per (wallet, asset) with the chain order it was read at."""

    def __init__(self) -> None:
        self._held: dict[tuple[str, str], tuple[int, tuple[int, int]]] = {}
        self._cut: dict[str, int] = {}

    def is_seeded(self, wallet: str) -> bool:
        return wallet in self._cut

    def seed(self, wallet: str, snap: WalletSnapshot) -> None:
        """A complete snapshot. Never overwrites something read at a later slot."""
        entries = {SOL: (snap.sol_lamports, snap.sol_slot), **snap.tokens}
        for asset, (atoms, slot) in entries.items():
            order = (slot, _SEED_TX)
            current = self._held.get((wallet, asset))
            if current is None or current[1] < order:
                self._held[(wallet, asset)] = (atoms, order)
        for asset, (_, order) in [(k[1], v) for k, v in self._held.items() if k[0] == wallet]:
            if asset != SOL and asset not in entries and order[0] <= snap.tokens_slot:
                del self._held[(wallet, asset)]  # learned before the cut, absent from the snapshot
        self._cut[wallet] = snap.tokens_slot

    def forget(self, wallet: str) -> None:
        """Drop everything known about ``wallet`` (a reconnect missed legs: the baseline is stale)."""
        self._cut.pop(wallet, None)
        for key in [k for k in self._held if k[0] == wallet]:
            del self._held[key]

    def apply(self, leg: BalanceLeg) -> tuple[int | None, str | None]:
        """``(delta_atoms, None)`` or ``(None, reason)`` with reason ``stale`` | ``no_baseline``.
        A non-stale leg becomes the new baseline either way."""
        key = (leg.wallet, leg.mint)
        current = self._held.get(key)
        if current is not None and leg.order <= current[1]:
            return None, "stale"
        cut = self._cut.get(leg.wallet)
        if current is None and cut is not None and not leg.is_sol and leg.slot <= cut:
            return (
                None,
                "stale",
            )  # inside the snapshot window of an absent mint: unknowable, not learned
        self._held[key] = (leg.balance_atoms, leg.order)
        if current is not None:
            return leg.balance_atoms - current[0], None
        if cut is not None and not leg.is_sol:
            return leg.balance_atoms, None  # no list held it up to the cut: it was zero
        return None, "no_baseline"


@dataclass(frozen=True, slots=True)
class LegOutcome:
    events: tuple[LeaderEvent, ...]
    reason: str
    """``event`` | ``pending_sol`` | ``sol_leg`` | ``stale`` | ``no_baseline`` | ``no_change`` | ``wsol``."""
    deadline_mono: float | None = None
    """Set when a buy now waits for its SOL leg: the monotonic time to call :meth:`LegProcessor.expire`."""


@dataclass(slots=True)
class _Pending:
    leg: BalanceLeg
    delta: int
    deadline: float


class LegProcessor:
    def __init__(self, book: BalanceBook) -> None:
        self.book = book
        self._sol: OrderedDict[tuple[str, str], int] = OrderedDict()
        self._first: OrderedDict[tuple[str, str], datetime] = OrderedDict()
        self._tokens: OrderedDict[tuple[str, str], int] = OrderedDict()
        self._pending: OrderedDict[tuple[str, str], list[_Pending]] = OrderedDict()

    def drop_wallet(self, wallet: str) -> None:
        """Forget the transactions in flight of one wallet (its baseline was reset)."""
        for book in (self._sol, self._first, self._tokens, self._pending):
            for key in [k for k in book if k[0] == wallet]:
                del book[key]

    def reset(self) -> None:
        """Forget every transaction in flight (a reconnect)."""
        self._sol.clear()
        self._first.clear()
        self._tokens.clear()
        self._pending.clear()

    def on_leg(self, leg: BalanceLeg, *, seen_at: datetime, now_mono: float) -> LegOutcome:
        key = (leg.wallet, leg.signature)
        self._first.setdefault(key, seen_at)
        delta, why = self.book.apply(leg)
        if leg.is_sol:
            return self._on_sol(key, delta, why, seen_at, now_mono)
        if leg.mint == WSOL_MINT:
            return LegOutcome((), "wsol")
        if delta is None:
            return LegOutcome((), why or "no_baseline")
        if delta == 0:
            return LegOutcome((), "no_change")
        count = self._tokens[key] = self._tokens.get(key, 0) + 1
        self._trim()
        sol = self._sol.get(key)
        if delta < 0 or sol is not None:  # a sell never waits; a buy with its SOL leg is complete
            event = self._build(leg, delta, None if count > 1 else sol, count > 1, seen_at)
            return LegOutcome((event,), "event")
        deadline = now_mono + PAIR_WAIT_S
        self._pending.setdefault(key, []).append(_Pending(leg, delta, deadline))
        return LegOutcome((), "pending_sol", deadline_mono=deadline)

    def _on_sol(
        self,
        key: tuple[str, str],
        delta: int | None,
        why: str | None,
        seen_at: datetime,
        now_mono: float,
    ) -> LegOutcome:
        if delta is None:
            return LegOutcome((), why or "no_baseline")
        self._sol[key] = delta
        self._trim()
        waiting = self._pending.pop(key, [])
        if not waiting:
            return LegOutcome((), "sol_leg")
        multi = self._tokens.get(key, 0) > 1
        events = tuple(
            self._build(
                p.leg,
                p.delta,
                None if multi or p.deadline <= now_mono else delta,  # overdue: decided by the clock
                multi,
                seen_at,
            )
            for p in waiting
        )
        return LegOutcome(events, "event")

    def expire(self, *, now_mono: float, now_wall: datetime) -> list[LeaderEvent]:
        """Buys whose SOL leg did not come in time, emitted with ``sol_delta_lamports=None``."""
        out: list[LeaderEvent] = []
        for key in list(self._pending):
            keep: list[_Pending] = []
            for p in self._pending[key]:
                if p.deadline <= now_mono:
                    multi = self._tokens.get(key, 0) > 1
                    out.append(self._build(p.leg, p.delta, None, multi, now_wall))
                else:
                    keep.append(p)
            if keep:
                self._pending[key] = keep
            else:
                del self._pending[key]
        return out

    def _trim(self) -> None:
        for book in (self._sol, self._first, self._tokens):
            while len(book) > _KEEP:
                # never the metadata of a transaction that still has a buy waiting on its SOL leg
                victim = next((k for k in book if k not in self._pending), None)
                if victim is None:
                    break
                del book[victim]

    def _build(
        self, leg: BalanceLeg, delta: int, sol: int | None, multi: bool, complete_at: datetime
    ) -> LeaderEvent:
        key = (leg.wallet, leg.signature)
        first = self._first.get(key, complete_at)
        transfer = sol is not None and ((delta > 0 and sol >= 0) or (delta < 0 and sol <= 0))
        return LeaderEvent(
            wallet=leg.wallet,
            mint=leg.mint,
            side="buy" if delta > 0 else "sell",
            token_delta_atoms=delta,
            sol_delta_lamports=sol,
            position_after_atoms=leg.balance_atoms,
            signature=leg.signature,
            slot=leg.slot,
            block_time=None,
            first_seen_at=first,
            fields_complete_at=max(complete_at, first),
            source="nats",
            confirmed=False,
            server_ts=leg.server_ts,
            multi_mint=multi,
            kind="transfer" if transfer else "unknown",
        )
