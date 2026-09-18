"""T4.52b-3's own knobs, straight from the environment — not in ``config.py``
(already at its 350-line budget; ``MemeConfig``'s own docstring names the
precedent for a worker owning a knob this way, as ``fast_lane_config.py`` and
``events_config.py`` already do).

``MEME_EVENT_GATE`` (``off`` | ``shadow`` | ``on``, default ``off``) is the
kill switch of plan-T4.52b.md §4: absent or unknown reads as ``off`` and a
warning, never a crash loop. ``shadow`` evaluates and counts
(``event_gate_shadow_proposals_total``) without ever writing a row;
``on`` writes through the same ``insert_proposals``/``wake`` the 15-second
and minute gates already use.

``SOLANA_RPC_WS_URL`` defaults to ``SOLANA_RPC_URL`` with its scheme swapped
(``https`` → ``wss``, ``http`` → ``ws``) so a WS subscription limit never
starves the executor's own HTTP RPC calls (plan §4, "provedor"); with neither
set, the public endpoint (``rpc_ws.PUBLIC_WS_URL``) is the same fallback the
rest of the adapter already uses.

``MEME_EVENT_COMMITMENT`` (default ``confirmed``, doctrine §8.2 of
``RISK_ENGINE_MEME.md``: ``processed`` never decides) and
``MEME_EVENT_GATE_MAX_MINTS`` (default 150, plan §4's "raio de explosão")
round out what a restart needs to read fresh; the queue size and the debounce
window are declared constants, not knobs — plan §5 fixes both numbers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from hunter_core.logging import get_logger

__all__ = [
    "EVENT_DEBOUNCE_MS",
    "EVENT_QUEUE_SIZE",
    "GATE_MODES",
    "GATE_OFF",
    "GATE_ON",
    "GATE_SHADOW",
    "MAX_MINTS_DEFAULT",
    "SUBSCRIPTION_SYNC_S",
    "EventGateConfig",
    "event_gate_commitment",
    "event_gate_max_mints",
    "event_gate_mode",
    "load_event_gate_config",
    "solana_rpc_ws_url",
]

logger = get_logger(__name__)

GATE_OFF = "off"
GATE_SHADOW = "shadow"
GATE_ON = "on"
GATE_MODES = frozenset({GATE_OFF, GATE_SHADOW, GATE_ON})

COMMITMENT_DEFAULT = "confirmed"
_COMMITMENTS = frozenset({"confirmed", "processed"})

MAX_MINTS_DEFAULT = 150
EVENT_QUEUE_SIZE = 2000
"""``asyncio.Queue`` bound between the WS reader and the evaluator (plan §4
"Backpressure"): full means a frame is dropped and counted, never blocked on."""
EVENT_DEBOUNCE_MS = 100
"""Minimum interval between two evaluations of the same mint (plan §4/§5)."""
SUBSCRIPTION_SYNC_S = 5
"""How often the subscribed set is resynced against ``fast_lane.young_mints``."""

_PUBLIC_WS_URL = "wss://api.mainnet-beta.solana.com"


def _str_env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _int_env(name: str, default: int) -> int:
    raw = _str_env(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("meme_event_gate_config_invalid", variable=name, value=raw)
        return default
    return value if value > 0 else default


def event_gate_mode() -> str:
    raw = _str_env("MEME_EVENT_GATE").lower()
    if not raw:
        return GATE_OFF
    if raw in GATE_MODES:
        return raw
    logger.warning("meme_event_gate_config_invalid", variable="MEME_EVENT_GATE", value=raw)
    return GATE_OFF


def solana_rpc_ws_url() -> str:
    explicit = _str_env("SOLANA_RPC_WS_URL")
    if explicit:
        return explicit
    http = _str_env("SOLANA_RPC_URL")
    if http.startswith("https://"):
        return "wss://" + http.removeprefix("https://")
    if http.startswith("http://"):
        return "ws://" + http.removeprefix("http://")
    return _PUBLIC_WS_URL


def event_gate_commitment() -> str:
    raw = _str_env("MEME_EVENT_COMMITMENT").lower()
    if not raw:
        return COMMITMENT_DEFAULT
    if raw in _COMMITMENTS:
        return raw
    logger.warning("meme_event_gate_config_invalid", variable="MEME_EVENT_COMMITMENT", value=raw)
    return COMMITMENT_DEFAULT


def event_gate_max_mints() -> int:
    return _int_env("MEME_EVENT_GATE_MAX_MINTS", MAX_MINTS_DEFAULT)


@dataclass(frozen=True, slots=True)
class EventGateConfig:
    """Immutable; built once at startup, like ``MemeConfig``."""

    mode: str
    ws_url: str
    commitment: str
    max_mints: int
    queue_size: int = EVENT_QUEUE_SIZE
    debounce_ms: int = EVENT_DEBOUNCE_MS
    subscription_sync_s: int = SUBSCRIPTION_SYNC_S

    @property
    def enabled(self) -> bool:
        return self.mode != GATE_OFF

    @property
    def shadow(self) -> bool:
        return self.mode == GATE_SHADOW


def load_event_gate_config() -> EventGateConfig:
    return EventGateConfig(
        mode=event_gate_mode(),
        ws_url=solana_rpc_ws_url(),
        commitment=event_gate_commitment(),
        max_mints=event_gate_max_mints(),
    )
