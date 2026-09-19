"""Build the ``GateRow`` the event gate judges (T4.52b-3, plan-T4.52b.md §2):
the last 15-second row of the mint (``EventGateCaches.base_rows``, T4.16's
identity/twitter/event/snapshot-shape columns), overridden by what changed
since — the in-memory series a chain event just fed
(:mod:`hunter_meme_worker.event_state`). Reuse, not reimplementation: the same
``compute_fast``, the same ``tape_for``/``tape_columns``, the same
``holders_trend``/``holders_for`` the fast lane already folds a photo with.

**Fail closed, exactly as the plan lists (§2/§4).** No base row is not this
module's problem — the caller (``event_gate.py``) counts
``event_gate_no_base_row`` and never calls this at all. Everything else keeps
the frozen vocabulary: a tape younger than a minute is ``event_feed_warming``
(``tape_columns``' own reasons), no holders reader is ``no_holders_reader``, no
snapshot (``total_supply`` or the event's own reserves unknown) leaves
``snapshot=None`` and ``evaluate_gate`` refuses ``no_snapshot_for_quote`` as it
already does for a 15-second row with none.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_indicators.meme.curve import CurveReserves
from hunter_indicators.meme.drawdown import DEFAULT_MAX_GAP_S, DEFAULT_WINDOW_S
from hunter_indicators.meme.fast import HoldersPoint, compute_fast, holders_trend
from hunter_meme_worker.features import NO_HOLDERS_READER, share_or_reason
from hunter_meme_worker.features_tape import NO_TRADE_FEED, holders_for, tape_columns
from hunter_meme_worker.lab_values import Snapshot
from hunter_meme_worker.proposals import GateRow

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hunter_meme_worker.event_state import MintEventState
    from hunter_meme_worker.features_tape import HoldersObservation

__all__ = ["SERIES_EVENT", "EventReserves", "build_event_row"]

SERIES_EVENT = "meme_event_gate_v1"
"""``reasons[0].series`` of every proposal this lane writes (``docs/DATABASE.md``)."""


@dataclass(frozen=True, slots=True)
class EventReserves:
    """The triggering notification's own reserves — a ``logsNotification``'s
    ``TradeEvent`` or an ``accountNotification``'s decoded account — kept
    separate from :class:`~hunter_meme_worker.event_state.CurvePoint` (which
    never carries virtual reserves, only what the drawdown/progress folds
    need) because a quote needs both virtual legs to price a buy."""

    virtual_sol_reserves: Decimal
    virtual_token_reserves: Decimal


def build_event_row(
    base: GateRow,
    state: MintEventState,
    *,
    as_of: datetime,
    reserves: EventReserves | None,
    holders_readings: Sequence[HoldersObservation],
) -> GateRow:
    """The 15-second base row, overridden with the mint's in-memory series at
    ``as_of``. ``base.mint`` is trusted to be ``state.mint``'s own row."""
    fast = compute_fast(
        state.fast_points(),
        as_of=as_of,
        initial_real_token_reserves=base.initial_real_token_reserves,
        mayhem_state=base.mayhem_state,
    )
    tape, tape_reason = state.tape_minute(as_of)
    tape_cols = tape_columns(tape, tape_reason or NO_TRADE_FEED)
    trend = holders_trend(
        [HoldersPoint(r.observed_at, r.received_at, r.holders) for r in holders_readings],
        as_of=as_of,
    )
    latest_holders = holders_for(list(holders_readings), end_time=as_of)
    dev_share, dev_reason = (
        share_or_reason(latest_holders.dev_share) if latest_holders is not None else (None, None)
    )
    newest = state.newest_point
    snapshot = None
    # A drained or migrated curve reports zero virtual reserves (19 evaluate_failed
    # per hour on 18/09/2026, ``virtual_sol_reserves must be positive``): that is
    # not a curve to quote — leave the snapshot ``None`` so the gate refuses
    # ``no_snapshot_for_quote`` instead of raising per notification.
    if (
        newest is not None
        and reserves is not None
        and state.total_supply is not None
        and reserves.virtual_sol_reserves > 0
        and reserves.virtual_token_reserves > 0
    ):
        snapshot = Snapshot(
            mint=state.mint,
            observed_at=as_of,
            source="solana_ws",
            reserves=CurveReserves(
                virtual_sol_reserves=reserves.virtual_sol_reserves,
                virtual_token_reserves=reserves.virtual_token_reserves,
                real_token_reserves=newest.real_token,
                initial_real_token_reserves=base.initial_real_token_reserves,
                complete=bool(state.complete),
            ),
            real_sol_reserves=newest.real_sol,
            total_supply=state.total_supply,
            complete=bool(state.complete),
            mcap_sol=fast.mcap_sol,
            mayhem_enabled=state.mayhem,
        )
    dd_pct, peak_age_s, dd_reason = state.recent_drawdown(
        as_of, window_s=DEFAULT_WINDOW_S, max_gap_s=DEFAULT_MAX_GAP_S
    )
    crowd = state.crowd_features(as_of)
    return replace(
        base,
        end_time=as_of,
        series=SERIES_EVENT,
        mcap_sol=fast.mcap_sol,
        curve_progress_pct=fast.curve_progress_pct,
        progress_reason=fast.progress_reason,
        progress_rising=fast.progress_rising,
        mcap_delta_60s=fast.mcap_delta_60s,
        snapshot=snapshot,
        completed_at=base.completed_at or (as_of if state.complete else None),
        holders=trend.holders,
        holders_prev=trend.holders_prev,
        holders_rising=trend.holders_rising,
        holders_reason=trend.holders_reason,
        dev_share=dev_share,
        dev_share_reason=dev_reason if latest_holders is not None else NO_HOLDERS_READER,
        snipers=None if latest_holders is None else latest_holders.snipers,
        # F4 (review-T4.52b.md §1): the 15-second row never carries
        # ``top10_share`` (``lab_repo_fast._FAST_ROWS`` selects no such
        # column) — the event row must fail exactly as closed, not compute
        # one from the boards the 15-second lane never reads.
        top10_share=base.top10_share,
        top10_reason=base.top10_reason,
        buys_1m=tape_cols.get("buys_1m"),
        sells_1m=tape_cols.get("sells_1m"),
        unique_buyers_1m=tape_cols.get("unique_buyers"),
        net_sol_flow_1m=tape_cols.get("net_sol_flow_1m"),
        curve_volume_1m_sol=tape_cols.get("curve_volume_1m_sol"),
        tape_reason=tape_cols.get("tape_reason"),
        # F3 (review-T4.52b.md §1): the in-memory flow can only ADD a sale,
        # never remove one already on the 15-second row. ``True`` on ``base``
        # (any source saw the creator sell) always wins; ``None`` on ``base``
        # defers entirely to the flow's own covered-from-birth rule; ``False``
        # on ``base`` is only upgraded by a sale the flow itself witnessed.
        creator_sold=(
            True
            if base.creator_sold
            else (
                tape_cols.get("creator_net_seller")
                if base.creator_sold is None
                else (True if tape_cols.get("creator_net_seller") else base.creator_sold)
            )
        ),
        recent_drawdown_pct=dd_pct,
        recent_drawdown_peak_age_s=peak_age_s,
        recent_drawdown_reason=dd_reason,
        # T4.66 (EXP-M19): the crowd behind the rise — only this lane can read
        # who bought and sold; the 15-second row leaves the four ``None``.
        early_retention_pct=crowd.early_retention_pct,
        early_age_s=crowd.early_age_s,
        new_wallets_30s=crowd.new_wallets_30s,
        quick_flip_share_30s=crowd.quick_flip_share_30s,
    )
