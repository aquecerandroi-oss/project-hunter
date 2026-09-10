"""Dedupe and the two R sums — pure, no IO (brief T3.78, item 1).

An "aposta" is ``(market_id, source_bar_close)`` — T3.60's own definition,
reused verbatim rather than redefined: several active versions of the same
family routinely decide on the same bar (``notes-T3.60.md`` §2, "oito versões
... quatro vezes o barulho"). ``pooled_r`` counts every version's row;
``unique_r`` counts the bet once, credited to the version whose
``activated_at`` is earliest (ties broken by ``strategy_version_id`` then
``signal_id`` — deterministic regardless of query order).

**One axis, never silently mixed** (T3.75, the funding-NULL problem).
``r_multiple`` is ``signal_outcomes``'s persisted net-of-costs R
(``"r_net"``); a terminal outcome can carry a ``NULL`` there when
``settle()`` could not resolve funding at write time. This module's sums
skip those rows and count them separately (``funding_null``) rather than
falling back to a recomputed ``r_ex_funding`` — recomputing it would mean
re-running ``resolve_funding``/``settle()`` from this read-only API, which is
out of scope here (``notes-T3.78.md`` CONCERN 1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from hunter_api.repositories.lab_daily_goal import DailyOutcomeRow

__all__ = ["AXIS", "BetKey", "DedupedBet", "RAxisSums", "dedupe_bets", "sum_axis"]

AXIS = "r_net"
"""The only axis this endpoint reports (``signal_outcomes.r_multiple``,
net of assumed spread/slippage/fee/funding). See the module docstring."""

_NEVER_ACTIVATED = datetime.max.replace(tzinfo=UTC)
"""Sort key for a version with no ``activated_at``: last, never a crash on
``None`` comparison."""


@dataclass(frozen=True, slots=True)
class BetKey:
    market_id: uuid.UUID
    source_bar_close: datetime


@dataclass(frozen=True, slots=True)
class DedupedBet:
    key: BetKey
    winner: DailyOutcomeRow
    """The row of the earliest-activated version among the ones sharing
    ``key`` — the one ``unique_r`` credits."""
    member_count: int
    """How many versions took this same bet (the pooling factor of this one
    bet, T3.60 §3's "4,42x" is this averaged over the day)."""


def _dedupe_sort_key(row: DailyOutcomeRow) -> tuple[datetime, uuid.UUID, uuid.UUID]:
    activated = row.version_activated_at or _NEVER_ACTIVATED
    return (activated, row.strategy_version_id, row.signal_id)


def dedupe_bets(rows: Iterable[DailyOutcomeRow]) -> list[DedupedBet]:
    """Group by :class:`BetKey`; the winner is the earliest-activated version."""
    groups: dict[BetKey, list[DailyOutcomeRow]] = {}
    for row in rows:
        key = BetKey(row.market_id, row.source_bar_close)
        groups.setdefault(key, []).append(row)
    return [
        DedupedBet(key=key, winner=min(members, key=_dedupe_sort_key), member_count=len(members))
        for key, members in groups.items()
    ]


@dataclass(frozen=True, slots=True)
class RAxisSums:
    """The two sums, the axis they were computed on, and what got skipped."""

    axis: str
    pooled_r: Decimal
    pooled_priced: int
    """Rows (every version) whose ``r_multiple`` is not ``NULL``."""
    pooled_funding_null: int
    unique_r: Decimal
    unique_bets: int
    """Deduped bets whose winner's ``r_multiple`` is not ``NULL``."""
    unique_funding_null: int
    """Deduped bets whose winner's ``r_multiple`` **is** ``NULL`` — excluded
    from ``unique_r``, counted here instead of silently dropped."""
    unique_wins: int
    """Deduped, priced bets with ``r_multiple > 0`` — the ``hit_rate``
    numerator."""


def sum_axis(pooled_rows: Iterable[DailyOutcomeRow], deduped: Iterable[DedupedBet]) -> RAxisSums:
    pooled_r = Decimal(0)
    pooled_priced = 0
    pooled_funding_null = 0
    for row in pooled_rows:
        if row.r_multiple is None:
            pooled_funding_null += 1
            continue
        pooled_priced += 1
        pooled_r += row.r_multiple

    unique_r = Decimal(0)
    unique_bets = 0
    unique_funding_null = 0
    unique_wins = 0
    for bet in deduped:
        r = bet.winner.r_multiple
        if r is None:
            unique_funding_null += 1
            continue
        unique_bets += 1
        unique_r += r
        if r > 0:
            unique_wins += 1

    return RAxisSums(
        axis=AXIS,
        pooled_r=pooled_r,
        pooled_priced=pooled_priced,
        pooled_funding_null=pooled_funding_null,
        unique_r=unique_r,
        unique_bets=unique_bets,
        unique_funding_null=unique_funding_null,
        unique_wins=unique_wins,
    )
