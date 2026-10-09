"""The daily snapshot in bounded memory (wave 1c-bis): the window replayed one mint at a time.

:func:`stream_snapshot` returns what :func:`.ranking.build_snapshot` returns for the same day —
proved by the differential tests against it — without ever holding the window: the caller streams
:class:`MintWindow` items (the mint's carry, its events received from the window start on and its
``CreateEvent`` s) three times, and memory holds one mint, the per-entity tallies, the window's
same-slot evidence and the carry it is handed (:mod:`.carry` says what, why, and the contract).

1. **survey** — contract checks, the window's same-slot co-buys (entities of the cut), horizon,
   window count, and the fills of transactions that touch more than one mint (tx-fee owner);
2. **bets** — only an entity's *first* qualifying buy in a mint can be a bet (``not_first_buy``
   comes before the caps and ``record`` marks every reason but ``below_min``); those that pass
   the local refusals are capped at the first N per (entity, UTC decision day) in decision order;
3. **replay** (:mod:`.stream_mint`) — books, W-PnL, exclusions, the bets' copies, and the carry of
   the next window start. Passes 1–2 are the coordinator's :func:`plan_night`; pass 3 is a pure
   function of the plan and one mint (:func:`replay_window`), so it can run in worker processes
   (:mod:`.stream_parallel`) and be reduced exactly (:meth:`.stream_mint.Tallies.merge`);
   :func:`finish_night` assembles the snapshot and the next global carry.
"""

from __future__ import annotations

from bisect import insort
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from types import MappingProxyType

from hunter_indicators.meme.wallets.carry import Carry, ContractViolation, MintCarry
from hunter_indicators.meme.wallets.entities import Entities, entities_as_of
from hunter_indicators.meme.wallets.follow import TriggerState, decision_order, refusal
from hunter_indicators.meme.wallets.metrics import EntityFacts, failing_reasons
from hunter_indicators.meme.wallets.params import FollowPolicy, RankingParams
from hunter_indicators.meme.wallets.ranking import assemble_snapshot, cut_of
from hunter_indicators.meme.wallets.snapshot import RankRow
from hunter_indicators.meme.wallets.stream_links import Pairs
from hunter_indicators.meme.wallets.stream_links import absorb as _absorb
from hunter_indicators.meme.wallets.stream_links import cobuys as _cobuys
from hunter_indicators.meme.wallets.stream_links import fee_seeds as _fee_seeds
from hunter_indicators.meme.wallets.stream_links import weak_links as _weak
from hunter_indicators.meme.wallets.stream_mint import Night, Tallies, earliest_create, replay_mint
from hunter_indicators.meme.wallets.stream_source import (
    MintWindow,
    StreamInputs,
    StreamResult,
    shared_signatures,
)
from hunter_indicators.meme.wallets.stream_source import each_mint as _each
from hunter_indicators.meme.wallets.stream_source import prepared as _prepared
from hunter_indicators.meme.wallets.tape import Fill

__all__ = [
    "MintPart",
    "MintWindow",
    "NightPlan",
    "StreamInputs",
    "StreamResult",
    "finish_night",
    "plan_night",
    "replay_one",
    "replay_window",
    "shared_signatures",
    "stream_snapshot",
]

_Identity = tuple[str, str, int]
_NO_STATE = TriggerState()


@dataclass(slots=True)
class _Survey:
    pairs: Pairs = field(default_factory=dict[tuple[str, str], dict[str, datetime]])
    day_pairs: Pairs = field(default_factory=dict[tuple[str, str], dict[str, datetime]])
    shared: list[Fill] = field(default_factory=list[Fill])
    horizon: int = -1
    window_fills: int = 0
    max_slot: int = -1
    events: dict[str, int] = field(default_factory=dict[str, int])
    """Per mint, in source order: its prepared events (the order, the fetch check, the cost)."""
    weight: dict[str, int] = field(default_factory=dict[str, int])
    """Per mint: the size of its carry (frontier, lots, flows) — work without new events."""


def _survey(inputs: StreamInputs, start: datetime, cut: datetime, settled: datetime) -> _Survey:
    carry, nxt = inputs.carry, start + timedelta(days=1)
    s = _Survey(horizon=carry.max_slot, max_slot=carry.max_slot)
    for window in _each(inputs):
        fills = _prepared(window, carry.sealed_until, start, cut)
        mint, kept = window.carry.mint, window.carry
        s.events[mint] = len(fills)
        s.weight[mint] = len(kept.frontier) + len(kept.lots) + len(kept.flows)
        buys = [f for f in fills if f.side == "buy" and f.block_time >= start]
        _absorb(s.pairs, mint, _cobuys(buys))
        _absorb(s.day_pairs, mint, _cobuys(f for f in buys if f.block_time < nxt))
        for f in fills:
            s.window_fills += f.block_time >= start
            if f.block_time < settled:
                s.horizon = max(s.horizon, f.slot)
            if f.received_at < nxt:
                s.max_slot = max(s.max_slot, f.slot)
            if f.signature in inputs.shared_signatures and f.block_time >= start:
                s.shared.append(f)
    return s


_Queue = list[tuple[tuple[datetime, int, str, int], _Identity, str]]


def _bets(
    inputs: StreamInputs, start: datetime, cut: datetime, policy: FollowPolicy, ents: Entities
) -> tuple[dict[str, frozenset[_Identity]], dict[str, int]]:
    """The bets (per mint, after the global per-entity daily cap) and each entity's trades."""
    capped: dict[tuple[str, date], _Queue] = {}
    trades: dict[str, int] = {}
    previous_day = cut - timedelta(days=1)
    decide = timedelta(seconds=float(policy.decision_seconds))
    for window in _each(inputs):
        fills = [
            f for f in _prepared(window, inputs.carry.sealed_until, start, cut)
            if f.block_time >= start
        ]  # fmt: skip
        create = earliest_create(window.carry, window.creates, cut)
        creates = {} if create is None else {create.mint: create}
        seen: set[str] = set()
        for f in sorted(fills, key=decision_order):
            entity = ents.of(f.wallet)
            trades[entity] = trades.get(entity, 0) + (f.block_time >= previous_day)
            if f.side != "buy" or f.sol_lamports < policy.min_trigger_lamports or entity in seen:
                continue
            seen.add(entity)
            wallets = ents.wallets_of(entity)
            if refusal(f, entity=entity, wallets=wallets, creates=creates, state=_NO_STATE,
                       policy=policy) is None:  # fmt: skip
                queue = capped.setdefault((entity, (f.received_at + decide).date()), [])
                insort(queue, (decision_order(f), f.identity, f.mint))  # identities never tie
                del queue[policy.max_bets_per_entity_day :]
    by_mint: dict[str, set[_Identity]] = {}
    for queue in capped.values():
        for _, identity, mint in queue:
            by_mint.setdefault(mint, set()).add(identity)
    return {m: frozenset(v) for m, v in by_mint.items()}, trades


@dataclass(frozen=True, slots=True)
class NightPlan:
    """Passes 1–2, the coordinator's part of a night (CPU plan step 3): what every mint's replay
    shares, what the assembly needs, and the survey's per-mint sizes (scheduling, fetch check)."""

    day: date
    policy: FollowPolicy
    params: RankingParams
    carry: Carry
    """The global carry handed in (its seal checks every window; its links make the next one)."""
    base: Night
    """The night without bets and fee seeds: :meth:`mint_night` adds one mint's."""
    trades: Mapping[str, int]
    window_fills: int
    max_slot: int
    day_pairs: Pairs
    events: Mapping[str, int]
    """Prepared events per mint; its keys are the source order."""
    weight: Mapping[str, int]
    bets: Mapping[str, frozenset[_Identity]]
    """Per mint, after the global per-entity daily cap of pass 2."""
    entity_seeds: Mapping[str, frozenset[tuple[str, str]]]
    wallet_seeds: Mapping[str, frozenset[tuple[str, str]]]

    @property
    def order(self) -> tuple[str, ...]:
        return tuple(self.events)

    def cost(self, mint: str) -> int:
        """A scheduling estimate, never a result: (events + carry) × (1 + bets) — each copy's
        stop scans the mint's tape, the super-linear part measured in step 1."""
        return (self.events[mint] + self.weight[mint]) * (1 + len(self.bets.get(mint, ())))

    def schedule(self) -> tuple[str, ...]:
        """Largest estimated cost first; ties keep the source order (stable sort)."""
        return tuple(sorted(self.events, key=lambda m: -self.cost(m)))

    def mint_night(self, mint: str) -> Night:
        none = frozenset[tuple[str, str]]()
        return replace(self.base, bets=self.bets.get(mint, frozenset()),
                       entity_seeds={mint: self.entity_seeds.get(mint, none)},
                       wallet_seeds={mint: self.wallet_seeds.get(mint, none)})  # fmt: skip


def plan_night(
    inputs: StreamInputs,
    day: date,
    *,
    policy: FollowPolicy | None = None,
    params: RankingParams | None = None,
) -> NightPlan:
    """Passes 1–2 over the whole source: survey, entities, bets (global daily cap), fee seeds."""
    pol, par = policy or FollowPolicy(), params or RankingParams()
    cut = cut_of(day)
    start = cut - timedelta(days=par.window_days)
    inputs.carry.check(start, par.window_days)
    if cut - timedelta(seconds=par.settle_seconds) < start:  # the carried max slot may be unsettled
        raise ContractViolation("settle_beyond_window", f"{par.settle_seconds} s")
    survey = _survey(inputs, start, cut, cut - timedelta(seconds=par.settle_seconds))
    links, _ = _weak(inputs.carry, survey.pairs)
    ents = entities_as_of((*inputs.links, *links), cut)
    funded = {w: fu for w, (fu, known) in inputs.funders.items() if known < cut}
    nxt = start + timedelta(days=1)
    bets, trades = _bets(inputs, start, cut, pol, ents)
    by_entity = _fee_seeds([(f, ents.of(f.wallet)) for f in survey.shared])
    by_wallet = _fee_seeds([(f, f.wallet) for f in survey.shared if f.block_time < nxt])
    base = Night(start, cut, nxt, survey.horizon, ents, MappingProxyType(funded), inputs.gaps, pol,
                 par, frozenset(), MappingProxyType({}), MappingProxyType({}))  # fmt: skip
    return NightPlan(
        day, pol, par, inputs.carry, base, MappingProxyType(trades), survey.window_fills,
        survey.max_slot, survey.day_pairs, MappingProxyType(survey.events),
        MappingProxyType(survey.weight), MappingProxyType(bets),
        MappingProxyType({m: frozenset(v) for m, v in by_entity.items()}),
        MappingProxyType({m: frozenset(v) for m, v in by_wallet.items()}),
    )  # fmt: skip


@dataclass(frozen=True, slots=True)
class MintPart:
    """One mint's pass 3: its tallies (for the exact reduction) and its next carry."""

    mint: str
    events: int
    tallies: Tallies
    carry: MintCarry | None
    """The next carry; ``None`` when empty (nothing to write)."""


def replay_one(night: Night, sealed_until: datetime, window: MintWindow) -> MintPart:
    """Pass 3 of one mint — a pure function of the night (carrying this mint's bets and fee
    seeds), the seal and the window: no state shared with any other mint's replay."""
    fills = _prepared(window, sealed_until, night.start, night.cut)
    tallies = Tallies()
    nxt = replay_mint(window.carry, fills, window.creates, night, tallies)
    return MintPart(window.carry.mint, len(fills), tallies, None if nxt.empty else nxt)


def replay_window(plan: NightPlan, window: MintWindow) -> MintPart:
    return replay_one(plan.mint_night(window.carry.mint), plan.carry.sealed_until, window)


def finish_night(
    plan: NightPlan, tallies: Tallies, carries: tuple[MintCarry, ...], code_version: str = ""
) -> StreamResult:
    """The snapshot from the reduced tallies, and the global carry of the next window start."""
    ents, par = plan.base.entities, plan.params
    rows: dict[str, RankRow] = {}
    for entity in sorted(tallies.books):
        copies = tallies.copies_of(entity)
        facts = EntityFacts(
            wallets=ents.wallets_of(entity), c_pnl_lamports=copies.total,
            trades_previous_day=plan.trades.get(entity, 0),
            w_pnl_lamports=tallies.w_pnl.get(entity, 0), copies=copies.copies,
            copies_incomplete=copies.incomplete, copies_contaminated=copies.contaminated,
        )  # fmt: skip
        metrics = tallies.books[entity].metrics(entity, facts, par)
        rows[entity] = RankRow(entity, failing_reasons(metrics, par), None, False, copies.total,
                               metrics)  # fmt: skip
    snapshot = assemble_snapshot(
        rows, day=plan.day, entities=ents, policy=plan.policy, params=par,
        code_version=code_version, window_fills=plan.window_fills, horizon=plan.base.horizon,
    )  # fmt: skip
    prior = plan.carry
    day_links, day_pending = _weak(prior, plan.day_pairs)
    pending = {**prior.pending, **day_pending}
    for link in day_links[len(prior.weak_links) :]:
        pending.pop((link.a, link.b), None)
    carry = Carry(plan.base.next_start, plan.base.cut, par.window_days, plan.max_slot,
                  tuple(day_links), MappingProxyType(pending))  # fmt: skip
    return StreamResult(snapshot, carry, carries)


def stream_snapshot(
    inputs: StreamInputs,
    day: date,
    *,
    policy: FollowPolicy | None = None,
    params: RankingParams | None = None,
    code_version: str = "",
    emit: Callable[[MintCarry], None] | None = None,
) -> StreamResult:
    """The unpublished snapshot of ``day`` and the carry of the next window start.

    ``emit`` receives each non-empty next per-mint carry as soon as its mint is replayed (to
    write it out), so the campaign's carry is never resident at once; without it they are
    collected into :attr:`StreamResult.mint_carries` (tests, small runs). One process; the
    parallel form is :func:`.stream_parallel.stream_snapshot_parallel`.
    """
    plan = plan_night(inputs, day, policy=policy, params=params)
    start, cut, seal = plan.base.start, plan.base.cut, plan.carry.sealed_until
    tallies, carries = Tallies(), list[MintCarry]()
    for window in _each(inputs):  # folded straight into one tally (the parallel form merges)
        fills = _prepared(window, seal, start, cut)
        night = plan.mint_night(window.carry.mint)
        nxt_carry = replay_mint(window.carry, fills, window.creates, night, tallies)
        if not nxt_carry.empty:
            (carries.append if emit is None else emit)(nxt_carry)
    return finish_night(plan, tallies, tuple(carries), code_version)
