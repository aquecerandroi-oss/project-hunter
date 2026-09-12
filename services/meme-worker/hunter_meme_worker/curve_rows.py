"""What a curve reading teaches the rows and the tracker — pure (split out of
``collect.py`` in T4.2d, when the reading started teaching four things:
the snapshot, the two REST-side completion signals, the denominator with its
provenance, and the tracked mint).

``mcap_sol`` is never written: the database generates it, so no producer can
write a market cap that disagrees with the reserves beside it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_meme_worker.graduation import curve_signals, denominator_for, earliest_completion
from hunter_meme_worker.repo_rows import SnapshotRow, TokenRow
from hunter_meme_worker.tracker import TrackedMint

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.models import NormalizedCurveState
    from hunter_exchanges.pumpfun.quote import GlobalParams


def snapshot_row(state: NormalizedCurveState) -> SnapshotRow:
    """A normalized reading -> one row of ``meme_curve_snapshots``."""
    return SnapshotRow(
        observed_at=state.observed_at,
        mint=state.mint,
        source=state.source,
        virtual_sol_reserves=state.virtual_sol_reserves,
        virtual_token_reserves=state.virtual_token_reserves,
        real_sol_reserves=state.real_sol_reserves,
        real_token_reserves=state.real_token_reserves,
        total_supply=state.total_supply,
        complete=state.complete,
        slot=state.slot,
        commitment=state.commitment,
        mayhem_enabled=state.mayhem_enabled,
        mayhem_state=state.mayhem_state,
        mayhem_mode=state.mayhem_mode,
    )


def token_row_from_curve(
    state: NormalizedCurveState, *, params: GlobalParams | None = None
) -> TokenRow:
    """What a curve reading teaches the dimension — once each, by ``COALESCE``:
    the denominator and where it came from, the REST-side completion signals,
    and the reducer's ``completed_at`` for this photo (``graduation.py``)."""
    denominator = denominator_for(state, params)
    signals = curve_signals(state, params)
    return TokenRow(
        mint=state.mint,
        first_seen_source=state.source,
        first_seen_at=state.observed_at,
        last_seen_at=state.observed_at,
        total_supply=state.total_supply,
        initial_real_token_reserves=denominator.value,
        progress_denominator_source=denominator.source,
        mayhem_enabled=state.mayhem_enabled,
        mayhem_mode=state.mayhem_mode,
        mayhem_state=state.mayhem_state,
        rest_complete_seen_at=signals.rest_complete_seen_at,
        curve_filled_seen_at=signals.curve_filled_seen_at,
        completed_at=earliest_completion(signals),
    )


def tracked_from_curve(
    state: NormalizedCurveState, known: TrackedMint | None, params: GlobalParams | None
) -> TrackedMint:
    """The tracker's view of the same reading. ``complete`` is the REST word
    (a closed curve has static reserves and stops costing budget) — the
    classification lives in the row, not here."""
    return TrackedMint(
        mint=state.mint,
        first_seen_at=known.first_seen_at if known else state.observed_at,
        created_at=known.created_at if known else None,
        bonding_curve=known.bonding_curve if known else None,
        mayhem_state=state.mayhem_state,
        initial_real_token_reserves=denominator_for(state, params).value,
        complete=state.complete,
        mcap_sol=state.market_cap_sol,
    )


__all__ = ["snapshot_row", "token_row_from_curve", "tracked_from_curve"]
