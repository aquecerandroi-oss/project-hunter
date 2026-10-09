"""Where the follow source lost coverage (H-037): the lane's in-memory registry of ``LeaderGap`` spans.

A gap is an interval ``[start, end)`` of one wallet — or of every wallet when ``wallet`` is ``None`` —
and ``end is None`` while it is still open. The question the book asks is only "did this leader's
event, by the chain's block time or by our observation, fall inside a span we could not see?";
answering it is a few comparisons over at most :data:`GAPS_MAX` spans per wallet, in memory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_exchanges.pumpfun.leader_events import LeaderGap

__all__ = ["GAPS_MAX", "GapRegistry"]

GAPS_MAX = 200


class GapRegistry:
    def __init__(self) -> None:
        self._spans: dict[str | None, list[tuple[datetime, datetime | None]]] = {}

    def add(self, gap: LeaderGap) -> None:
        spans = self._spans.setdefault(gap.wallet, [])
        spans[:] = [s for s in spans if s[0] != gap.start]  # a gap re-sent with its end replaces
        spans.append((gap.start, gap.end))
        del spans[:-GAPS_MAX]

    def covers(self, wallet: str, *instants: datetime | None) -> bool:
        for key in (wallet, None):
            for start, end in self._spans.get(key, ()):
                for at in instants:
                    if at is not None and start <= at and (end is None or at < end):
                        return True
        return False

    @staticmethod
    def overlaps_life(gap: LeaderGap, opened_by: datetime) -> bool:
        """The gap touches a copy opened at ``opened_by`` that is still alive now."""
        return gap.end is None or gap.end > opened_by
