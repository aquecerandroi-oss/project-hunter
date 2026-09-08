"""``identity_key`` for a Shadow Lab signal (T3.38a; stop + normalization
fixes T3.38c, review findings 2-4 on ``brief-T3.38c-identity-key-fixes.md``).

Sibling strategy versions (a byte-identical paper copy, or a version whose
only change is a filter the signal still passes) can decide on the exact same
operation and each persist their own ``agent_signals``/``signal_outcomes``
row -- ``brief-T3.38-lab-identical-signals-grouped.md``'s ``RAYSOLUSDT``
report: three rows, one real operation. ``identity_key`` is a stable hash of
the tuple that *defines* "the same operation" -- market, the decision bar,
entry price, virtual stop, exit price, exit reason and result -- computed
once here, on the server, from the envelope, so the web never has to
re-derive ``Decimal`` equality itself (float-shaped bugs live there).

T3.38c finding 2: two sibling versions can share entry/exit/result but ship
a different ``stop`` (hence a different R and a different money amount) --
the stop it actually tracked, ``signal_outcomes.virtual_stop``, is now part
of the tuple, not the plan's originally proposed ``agent_signals.stop``.

T3.38c finding 3: two numerically equal ``Decimal``\\ s with a different
number of trailing zeros (``Decimal("1.16930116")`` vs
``Decimal("1.169301160")``) used to ``str()`` to different text and hash to
different keys -- every decimal part is now quantized to the same scale the
SQL side casts to (``numeric(28,10)``, ``repositories/lab_signals.py``'s
``_IDENTITY_KEY_TEXT``) before it enters the hash input.

Hashed, not the raw tuple, only so the wire payload stays a short opaque
string; the algorithm has no significance beyond "stable and collision-free
for this input space" -- nothing decodes it back.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_core.domain.enums import OutcomeResult

__all__ = ["compute_identity_key"]

_FIELD_SEP = "\x1f"
"""ASCII unit separator -- never legal inside a market symbol, a decimal's
text form, an ISO timestamp or a reason slug, so it cannot let two different
tuples collide by shifting field boundaries. The SQL-side twin
(``repositories/lab_signals.py``'s ``_IDENTITY_KEY_TEXT``) uses the same
``chr(31)`` (T3.38c finding 4) so a seeded row's SQL text and this module's
hash input are byte-identical, not merely non-colliding."""

_NULL = "\x00"
"""Sentinel for ``None`` -- distinct from every real value, including the
empty string and ``Decimal("0")`` (both used as literal parts elsewhere)."""

_DECIMAL_SCALE = Decimal("1e-10")
"""Ten decimal places -- matches the SQL side's ``numeric(28,10)`` cast
(T3.38c finding 3), so two ``Decimal``\\ s that are numerically equal but
textually different (trailing zeros, differing exponents) collapse to the
exact same hash input."""


def _decimal_part(value: Decimal | None) -> str:
    if value is None:
        return _NULL
    with localcontext() as ctx:
        ctx.prec = 50  # headroom above numeric(28,10)'s 28 total digits
        quantized = value.quantize(_DECIMAL_SCALE)
    # ``format(..., "f")`` -- never ``str()`` -- forces fixed-point notation;
    # ``str()`` on a quantized value near zero (e.g. ``Decimal("1e-10")``)
    # renders as scientific notation (``"1E-10"``), which would not match
    # Postgres's ``numeric`` text output for the same value.
    return format(quantized, "f")


def _text_part(value: str | None) -> str:
    return _NULL if value is None else value


def compute_identity_key(
    *,
    market: str,
    source_bar_close: datetime,
    entry_price: Decimal | None,
    stop: Decimal | None,
    exit_price: Decimal | None,
    exit_reason: str | None,
    result: OutcomeResult,
) -> str:
    """Sha256 hex digest of
    ``market|bar_close|entry|stop|exit|exit_reason|result``.

    ``source_bar_close`` must be tz-aware (``ensure_utc`` raises otherwise --
    the same rule every other timestamp in this API follows). ``stop`` is the
    tracked virtual stop (``signal_outcomes.virtual_stop``), not the plan's
    originally proposed ``agent_signals.stop`` -- see finding 2 above.
    """
    parts = (
        market,
        ensure_utc(source_bar_close).isoformat(),
        _decimal_part(entry_price),
        _decimal_part(stop),
        _decimal_part(exit_price),
        _text_part(exit_reason),
        result.value,
    )
    digest = hashlib.sha256(_FIELD_SEP.join(parts).encode("utf-8"))
    return digest.hexdigest()
