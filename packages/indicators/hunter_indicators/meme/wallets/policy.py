"""The copy policy as a pure simulation (§3): one trigger in, one outcome out.

The same function is the `follow`/`control` arms **and** the C-PnL of the
ranking (§1 item 3), so what ranks an entity is exactly what we would have done.

- **Entry:** lands at ``trigger.slot + delay`` with the policy budget, priced by
  the §3.1 contract. If ``received_at + decision`` is after the landing instant
  the trigger is ``refused/late_event`` — no retroactive buy.
- **Exit**, the first of: (a) the leader entity has sold **more than** half of
  what it bought in the mint, (b) our sale quote at an observed state is ≤ the
  stop fraction of the budget, (c) the time cap counted from the entry instant.
  An event-driven exit lands at ``max(fire + delay, first slot after received +
  decision, entry + 1)``; the timer lands at ``fire + delay``. The leader's
  sold share is counted in arrival order, never with sales not yet received.
- **Outcome:** ``closed`` (net lamports and R), ``censored`` (migration without a
  decoded pool: the pre-registered imputation R = censored_r, *not* a lower
  bound — a full loss is R = −2), ``incomplete`` (the exit lands beyond the
  settled horizon: "the series ended" is never a sale, KB-0148), ``no_fill``
  (the entry slot cannot be priced) or ``refused``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import Literal

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.wallets.clock import NominalClock, SlotClock
from hunter_indicators.meme.wallets.params import FollowPolicy
from hunter_indicators.meme.wallets.pricing import Censored, MintTape, sell_lamports
from hunter_indicators.meme.wallets.tape import Fill, Gap, event_order, touches_gap

__all__ = ["CopyOutcome", "CopyStatus", "simulate_copy"]

CopyStatus = Literal["closed", "censored", "incomplete", "no_fill", "refused"]


@dataclass(frozen=True, slots=True)
class CopyOutcome:
    status: CopyStatus
    reason: str
    trigger_slot: int
    entry_slot: int | None = None
    entry_atoms: int | None = None
    exit_fire_slot: int | None = None
    exit_slot: int | None = None
    net_lamports: int | None = None
    r: Decimal | None = None
    contaminated: bool = False


def _r(net: int, policy: FollowPolicy) -> Decimal:
    with localcontext(CONTEXT):
        return Decimal(net) / (policy.r_unit * policy.budget_lamports)


def _stop_floor(policy: FollowPolicy) -> Decimal:
    """``stop_fraction × budget``, once per copy (it was recomputed per scanned event)."""
    with localcontext(CONTEXT):
        return policy.stop_fraction * policy.budget_lamports


def _stopped(event: Fill, atoms: int, floor: Decimal) -> bool:
    quote = sell_lamports(event.reserves, atoms, fee_bps=event.fee_bps)
    if quote is None:  # a completed curve cannot be quoted; the timer/censor decide
        return False
    with localcontext(CONTEXT):  # same context as before step 2, whatever the caller's traps
        return Decimal(quote) <= floor


@dataclass(frozen=True, slots=True)
class _Exit:
    reason: str
    fire_slot: int
    landing_slot: int


def _landing(event: Fill, policy: FollowPolicy, clock: SlotClock, entry_slot: int) -> int:
    decision = timedelta(seconds=float(policy.decision_seconds))
    return max(
        event.slot + policy.delay_slots,
        clock.first_slot_at_or_after(event.received_at + decision),
        entry_slot + 1,
    )


def _leader_exit(
    trigger: Fill,
    leader_wallets: frozenset[str],
    tape: MintTape,
    policy: FollowPolicy,
    clock: SlotClock,
    entry_slot: int,
    prior: tuple[int, int] = (0, 0),
    since: datetime | None = None,
) -> _Exit | None:
    """The leader's > half sold, counted in **arrival** order (Astra must-fix 2).

    The check is armed only once the trigger itself has arrived — what we knew
    when we decided — and is then re-evaluated at every later arrival, whatever
    the slot it was mined in (a sale mined before the trigger but received after
    it can fire; a sale received before it is judged with the trigger counted).

    ``prior`` = (bought, sold) atoms of the leader's events received before ``since``; those
    events are then skipped in the tape (wave 1c-bis: the tape keeps only the frontier of what
    arrived before the window, and the whole-history count comes from the carried totals).
    """
    leader = sorted(
        (e for e in tape.of_wallets(leader_wallets) if since is None or e.received_at >= since),
        key=lambda e: (e.received_at, *event_order(e)),
    )
    bought, sold = prior
    armed = False
    best: _Exit | None = None
    for event in leader:
        if event.side == "buy":
            bought += event.token_atoms
        else:
            sold += event.token_atoms
        armed = armed or event.identity == trigger.identity
        if not armed:
            continue
        with localcontext(CONTEXT):
            fired = Decimal(sold) > policy.exit_sold_fraction * bought
        if fired:
            landing = _landing(event, policy, clock, entry_slot)
            if best is None or landing < best.landing_slot:
                best = _Exit("leader_sold", event.slot, landing)
    return best


def _find_exit(
    trigger: Fill,
    leader_wallets: frozenset[str],
    tape: MintTape,
    policy: FollowPolicy,
    clock: SlotClock,
    entry_slot: int,
    atoms: int,
    prior: tuple[int, int],
    since: datetime | None,
) -> _Exit:
    entry_instant = clock.instant(entry_slot)
    cap_fire = clock.first_slot_at_or_after(
        entry_instant + timedelta(seconds=policy.time_cap_seconds)
    )
    best = _Exit("time_cap", cap_fire, cap_fire + policy.delay_slots)
    leader = _leader_exit(trigger, leader_wallets, tape, policy, clock, entry_slot, prior, since)
    if leader is not None and leader.landing_slot < best.landing_slot:
        best = leader
    # Slot order. The stop is only checked after the entry slot, so the scan starts there: an
    # earlier event never fired it, and one that ended the scan means the first later event
    # ends it too, before any check (step 2; Astra corrected the first wording).
    events, floor = tape.fills, None
    for k in range(tape.first_after(entry_slot), len(events)):
        event = events[k]
        if event.slot > best.landing_slot:
            break
        floor = _stop_floor(policy) if floor is None else floor  # at the first scanned event
        if _stopped(event, atoms, floor):
            landing = _landing(event, policy, clock, entry_slot)
            if landing < best.landing_slot:
                best = _Exit("stop", event.slot, landing)
    return best


def simulate_copy(
    trigger: Fill,
    *,
    leader_wallets: frozenset[str],
    tape: MintTape,
    policy: FollowPolicy,
    horizon_slot: int,
    gaps: Sequence[Gap] = (),
    clock: SlotClock | None = None,
    leader_prior: tuple[int, int] = (0, 0),
    leader_since: datetime | None = None,
) -> CopyOutcome:
    """Follow ``trigger`` (a buy by the leader) on ``tape`` (the mint's events).

    ``leader_prior``/``leader_since``: see :func:`_leader_exit` (the default reads the whole tape).
    """
    if not tape.has(trigger.identity):
        raise ValueError("the tape must contain the trigger (the leader state is armed on it)")
    clk = clock or NominalClock.anchored_on(trigger.slot, trigger.block_time, policy.slot_seconds)
    entry_slot = trigger.slot + policy.delay_slots
    decided_at = trigger.received_at + timedelta(seconds=float(policy.decision_seconds))
    if decided_at > clk.instant(entry_slot):
        return CopyOutcome("refused", "late_event", trigger.slot)
    if entry_slot > horizon_slot:
        dirty = touches_gap(trigger.slot, horizon_slot, gaps)
        return CopyOutcome("incomplete", "entry_beyond_horizon", trigger.slot, contaminated=dirty)
    atoms = tape.landing_buy(entry_slot, policy.budget_lamports)
    if atoms is None or isinstance(atoms, Censored) or atoms <= 0:
        return CopyOutcome("no_fill", "entry_unpriceable", trigger.slot, entry_slot)
    found = _find_exit(
        trigger, leader_wallets, tape, policy, clk, entry_slot, atoms, leader_prior, leader_since
    )
    if found.landing_slot > horizon_slot:
        dirty = touches_gap(trigger.slot, horizon_slot, gaps)
        return CopyOutcome(
            "incomplete",
            found.reason,
            trigger.slot,
            entry_slot,
            atoms,
            found.fire_slot,
            contaminated=dirty,
        )
    dirty = touches_gap(trigger.slot, found.landing_slot, gaps)
    proceeds = tape.landing_sell(found.landing_slot, atoms)
    if proceeds is None or isinstance(proceeds, Censored):
        with localcontext(CONTEXT):
            net = int(policy.censored_r * policy.r_unit * policy.budget_lamports)
        status: CopyStatus = "censored"
        r = policy.censored_r
    else:
        costs = (
            2 * policy.network_leg_lamports
            + policy.ata_close_lamports
            + policy.ata_rent_lost_lamports
        )
        net = proceeds - policy.budget_lamports - costs
        status, r = "closed", _r(net, policy)
    return CopyOutcome(
        status,
        found.reason,
        trigger.slot,
        entry_slot,
        atoms,
        found.fire_slot,
        found.landing_slot,
        net,
        r,
        dirty,
    )
