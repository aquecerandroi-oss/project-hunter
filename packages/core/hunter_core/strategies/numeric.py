"""The one arithmetic context of the strategy layer.

``Decimal`` addition, multiplication and division all round under the *ambient*
context (``decimal.getcontext()``), which any library in the process can change.
A frozen strategy version whose thresholds depend on the ambient precision is
not frozen at all, so every operation that can round runs inside
``localcontext(CONTEXT)``.

28 significant digits and ``ROUND_HALF_EVEN`` are Python's own defaults; naming
them here makes them part of the written contract instead of an accident of the
runtime (Astra, S1 design review, must-fix 6).
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Context

CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)
"""Frozen with every strategy version: changing it changes historical numbers."""
