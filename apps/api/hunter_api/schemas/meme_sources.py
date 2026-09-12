"""``GET /api/v1/orgs/{org_id}/meme/sources`` — every source of the meme radar,
as the worker reports it and as the database shows it (T4.2c).

Two witnesses per source, both named: the worker's heartbeat (``hb:meme:radar``,
the ``sources`` JSON field the worker writes every 15 s) and the newest row
each source left in its table. **Never a silent zero**: a source that is off
says ``disabled``, one that never spoke says ``never_observed``, a heartbeat that
is missing or stale says so in ``radar_status``, and a table with no rows says
``no_rows`` — each an explicit ``reason`` next to a ``null``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

__all__ = [
    "DISCOVERY_BLIND_EXPLANATION",
    "MEME_SOURCES_LABEL",
    "MemeSourceOut",
    "MemeSourcesOut",
    "RadarStatus",
    "SourceStatus",
]

MEME_SOURCES_LABEL = "Meme Radar — fontes de dados; só monitoramento, nunca execução (pump.fun)"

DISCOVERY_BLIND_EXPLANATION = (
    "programa fora do escopo do adaptador: a descoberta ouve só o programa pump "
    "(PumpPortal subscribeNewToken + boards new/graduating com pg = pump); entradas do "
    "board new em raydium_launchpad/StonkFun e afins são invisíveis por construção e não "
    "são rastreadas — a fração declara o tamanho da cegueira, não a corrige"
)
"""The declared blindness (T4.2d, item 3). Fixed text: the reason is structural."""

RadarStatus = Literal["alive", "stale", "never", "heartbeat_missing", "redis_unavailable"]
"""The worker's own heartbeat fields: ``alive`` when ``sources_at`` is fresh,
``stale`` when older than ``stalled_after_s``, ``never`` when the runtime
heartbeat exists but the radar never wrote its fields."""

SourceStatus = Literal["connected", "disconnected", "ok", "erroring", "disabled", "unknown"]
"""Per source. Socket sources are ``connected``/``disconnected``; request
sources are ``ok`` (a recent observation) or ``erroring`` (errors in the last
hour and nothing observed since); ``disabled`` by switch; ``unknown`` when the
heartbeat carries nothing about the source."""


class MemeSourceOut(BaseModel):
    name: str
    status: SourceStatus
    enabled: bool | None
    connected: bool | None
    last_observed_at: datetime | None
    last_received_at: datetime | None
    lag_s: float | None
    """``received_at − observed_at`` of the newest observation: how far behind
    the source's own clock ours is."""
    age_s: float | None
    """Seconds since the newest observation reached the worker (as of ``as_of``)."""
    used_60s: int | None
    budget_60s: int | None
    errors_1h: int | None
    last_error: str | None
    last_error_at: datetime | None
    reason: str | None
    """Why there is no observation: ``disabled`` | ``never_observed`` |
    ``heartbeat_missing`` — the worker's word, never inferred here."""
    table: str | None
    last_row_observed_at: datetime | None
    """The newest row the source left in ``table`` — the database's witness."""
    row_reason: str | None
    """``no_rows`` when the table has none, ``no_table`` when the source
    writes no table of its own."""


class MemeSourcesOut(BaseModel):
    label: str = MEME_SOURCES_LABEL
    as_of: datetime
    heartbeat_key: str
    heartbeat_ts: datetime | None
    heartbeat_age_s: int | None
    radar_status: RadarStatus
    radar_reason: str | None
    sources_at: datetime | None
    stalled_after_s: int
    tracked: int | None
    budget_used_60s: int | None
    budget_60s: int | None
    gaps_60s: int | None
    ws_malformed_60s: int | None
    last_snapshot_observed_at: datetime | None
    lag_s: float | None
    trenches_connected: bool | None
    trenches_patches_60s: int | None
    swap_api_used_60s: int | None
    swap_api_budget_60s: int | None
    discovery_blind_share_1h: float | None = None
    """Share of the ``new`` board's listings in the last hour whose program is
    not ``pump`` (``blind_share_1h`` of the heartbeat). ``None`` when the board
    listed nothing in the hour, or when the worker predates T4.2d."""
    discovery_new_board_entries_1h: int | None = None
    discovery_non_pump_entries_1h: int | None = None
    discovery_blind_explanation: str = DISCOVERY_BLIND_EXPLANATION
    sources: list[MemeSourceOut]
