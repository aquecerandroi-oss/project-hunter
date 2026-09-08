"""Assembling ``GET /api/v1/lab/shadow/signals`` — contract-S3-lab.md.

Every field but ``decision_at``/``cohort`` (which need the JSONB filter/sort
expression from the repository) is read straight off the immutable envelope or
``signal_outcomes.meta`` — no recomputation, the number shown is the number the
worker persisted.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_api.schemas.lab_signals import SegmentTotalsOut, SignalListItemOut, SignalsPage
from hunter_api.schemas.lab_signals import SignalsPagePositionOut as PagePositionOut
from hunter_api.services.lab_signal_identity import compute_identity_key
from hunter_core.domain.enums import ShadowTrackingState
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from hunter_api.repositories.lab_signals import SignalRow, SignalsPageResult

__all__ = ["build_signals_page"]


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _ts(value: Any) -> datetime | None:
    return None if value is None else ensure_utc(datetime.fromisoformat(value))


def _exit_reason(row: SignalRow) -> str | None:
    """T3.38a: the "why" half of ``identity_key``'s tuple. A ``no_entry``/
    ``censored`` row's specific reason distinguishes it from another row that
    also never resolved to a result; every other tracking state's reason is
    ``result`` itself (``target``/``stop``/``expired``/``invalidated``/``open``
    -- ``EXIT_REASON_LABEL`` on the web reads the very same field for the
    "Saiu" column, T3.17b)."""
    if row.tracking_state == ShadowTrackingState.NO_ENTRY:
        return row.no_entry_reason
    if row.tracking_state == ShadowTrackingState.CENSORED:
        return row.censored_reason
    return row.result.value


def _to_out(row: SignalRow, *, include_envelope: bool) -> SignalListItemOut:
    meta = row.meta
    source_bar_close = _ts(row.supporting_features.get("observation_ts")) or row.decision_at
    identity_key = compute_identity_key(
        market=row.market,
        source_bar_close=source_bar_close,
        entry_price=row.virtual_entry,
        stop=row.virtual_stop,
        exit_price=row.exit_price,
        exit_reason=_exit_reason(row),
        result=row.result,
    )
    return SignalListItemOut(
        signal_id=row.signal_id,
        strategy_version_id=row.strategy_version_id,
        market=row.market,
        cohort=row.cohort,
        decision_at=row.decision_at,
        source_bar_close=source_bar_close,
        reference_price=_dec(meta.get("reference_price")),
        stop=row.stop,
        target1=_dec(row.targets[0]) if row.targets else None,
        entry_plan=meta.get("entry_plan", {}),
        virtual_entry=row.virtual_entry,
        entry_ts=row.entry_ts,
        exit_price=row.exit_price,
        exit_ts=row.exit_ts,
        result=row.result,
        tracking_state=row.tracking_state,
        no_entry_reason=row.no_entry_reason,
        censored_reason=row.censored_reason,
        r_multiple=row.r_multiple,
        r_multiple_reason=meta.get("r_net_reason"),
        r_ex_funding=_dec(meta.get("r_ex_funding")),
        excursions=meta.get("excursions", {}),
        purpose=meta.get("purpose", "research_only"),
        supporting_features=row.supporting_features if include_envelope else None,
        identity_key=identity_key,
    )


def build_signals_page(result: SignalsPageResult, *, include_envelope: bool) -> SignalsPage:
    return SignalsPage(
        items=[_to_out(row, include_envelope=include_envelope) for row in result.items],
        next_cursor=result.next_cursor,
        totals=SegmentTotalsOut(**result.totals),
        page=PagePositionOut(**{"from": result.page_from, "to": result.page_to}),
    )
