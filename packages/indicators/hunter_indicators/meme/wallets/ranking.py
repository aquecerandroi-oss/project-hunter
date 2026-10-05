"""The daily snapshot of day D, point in time (design §1, §1.2, §2.1).

:func:`build_snapshot` receives **everything** it might be tempted by — late
trades, future links, creates received tomorrow — and is the one place the
three instants are applied:

1. **economic cut** ``T_D = D 00:00 UTC``: only copies whose whole outcome,
   exit landing included, ends at or before the *settled* horizon (the last slot
   mined before ``T_D − settle_seconds``) count in the C-PnL;
2. **availability**: only fills mined *and* received before ``T_D``
   (:func:`.tape.causal_view`), links with ``known_at < T_D``, creates received
   before ``T_D``, funders resolved before ``T_D``;
3. **publication** is the caller's: the result has ``published_at = None`` and
   is stamped once with :meth:`.snapshot.Snapshot.published`.

The C-PnL is :func:`.policy.simulate_copy` — the same function the `follow`
arm uses — over the entity's triggers selected by :func:`.follow.refusal`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from types import MappingProxyType

from hunter_indicators.meme.wallets.entities import Entities, Link, entities_as_of, same_slot_links
from hunter_indicators.meme.wallets.episodes import Episode, window_books
from hunter_indicators.meme.wallets.follow import TriggerLedger, decision_order, refusal
from hunter_indicators.meme.wallets.lots import Lot, fifo
from hunter_indicators.meme.wallets.metrics import (
    EntityFacts,
    classify_episodes,
    entity_metrics,
    failing_reasons,
)
from hunter_indicators.meme.wallets.params import FollowPolicy, RankingParams, manifest_hash
from hunter_indicators.meme.wallets.policy import simulate_copy
from hunter_indicators.meme.wallets.pricing import MintTape
from hunter_indicators.meme.wallets.snapshot import RankRow, Snapshot
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Gap, causal_view, dedupe

__all__ = ["RankInputs", "build_snapshot", "cut_of"]


@dataclass(frozen=True, slots=True)
class RankInputs:
    fills: tuple[Fill, ...] = ()
    creates: tuple[CreateEvent, ...] = ()
    links: tuple[Link, ...] = ()
    funders: Mapping[str, tuple[str, datetime]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    """wallet → (first funder, when that resolution was known)."""
    opening_lots: tuple[Lot, ...] = ()
    """Preserved per-wallet lots at the window start (``owner`` = wallet)."""
    gaps: tuple[Gap, ...] = ()


def cut_of(day: date) -> datetime:
    return datetime.combine(day, time(0), tzinfo=UTC)


def _hash(entity: str) -> str:
    return hashlib.sha256(entity.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class _Tally:
    total: int = 0
    copies: int = 0
    incomplete: int = 0
    contaminated: int = 0


def _excluded(f: Fill, by_mint: Mapping[str, list[Episode]]) -> bool:
    return any(
        e.opened_slot <= f.slot <= (e.closed_slot if e.closed_slot is not None else f.slot)
        for e in by_mint.get(f.mint, ())
    )


def _c_pnl(
    entity: str,
    wallets: frozenset[str],
    fills: list[Fill],
    tapes: Mapping[str, MintTape],
    creates: Mapping[str, CreateEvent],
    policy: FollowPolicy,
    horizon: int,
    gaps: tuple[Gap, ...],
    excluded: list[Episode],
) -> _Tally:
    """The entity's copies: complete ones summed, incomplete/contaminated counted.

    Triggers are taken in arrival order; a trigger inside an episode the
    historical exclusions removed (creator, create block, MEV) is not copied.
    """
    ledger, t = TriggerLedger(), _Tally()
    by_mint: dict[str, list[Episode]] = {}
    for e in excluded:
        by_mint.setdefault(e.mint, []).append(e)
    for f in sorted(fills, key=decision_order):
        if f.side != "buy":
            continue
        reason = refusal(
            f, entity=entity, wallets=wallets, creates=creates, state=ledger.view, policy=policy
        )
        decided_at = f.received_at + timedelta(seconds=float(policy.decision_seconds))
        ledger.record(f, entity, reason, decided_at)
        if reason is not None or _excluded(f, by_mint):
            continue
        out = simulate_copy(
            f,
            leader_wallets=wallets,
            tape=tapes[f.mint],
            policy=policy,
            horizon_slot=horizon,
            gaps=gaps,
        )
        dirty = t.contaminated + int(out.contaminated)
        if out.status in ("closed", "censored") and out.net_lamports is not None:
            t = _Tally(t.total + out.net_lamports, t.copies + 1, t.incomplete, dirty)
        elif out.status == "incomplete":
            t = _Tally(t.total, t.copies, t.incomplete + 1, dirty)
    return t


def _entities(inputs: RankInputs, causal: tuple[Fill, ...], cut: datetime) -> Entities:
    return entities_as_of((*inputs.links, *same_slot_links(causal)), cut)


def build_snapshot(
    inputs: RankInputs,
    day: date,
    *,
    policy: FollowPolicy | None = None,
    params: RankingParams | None = None,
    code_version: str = "",
) -> Snapshot:
    """The unpublished snapshot of ``day`` from inputs that may contain the future."""
    pol, par = policy or FollowPolicy(), params or RankingParams()
    cut = cut_of(day)
    start = cut - timedelta(days=par.window_days)
    causal = causal_view(dedupe(inputs.fills), cut)
    window = [f for f in causal if f.block_time >= start]
    ents = _entities(inputs, causal, cut)
    creates: dict[str, CreateEvent] = {}
    for c in inputs.creates:  # the earliest received copy of a mint's create wins
        if c.received_at < cut and (
            c.mint not in creates or c.received_at < creates[c.mint].received_at
        ):
            creates[c.mint] = c
    funded_by = {w: fu for w, (fu, known) in inputs.funders.items() if known < cut}
    by_mint: dict[str, list[Fill]] = {}
    for f in causal:
        by_mint.setdefault(f.mint, []).append(f)
    tapes = {mint: MintTape(fills) for mint, fills in by_mint.items()}
    opening = tuple(  # preserved lots only: a lot opened inside the window is its own buy
        Lot(
            ents.of(lot.owner),
            lot.mint,
            lot.atoms,
            lot.cost_lamports,
            lot.opened_slot,
            lot.opened_at,
        )
        for lot in inputs.opening_lots
        if lot.opened_at < start
    )
    books = window_books(
        window, owner_of=ents.of, opening=opening, tapes=tapes, start=start,
        days=par.window_days, gaps=inputs.gaps,
    )  # fmt: skip
    realized = fifo(window, owner_of=ents.of, opening=opening)
    w_pnl: dict[str, int] = {}
    for m in realized.matches:
        if m.cost_lamports is not None:
            w_pnl[m.owner] = w_pnl.get(m.owner, 0) + m.proceeds_lamports - m.cost_lamports
    settled = cut - timedelta(seconds=par.settle_seconds)
    horizon = max((f.slot for f in causal if f.block_time < settled), default=-1)
    previous_day = cut - timedelta(days=1)
    by_entity: dict[str, list[Fill]] = {}
    for f in window:
        by_entity.setdefault(ents.of(f.wallet), []).append(f)
    rows: dict[str, RankRow] = {}
    for entity, book in books.items():
        wallets = ents.wallets_of(entity)
        own = by_entity.get(entity, [])
        creator, block, mev = classify_episodes(book, wallets, creates, funded_by, par)
        tally = _c_pnl(
            entity,
            wallets,
            own,
            tapes,
            creates,
            pol,
            horizon,
            inputs.gaps,
            [*creator, *block, *mev],
        )
        c_pnl = tally.total
        facts = EntityFacts(
            wallets=wallets,
            c_pnl_lamports=c_pnl,
            trades_previous_day=sum(1 for f in own if f.block_time >= previous_day),
            w_pnl_lamports=w_pnl.get(entity, 0),
            copies=tally.copies,
            copies_incomplete=tally.incomplete,
            copies_contaminated=tally.contaminated,
        )
        metrics = entity_metrics(book, facts, creates=creates, funded_by=funded_by, params=par)
        rows[entity] = RankRow(
            entity, failing_reasons(metrics, par), rank=None, followed=False,
            c_pnl_lamports=c_pnl, metrics=metrics,
        )  # fmt: skip
    eligible = sorted(
        (r for r in rows.values() if r.eligible), key=lambda r: (-r.c_pnl_lamports, _hash(r.entity))
    )
    for rank, row in enumerate(eligible, start=1):
        rows[row.entity] = RankRow(
            row.entity, row.reasons, rank, rank <= par.top_n, row.c_pnl_lamports, row.metrics
        )
    comparable = sum(1 for r in eligible if r.entity in rows and not rows[r.entity].followed)
    digest = manifest_hash(pol, par)
    manifest = {
        "code_version": code_version,
        "params_hash": digest,
        "window_fills": str(len(window)),
        "entities_version": ents.version,
        "horizon_slot": str(horizon),
        "eligible": str(len(eligible)),
        "h2_comparable_entities": str(comparable),
        "h2_supported": str(comparable >= par.min_h2_entities).lower(),
    }
    return Snapshot(
        f"{day.isoformat()}:{digest[:12]}",
        day,
        cut,
        None,
        ents,
        MappingProxyType(rows),
        MappingProxyType(manifest),
    )
