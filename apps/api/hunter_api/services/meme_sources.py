"""Assembles ``GET /meme/sources`` (T4.2c) from the worker's heartbeat and the
repository's newest rows — pure, no IO, tested as a table.

The heartbeat carries the flat fields of the adendo (``tracked``,
``budget_used_60s``, ``gaps_60s``, ``ws_malformed_60s``,
``last_snapshot_observed_at``, ``lag_s``, ``trenches_connected``,
``trenches_patches_60s``, ``swap_api_used_60s``) and one JSON field,
``sources``, with a block per source (``services/meme-worker/…/sources.py``).
Nothing here computes a number the worker did not report; what this module
adds is the *status word* and the database witness beside each source.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from hunter_api.schemas.meme_sources import MemeSourceOut, MemeSourcesOut
from hunter_api.services.system_status import parse_heartbeat_datetime, parse_heartbeat_int

if TYPE_CHECKING:
    from hunter_api.repositories.meme_sources import LatestRow

__all__ = ["SOURCE_NAMES", "build_meme_sources", "source_status"]

SOURCE_NAMES: tuple[str, ...] = (
    "pumpportal_ws",
    "pumpfun_rest",
    "solana_rpc",
    "trenches_ws",
    "swap_api",
    "indexer_risk",
)
SOCKET_SOURCES = frozenset({"pumpportal_ws", "trenches_ws"})


def _float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return None


def _bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _instant(value: object) -> datetime | None:
    return parse_heartbeat_datetime(value) if isinstance(value, str) else None


def _blocks(raw: str | None) -> dict[str, dict[str, Any]]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(name): cast(dict[str, Any], block)
        for name, block in cast(dict[str, Any], parsed).items()
        if isinstance(block, dict)
    }


def source_status(name: str, block: Mapping[str, Any] | None) -> tuple[str, str | None]:
    """The status word and the reason, from the worker's own block."""
    if block is None:
        return "unknown", "heartbeat_missing"
    if block.get("enabled") is False:
        return "disabled", "disabled"
    reason = block.get("reason") if isinstance(block.get("reason"), str) else None
    if name in SOCKET_SOURCES:
        connected = _bool(block.get("connected"))
        if connected is None:
            return "unknown", reason or "never_connected"
        return ("connected" if connected else "disconnected"), reason
    observed = _instant(block.get("last_observed_at"))
    errors = _int(block.get("errors_1h")) or 0
    last_error_at = _instant(block.get("last_error_at"))
    if observed is None:
        return ("erroring" if errors else "unknown"), reason or "never_observed"
    if errors and (last_error_at is None or last_error_at > observed):
        return "erroring", reason
    return "ok", reason


def _source_out(
    name: str, block: Mapping[str, Any] | None, latest: LatestRow | None
) -> MemeSourceOut:
    status, reason = source_status(name, block)
    b: Mapping[str, Any] = block or {}
    return MemeSourceOut(
        name=name,
        status=status,  # type: ignore[arg-type]
        enabled=_bool(b.get("enabled")),
        connected=_bool(b.get("connected")),
        last_observed_at=_instant(b.get("last_observed_at")),
        last_received_at=_instant(b.get("last_received_at")),
        lag_s=_float(b.get("lag_s")),
        age_s=_float(b.get("age_s")),
        used_60s=_int(b.get("used_60s")),
        budget_60s=_int(b.get("budget_60s")),
        errors_1h=_int(b.get("errors_1h")),
        last_error=b.get("last_error") if isinstance(b.get("last_error"), str) else None,
        last_error_at=_instant(b.get("last_error_at")),
        reason=reason,
        table=None if latest is None else latest.table,
        last_row_observed_at=None if latest is None else latest.observed_at,
        row_reason=(
            "no_table" if latest is None else ("no_rows" if latest.observed_at is None else None)
        ),
    )


def _radar_status(
    fields: Mapping[str, str], *, as_of: datetime, stalled_after_s: int, error: str | None
) -> tuple[str, str | None, datetime | None]:
    if error is not None:
        return "redis_unavailable", error, None
    if not fields:
        return "heartbeat_missing", "no heartbeat hash at the key", None
    sources_at = parse_heartbeat_datetime(fields.get("sources_at"))
    if sources_at is None:
        return "never", "the runtime heartbeat exists; the radar never wrote its fields", None
    age = (as_of - sources_at).total_seconds()
    if age > stalled_after_s:
        return "stale", f"radar fields are {int(age)}s old", sources_at
    return "alive", None, sources_at


def _trenches(value: str | None) -> bool | None:
    return None if value in (None, "", "disabled") else value == "true"


def build_meme_sources(
    heartbeat: Mapping[str, str] | None,
    latest: Mapping[str, LatestRow],
    *,
    as_of: datetime,
    heartbeat_key: str,
    redis_error: str | None = None,
    stalled_after_s: int = 60,
) -> MemeSourcesOut:
    fields = heartbeat or {}
    status, reason, sources_at = _radar_status(
        fields, as_of=as_of, stalled_after_s=stalled_after_s, error=redis_error
    )
    blocks = _blocks(fields.get("sources"))
    ts = parse_heartbeat_datetime(fields.get("ts"))
    names = list(SOURCE_NAMES) + [n for n in blocks if n not in SOURCE_NAMES]
    return MemeSourcesOut(
        as_of=as_of,
        heartbeat_key=heartbeat_key,
        heartbeat_ts=ts,
        heartbeat_age_s=None if ts is None else int((as_of - ts).total_seconds()),
        radar_status=status,  # type: ignore[arg-type]
        radar_reason=reason,
        sources_at=sources_at,
        stalled_after_s=stalled_after_s,
        tracked=parse_heartbeat_int(fields.get("tracked")),
        budget_used_60s=parse_heartbeat_int(fields.get("budget_used_60s")),
        budget_60s=parse_heartbeat_int(fields.get("budget_60s")),
        gaps_60s=parse_heartbeat_int(fields.get("gaps_60s")),
        ws_malformed_60s=parse_heartbeat_int(fields.get("ws_malformed_60s")),
        last_snapshot_observed_at=parse_heartbeat_datetime(fields.get("last_snapshot_observed_at")),
        lag_s=_float(fields.get("lag_s") or None),
        trenches_connected=_trenches(fields.get("trenches_connected")),
        trenches_patches_60s=parse_heartbeat_int(fields.get("trenches_patches_60s")),
        swap_api_used_60s=parse_heartbeat_int(fields.get("swap_api_used_60s")),
        swap_api_budget_60s=parse_heartbeat_int(fields.get("swap_api_budget_60s")),
        sources=[_source_out(name, blocks.get(name), latest.get(name)) for name in names],
    )
