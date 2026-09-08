"""What happened to one ``market.backfill.requested`` message, whatever the
lane. Split out of ``backfill.py`` (T3.7c) so the funding lane
(``funding_backfill.py``) can report in the same shape without importing the
candle consumer -- ``backfill.py`` itself imports ``funding_backfill`` to
dispatch on ``kind``, and the reverse import would be circular.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Outcome"]


@dataclass(frozen=True)
class Outcome:
    """What happened to one request, in one word plus the reason."""

    name: str
    reason: str = ""
    minutes: int = 0
    chunks: int = 0
    deferred: int = 0
    final: bool = False
