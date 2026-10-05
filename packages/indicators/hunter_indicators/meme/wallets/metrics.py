"""Eligibility of an entity on a snapshot day (design §1, exclusions §1.1).

Historical exclusions remove **episodes** from the metrics (creator, create
block, MEV) and, above a share, the **entity** (creator > 20 %, create block >
30 %). The volume-bot rule reads the previous day's trade count, never the
final count of the day being decided (Astra must-fix 3).

``failing_reasons`` returns *every* failing check, in a fixed order, so the
snapshot persists why an entity is out instead of only the first reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from statistics import median

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.wallets.episodes import Episode, OwnerBook
from hunter_indicators.meme.wallets.params import RankingParams
from hunter_indicators.meme.wallets.tape import CreateEvent

__all__ = [
    "EntityFacts",
    "EntityMetrics",
    "classify_episodes",
    "entity_metrics",
    "failing_reasons",
    "max_drawdown",
]


@dataclass(frozen=True, slots=True)
class EntityFacts:
    """What the metrics need besides the book, all known before the cut."""

    wallets: frozenset[str]
    c_pnl_lamports: int
    trades_previous_day: int
    w_pnl_lamports: int = 0
    copies: int = 0
    copies_incomplete: int = 0
    copies_contaminated: int = 0


@dataclass(frozen=True, slots=True)
class EntityMetrics:
    entity: str
    e_pnl_lamports: int
    w_pnl_lamports: int
    c_pnl_lamports: int
    copies: int
    daily: tuple[int, ...]
    episodes_total: int
    closed_non_neutral: int
    mints: int
    active_days: int
    positive_days: int
    max_drawdown_lamports: int
    largest_episode_lamports: int
    median_hold_seconds: float | None
    short_hold_share: float
    unmatched_share: float
    creator_share: float
    create_block_share: float
    incomplete_episodes: int
    contaminated_episodes: int
    copies_incomplete: int
    copies_contaminated: int
    trades_previous_day: int


def max_drawdown(daily: Sequence[int]) -> int:
    """Largest fall of the cumulative daily curve from its running peak (peak ≥ 0)."""
    peak = cum = worst = 0
    for value in daily:
        cum += value
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return worst


def _share(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def _is_creator(ep: Episode, creates: Mapping[str, CreateEvent], insiders: frozenset[str]) -> bool:
    event = creates.get(ep.mint)
    return event is not None and event.creator in insiders


def _is_create_block(
    ep: Episode, creates: Mapping[str, CreateEvent], params: RankingParams
) -> bool:
    event = creates.get(ep.mint)
    first = ep.first_buy_slot if ep.first_buy_slot is not None else ep.opened_slot
    return event is not None and first <= event.slot + params.create_block_slots


def _is_mev(ep: Episode, params: RankingParams) -> bool:
    return ep.closed and ep.hold_slots is not None and ep.hold_slots <= params.mev_slots


def _neutral(ep: Episode, params: RankingParams) -> bool:
    with localcontext(CONTEXT):
        return Decimal(abs(ep.result_lamports)) < params.neutral_fraction * max(ep.cost_lamports, 1)


def classify_episodes(
    book: OwnerBook,
    wallets: frozenset[str],
    creates: Mapping[str, CreateEvent],
    funded_by: Mapping[str, str],
    params: RankingParams,
) -> tuple[list[Episode], list[Episode], list[Episode]]:
    """(creator, create-block, MEV) episodes — the historical exclusions of §1.1.

    Shared with the ranking so an excluded episode leaves the C-PnL too
    (Astra must-fix 7), not only the E-PnL.
    """
    insiders = wallets | frozenset(funded_by[w] for w in wallets if w in funded_by)
    creator = [e for e in book.episodes if _is_creator(e, creates, insiders)]
    block = [e for e in book.episodes if _is_create_block(e, creates, params)]
    mev = [e for e in book.episodes if _is_mev(e, params)]
    return creator, block, mev


def entity_metrics(
    book: OwnerBook,
    facts: EntityFacts,
    *,
    creates: Mapping[str, CreateEvent],
    funded_by: Mapping[str, str],
    params: RankingParams,
) -> EntityMetrics:
    """Compute the §1 metrics over the episodes that survive the exclusions."""
    creator, block, mev = classify_episodes(book, facts.wallets, creates, funded_by, params)
    total = len(book.episodes)
    out = {id(e) for e in (*creator, *block, *mev)}
    kept = [e for e in book.episodes if id(e) not in out]
    days = len(book.episodes[0].daily) if book.episodes else params.window_days
    daily = tuple(sum(e.daily[d] for e in kept) for d in range(days))
    counted = [e for e in kept if e.closed and not e.incomplete]
    active = [e for e in counted if not _neutral(e, params)]
    holds = [e.hold_seconds for e in counted if e.hold_seconds is not None]
    return EntityMetrics(
        entity=book.owner,
        e_pnl_lamports=sum(daily),
        w_pnl_lamports=facts.w_pnl_lamports,
        c_pnl_lamports=facts.c_pnl_lamports,
        copies=facts.copies,
        daily=daily,
        episodes_total=total,
        closed_non_neutral=len(active),
        mints=len({e.mint for e in active}),
        active_days=len({e.closed_at.date() for e in active if e.closed_at is not None}),
        positive_days=sum(1 for d in daily if d > 0),
        max_drawdown_lamports=max_drawdown(daily),
        largest_episode_lamports=max((e.result_lamports for e in kept), default=0),
        median_hold_seconds=median(holds) if holds else None,
        short_hold_share=_share(sum(1 for h in holds if h < params.short_hold_seconds), len(holds)),
        unmatched_share=_share(book.unmatched_atoms, book.sold_atoms),
        creator_share=_share(len(creator), total),
        create_block_share=_share(len(block), total),
        incomplete_episodes=sum(1 for e in book.episodes if e.incomplete),
        contaminated_episodes=sum(1 for e in book.episodes if e.contaminated),
        copies_incomplete=facts.copies_incomplete,
        copies_contaminated=facts.copies_contaminated,
        trades_previous_day=facts.trades_previous_day,
    )


def failing_reasons(m: EntityMetrics, p: RankingParams) -> tuple[str, ...]:
    """Every failed check; an entity is eligible iff this is empty."""
    e = Decimal(m.e_pnl_lamports)
    with localcontext(CONTEXT):
        checks = (
            ("volume_bot", m.trades_previous_day > p.max_trades_previous_day),
            ("creator_share", Decimal(str(m.creator_share)) > p.max_creator_share),
            ("create_block_share", Decimal(str(m.create_block_share)) > p.max_create_block_share),
            ("unmatched_share", Decimal(str(m.unmatched_share)) > p.max_unmatched_share),
            ("activity_episodes", m.closed_non_neutral < p.min_episodes),
            ("activity_mints", m.mints < p.min_mints),
            ("activity_days", m.active_days < p.min_active_days),
            ("e_pnl_below_min", m.e_pnl_lamports < p.min_e_pnl_lamports),
            ("positive_days", m.positive_days < p.min_positive_days),
            (
                "drawdown",
                m.max_drawdown_lamports
                > max(Decimal(p.drawdown_floor_lamports), p.drawdown_fraction * e),
            ),
            ("largest_episode_share", m.largest_episode_lamports > p.max_episode_fraction * e),
            (
                "median_hold",
                m.median_hold_seconds is None or m.median_hold_seconds < p.min_median_hold_seconds,
            ),
            ("short_hold_share", Decimal(str(m.short_hold_share)) > p.max_short_hold_share),
            ("c_pnl_not_positive", m.c_pnl_lamports <= 0),
        )
    return tuple(name for name, failed in checks if failed)
