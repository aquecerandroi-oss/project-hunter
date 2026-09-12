"""The 15-second row — ``meme_features_15s`` (``meme_features_15s_v1``, T4.16)
— as the fast lane writes it: the pure package's instantaneous features
(:mod:`hunter_indicators.meme.fast`) beside the tape of the last 60 s
(``features_tape.tape_for`` with ``end_time = as_of``) and the holders
reading the instant already had (``features_tape.holders_for``), every
value/reason pair exclusive by construction here **and** by CHECK in the
database.

**Non-anticipation is decided in the inputs**, once: the caller hands this
module points, trades and readings that carry ``received_at``, and every
function it calls refuses what reached us after ``as_of``. ``test_fast_lane.py``
proves it against the loop and ``test_lab_fast.py`` against Postgres: a photo
received one second after the instant changes nothing in the row.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from hunter_indicators.meme.fast import (
    FastPoint,
    HoldersPoint,
    compute_fast,
    holders_trend,
)
from hunter_meme_worker.features import NO_HOLDERS_READER, NO_TRADE_FEED, share_or_reason
from hunter_meme_worker.features_tape import HoldersObservation, TapeMinute, holders_for

FEATURES_15S_VERSION = "meme_features_15s_v1"
"""Frozen protocol name of the 15-second series (``hunter_core.db.models
.meme_features_15s.FEATURES_15S_VERSION_V1``, copied — a service does not
import a model to name its own series). A different window or formula is a
different version, never an edit."""


@dataclass(frozen=True, slots=True)
class FastInputs:
    """Everything the 15-second fold is allowed to look at, for one mint."""

    mint: str
    as_of: datetime
    created_at: datetime | None
    initial_real_token_reserves: Decimal | None
    points: Sequence[FastPoint]
    """The curve photos of the last minutes (``repo_fast.load_fast_points``)."""
    snapshot_source: str | None
    """The source of the newest photo (the points do not carry it)."""
    readings: Sequence[HoldersObservation] = ()
    """Board/risk readings of the mint (``ctx.boards.readings`` + ``ctx.risk.readings``)."""
    tape: TapeMinute | None = None
    """``tape_for(..., end_time=as_of)``, or ``None`` when the tape was not pulled."""
    tape_absence_reason: str = NO_TRADE_FEED


@dataclass(frozen=True, slots=True)
class Fast15sRow:
    """One row of ``meme_features_15s``, ready to insert."""

    as_of: datetime
    mint: str
    features_version: str
    snapshot_observed_at: datetime | None
    snapshot_source: str | None
    snapshots_120s: int
    age_s: int | None
    mcap_sol: Decimal | None
    mcap_delta_60s: Decimal | None
    mcap_slope_60s: Decimal | None
    window_reason: str | None
    curve_progress_pct: Decimal | None
    progress_delta_60s: Decimal | None
    progress_rising: bool | None
    progress_reason: str | None
    holders: int | None
    holders_prev: int | None
    holders_rising: bool | None
    holders_reason: str | None
    buys_60s: int | None
    sells_60s: int | None
    unique_buyers_60s: int | None
    net_sol_flow_60s: Decimal | None
    curve_volume_60s_sol: Decimal | None
    tape_reason: str | None
    creator_net_seller: bool | None
    creator_net_seller_reason: str | None
    dev_share: Decimal | None
    dev_share_reason: str | None
    snipers: int | None
    snipers_reason: str | None


def _age_s(as_of: datetime, created_at: datetime | None) -> int | None:
    if created_at is None or created_at > as_of:
        return None
    return int((as_of - created_at).total_seconds())


def build_fast_row(
    inputs: FastInputs, *, features_version: str = FEATURES_15S_VERSION
) -> Fast15sRow:
    """Fold one instant of one mint. Total: every input shape yields a legal row."""
    fast = compute_fast(
        inputs.points,
        as_of=inputs.as_of,
        initial_real_token_reserves=inputs.initial_real_token_reserves,
    )
    trend = holders_trend(
        [
            HoldersPoint(observed_at=r.observed_at, received_at=r.received_at, holders=r.holders)
            for r in inputs.readings
        ],
        as_of=inputs.as_of,
    )
    latest = holders_for(list(inputs.readings), end_time=inputs.as_of)
    dev, dev_reason = share_or_reason(latest.dev_share) if latest is not None else (None, None)
    tape = inputs.tape
    return Fast15sRow(
        as_of=inputs.as_of,
        mint=inputs.mint,
        features_version=features_version,
        snapshot_observed_at=fast.snapshot_observed_at,
        snapshot_source=inputs.snapshot_source if fast.snapshot_observed_at is not None else None,
        snapshots_120s=fast.snapshots_120s,
        age_s=_age_s(inputs.as_of, inputs.created_at),
        mcap_sol=fast.mcap_sol,
        mcap_delta_60s=fast.mcap_delta_60s,
        mcap_slope_60s=fast.mcap_slope_60s,
        window_reason=fast.window_reason,
        curve_progress_pct=fast.curve_progress_pct,
        progress_delta_60s=fast.progress_delta_60s,
        progress_rising=fast.progress_rising,
        progress_reason=fast.progress_reason,
        holders=trend.holders,
        holders_prev=trend.holders_prev,
        holders_rising=trend.holders_rising,
        holders_reason=trend.holders_reason,
        buys_60s=None if tape is None else tape.buys,
        sells_60s=None if tape is None else tape.sells,
        unique_buyers_60s=None if tape is None else tape.unique_buyers,
        net_sol_flow_60s=None if tape is None else tape.net_sol_flow,
        curve_volume_60s_sol=None if tape is None else tape.volume_sol,
        tape_reason=None if tape is not None else inputs.tape_absence_reason,
        creator_net_seller=None if tape is None else tape.creator_net_seller,
        creator_net_seller_reason=(
            None
            if tape is not None and tape.creator_net_seller is not None
            else (inputs.tape_absence_reason if tape is None else NO_TRADE_FEED)
        ),
        dev_share=dev,
        dev_share_reason=dev_reason if latest is not None else NO_HOLDERS_READER,
        snipers=None if latest is None else latest.snipers,
        snipers_reason=(
            None if latest is not None and latest.snipers is not None else NO_HOLDERS_READER
        ),
    )


__all__ = ["FEATURES_15S_VERSION", "Fast15sRow", "FastInputs", "build_fast_row"]
