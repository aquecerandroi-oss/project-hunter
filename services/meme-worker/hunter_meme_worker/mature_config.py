"""The mature-retention budget's own knob (I1, EXP-M26) — not in ``config.py``
(already at its 350-line budget; that module's own docstring names the
precedent for a worker owning a knob straight from the environment when that
happens, as ``fast_lane_config.py`` already does).

``MEME_TRACK_MATURE_TOP_K`` (default ``0``) is read fresh at every prune: the
default keeps the policy off in code everywhere it is not explicitly turned
on (``docs/design/exp-m26-grafico-moedas-maduras.md`` §1.6 — "padrão 0 =
desligado"), and the experiment's own compose sets it to 60
(``infra/vps/docker-compose.prod.yml``, C1).
"""

from __future__ import annotations

import os

from hunter_core.logging import get_logger

__all__ = ["MATURE_TOP_K_DEFAULT", "mature_top_k"]

MATURE_TOP_K_DEFAULT = 0


def mature_top_k() -> int:
    """``MEME_TRACK_MATURE_TOP_K``, or ``0``; a malformed value is the default
    **and a warning**, never a crash loop (``config._int_env``'s own rule)."""
    raw = os.environ.get("MEME_TRACK_MATURE_TOP_K", "").strip()
    if not raw:
        return MATURE_TOP_K_DEFAULT
    try:
        return max(0, int(raw))
    except ValueError:
        get_logger(__name__).warning(
            "meme_config_invalid", variable="MEME_TRACK_MATURE_TOP_K", value=raw
        )
        return MATURE_TOP_K_DEFAULT
