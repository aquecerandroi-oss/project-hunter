"""The bounded book of armed entries at the pullback (T4.91, H-016) — split
from :mod:`hunter_meme_worker.entry_pullback` for the 350-line budget; pure
(no I/O, no clock: every instant is an argument). The contract — the window,
the FIFO proof of expiry, one arming per (set, mint) per process run, what a
restart forgets — is that module's docstring.
"""

from __future__ import annotations

import copy
from collections import OrderedDict, deque
from dataclasses import replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from hunter_meme_worker.entry_pullback import (
    ARMED,
    DROPPED_CAP,
    FEED_LOST,
    NO_PULLBACK,
    STALL_S,
    ArmedEntry,
    price_of,
)
from hunter_meme_worker.gate_refusal_trail import RefusalTrailRow

if TYPE_CHECKING:
    from collections.abc import Sequence
    from decimal import Decimal

    from hunter_exchanges.pumpfun.models import NormalizedCurveTrade
    from hunter_meme_worker.decision_tape import DecisionTape
    from hunter_meme_worker.event_gate_rows import EventReserves
    from hunter_meme_worker.event_state import MintEventState
    from hunter_meme_worker.lab_models import RuleSetSpec
    from hunter_meme_worker.proposals import ProposalDraft
    from hunter_meme_worker.proposals_row import GateRow

__all__ = ["MAX_ARMED", "PullbackBook", "arm_from_gate"]

MAX_ARMED: Final = 256
MAX_SPENT: Final = 4096
SPENT_TTL_S: Final = 3600
MAX_TRAIL: Final = 1024


class PullbackBook:
    """Every armed entry of the lane, bounded; the counters the heartbeat reads."""

    def __init__(
        self, *, max_armed: int = MAX_ARMED, max_trail: int = MAX_TRAIL, max_spent: int = MAX_SPENT
    ) -> None:
        self._by_mint: dict[str, dict[str, ArmedEntry]] = {}
        self._spent: OrderedDict[tuple[str, str], datetime] = OrderedDict()
        self._trail: deque[tuple[RefusalTrailRow, DecisionTape | None]] = deque()
        self._max_armed, self._max_trail, self._max_spent = max_armed, max_trail, max_spent
        self.processed_through: datetime | None = None
        """``received_at`` of the newest frame the lane has folded (FIFO)."""
        self.armed = self.triggered = self.proposed = self.not_inserted = 0
        self.expired_no_pullback = self.censored = self.killed_by_recheck = 0
        self.dropped_cap = self.trail_dropped = self.trail_write_failed = 0

    @property
    def size(self) -> int:
        return sum(len(by_spec) for by_spec in self._by_mint.values())

    def is_armed(self, mint: str) -> bool:
        return mint in self._by_mint

    def can_arm(self, spec_id: str, mint: str, t0: datetime) -> bool:
        """Neither armed already nor spent — checked before the ``t0`` tape
        is captured, so an armed mint re-judged every debounce costs nothing."""
        spent_until = self._spent.get((spec_id, mint))
        if spent_until is not None and t0 < spent_until:
            return False
        return spec_id not in self._by_mint.get(mint, {})

    def armable(
        self, to_arm: list[tuple[RuleSetSpec, list[ProposalDraft]]], mint: str, t0: datetime
    ) -> list[tuple[RuleSetSpec, list[ProposalDraft]]]:
        return [(spec, drafts) for spec, drafts in to_arm if self.can_arm(spec.id, mint, t0)]

    def arm(self, entry: ArmedEntry) -> bool:
        """``False`` when this (set, mint) is armed already or spent."""
        if not self.can_arm(entry.spec_id, entry.mint, entry.t0):
            return False
        if self.size >= self._max_armed:
            oldest = min(
                (e for by_spec in self._by_mint.values() for e in by_spec.values()),
                key=lambda e: e.t0,
            )
            self._remove(oldest)
            self.dropped_cap += 1
            dropped = RefusalTrailRow(entry.t0, oldest.spec_id, oldest.mint, DROPPED_CAP)
            self.queue_trail(dropped, None)
        self._by_mint.setdefault(entry.mint, {})[entry.spec_id] = entry
        self.armed += 1
        return True

    def observe_trade(self, mint: str, trade: NormalizedCurveTrade) -> None:
        """O(1) for an unarmed mint — called for every ``TradeEvent``."""
        by_spec = self._by_mint.get(mint)
        if by_spec is None:
            return
        price = price_of(trade.virtual_sol_reserves, trade.virtual_token_reserves)
        if price is None:
            return
        for entry in by_spec.values():
            entry.observe(price, trade.received_at, signature=trade.signature, slot=trade.slot)

    def mark_processed(self, received_at: datetime) -> None:
        """Every frame the lane folded, in queue order — the expiry's proof."""
        if self.processed_through is None or received_at > self.processed_through:
            self.processed_through = received_at

    def pop_fired(self, mint: str) -> list[ArmedEntry]:
        fired = [e for e in self._by_mint.get(mint, {}).values() if e.fired]
        for entry in fired:
            self._remove(entry)
        self.triggered += len(fired)
        return fired

    def pop_due(self, now: datetime) -> list[tuple[ArmedEntry, str]]:
        """Unfired entries whose window is over: :data:`NO_PULLBACK` once a
        frame received after the deadline was folded, :data:`FEED_LOST` when
        :data:`STALL_S` passed without that proof."""
        stall = timedelta(seconds=STALL_S)
        through = self.processed_through
        due: list[tuple[ArmedEntry, str]] = []
        for by_spec in self._by_mint.values():
            for entry in by_spec.values():
                if entry.fired:
                    continue
                if through is not None and through > entry.deadline:
                    due.append((entry, NO_PULLBACK))
                elif now - entry.deadline >= stall:
                    due.append((entry, FEED_LOST))
        for entry, _outcome in due:
            self._remove(entry)
        return due

    def queue_trail(self, row: RefusalTrailRow, tape: DecisionTape | None) -> None:
        if len(self._trail) >= self._max_trail:
            self._trail.popleft()
            self.trail_dropped += 1
        self._trail.append((row, tape))

    def requeue_trail(self, rows: list[tuple[RefusalTrailRow, DecisionTape | None]]) -> None:
        """A batch whose write failed goes back to the front, in order (the
        insert is ``ON CONFLICT DO NOTHING``: a retry never writes twice)."""
        self.trail_write_failed += 1
        self._trail.extendleft(reversed(rows))
        while len(self._trail) > self._max_trail:
            self._trail.pop()
            self.trail_dropped += 1

    def drain_trail(
        self, limit: int | None = None
    ) -> list[tuple[RefusalTrailRow, DecisionTape | None]]:
        count = len(self._trail) if limit is None else min(limit, len(self._trail))
        return [self._trail.popleft() for _ in range(count)]

    def arm_gate(
        self,
        to_arm: Sequence[tuple[RuleSetSpec, list[ProposalDraft]]],
        row: GateRow,
        state: MintEventState,
        reserves: EventReserves | None,
        tape: DecisionTape | None,
        now: datetime,
        shared: bool,
    ) -> None:
        """``event_gate_eval.evaluate_mint``'s one call: every set whose gate
        passed at ``now`` and waits for the pullback. The ``t0`` tape is
        offered with the first ``armed`` row only when no other row of this
        instant (a proposal, a queued trail row — ``shared``) offers it:
        ``meme_decision_tapes`` keeps one tape per ``(mint, as_of)``."""
        t0_price = (
            None
            if reserves is None
            else price_of(reserves.virtual_sol_reserves, reserves.virtual_token_reserves)
        )
        offer = not shared
        for spec, drafts in to_arm:
            if arm_from_gate(
                self,
                drafts,
                spec=spec,
                row=row,
                state=state,
                t0_price=t0_price,
                tape=tape,
                offer_tape=offer,
                now=now,
            ):
                offer = False

    def heartbeat_fields(self) -> dict[str, str]:
        prefix = "event_gate_pullback_"
        return {
            f"{prefix}armed_now": str(self.size),
            f"{prefix}armed_total": str(self.armed),
            f"{prefix}triggered_total": str(self.triggered),
            f"{prefix}proposed_total": str(self.proposed),
            f"{prefix}not_inserted_total": str(self.not_inserted),
            f"{prefix}expired_no_pullback_total": str(self.expired_no_pullback),
            f"{prefix}censored_total": str(self.censored),
            f"{prefix}killed_by_recheck_total": str(self.killed_by_recheck),
            f"{prefix}dropped_cap_total": str(self.dropped_cap),
            f"{prefix}trail_dropped_total": str(self.trail_dropped),
            f"{prefix}trail_write_failed_total": str(self.trail_write_failed),
        }

    def _remove(self, entry: ArmedEntry) -> None:
        by_spec = self._by_mint.get(entry.mint, {})
        by_spec.pop(entry.spec_id, None)
        if not by_spec:
            self._by_mint.pop(entry.mint, None)
        key = (entry.spec_id, entry.mint)
        self._spent.pop(key, None)
        self._spent[key] = entry.t0 + timedelta(seconds=SPENT_TTL_S)
        while len(self._spent) > self._max_spent:
            self._spent.popitem(last=False)


def arm_from_gate(
    book: PullbackBook,
    drafts: list[ProposalDraft],
    *,
    spec: RuleSetSpec,
    row: GateRow,
    state: MintEventState,
    t0_price: Decimal | None,
    tape: DecisionTape | None,
    offer_tape: bool,
    now: datetime,
) -> bool:
    """Arm (spec, mint) from the gate's ``t0`` draft instead of inserting it;
    queue the ``armed`` trail row (with the ``t0`` tape when no other row of
    this instant offers it). ``False``: already armed/spent, or no price."""
    params = spec.entry_pullback
    if not drafts or t0_price is None or params is None:
        return False
    # Held up to W seconds and re-emitted: never a dict another set's draft of
    # this instant (or the tape) also carries (risk-engine-guardian, LOW).
    extra = [] if tape is None else [tape.reasons_block()]
    draft = replace(drafts[0], reasons=copy.deepcopy([*drafts[0].reasons, *extra]))
    entry = ArmedEntry(
        spec_id=spec.id,
        mint=row.mint,
        params=params,
        t0=now,
        armed_max=t0_price,
        gaps=state.gaps,
        creator_sells=state.creator_flow(now).sells,
        draft=draft,
        row=row,
        spec=spec,
    )
    if not book.arm(entry):
        return False
    trail = RefusalTrailRow(now, spec.id, row.mint, ARMED, limit=params.pct)
    book.queue_trail(trail, tape if offer_tape else None)
    return True
