"""Per-entity accumulator of the bounded engine (wave 1c-bis): one mint's books at a time.

:func:`.metrics.entity_metrics` needs the entity's whole :class:`~.episodes.OwnerBook` — every
episode of the window in memory. :class:`EntityTally` folds the books of one mint at a time and
yields the same :class:`~.metrics.EntityMetrics`; the batch function stays the independent oracle
(Astra must-fix 5), so this module re-states each formula instead of sharing it.

The median hold is exact: every counted hold is kept (8 bytes in an ``array('d')``), because a
median is not decomposable (``[1, 2, 100]`` and ``[1, 50, 100]`` share count and share below
60 s). That memory is proportional to the counted episodes — an explicit budget, not a bound.
"""

from __future__ import annotations

from array import array
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, localcontext
from statistics import median

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.wallets.episodes import Episode, OwnerBook
from hunter_indicators.meme.wallets.metrics import (
    EntityFacts,
    EntityMetrics,
    classify_episodes,
    max_drawdown,
)
from hunter_indicators.meme.wallets.params import RankingParams
from hunter_indicators.meme.wallets.tape import CreateEvent

__all__ = ["EntityTally"]


def _holds() -> array[float]:
    return array("d")


def _ratio(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def _neutral(ep: Episode, params: RankingParams) -> bool:
    with localcontext(CONTEXT):
        return Decimal(abs(ep.result_lamports)) < params.neutral_fraction * max(ep.cost_lamports, 1)


@dataclass(slots=True)
class EntityTally:
    """Everything :func:`.metrics.entity_metrics` reads from a book, folded mint by mint."""

    days: int
    episodes: int = 0
    creator: int = 0
    create_block: int = 0
    daily: list[int] = field(default_factory=list[int])
    closed_non_neutral: int = 0
    mints: set[str] = field(default_factory=set[str])
    active_dates: set[date] = field(default_factory=set[date])
    largest: int | None = None
    holds: array[float] = field(default_factory=_holds)
    incomplete: int = 0
    contaminated: int = 0
    sold_atoms: int = 0
    unmatched_atoms: int = 0

    def __post_init__(self) -> None:
        if not self.daily:
            self.daily = [0] * self.days

    def fold(
        self,
        book: OwnerBook,
        wallets: frozenset[str],
        creates: Mapping[str, CreateEvent],
        funded_by: Mapping[str, str],
        params: RankingParams,
    ) -> list[Episode]:
        """Fold one mint's book of the entity; returns its excluded episodes (for the C-PnL)."""
        creator, block, mev = classify_episodes(book, wallets, creates, funded_by, params)
        out = {id(e) for e in (*creator, *block, *mev)}
        self.episodes += len(book.episodes)
        self.creator += len(creator)
        self.create_block += len(block)
        self.sold_atoms += book.sold_atoms
        self.unmatched_atoms += book.unmatched_atoms
        for ep in book.episodes:
            self.incomplete += ep.incomplete
            self.contaminated += ep.contaminated
            if id(ep) in out:
                continue
            for day, value in enumerate(ep.daily):
                self.daily[day] += value
            result = ep.result_lamports
            self.largest = result if self.largest is None else max(self.largest, result)
            if not ep.closed or ep.incomplete:
                continue
            if ep.hold_seconds is not None:
                self.holds.append(ep.hold_seconds)
            if not _neutral(ep, params):
                self.closed_non_neutral += 1
                self.mints.add(ep.mint)
                if ep.closed_at is not None:
                    self.active_dates.add(ep.closed_at.date())
        return [*creator, *block, *mev]

    def metrics(self, entity: str, facts: EntityFacts, params: RankingParams) -> EntityMetrics:
        daily = tuple(self.daily)
        holds = self.holds  # read in place; median() makes the one sorted copy it needs
        short = sum(1 for h in holds if h < params.short_hold_seconds)
        return EntityMetrics(
            entity=entity,
            e_pnl_lamports=sum(daily),
            w_pnl_lamports=facts.w_pnl_lamports,
            c_pnl_lamports=facts.c_pnl_lamports,
            copies=facts.copies,
            daily=daily,
            episodes_total=self.episodes,
            closed_non_neutral=self.closed_non_neutral,
            mints=len(self.mints),
            active_days=len(self.active_dates),
            positive_days=sum(1 for d in daily if d > 0),
            max_drawdown_lamports=max_drawdown(daily),
            largest_episode_lamports=0 if self.largest is None else self.largest,
            median_hold_seconds=median(holds) if holds else None,
            short_hold_share=_ratio(short, len(holds)),
            unmatched_share=_ratio(self.unmatched_atoms, self.sold_atoms),
            creator_share=_ratio(self.creator, self.episodes),
            create_block_share=_ratio(self.create_block, self.episodes),
            incomplete_episodes=self.incomplete,
            contaminated_episodes=self.contaminated,
            copies_incomplete=facts.copies_incomplete,
            copies_contaminated=facts.copies_contaminated,
            trades_previous_day=facts.trades_previous_day,
        )
