"""The per-mint gate refusal trail's own two knobs (T4.43) — not in
``config.py`` (already at its 350-line budget; ``MemeConfig``'s own docstring
names the precedent for a worker owning a knob straight from the environment
when that happens, as ``events_config.py``/``fast_lane_config.py`` already do).

``MEME_GATE_TRAIL_MAX_ROWS_PER_TICK`` (default 200,
``gate_refusal_trail.DEFAULT_TRAIL_CAP``) bounds the fast lane's own batched
``INSERT`` per tick — R27's measured volume (a few hundred rows judged per
tick, near-misses the minority of those) already keeps the count small; the
cap is the backstop, not the shape (docs/DATABASE.md §54.2).

``TRAIL_RETENTION_DAYS`` is not read from the environment: 7 days is the
contract (docs/DATABASE.md §54.2), the same number ``prune_refusal_trail``'s
own tests are written against.
"""

from __future__ import annotations

import os

from hunter_core.logging import get_logger
from hunter_meme_worker.gate_refusal_trail import DEFAULT_TRAIL_CAP

__all__ = ["TRAIL_RETENTION_DAYS", "trail_max_rows_per_tick"]

TRAIL_RETENTION_DAYS = 7


def trail_max_rows_per_tick() -> int:
    """``MEME_GATE_TRAIL_MAX_ROWS_PER_TICK``, read fresh every tick (cheap: an
    ``os.environ`` lookup, never cached) — a malformed or negative value is
    the default **and a warning**, never a crash loop (``config._int_env``'s
    own rule)."""
    raw = os.environ.get("MEME_GATE_TRAIL_MAX_ROWS_PER_TICK", "").strip()
    if not raw:
        return DEFAULT_TRAIL_CAP
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if value < 0:
        get_logger(__name__).warning(
            "meme_config_invalid", variable="MEME_GATE_TRAIL_MAX_ROWS_PER_TICK", value=raw
        )
        return DEFAULT_TRAIL_CAP
    return value
