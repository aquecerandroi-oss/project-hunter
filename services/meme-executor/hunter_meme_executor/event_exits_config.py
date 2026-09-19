"""T4.63 — the knobs of the event-driven exits, read from the environment.

``MEME_EVENT_EXITS`` (``off`` | ``on``, default ``off``): with it on the
executor owns **one** Solana RPC WebSocket (``SOLANA_RPC_WS_URL``, the same
variable the radar's event gate reads — empty derives it from
``SOLANA_RPC_URL`` with the scheme swapped, and with neither set the public
endpoint) and, for every open real position, subscribes to the mint's
bonding-curve PDA (``accountSubscribe`` + ``logsSubscribe``, commitment
``confirmed`` — ``processed`` never decides, doctrine §8.2). Anything else
in the variable reads as ``off`` with a warning, never a crash.

Not policy of capital: none of this moves a limit. Off, the 10-second tick is
the only exit path, exactly as before this task. On, the tick stays as
fallback and reconciliation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.rpc_ws import PUBLIC_WS_URL

__all__ = [
    "ENV_EVENT_EXITS",
    "ENV_SOLANA_RPC_WS_URL",
    "EventExitsConfig",
    "solana_rpc_ws_url",
]

logger = get_logger(__name__)

ENV_EVENT_EXITS = "MEME_EVENT_EXITS"
ENV_SOLANA_RPC_WS_URL = "SOLANA_RPC_WS_URL"
ENV_EVENT_COMMITMENT = "MEME_EVENT_COMMITMENT"
_MODES = frozenset({"off", "on"})
_COMMITMENTS = frozenset({"confirmed", "processed"})

SYNC_S = 2.0
"""How often the watched set is resynced against ``open_positions`` (the
entries loop also wakes it on every fill)."""
QUEUE_SIZE = 1000
"""Bound between the WS reader and the evaluator: full means the frame is
dropped and counted — the tick still covers the position — never a blocked socket."""
RESTART_DELAY_S = 5.0
"""After the runtime's own ``TaskGroup`` dies for any reason it restarts
after this (mirrors T4.62's ``run_event_gate_forever``)."""
MARK_WRITE_MIN_INTERVAL_S = 1.0
"""A hot curve updates many times a second; the row's mark is written at
most this often — except a new peak, which is always persisted (a restart
must not forget the high-water the trailing stop measures from)."""


def _raw(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def solana_rpc_ws_url(env: Mapping[str, str]) -> str:
    """The radar's own rule (``hunter_meme_worker.event_gate_config``),
    duplicated rather than imported: the executor does not depend on the worker."""
    explicit = _raw(env, ENV_SOLANA_RPC_WS_URL)
    if explicit:
        return explicit
    http = _raw(env, "SOLANA_RPC_URL")
    if http.startswith("https://"):
        return "wss://" + http.removeprefix("https://")
    if http.startswith("http://"):
        return "ws://" + http.removeprefix("http://")
    return PUBLIC_WS_URL


@dataclass(frozen=True, slots=True)
class EventExitsConfig:
    enabled: bool = False
    ws_url: str = PUBLIC_WS_URL
    commitment: str = "confirmed"
    sync_s: float = SYNC_S
    queue_size: int = QUEUE_SIZE
    restart_delay_s: float = RESTART_DELAY_S
    mark_write_min_interval_s: float = MARK_WRITE_MIN_INTERVAL_S

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> EventExitsConfig:
        mode = _raw(env, ENV_EVENT_EXITS).lower()
        if mode and mode not in _MODES:
            logger.warning("meme_event_exits_config_invalid", variable=ENV_EVENT_EXITS, value=mode)
            mode = "off"
        commitment = _raw(env, ENV_EVENT_COMMITMENT).lower() or "confirmed"
        if commitment not in _COMMITMENTS:
            logger.warning(
                "meme_event_exits_config_invalid", variable=ENV_EVENT_COMMITMENT, value=commitment
            )
            commitment = "confirmed"
        return cls(enabled=mode == "on", ws_url=solana_rpc_ws_url(env), commitment=commitment)
