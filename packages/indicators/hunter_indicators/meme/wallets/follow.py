"""`follow` and `control` arms as pure ``evaluate`` functions (§3, §3.2).

``evaluate(ctx)`` reads nothing but its context: the event, the snapshots
(the one in force is chosen by ``published_at``), the ``CreateEvent`` s, the
arm's own past (:class:`TriggerState`) and the policy. No IO, no clock — the
decision instant is ``received_at + decision_seconds``.

Trigger rules (causal only, §1.1 "on the forward bet"):

1. a buy of ≥ ``min_trigger_lamports`` (smaller buys neither trigger nor
   consume the "first buy");
2. the entity's **first** such buy in the mint (one bet per entity per mint);
3. not in a mint created by the entity, and not within 2 slots of the
   ``create`` — both only when the ``CreateEvent`` was received before the
   decision (an unknown create cannot refuse);
4. the decision fits before the landing instant (no retroactive buy);
5. ≤ 20 bets per entity per UTC day (the first ones) and one bet per mint per
   30 min in the arm.

:func:`pair_controls` draws the H2 control of each `follow` bet (§3.2).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Literal

from hunter_indicators.meme.wallets.clock import NominalClock
from hunter_indicators.meme.wallets.params import FollowPolicy
from hunter_indicators.meme.wallets.pricing import pre_trade_state
from hunter_indicators.meme.wallets.snapshot import Snapshot, current_snapshot
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, event_order

__all__ = [
    "CONTROL2_ALLOWED",
    "Arm",
    "ArmContext",
    "ArmDecision",
    "TriggerLedger",
    "TriggerState",
    "decision_order",
    "evaluate",
    "pair_controls",
    "pre_trade_real_sol",
    "run_arm",
]

Arm = Literal["follow", "control", "control2"]
CONTROL2_ALLOWED: frozenset[str] = frozenset(
    {"e_pnl_below_min", "positive_days", "drawdown", "largest_episode_share", "c_pnl_not_positive"}
)
"""Control 2 (§3.2, descriptive): active, not eligible, but passing activity, holding
time and the exclusions — so it fails *only* the money/copyability checks."""


def decision_order(fill: Fill) -> tuple[datetime, int, str, int]:
    """Decisions happen in arrival order (Astra must-fix 1), never in slot order:
    an earlier-slot event received late cannot reorder what was already decided."""
    return (fill.received_at, *event_order(fill))


@dataclass(frozen=True, slots=True)
class TriggerState:
    bets_per_entity_day: Mapping[tuple[str, date], int] = field(
        default_factory=lambda: MappingProxyType({})
    )
    last_bet_per_mint: Mapping[str, datetime] = field(default_factory=lambda: MappingProxyType({}))
    first_buy_seen: AbstractSet[tuple[str, str]] = frozenset()


@dataclass(frozen=True, slots=True)
class ArmContext:
    fill: Fill
    snapshots: Sequence[Snapshot]
    creates: Mapping[str, CreateEvent]
    state: TriggerState
    policy: FollowPolicy
    arm: Arm


@dataclass(frozen=True, slots=True)
class ArmDecision:
    arm: Arm
    bet: bool
    reason: str
    fill: Fill
    decided_at: datetime
    entity: str | None = None
    snapshot_id: str | None = None
    leaders: frozenset[str] = frozenset()


def refusal(
    fill: Fill,
    *,
    entity: str,
    wallets: frozenset[str],
    creates: Mapping[str, CreateEvent],
    state: TriggerState,
    policy: FollowPolicy,
) -> str | None:
    """The first trigger rule ``fill`` breaks, or ``None`` (shared with the C-PnL)."""
    if fill.side != "buy" or fill.sol_lamports < policy.min_trigger_lamports:
        return "below_min"
    if (entity, fill.mint) in state.first_buy_seen:
        return "not_first_buy"
    decided_at = fill.received_at + timedelta(seconds=float(policy.decision_seconds))
    known = creates.get(fill.mint)
    if known is not None and known.received_at <= decided_at:
        if known.creator in wallets:
            return "own_mint"
        if fill.slot <= known.slot + policy.create_block_slots:
            return "create_block"
    clock = NominalClock.anchored_on(fill.slot, fill.block_time, policy.slot_seconds)
    if decided_at > clock.instant(fill.slot + policy.delay_slots):
        return "late_event"
    if (
        state.bets_per_entity_day.get((entity, decided_at.date()), 0)
        >= policy.max_bets_per_entity_day
    ):
        return "entity_day_cap"
    last = state.last_bet_per_mint.get(fill.mint)
    if last is not None and decided_at - last < timedelta(seconds=policy.mint_cooldown_seconds):
        return "mint_cooldown"
    return None


class TriggerLedger:
    """The arm's running state, recorded in place; :attr:`view` is a read-only
    :class:`TriggerState` over the live data (no copy per decision, so a busy
    entity is not quadratic). ``evaluate`` stays pure: it only reads the view."""

    def __init__(self) -> None:
        self._bets: dict[tuple[str, date], int] = {}
        self._last: dict[str, datetime] = {}
        self._seen: dict[tuple[str, str], None] = {}
        self.view = TriggerState(
            MappingProxyType(self._bets),
            MappingProxyType(self._last),
            MappingProxyType(self._seen).keys(),
        )

    def record(self, fill: Fill, entity: str, reason: str | None, decided_at: datetime) -> None:
        """A qualifying buy consumes the first buy; a bet also counts the caps."""
        if reason == "below_min":
            return
        self._seen[(entity, fill.mint)] = None
        if reason is None:
            key = (entity, decided_at.date())
            self._bets[key] = self._bets.get(key, 0) + 1
            self._last[fill.mint] = decided_at


def evaluate(ctx: ArmContext) -> ArmDecision:
    """Decide one event for one arm. Pure."""
    f, policy = ctx.fill, ctx.policy
    decided_at = f.received_at + timedelta(seconds=float(policy.decision_seconds))
    snap = current_snapshot(ctx.snapshots, decided_at)
    if snap is None:
        return ArmDecision(ctx.arm, bet=False, reason="no_snapshot", fill=f, decided_at=decided_at)
    entity = snap.entities.of(f.wallet)
    row = snap.row(entity)
    if row is None:
        in_arm = False
    elif ctx.arm == "follow":
        in_arm = row.followed
    elif ctx.arm == "control":
        in_arm = row.eligible and not row.followed
    else:
        in_arm = not row.eligible and set(row.reasons) <= CONTROL2_ALLOWED
    wallets = snap.entities.wallets_of(entity)
    if not in_arm:
        return ArmDecision(
            ctx.arm, bet=False, reason="not_in_arm", fill=f, decided_at=decided_at,
            entity=entity, snapshot_id=snap.snapshot_id,
        )  # fmt: skip
    reason = refusal(
        f, entity=entity, wallets=wallets, creates=ctx.creates, state=ctx.state, policy=policy
    )
    return ArmDecision(
        ctx.arm,
        reason is None,
        reason or "trigger",
        f,
        decided_at,
        entity,
        snap.snapshot_id,
        wallets,
    )


def run_arm(
    fills: Iterable[Fill],
    snapshots: Sequence[Snapshot],
    creates: Mapping[str, CreateEvent],
    policy: FollowPolicy,
    arm: Arm,
) -> tuple[ArmDecision, ...]:
    """Every buy through :func:`evaluate`, in arrival order, threading the state."""
    ledger = TriggerLedger()
    out: list[ArmDecision] = []
    for f in sorted(fills, key=decision_order):
        if f.side != "buy":
            continue
        d = evaluate(ArmContext(f, snapshots, creates, ledger.view, policy, arm))
        out.append(d)
        if d.entity is not None and d.reason != "not_in_arm":
            ledger.record(f, d.entity, None if d.bet else d.reason, d.decided_at)
    return tuple(out)


def _age_bucket(f: Fill, creates: Mapping[str, CreateEvent]) -> str:
    known = creates.get(f.mint)
    if known is None:
        return "unknown"
    minutes = (f.block_time - known.block_time).total_seconds() / 60
    return "<5m" if minutes < 5 else "5-60m" if minutes <= 60 else ">60m"


def pre_trade_real_sol(f: Fill) -> int | None:
    """Real SOL in the curve/pool just before ``f`` (:func:`~.pricing.pre_trade_state`: the
    exact vault flow, LP fee included); ``None`` (unknown, never 0) when that state is
    impossible."""
    pre = pre_trade_state(f)
    if pre is None:
        return None
    return (pre.real_sol_lamports if pre.venue == "curve" else pre.sol_lamports) or 0


def _stratum(
    f: Fill, creates: Mapping[str, CreateEvent], edges: tuple[int, int]
) -> tuple[str, str, int] | None:
    """The pairing cell; ``None`` when the liquidity before the trigger is unknown."""
    real = pre_trade_real_sol(f)
    if real is None:
        return None
    tercile = 0 if real < edges[0] else 1 if real < edges[1] else 2
    return (f.venue, _age_bucket(f, creates), tercile)


def _draw(seed: int, a: str, b: str) -> str:
    return hashlib.sha256(f"{seed}:{a}:{b}".encode()).hexdigest()


def pair_controls(
    follows: Sequence[Fill],
    controls: Sequence[Fill],
    *,
    creates: Mapping[str, CreateEvent],
    tercile_edges: tuple[int, int],
    seed: int,
    window_seconds: int = 60,
) -> dict[str, str | None]:
    """One control per `follow` trigger: same minute (±60 s), other mint, same
    venue, age bucket and real-SOL tercile before the trigger; seeded hash draw,
    without replacement. Outcome-blind: only trigger fields are read, so
    incomplete or censored controls stay in the pool (Astra). The tercile edges
    are frozen inputs computed outside, blind to outcomes. A trigger whose liquidity
    before the trade is unknown (impossible pre-state) is never paired, and such a
    control is never drawn: its pair is ``None``, counted like any unpaired bet."""
    used: set[str] = set()
    pairs: dict[str, str | None] = {}
    for f in sorted(follows, key=lambda x: (x.received_at, _draw(seed, x.signature, ""))):
        key = _stratum(f, creates, tercile_edges)
        if key is None:
            pairs[f.signature] = None
            continue
        pool = [
            c
            for c in controls
            if c.signature not in used
            and c.mint != f.mint
            and abs((c.block_time - f.block_time).total_seconds()) <= window_seconds
            and _stratum(c, creates, tercile_edges) == key
        ]
        pick = min(pool, key=lambda c: _draw(seed, f.signature, c.signature), default=None)
        pairs[f.signature] = None if pick is None else pick.signature
        if pick is not None:
            used.add(pick.signature)
    return pairs
