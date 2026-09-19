"""T4.67a's own knob, read from the environment exactly as ``event_gate_config.py``
reads ``MEME_EVENT_GATE`` — a switch this module owns because ``config.py`` is
already at its 350-line budget.

``MEME_LAUNCH_LANE`` (``off`` | ``paper`` | ``on``, default ``off``): ``off``
subscribes to nothing and writes nothing (not even ``shadow``-style counting —
EXP-M18 is pre-registered as "arm if it pays in paper", so there is no
"measure without acting" phase here, unlike ``MEME_EVENT_GATE``). ``paper``
runs the whole lane — proposal, entry, exit — against ``launch_v0/1``'s own
``research_only`` rule set, which is paper by construction (the executor only
ever opens proposals of an ``operator`` set). ``on`` is reserved for the day a
``launch_*`` set of ``kind = 'operator'`` exists; until then it behaves like
``paper`` (there is nothing else to turn on).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from hunter_core.logging import get_logger

__all__ = [
    "LAUNCH_LANE_MODES",
    "LAUNCH_LANE_OFF",
    "LAUNCH_LANE_ON",
    "LAUNCH_LANE_PAPER",
    "MAX_WATCHES_DEFAULT",
    "LaunchLaneConfig",
    "load_launch_lane_config",
]

logger = get_logger(__name__)

LAUNCH_LANE_OFF = "off"
LAUNCH_LANE_PAPER = "paper"
LAUNCH_LANE_ON = "on"
LAUNCH_LANE_MODES = frozenset({LAUNCH_LANE_OFF, LAUNCH_LANE_PAPER, LAUNCH_LANE_ON})

MAX_WATCHES_DEFAULT = 200
"""The brief's own ceiling: at most this many mints priced at once."""

ENTRY_DELAY_S = 1
""""the first curve price after +1 s from the create" — a constant, not a
knob: the pre-registration (EXP-M18) fixes it with the arm."""

BORN_FULL_WINDOW_S = 2
BORN_FULL_PROGRESS_PCT = 90
"""KB-0123's "born full": progress at or above this within
:data:`BORN_FULL_WINDOW_S` of the create — counted, and the pending entry is
abandoned (module docstring of ``launch_lane.py``)."""


def _str_env(name: str) -> str:
    return os.environ.get(name, "").strip()


def launch_lane_mode() -> str:
    raw = _str_env("MEME_LAUNCH_LANE").lower()
    if not raw:
        return LAUNCH_LANE_OFF
    if raw in LAUNCH_LANE_MODES:
        return raw
    logger.warning("meme_launch_lane_config_invalid", variable="MEME_LAUNCH_LANE", value=raw)
    return LAUNCH_LANE_OFF


@dataclass(frozen=True, slots=True)
class LaunchLaneConfig:
    """Immutable; built once at startup, like ``EventGateConfig``."""

    mode: str
    ws_url: str
    commitment: str
    max_watches: int = MAX_WATCHES_DEFAULT
    entry_delay_s: int = ENTRY_DELAY_S

    @property
    def enabled(self) -> bool:
        return self.mode != LAUNCH_LANE_OFF


def load_launch_lane_config(*, ws_url: str, commitment: str) -> LaunchLaneConfig:
    """``ws_url``/``commitment`` are the event gate's own resolved values
    (``event_gate_config.solana_rpc_ws_url``/``event_gate_commitment``) — one
    provider, one commitment policy, read once in ``main.py`` and handed to
    both lanes rather than re-read here."""
    return LaunchLaneConfig(mode=launch_lane_mode(), ws_url=ws_url, commitment=commitment)
