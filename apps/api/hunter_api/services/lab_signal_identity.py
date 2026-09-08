"""``identity_key`` for a Shadow Lab signal (T3.38a).

Sibling strategy versions (a byte-identical paper copy, or a version whose
only change is a filter the signal still passes) can decide on the exact same
operation and each persist their own ``agent_signals``/``signal_outcomes``
row -- ``brief-T3.38-lab-identical-signals-grouped.md``'s ``RAYSOLUSDT``
report: three rows, one real operation. ``identity_key`` is a stable hash of
the tuple that *defines* "the same operation" -- market, the decision bar,
entry price, exit price, exit reason and result -- computed once here, on the
server, from the envelope, so the web never has to re-derive ``Decimal``
equality itself (float-shaped bugs live there).

Hashed, not the raw tuple, only so the wire payload stays a short opaque
string; the algorithm has no significance beyond "stable and collision-free
for this input space" -- nothing decodes it back.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_core.domain.enums import OutcomeResult

__all__ = ["compute_identity_key"]

_FIELD_SEP = "\x1f"
"""ASCII unit separator -- never legal inside a market symbol, a decimal's
text form, an ISO timestamp or a reason slug, so it cannot let two different
tuples collide by shifting field boundaries."""

_NULL = "\x00"
"""Sentinel for ``None`` -- distinct from every real value, including the
empty string and ``Decimal("0")`` (both used as literal parts elsewhere)."""


def _decimal_part(value: Decimal | None) -> str:
    return _NULL if value is None else str(value)


def _text_part(value: str | None) -> str:
    return _NULL if value is None else value


def compute_identity_key(
    *,
    market: str,
    source_bar_close: datetime,
    entry_price: Decimal | None,
    exit_price: Decimal | None,
    exit_reason: str | None,
    result: OutcomeResult,
) -> str:
    """Sha256 hex digest of ``market|bar_close|entry|exit|exit_reason|result``.

    ``source_bar_close`` must be tz-aware (``ensure_utc`` raises otherwise --
    the same rule every other timestamp in this API follows).
    """
    parts = (
        market,
        ensure_utc(source_bar_close).isoformat(),
        _decimal_part(entry_price),
        _decimal_part(exit_price),
        _text_part(exit_reason),
        result.value,
    )
    digest = hashlib.sha256(_FIELD_SEP.join(parts).encode("utf-8"))
    return digest.hexdigest()
