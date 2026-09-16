"""The fast lane's own RPC commitment (T4.42) — not in ``config.py`` (already
at its 350-line budget; ``MemeConfig``'s own docstring names the precedent for
a worker owning a knob straight from the environment when that happens, as
``events_config.py`` already does).

``MEME_FAST_LANE_COMMITMENT`` (default ``confirmed``) is read at every fast
lane tick, never cached: KB-0117 (16/09) measured the 15 s series reading the
chain at ``finalized`` and paying ~11-12 s of *structural* lag for it (32
slots' worth of finality) on top of the series' own age — 20,7 s (p50) of
state age at the instant of a proposal. ``confirmed`` is one slot behind the
tip rather than thirty-two; the read still only feeds a proposal or a paper
mark, never an order — ``services/meme-executor/hunter_meme_worker/chain.py``
already re-reads the curve live at admission, so a ``confirmed`` reorg (rare,
and never unseen — the next tick re-reads) costs the Lab a mispriced paper
row at worst, not money. The minute loop that marks ``meme_curve_snapshots``
for paper PnL (``chain.py``) keeps ``finalized`` — unrelated call, unrelated
default, unchanged by this module.
"""

from __future__ import annotations

import os

from hunter_core.logging import get_logger

__all__ = ["FAST_LANE_COMMITMENT_DEFAULT", "fast_lane_commitment"]

FAST_LANE_COMMITMENT_DEFAULT = "confirmed"
_KNOWN = frozenset({"confirmed", "finalized"})


def fast_lane_commitment() -> str:
    """``MEME_FAST_LANE_COMMITMENT``, lower-cased; an unknown value is the
    default **and a warning**, never a crash loop (``config._bool_env``'s own
    rule)."""
    raw = os.environ.get("MEME_FAST_LANE_COMMITMENT", "").strip().lower()
    if not raw:
        return FAST_LANE_COMMITMENT_DEFAULT
    if raw in _KNOWN:
        return raw
    get_logger(__name__).warning(
        "meme_config_invalid", variable="MEME_FAST_LANE_COMMITMENT", value=raw
    )
    return FAST_LANE_COMMITMENT_DEFAULT
