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
   the next window start.
"""

from __future__ import annotations

from bisect import insort
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from itertools import combinations
from types import MappingProxyType

from hunter_indicators.meme.wallets.carry import (
    Carry,
    ContractViolation,
    Evidence,
    MintCarry,
    canonical_order,
    merge_evidence,
)
from hunter_indicators.meme.wallets.entities import Entities, Link, entities_as_of
from hunter_indicators.meme.wallets.follow import TriggerState, decision_order, refusal
from hunter_indicators.meme.wallets.metrics import EntityFacts, failing_reasons
from hunter_indicators.meme.wallets.params import FollowPolicy, RankingParams
from hunter_indicators.meme.wallets.ranking import assemble_snapshot, cut_of
from hunter_indicators.meme.wallets.snapshot import RankRow, Snapshot
from hunter_indicators.meme.wallets.stream_mint import Night, Tallies, earliest_create, replay_mint
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Gap, dedupe, event_order

__all__ = ["MintWindow", "StreamInputs", "StreamResult", "shared_signatures", "stream_snapshot"]

Pairs = dict[tuple[str, str], dict[str, datetime]]
_Seeds = dict[str, set[tuple[str, str]]]
_NO_STATE = TriggerState()


@dataclass(frozen=True, slots=True)
class MintWindow:
    carry: MintCarry
    fills: tuple[Fill, ...] = ()
    """The mint's events received at or after the window start, in canonical order (later ones
    than the cut are ignored)."""
    creates: tuple[CreateEvent, ...] = ()
    """The mint's ``CreateEvent`` s received at or after the window start."""


def _no_funders() -> Mapping[str, tuple[str, datetime]]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class StreamInputs:
    carry: Carry
    mints: Callable[[], Iterable[MintWindow]]
    """A re-iterable source (read three times): every mint with a carry or a new event, once.
    Completeness is the source's guarantee (an omitted mint cannot be seen from here)."""
    shared_signatures: frozenset[str]
    """Every signature with events in more than one mint of the window (:func:`shared_signatures`);
    the tx fee goes to the owner's first event of the transaction across mints. REQUIRED, no
    default: "none shared" must be said, not assumed. Completeness is the storage's guarantee —
    one mint at a time cannot see an omission, and an omitted one charges the fee twice."""
    links: tuple[Link, ...] = ()
    funders: Mapping[str, tuple[str, datetime]] = field(default_factory=_no_funders)
    gaps: tuple[Gap, ...] = ()


@dataclass(frozen=True, slots=True)
class StreamResult:
    snapshot: Snapshot
    carry: Carry
    """The global carry at the next window start (``boundary + 1 day``)."""
    mint_carries: tuple[MintCarry, ...]
    """The non-empty per-mint carries at the next window start."""


def shared_signatures(fills: Iterable[Fill]) -> frozenset[str]:
    first: dict[str, str] = {}
    shared: set[str] = set()
    for f in fills:
        if first.setdefault(f.signature, f.mint) != f.mint:
            shared.add(f.signature)
    return frozenset(shared)


def _prepared(window: MintWindow, carry: Carry, start: datetime, cut: datetime) -> tuple[Fill, ...]:
    """The mint's causal events from the window start on, folded like ``dedupe``, contract-checked."""
    mint = window.carry.mint
    if any(f.mint != mint for f in window.fills) or any(c.mint != mint for c in window.creates):
        raise ValueError(f"an event of another mint in the window of {mint}")
    early = next((f for f in window.fills if f.received_at < start), None)
    if early is not None:  # already in the carry: it would be counted twice (Astra, diff review)
        raise ContractViolation(
            "received_before_window", f"{early.signature}/{early.event_ordinal}"
        )
    fills = tuple(
        sorted(dedupe(f for f in window.fills if f.received_at < cut), key=canonical_order)
    )
    times: dict[int, datetime] = {}
    for f in (*window.carry.frontier, *fills):
        if f.received_at < f.block_time:
            raise ContractViolation("received_before_mined", f"{f.signature}/{f.event_ordinal}")
        if f.block_time < start and f.received_at >= carry.sealed_until:
            raise ContractViolation("late_beyond_seal", f"{f.signature}/{f.event_ordinal}")
        if times.setdefault(f.slot, f.block_time) != f.block_time:
            raise ContractViolation("slot_time_inconsistent", f"{mint} slot {f.slot}")
    ordered = sorted(times.items())
    if any(b[1] < a[1] for a, b in zip(ordered, ordered[1:], strict=False)):
        raise ContractViolation("slot_time_inconsistent", f"{mint}: time decreases with the slot")
    return fills


def _each(inputs: StreamInputs) -> Iterable[MintWindow]:
    """One pass over the source, refusing a mint seen twice (it would be replayed twice)."""
    seen: set[str] = set()
    for window in inputs.mints():
        if window.carry.mint in seen:
            raise ContractViolation("repeated_mint", window.carry.mint)
        seen.add(window.carry.mint)
        yield window


def _cobuys(buys: Iterable[Fill]) -> dict[tuple[str, str], datetime]:
    """One mint's same-slot buyer pairs → the earliest instant the coincidence was knowable."""
    groups: dict[int, dict[str, datetime]] = {}
    for f in buys:
        seen = groups.setdefault(f.slot, {})
        seen[f.wallet] = min(seen.get(f.wallet, f.received_at), f.received_at)
    out: dict[tuple[str, str], datetime] = {}
    for buyers in groups.values():
        for a, b in combinations(sorted(buyers), 2):
            known = max(buyers[a], buyers[b])
            out[(a, b)] = min(out.get((a, b), known), known)
    return out


def _absorb(pairs: Pairs, mint: str, found: Mapping[tuple[str, str], datetime]) -> None:
    for pair, known in found.items():
        pairs.setdefault(pair, {})[mint] = known


def _link(pair: tuple[str, str], evidence: Evidence) -> Link:
    return Link(pair[0], pair[1], "weak", evidence[-1][0], ",".join(m for _, m in evidence))


def _weak(carry: Carry, pairs: Pairs) -> tuple[list[Link], dict[tuple[str, str], Evidence]]:
    """Links reaching 3 mints once ``pairs`` join the carry's evidence, and the pairs still pending."""
    done = {(link.a, link.b) for link in carry.weak_links}
    links, pending = list(carry.weak_links), dict[tuple[str, str], Evidence]()
    for pair, per_mint in pairs.items():
        if pair in done:
            continue
        merged = merge_evidence(carry.pending.get(pair, ()), per_mint)
        if len(merged) >= 3:
            links.append(_link(pair, merged))
        else:
            pending[pair] = merged
    return links, pending


def _fee_seeds(shared: list[tuple[Fill, str]]) -> _Seeds:
    """(owner, signature) → the mints where its fee is NOT due: the owner's first event of the
    transaction (event order, then input order) carries it."""
    first: dict[
        tuple[str, str], tuple[tuple[int, str, int], tuple[datetime, int, str, int, str], str]
    ]
    first = {}
    touched: dict[tuple[str, str], set[str]] = {}
    for f, owner in shared:
        key = (owner, f.signature)
        rank = (event_order(f), canonical_order(f), f.mint)
        if key not in first or rank[:2] < first[key][:2]:
            first[key] = rank
        touched.setdefault(key, set()).add(f.mint)
    seeds: _Seeds = {}
    for key, mints in touched.items():
        for mint in mints - {first[key][2]}:
            seeds.setdefault(mint, set()).add(key)
    return seeds


@dataclass(slots=True)
class _Survey:
    pairs: Pairs = field(default_factory=dict[tuple[str, str], dict[str, datetime]])
    day_pairs: Pairs = field(default_factory=dict[tuple[str, str], dict[str, datetime]])
    shared: list[Fill] = field(default_factory=list[Fill])
    horizon: int = -1
    window_fills: int = 0
    max_slot: int = -1


def _survey(inputs: StreamInputs, start: datetime, cut: datetime, settled: datetime) -> _Survey:
    carry, nxt = inputs.carry, start + timedelta(days=1)
    s = _Survey(horizon=carry.max_slot, max_slot=carry.max_slot)
    for window in _each(inputs):
        fills = _prepared(window, carry, start, cut)
        mint = window.carry.mint
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


_Queue = list[tuple[tuple[datetime, int, str, int], tuple[str, str, int]]]


def _bets(
    inputs: StreamInputs, start: datetime, cut: datetime, policy: FollowPolicy, ents: Entities
) -> tuple[frozenset[tuple[str, str, int]], dict[str, int]]:
    capped: dict[tuple[str, date], _Queue] = {}
    trades: dict[str, int] = {}
    previous_day = cut - timedelta(days=1)
    decide = timedelta(seconds=float(policy.decision_seconds))
    for window in _each(inputs):
        fills = [f for f in _prepared(window, inputs.carry, start, cut) if f.block_time >= start]
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
                insort(queue, (decision_order(f), f.identity))
                del queue[policy.max_bets_per_entity_day :]
    return frozenset(i for queue in capped.values() for _, i in queue), trades


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
    collected into :attr:`StreamResult.mint_carries` (tests, small runs).
    """
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
    night = Night(
        start, cut, nxt, survey.horizon, ents, MappingProxyType(funded), inputs.gaps, pol, par,
        bets, MappingProxyType({m: frozenset(v) for m, v in by_entity.items()}),
        MappingProxyType({m: frozenset(v) for m, v in by_wallet.items()}),
    )  # fmt: skip
    tallies, carries = Tallies(), list[MintCarry]()
    for window in _each(inputs):
        fills = _prepared(window, inputs.carry, start, cut)
        nxt_carry = replay_mint(window.carry, fills, window.creates, night, tallies)
        if not nxt_carry.empty:
            (carries.append if emit is None else emit)(nxt_carry)
    rows: dict[str, RankRow] = {}
    for entity in sorted(tallies.books):
        copies = tallies.copies_of(entity)
        facts = EntityFacts(
            wallets=ents.wallets_of(entity), c_pnl_lamports=copies.total,
            trades_previous_day=trades.get(entity, 0), w_pnl_lamports=tallies.w_pnl.get(entity, 0),
            copies=copies.copies, copies_incomplete=copies.incomplete,
            copies_contaminated=copies.contaminated,
        )  # fmt: skip
        metrics = tallies.books[entity].metrics(entity, facts, par)
        rows[entity] = RankRow(entity, failing_reasons(metrics, par), None, False, copies.total,
                               metrics)  # fmt: skip
    snapshot = assemble_snapshot(
        rows, day=day, entities=ents, policy=pol, params=par, code_version=code_version,
        window_fills=survey.window_fills, horizon=survey.horizon,
    )  # fmt: skip
    day_links, day_pending = _weak(inputs.carry, survey.day_pairs)
    pending = {**inputs.carry.pending, **day_pending}
    for link in day_links[len(inputs.carry.weak_links) :]:
        pending.pop((link.a, link.b), None)
    carry = Carry(nxt, cut, par.window_days, survey.max_slot, tuple(day_links),
                  MappingProxyType(pending))  # fmt: skip
    return StreamResult(snapshot, carry, tuple(carries))
