"""``routers/meme.py``'s use cases — assembling repository rows and the
overview's upstream passthrough into ``schemas/meme.py`` payloads.

**Overview: real data, two possible shapes, never a fabricated number**
(brief T4.3). ``meme_tokens`` starts empty until T4.2's collector actually
runs; reading a plain aggregate off an empty table would show "0 coins
created" as if the whole pump.fun market went quiet, when the truth is this
radar has not observed anything yet. So: if this radar has tracked at least
one mint ever, the overview is computed from ``meme_tokens`` itself (real,
first-party numbers, cheap); otherwise it falls back to a labelled passthrough
of the free ``frontend-api-v3.pump.fun`` ``/mayhem/overview`` (T4.1's
``PumpFunRestClient.get_mayhem_overview``, already built and tested) — real,
third-party, market-wide numbers, clearly sourced as such.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from hunter_api.repositories.meme import (
    MemeFeatureRow,
    MemeGapRow,
    MemeRepository,
    MemeSnapshotRow,
    MemeTokenRow,
)
from hunter_api.schemas.meme import (
    GraduationsOut,
    MemeFeaturePointOut,
    MemeGapOut,
    MemeOverviewOut,
    MemeSnapshotPointOut,
    MemeTokenDetailOut,
    MemeTokenOut,
    MemeTokenState,
    OverviewByModeOut,
    OverviewWindowCountOut,
)
from hunter_core.domain.types import utcnow
from hunter_exchanges.pumpfun.rest import PumpFunRestClient

__all__ = [
    "build_gap_out",
    "build_overview",
    "build_token_detail",
    "build_token_out",
    "derive_state",
]


def derive_state(row: MemeTokenRow) -> MemeTokenState:
    """``migrated`` (``migrated_at`` set) > ``completed`` (``completed_at``
    set, not yet migrated) > ``curve`` (neither timestamp observed yet — the
    contract's nullable-timestamp way of saying "unknown", never conflated
    with "confirmed still on the curve")."""
    if row.migrated_at is not None:
        return "migrated"
    if row.completed_at is not None:
        return "completed"
    return "curve"


def build_token_out(row: MemeTokenRow, *, now: datetime) -> MemeTokenOut:
    age_minutes = (
        max(0, int((now - row.created_at).total_seconds() // 60))
        if row.created_at is not None
        else None
    )
    return MemeTokenOut(
        mint=row.mint,
        name=row.name,
        symbol=row.symbol,
        creator=row.creator,
        created_at=row.created_at,
        age_minutes=age_minutes,
        state=derive_state(row),
        mcap_sol=row.mcap_sol,
        curve_progress_pct=row.curve_progress_pct,
        mayhem_enabled=row.mayhem_enabled,
        mayhem_state=row.mayhem_state,
        migrated_at=row.migrated_at,
        snapshot_observed_at=row.snapshot_observed_at,
        snapshot_source=row.snapshot_source,  # type: ignore[arg-type]
    )


def build_snapshot_out(row: MemeSnapshotRow) -> MemeSnapshotPointOut:
    return MemeSnapshotPointOut(
        observed_at=row.observed_at,
        source=row.source,  # type: ignore[arg-type]
        virtual_sol_reserves=row.virtual_sol_reserves,
        virtual_token_reserves=row.virtual_token_reserves,
        real_sol_reserves=row.real_sol_reserves,
        real_token_reserves=row.real_token_reserves,
        complete=row.complete,
        mcap_sol=row.mcap_sol,
    )


def build_feature_out(row: MemeFeatureRow) -> MemeFeaturePointOut:
    return MemeFeaturePointOut(
        end_time=row.end_time,
        age_minutes=row.age_minutes,
        curve_progress_pct=row.curve_progress_pct,
        progress_reason=row.progress_reason,  # type: ignore[arg-type]
        mcap_sol=row.mcap_sol,
        curve_reason=row.curve_reason,  # type: ignore[arg-type]
        unique_buyers=row.unique_buyers,
        unique_buyers_reason=row.unique_buyers_reason,  # type: ignore[arg-type]
        buy_sell_ratio=row.buy_sell_ratio,
        buy_sell_ratio_reason=row.buy_sell_ratio_reason,  # type: ignore[arg-type]
        top10_share=row.top10_share,
        top10_share_reason=row.top10_share_reason,  # type: ignore[arg-type]
        creator_sold=row.creator_sold,
        creator_sold_reason=row.creator_sold_reason,  # type: ignore[arg-type]
        coverage=row.coverage,
        features_version=row.features_version,
    )


def build_token_detail(
    token: MemeTokenRow,
    snapshots: list[MemeSnapshotRow],
    features: list[MemeFeatureRow],
    *,
    now: datetime,
) -> MemeTokenDetailOut:
    return MemeTokenDetailOut(
        token=build_token_out(token, now=now),
        snapshots=[build_snapshot_out(s) for s in snapshots],
        features=[build_feature_out(f) for f in features],
    )


def build_gap_out(row: MemeGapRow) -> MemeGapOut:
    return MemeGapOut(
        id=row.id,
        stream=row.stream,  # type: ignore[arg-type]
        mint=row.mint,
        gap_start=row.gap_start,
        gap_end=row.gap_end,
        detected_at=row.detected_at,
        reason=row.reason,
        generation=row.generation,
        detail=row.detail,
    )


async def _overview_from_repository(
    repo: MemeRepository, *, tracked: int, now: datetime
) -> MemeOverviewOut:
    created_24h, created_7d = await repo.created_counts_by_window(now)
    active = await repo.mayhem_active_count()
    graduations = await repo.graduations_last_24h(now)
    return MemeOverviewOut(
        source="meme_tokens",
        observed_at=now,
        coins_created_24h=created_24h,
        coins_created_7d=created_7d,
        coins_created_by_mode=None,
        mayhem_active_coins=active,
        graduations_24h=GraduationsOut(count=graduations, tracked_tokens=tracked),
    )


def _window_count(raw: dict[str, Any], key: str) -> OverviewWindowCountOut:
    section = raw.get(key)
    values: dict[str, Any] = cast("dict[str, Any]", section) if isinstance(section, dict) else {}
    return OverviewWindowCountOut(
        last_24h=int(values.get("24h", 0) or 0),
        last_7d=int(values.get("7d", 0) or 0),
    )


async def _overview_from_passthrough(rest_client: PumpFunRestClient) -> MemeOverviewOut:
    """The free ``/mayhem/overview`` upstream payload
    (``tests/fixtures/pumpfun/mayhem_overview_raw.json``, captured live
    2026-09-12): ``coinsCreated``, ``coinsCreatedByMode.{auto,manual}``,
    ``activeCoins``, ``updatedAt`` (epoch ms). No graduation count exists
    upstream — reported honestly as ``None`` with ``insufficient_coverage``,
    tracked against zero (this radar has not tracked any mint yet, which is
    exactly why this fallback path was taken)."""
    overview = await rest_client.get_mayhem_overview()
    raw = overview.metadata
    created = raw.get("coinsCreated")
    created_map: dict[str, Any] = (
        cast("dict[str, Any]", created) if isinstance(created, dict) else {}
    )
    by_mode = raw.get("coinsCreatedByMode")
    by_mode_map: dict[str, Any] = (
        cast("dict[str, Any]", by_mode) if isinstance(by_mode, dict) else {}
    )
    updated_at_ms = raw.get("updatedAt")
    observed_at = (
        datetime.fromtimestamp(float(updated_at_ms) / 1000, tz=overview.observed_at.tzinfo)
        if isinstance(updated_at_ms, (int, float, Decimal))
        else overview.observed_at
    )
    active_raw = raw.get("activeCoins")
    return MemeOverviewOut(
        source="pumpfun_rest_mayhem_overview",
        observed_at=observed_at,
        coins_created_24h=int(created_map.get("24h", 0) or 0) if created_map else None,
        coins_created_7d=int(created_map.get("7d", 0) or 0) if created_map else None,
        coins_created_by_mode=(
            OverviewByModeOut(
                auto=_window_count(by_mode_map, "auto"), manual=_window_count(by_mode_map, "manual")
            )
            if by_mode_map
            else None
        ),
        mayhem_active_coins=int(active_raw)
        if isinstance(active_raw, (int, float, Decimal))
        else None,
        graduations_24h=GraduationsOut(
            count=None, tracked_tokens=0, reason="insufficient_coverage"
        ),
    )


async def build_overview(repo: MemeRepository, rest_client: PumpFunRestClient) -> MemeOverviewOut:
    tracked = await repo.token_coverage_count()
    if tracked > 0:
        return await _overview_from_repository(repo, tracked=tracked, now=utcnow())
    return await _overview_from_passthrough(rest_client)
