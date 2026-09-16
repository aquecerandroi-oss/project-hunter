"""The event ↔ coin matching job's own two knobs (T4.26b) — not in
``config.py`` (already at its 350-line budget the day this task landed;
``MemeConfig``'s own docstring names the precedent for a worker owning a knob
straight from the environment when that happens).

``MEME_EVENT_MATCH_WINDOW_H`` (default 72) and ``MEME_EVENT_MATCH_GRACE_MIN``
(default 30) are KB-0100's own numbers: the plantão's median news→registration
latency measured 172,8 min that day, and events routinely land with a
retroactive ``observed_at`` hours in the past — a 65-minute lookback and a
forward-only match window (0041) never had a chance to fire.
"""

from __future__ import annotations

import os

from hunter_core.logging import get_logger

__all__ = ["MATCH_GRACE_MIN_DEFAULT", "MATCH_WINDOW_H_DEFAULT", "match_grace_min", "match_window_h"]

MATCH_WINDOW_H_DEFAULT = 72
MATCH_GRACE_MIN_DEFAULT = 30


def _int_env(name: str, default: int) -> int:
    """A malformed value is the default **and a warning**, never a crash loop —
    ``config._int_env``'s own rule, duplicated here rather than imported
    private across modules."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        get_logger(__name__).warning("meme_events_config_invalid", variable=name, value=raw)
        return default


def match_window_h() -> int:
    return _int_env("MEME_EVENT_MATCH_WINDOW_H", MATCH_WINDOW_H_DEFAULT)


def match_grace_min() -> int:
    return _int_env("MEME_EVENT_MATCH_GRACE_MIN", MATCH_GRACE_MIN_DEFAULT)
